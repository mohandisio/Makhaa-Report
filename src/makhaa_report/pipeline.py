"""Scrape orchestration: scrapers → drift check → manual → overrides → write."""

import logging
import sqlite3

from . import db, export, manual, registry
from .fetch import Fetch
from .models import Location, RawLocation, RunStats, utcnow_iso
from .normalize import to_location
from .scrapers import SCRAPERS

log = logging.getLogger("makhaa")


class DriftError(Exception):
    def __init__(self, brand: str, count: int, band: tuple[int, int]):
        super().__init__(f"{brand}: scraped {count} rows, expected {band[0]}-{band[1]}")
        self.brand, self.count, self.band = brand, count, band


def run_scrape(
    conn: sqlite3.Connection,
    *,
    brands: list[str] | None = None,
    fetch: Fetch | None = None,
    allow_drift: bool = False,
) -> RunStats:
    if fetch is None:
        from .fetch import make_fetcher

        fetch = make_fetcher()

    def selected(slug: str) -> bool:
        return not brands or slug in brands

    # 1. Open run. finished_at stays NULL until the very end, so a crash
    # is visible as a NULL in the runs table.
    db.sync_registry(conn, registry.BRANDS, registry.EXCLUSIONS)
    now = utcnow_iso()
    stats = RunStats(run_id=db.start_run(conn, now))

    # 2+3. Scrape each brand; quarantine on error or band drift. A
    # quarantined brand's existing rows are left untouched — stale
    # last_seen is the signal.
    scraped: list[tuple[RawLocation, bool]] = []  # (row, is_manual)
    for brand in registry.scraped_brands():
        if not selected(brand.slug):
            continue
        try:
            rows = SCRAPERS[brand.slug](fetch)
        except KeyError:
            log.warning("%s: no scraper registered yet, skipping", brand.slug)
            continue
        except Exception:
            log.exception("%s: scrape failed — brand quarantined this run", brand.slug)
            stats.brands_failed.append(brand.slug)
            continue
        low, high = brand.band
        if not low <= len(rows) <= high and not allow_drift:
            log.error(
                "%s: DRIFT — scraped %d rows, expected %d-%d. Brand quarantined; "
                "no rows written. Re-run with --allow-drift to override.",
                brand.slug, len(rows), low, high,
            )
            stats.brands_failed.append(brand.slug)
            continue
        scraped.extend((r, False) for r in rows)
        stats.brands_succeeded.append(brand.slug)

    # 4. Manual CSVs — ground truth, no drift check.
    manual_rows = [r for r in manual.load_manual_brands() if selected(r.brand)]
    scraped.extend((r, True) for r in manual_rows)
    stats.brands_succeeded.extend(
        b.slug for b in registry.manual_brands() if selected(b.slug)
    )

    # 5. Normalize + uid; within-brand collision keeps first row, loudly.
    locations: dict[str, Location] = {}
    for raw, is_manual in scraped:
        loc = to_location(raw, now, is_manual=is_manual)
        if loc.uid in locations:
            log.warning(
                "uid collision: %s '%s' collides with '%s' — keeping first. "
                "Two stores normalizing to one address means the normalizer "
                "or the locator is wrong.",
                loc.uid, loc.name, locations[loc.uid].name,
            )
            continue
        locations[loc.uid] = loc

    # 6. Overrides — merged last so manual edits win.
    manual.apply_overrides(locations, now)

    # 7. Write phase — one transaction: snapshot then upsert per row.
    with conn:
        for loc in locations.values():
            db.insert_snapshot(conn, stats.run_id, loc.uid, now, loc.status, loc.fragment)
            db.upsert_location(conn, loc)

    # 8. Close run + mirror to CSV.
    stats.total_rows = len(locations)
    db.finish_run(conn, stats, utcnow_iso())
    export.export_all(conn)
    return stats
