"""Resolve stored addresses against the Census geocoder and adopt the good ones.

Reads every location, asks Census about it, and rewrites the address where
Census returned an exact match. Non-exact and unmatched rows are left
untouched and reported, because a non-exact match is a guess and a wrong
address is worse than an ugly one.
"""

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

from . import config, db, geo, manual
from .normalize import make_uid, split_unit

log = logging.getLogger("makhaa")


class NullProgress:
    """Default reporter: the resolution runs the same with nobody watching."""

    def start(self, slugs: list[str]) -> None: ...
    def lookup_started(self, fresh: int, cached: int) -> None: ...
    def lookup_finished(self) -> None: ...
    def record(self, slug: str, verdict: str) -> None: ...
    def finish_brand(self, slug: str) -> None: ...
    def coords(self, slug: str) -> None: ...
    def fallback_started(self, total: int) -> None: ...
    def fallback_step(self, address: str) -> None: ...
    def fallback_finished(self) -> None: ...


@dataclass
class Change:
    """One row's before and after, for review."""

    slug: str
    verdict: str
    old_street: str
    old_city: str
    new_street: str
    new_city: str
    old_postal: str | None = None
    new_postal: str | None = None
    state: str = ""
    #: Already corrected by hand, so not waiting on anybody.
    by_hand: bool = False

    def before(self) -> str:
        zip_ = f" {self.old_postal}" if self.old_postal else ""
        return f"{self.old_street}, {self.old_city}, {self.state}{zip_}"

    def after(self) -> str:
        zip_ = f" {self.new_postal}" if self.new_postal else ""
        return f"{self.new_street}, {self.new_city}, {self.state}{zip_}"

    @property
    def cosmetic(self) -> bool:
        """True when only letter case and punctuation moved."""
        return _squash(self.old_street) == _squash(self.new_street) and _squash(
            self.old_city
        ) == _squash(self.new_city)


@dataclass
class GeocodeStats:
    counts: dict[str, int] = field(default_factory=dict)
    changes: list[Change] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    #: How many coordinates each source supplied this run.
    filled: dict[str, int] = field(default_factory=dict)
    #: Rows left without coordinates, or carrying ones outside the US.
    flagged: list[str] = field(default_factory=list)
    still_dark: int = 0
    #: Which source could confirm each address exists.
    verified: dict[str, int] = field(default_factory=dict)
    #: Addresses no source recognised, as "street, city, ST".
    unverified: list[str] = field(default_factory=list)
    #: Adoptions written to overrides.csv so a re-scrape cannot undo them.
    recorded: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def substantive(self) -> list[Change]:
        return [c for c in self.changes if c.verdict == "adopted" and not c.cosmetic]

    @property
    def cosmetic(self) -> int:
        return sum(1 for c in self.changes if c.verdict == "adopted" and c.cosmetic)

    @property
    def unresolved(self) -> list[Change]:
        """Rows still waiting on a human — not ones a human already fixed."""
        return [c for c in self.changes
                if c.verdict in ("inexact", "unmatched") and not c.by_hand]


