"""Resolve stored addresses against the Census geocoder and adopt the good ones.

Reads every location, asks Census about it, and rewrites the address where
Census returned an exact match. Non-exact and unmatched rows are left
untouched and reported, because a non-exact match is a guess and a wrong
address is worse than an ugly one.
"""

import logging
import sqlite3
from dataclasses import dataclass, field

from . import config, db, geo
from .normalize import make_uid, split_unit

log = logging.getLogger("makhaa")


class NullProgress:
    """Default reporter: the resolution runs the same with nobody watching."""

    def start(self, slugs: list[str]) -> None: ...
    def lookup_started(self, fresh: int, cached: int) -> None: ...
    def lookup_finished(self) -> None: ...
    def record(self, slug: str, verdict: str) -> None: ...
    def finish_brand(self, slug: str) -> None: ...


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
        return [c for c in self.changes if c.verdict in ("inexact", "unmatched")]


def _squash(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def run_geocode(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    post: geo.Post | None = None,
    progress: NullProgress | None = None,
) -> GeocodeStats:
    progress = progress or NullProgress()
    stats = GeocodeStats()

    rows = conn.execute(
        "SELECT uid, brand, street, city, state, postal FROM locations "
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

    for row in rows:
        resolution = geo.resolve(
            row["uid"], matches.get(row["uid"]),
            row["street"], row["city"], row["postal"],
        )
        stats.counts[resolution.verdict] = stats.counts.get(resolution.verdict, 0) + 1
        progress.record(row["brand"], resolution.verdict)

        if resolution.verdict in ("adopted", "inexact", "unmatched"):
            stats.changes.append(Change(
                slug=row["brand"], verdict=resolution.verdict,
                old_street=row["street"], old_city=row["city"],
                new_street=resolution.street, new_city=resolution.city,
                old_postal=row["postal"], new_postal=resolution.postal,
            ))
        if not resolution.changed:
            continue

        new_uid = make_uid(row["brand"], resolution.street, resolution.city, row["state"])
        if new_uid != row["uid"] and new_uid in taken:
            log.warning(
                "%s: '%s, %s' now matches '%s, %s' — same store twice in the "
                "locator. Left as-is for a human to drop.",
                row["brand"], row["street"], row["city"],
                resolution.street, resolution.city,
            )
            stats.collisions.append(row["uid"])
            continue
        if not dry_run:
            db.rekey_location(conn, row["uid"], new_uid,
                              resolution.street, resolution.city, resolution.postal)
            taken.discard(row["uid"])
            taken.add(new_uid)

    for slug in sorted({r["brand"] for r in rows}):
        progress.finish_brand(slug)

    if not dry_run:
        conn.commit()
    return stats
