"""Scrape orchestration: scrapers → manual → overrides → write."""

import logging
import sqlite3
from collections import Counter
from dataclasses import replace
from typing import Protocol

from . import db, export, manual, registry
from .fetch import Fetch
from .models import BrandResult, Location, RawLocation, RunStats, utcnow_iso
from .normalize import make_uid, to_location
from .scrapers import SCRAPERS

log = logging.getLogger("makhaa")


class AddressConfirmer(Protocol):
    """Public shape pipeline.py relies on; the real one lives in confirm.py."""

    def confirm(
        self, rows: list[RawLocation], *, leave: "set[str]" = ...
    ) -> list[RawLocation]: ...


class NullProgress:
    """Default reporter: the pipeline runs the same with nobody watching."""

    def start(self, run_id: int, slugs: list[str]) -> None: ...
    def start_brand(self, slug: str) -> None: ...
    def note_request(self, slug: str) -> None: ...
    def finish_brand(self, result: BrandResult) -> None: ...


def run_scrape(
    conn: sqlite3.Connection,
    *,
    brands: list[str] | None = None,
    fetch: Fetch | None = None,
    progress: NullProgress | None = None,
    confirmer: AddressConfirmer | None = None,
) -> RunStats:
    if fetch is None:
        from .fetch import make_fetcher

        fetch = make_fetcher()
    progress = progress or NullProgress()

    def selected(slug: str) -> bool:
        return not brands or slug in brands

    def watched(slug: str) -> Fetch:
        """Report each request so a slow multi-page brand shows movement."""

        def wrapped(url: str) -> str:
            progress.note_request(slug)
            return fetch(url)

        return wrapped

    # 1. Open run. finished_at stays NULL until the very end, so a crash
    # is visible as a NULL in the runs table.
    db.sync_registry(conn, registry.BRANDS, registry.EXCLUSIONS)
    now = utcnow_iso()
    # Biggest brands first, manual entries last, so the run reads in
    # order of how much each contributes.
    ordered = [
        b for b in (*registry.scraped_brands(db.location_counts(conn)),
                    *registry.manual_brands())
        if selected(b.slug)
    ]
    stats = RunStats(run_id=db.start_run(conn, now))
    progress.start(stats.run_id, [b.slug for b in ordered])

    # 2. Scrape each brand. A scraper that raises is skipped for the run;
    # its existing rows are left untouched, so stale last_seen is the signal.
    scraped: list[tuple[RawLocation, bool]] = []  # (row, is_manual)
    for brand in ordered:
        if brand.method != "scrape":
            continue
        if brand.slug not in SCRAPERS:
            result = BrandResult(brand.slug, "no_scraper")
            stats.results.append(result)
            progress.finish_brand(result)
            continue
        progress.start_brand(brand.slug)
        try:
            rows = SCRAPERS[brand.slug](watched(brand.slug))
        except Exception as exc:
            log.exception("%s: scrape failed — skipped this run, rows left as they were",
                          brand.slug)
            result = BrandResult(brand.slug, "error", note=str(exc))
            stats.results.append(result)
            progress.finish_brand(result)
            continue
        scraped.extend((r, False) for r in rows)
        result = BrandResult(brand.slug, "ok", len(rows))
        stats.results.append(result)
        progress.finish_brand(result)

    # 3. Manual entries — the source of truth for the rows they cover.
    manual_rows = [r for r in manual.load_manual_brands() if selected(r.brand)]
    for brand in ordered:
        if brand.method == "manual":
            count = sum(1 for r in manual_rows if r.brand == brand.slug)
            result = BrandResult(brand.slug, "ok", count, "manual entry")
            stats.results.append(result)
            progress.finish_brand(result)

    # 4. Confirm addresses, before uids are hashed from them. Rows an
    # override names are left with their published spelling, so the
    # override — matched by uid — keeps matching after this run.
    if confirmer is not None:
        leave = {ov.uid for ov in manual.load_overrides() if ov.uid}
        confirmed = confirmer.confirm([r for r, _ in scraped], leave=leave)
        scraped = [(r, False) for r in confirmed]

    # 5. Normalize + uid. Two scraped rows sharing a uid means the
    # normalizer or the locator is wrong, so the first wins and says so.
    locations: dict[str, Location] = {}
    for raw, _ in scraped:
        loc = to_location(raw, now)
        if loc.uid in locations:
            log.warning(
                "uid collision: %s '%s, %s' collides with '%s, %s' — keeping "
                "first. Two stores normalizing to one address means the "
                "normalizer or the locator is wrong.",
                loc.uid, loc.street, loc.city,
                locations[loc.uid].street, locations[loc.uid].city,
            )
            continue
        locations[loc.uid] = loc

    # 6. Manual entries land on top as corrections: what they state wins,
    # what they leave blank keeps whatever the scraper found.
    manual.apply_manual_entries(locations, manual_rows, now)

    # 7. Overrides last, so a hand correction beats everything.
    manual.apply_overrides(locations, now)

    # Report each brand's real total, which for a scraped brand includes
    # any manual entries filling gaps its locator leaves.
    totals = Counter(loc.brand for loc in locations.values())
    stats.results = [
        replace(result, rows=totals.get(result.slug, 0))
        if result.outcome == "ok" else result
        for result in stats.results
    ]
    for result in stats.results:
        progress.finish_brand(result)

    # 8. Write phase — one transaction: snapshot then upsert per row.
    # A row can be stored under a uid its current address no longer hashes
    # to two ways: a hand correction (override or manual entry) rewrites
    # street or city, which upsert_location will not do since those feed
    # the uid; or the confirmer corrects the address on a later run after
    # an earlier one — a Census outage, say — left it alone and stored it
    # under the uid its published spelling hashed to (published_uid carries
    # that old uid forward). Either way source_uid is where the row may
    # already live and target_uid is where it belongs now; rekey_location
    # moves it there (row and snapshots), or merge_into folds it onto a
    # copy already filed under target_uid from an earlier run.
    with conn:
        taken = {r[0] for r in conn.execute("SELECT uid FROM locations")}
        for loc in locations.values():
            db.insert_snapshot(conn, stats.run_id, loc.uid, now, loc.status, loc.fragment)
            source_uid = loc.published_uid or loc.uid
            target_uid = (
                make_uid(loc.brand, loc.street, loc.city, loc.state)
                if loc.is_manual else loc.uid
            )
            if target_uid != source_uid:
                if target_uid in taken:
                    # Applied before: the destination already holds this
                    # store, because a previous run moved it there. Same
                    # brand and same address is the same store, so adopt
                    # that uid — inserting the old one instead would
                    # collide on UNIQUE (brand, street, city, state).
                    db.merge_into(conn, source_uid, target_uid)
                else:
                    db.rekey_location(conn, source_uid, target_uid,
                                      loc.street, loc.city, loc.postal)
                taken.discard(source_uid)
                taken.add(target_uid)
                loc.uid = target_uid
            db.upsert_location(conn, loc)
            if confirmer is not None and not loc.is_manual:
                # _UPSERT deliberately never touches geocode_flagged, so the
                # confirmer's verdict has to be written explicitly.
                db.set_flagged(conn, loc.uid, loc.geocode_flagged)
            taken.add(loc.uid)

    # 9. Close run + mirror to CSV.
    stats.total_rows = len(locations)
    db.finish_run(conn, stats, utcnow_iso())
    export.export_all(conn)
    return stats
