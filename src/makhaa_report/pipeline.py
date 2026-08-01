"""Scrape orchestration: scrapers → drift check → manual → overrides → write."""

import logging
import sqlite3

from . import db, export, manual, registry
from .fetch import Fetch
from .models import BrandResult, Location, RawLocation, RunStats, utcnow_iso
from .normalize import to_location
from .scrapers import SCRAPERS

log = logging.getLogger("makhaa")


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
    allow_drift: bool = False,
    progress: NullProgress | None = None,
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
    stats = RunStats(run_id=db.start_run(conn, now))
    progress.start(
        stats.run_id, [b.slug for b in registry.BRANDS if selected(b.slug)]
    )

    # 2+3. Scrape each brand; quarantine on error or band drift. A
    # quarantined brand's existing rows are left untouched — stale
    # last_seen is the signal.
    scraped: list[tuple[RawLocation, bool]] = []  # (row, is_manual)
    for brand in registry.scraped_brands():
        if not selected(brand.slug):
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
            log.exception("%s: scrape failed — brand quarantined this run", brand.slug)
            result = BrandResult(brand.slug, "error", note=str(exc))
            stats.results.append(result)
            progress.finish_brand(result)
            continue
        low, high = brand.band
        if not low <= len(rows) <= high and not allow_drift:
            log.error(
                "%s: DRIFT — scraped %d rows, expected %d-%d. Brand quarantined; "
                "no rows written. Re-run with --allow-drift to override.",
                brand.slug, len(rows), low, high,
            )
            result = BrandResult(brand.slug, "drift", len(rows), "quarantined, no rows written")
            stats.results.append(result)
            progress.finish_brand(result)
            continue
        scraped.extend((r, False) for r in rows)
        result = BrandResult(brand.slug, "ok", len(rows))
        stats.results.append(result)
        progress.finish_brand(result)

    # 4. Manual entries — no drift check; these are the source of truth
    # for the rows they cover.
    manual_rows = [r for r in manual.load_manual_brands() if selected(r.brand)]
    for brand in registry.manual_brands():
        if selected(brand.slug):
            count = sum(1 for r in manual_rows if r.brand == brand.slug)
            result = BrandResult(brand.slug, "ok", count, "manual entry")
            stats.results.append(result)
            progress.finish_brand(result)

    # 5. Normalize + uid. Two scraped rows sharing a uid means the
    # normalizer or the locator is wrong, so the first wins and says so.
    locations: dict[str, Location] = {}
    for raw, _ in scraped:
        loc = to_location(raw, now)
        if loc.uid in locations:
            log.warning(
                "uid collision: %s '%s' collides with '%s' — keeping first. "
                "Two stores normalizing to one address means the normalizer "
                "or the locator is wrong.",
                loc.uid, loc.name, locations[loc.uid].name,
            )
            continue
        locations[loc.uid] = loc

    # 6. Manual entries land on top as corrections: what they state wins,
    # what they leave blank keeps whatever the scraper found.
    manual.apply_manual_entries(locations, manual_rows, now)

    # 7. Overrides last, so a hand correction beats everything.
    manual.apply_overrides(locations, now)

    # 8. Write phase — one transaction: snapshot then upsert per row.
    with conn:
        for loc in locations.values():
            db.insert_snapshot(conn, stats.run_id, loc.uid, now, loc.status, loc.fragment)
            db.upsert_location(conn, loc)

    # 9. Close run + mirror to CSV.
    stats.total_rows = len(locations)
    db.finish_run(conn, stats, utcnow_iso())
    export.export_all(conn)
    return stats