def _squash(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _record(stats: "GeocodeStats", row, resolution) -> None:
    """Keep a correction that moved a row, so a re-scrape cannot undo it.

    The scraper still publishes the old address. Without a recorded
    override the next run files it as a second store; with one, the
    override layer rewrites it before it is ever written. A correction
    that leaves the uid alone needs no record — the next geocode simply
    makes it again.
    """
    if manual.append_override(
        row["uid"],
        {"street": resolution.street, "city": resolution.city,
         "postal": resolution.postal or ""},
        note=f"census: {row['street']}, {row['city']} -> "
             f"{resolution.street}, {resolution.city}",
    ):
        stats.recorded.append(row["uid"])


def run_geocode(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    post: geo.Post | None = None,
    get: geo.Get | None = None,
    sleep: Callable[[float], None] = time.sleep,
    progress: NullProgress | None = None,
) -> GeocodeStats:
    progress = progress or NullProgress()
    stats = GeocodeStats()

    rows = conn.execute(
        "SELECT uid, brand, street, city, state, postal, is_manual FROM locations "
        "ORDER BY brand, state, city, street"
    ).fetchall()
    progress.start(sorted({r["brand"] for r in rows}))

    queries = [
        geo.Query(r["uid"], split_unit(r["street"])[0], r["city"], r["state"], r["postal"])
        for r in rows
    ]
    cache = geo.MatchCache(config.GEO_DIR / "census.json")
    fresh = sum(1 for q in queries if cache.get(q) is None)
    progress.lookup_started(fresh, len(queries) - fresh)
    matches = geo.lookup_cached(queries, cache, post=post)
    progress.lookup_finished()

    # A corrected address hashes to a new uid, so a row can land on one
    # another row already holds. That is a genuine duplicate rather than a
    # failure, and is reported instead of being written over.
    taken = {r["uid"] for r in rows}
    # Census answers arrive keyed by the uid a row had *before* it was
    # corrected. Collecting the coordinates here, while both uids are in
    # hand, is what stops a corrected row losing them.
    points: dict[str, tuple[float, float]] = {}
    # Addresses Census could not confirm. OpenStreetMap gets a second
    # look at these, whether or not they already have coordinates —
    # the question there is whether the address exists at all.
    unresolved: set[str] = set()

    for row in rows:
        match = matches.get(row["uid"])
        resolution = geo.resolve(
            row["uid"], match, row["street"], row["city"], row["postal"],
        )
        stats.counts[resolution.verdict] = stats.counts.get(resolution.verdict, 0) + 1
        progress.record(row["brand"], resolution.verdict)

        if resolution.verdict in ("adopted", "inexact", "unmatched"):
            stats.changes.append(Change(
                slug=row["brand"], verdict=resolution.verdict,
                old_street=row["street"], old_city=row["city"],
                new_street=resolution.street, new_city=resolution.city,
                old_postal=row["postal"], new_postal=resolution.postal,
                state=row["state"], by_hand=bool(row["is_manual"]),
            ))
        def keep_point(uid: str, match=match, verdict=resolution.verdict,
                       row=row) -> None:
            confirmed = verdict not in ("inexact", "unmatched")
            # Coordinates only from a match whose street is ours. A
            # non-exact hit resolves to a different address — "1326 Lake
            # St" comes back as "1326 W LAKE ST" — and plotting the store
            # there would be a wrong answer dressed as a right one.
            if confirmed and match is not None and match.lat is not None:
                points[uid] = (match.lat, match.lon)
            if confirmed:
                stats.verified["census"] = stats.verified.get("census", 0) + 1
            elif row["is_manual"]:
                # Somebody checked this one by hand; that outranks a
                # gazetteer that has never heard of the street.
                stats.verified["hand"] = stats.verified.get("hand", 0) + 1
            else:
                unresolved.add(uid)

        if not resolution.changed:
            keep_point(row["uid"])
            continue

        new_uid = make_uid(row["brand"], resolution.street, resolution.city, row["state"])
        if new_uid != row["uid"] and new_uid in taken:
            # One brand, one canonical address, so one store — either the
            # locator lists it twice, or a scrape re-published the address
            # a previous run already corrected. Folding the two is right
            # in both readings; leaving them apart doubles the store.
            log.info(
                "%s: '%s, %s' resolves to '%s, %s', which another row already "
                "holds — folded into it.",
                row["brand"], row["street"], row["city"],
                resolution.street, resolution.city,
            )
            stats.collisions.append(row["uid"])
            if not dry_run:
                db.merge_into(conn, row["uid"], new_uid)
                taken.discard(row["uid"])
                _record(stats, row, resolution)
            keep_point(new_uid if not dry_run else row["uid"])
            continue
        if dry_run:
            keep_point(row["uid"])
        else:
            db.rekey_location(conn, row["uid"], new_uid,
                              resolution.street, resolution.city, resolution.postal)
            if new_uid != row["uid"]:
                _record(stats, row, resolution)
            taken.discard(row["uid"])
            taken.add(new_uid)
            keep_point(new_uid)

    if not dry_run:
        conn.commit()

    _fill_coordinates(conn, points, unresolved, stats, dry_run=dry_run,
                      progress=progress, get=get, sleep=sleep)

    for slug in sorted({r["brand"] for r in rows}):
        progress.finish_brand(slug)
    return stats


def _fill_coordinates(
    conn: sqlite3.Connection,
    points: dict[str, tuple[float, float]],
    unresolved: set[str],
    stats: GeocodeStats,
    *,
    dry_run: bool,
    progress: NullProgress,
    get: geo.Get | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Place the rows that have no coordinates, and confirm the doubtful ones.

    A row already carrying coordinates keeps them — a locator that
    publishes its own sits closer to the store than a gazetteer does —
    but every coordinate is checked for being in the country, because one
    locator published a New Jersey store's position in Lebanon.

    OpenStreetMap sees two kinds of row: those with no coordinates, and
    those whose address Census could not confirm. The second kind may
    already be plotted; the open question is whether the address is real.
    """
    rows = conn.execute(
        "SELECT uid, brand, street, city, state, postal, lat, lon, geocode_flagged "
        "FROM locations ORDER BY brand, state, city, street"
    ).fetchall()

    ask_osm: list = []
    for row in rows:
        if row["lat"] is None and row["uid"] in points:
            _write_point(conn, row, *points[row["uid"]], "census", stats,
                         dry_run=dry_run, progress=progress)
        elif row["lat"] is None or row["uid"] in unresolved:
            ask_osm.append(row)
        if row["lat"] is not None:
            _check_bounds(conn, row, stats, dry_run=dry_run)

    if ask_osm:
        _ask_nominatim(conn, ask_osm, unresolved, stats, dry_run=dry_run,
                       progress=progress, get=get, sleep=sleep)


def _query_for(row) -> geo.Query:
    return geo.Query(row["uid"], split_unit(row["street"])[0],
                     row["city"], row["state"], row["postal"])


def _write_point(conn, row, lat: float, lon: float, source: str,
                 stats: GeocodeStats, *, dry_run: bool,
                 progress: NullProgress) -> None:
    stats.filled[source] = stats.filled.get(source, 0) + 1
    progress.coords(row["brand"])
    if not dry_run:
        db.set_coordinates(conn, row["uid"], lat, lon, source)
    _flag(conn, row, stats, not geo.in_us(lat, lon), dry_run=dry_run)


def _check_bounds(conn, row, stats: GeocodeStats, *, dry_run: bool) -> None:
    ok = geo.in_us(row["lat"], row["lon"])
    if not ok:
        log.warning(
            "%s: '%s, %s, %s' sits at %.4f,%.4f — outside the US. Coordinates "
            "kept but flagged; the locator published them.",
            row["brand"], row["street"], row["city"], row["state"],
            row["lat"], row["lon"],
        )
    _flag(conn, row, stats, not ok, dry_run=dry_run)


def _flag(conn, row, stats: GeocodeStats, flagged: bool, *, dry_run: bool) -> None:
    """Write the flag every run, so a row that gets fixed stops being flagged."""
    if flagged and row["uid"] not in stats.flagged:
        # A row can fail two checks at once; it is still one row to review.
        stats.flagged.append(row["uid"])
    if not dry_run:
        # Written unconditionally: the row was read before the earlier
        # checks ran, so comparing against it would miss a flag that a
        # later check needs to set.
        db.set_flagged(conn, row["uid"], flagged)


def _ask_nominatim(conn, rows, unresolved: set[str], stats: GeocodeStats, *,
                   dry_run: bool, progress: NullProgress, get: geo.Get | None,
                   sleep: Callable[[float], None]) -> None:
    """Place and confirm what the Census gazetteer could not, one at a time.

    OpenStreetMap's usage policy caps this at one request a second and
    forbids bulk querying, so the cache is what keeps a weekly run down to
    the handful of addresses that are genuinely new.

    A hit here is weaker evidence than a Census exact match — OSM answers
    from contributed data and may land on a street rather than a building
    — so it confirms that the address exists and supplies coordinates,
    but never rewrites the stored address.
    """
    cache = geo.MatchCache(config.GEO_DIR / "nominatim.json")
    progress.fallback_started(len(rows))
    for row in rows:
        query = _query_for(row)
        match = cache.get(query)
        progress.fallback_step(f"{row['street']}, {row['city']}")
        if match is None:
            match = geo.nominatim_lookup(query, get=get)
            cache.put(query, match)
            cache.save()
            # One request a second, as OpenStreetMap asks. Only after a
            # real lookup — a cache hit costs them nothing.
            sleep(config.RATE_DELAY_S)

        if match.matched and row["uid"] in unresolved:
            stats.verified["openstreetmap"] = stats.verified.get("openstreetmap", 0) + 1

        if match.matched and match.lat is not None and row["lat"] is None:
            _write_point(conn, row, match.lat, match.lon, "nominatim", stats,
                         dry_run=dry_run, progress=progress)
            continue
        if match.matched:
            continue  # already plotted; OSM was only asked to confirm it

        if row["lat"] is None:
            stats.still_dark += 1
        if row["uid"] in unresolved:
            stats.unverified.append(
                f"{row['street']}, {row['city']}, {row['state']}"
            )
        _flag(conn, row, stats, True, dry_run=dry_run)
    progress.fallback_finished()
    if not dry_run:
        conn.commit()
