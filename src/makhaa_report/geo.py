"""Address lookup against the US Census geocoder.

Nothing here touches the database. The functions take and return plain
records, so the module tests offline against a saved response.

The Census batch service is free, needs no key, and answers both questions
at once: whether an address resolves to a real US address, and where it is.
It reports the quality of each hit, which matters because a non-exact match
is a guess — "285 South Broadway, Long Isand, NY" comes back as
"285 BROADWAY, ISLAND PARK, NY", a different street in a different town.
Only exact matches are safe to adopt; callers are expected to enforce that.
"""

import csv
import io
import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

from . import config
from .normalize import recase, split_unit

log = logging.getLogger("makhaa")

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_BENCHMARK = "Public_AR_Current"
#: Service limit on one upload.
CENSUS_BATCH_LIMIT = 10_000

# A hit is 8 columns, a miss is 3. Both open with the id and the echoed
# input, so the width is what tells them apart.
_HIT_WIDTH = 8


@dataclass(frozen=True)
class Query:
    """One address to look up, with its unit already removed."""

    key: str  # the caller's identifier, echoed back by the service
    street: str
    city: str
    state: str
    postal: str | None = None

    def cache_key(self) -> str:
        return "|".join(
            (self.street.casefold(), self.city.casefold(),
             self.state.casefold(), self.postal or "")
        )


@dataclass(frozen=True)
class Match:
    """What the geocoder said about one address."""

    matched: bool
    exact: bool
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal: str | None = None
    lat: float | None = None
    lon: float | None = None


MISS = Match(matched=False, exact=False)


def _to_csv(queries: Sequence[Query]) -> str:
    """Census wants exactly five unheaded columns: id, street, city, state, zip.

    A comma inside the street would be read as a column break, so it is
    flattened to a space. This affects the query only; the stored address
    keeps whatever the locator published.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    for q in queries:
        writer.writerow([
            q.key,
            q.street.replace(",", " "),
            q.city.replace(",", " "),
            q.state,
            q.postal or "",
        ])
    return buf.getvalue()


def parse_batch(text: str) -> dict[str, Match]:
    """Turn a batch response into {key: Match}.

    Column order, confirmed against the live service:
    id, echoed input, Match|No_Match|Tie, Exact|Non_Exact,
    matched address, "lon,lat", TIGER line id, side.
    """
    out: dict[str, Match] = {}
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        key = row[0]
        if len(row) < _HIT_WIDTH or row[2] != "Match":
            out[key] = MISS
            continue
        street, city, state, postal = _split_matched(row[4])
        lon, _, lat = row[5].partition(",")
        out[key] = Match(
            matched=True,
            exact=row[3] == "Exact",
            street=street,
            city=city,
            state=state,
            postal=postal or None,
            # Census orders coordinates lon,lat — the reverse of the schema.
            lat=float(lat),
            lon=float(lon),
        )
    return out


def _split_matched(address: str) -> tuple[str, str, str, str]:
    """'6124 N CANTON CENTER RD, CANTON, MI, 48187' -> its four parts."""
    parts = [p.strip() for p in address.split(",")]
    parts += [""] * (4 - len(parts))
    return parts[0], parts[1], parts[2], parts[3]


Post = Callable[[str], str]


def _requests_post(body: str) -> str:
    import requests

    response = requests.post(
        CENSUS_URL,
        files={"addressFile": ("addresses.csv", body, "text/csv")},
        data={"benchmark": CENSUS_BENCHMARK},
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.GEOCODE_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.text


def lookup(queries: Sequence[Query], *, post: Post | None = None) -> dict[str, Match]:
    """Look up every query, in service-sized batches. No caching."""
    post = post or _requests_post
    out: dict[str, Match] = {}
    for start in range(0, len(queries), CENSUS_BATCH_LIMIT):
        chunk = queries[start:start + CENSUS_BATCH_LIMIT]
        out.update(parse_batch(post(_to_csv(chunk))))
    # A service that drops rows silently would otherwise look like a miss.
    for q in queries:
        if q.key not in out:
            log.warning("census returned no row for %s (%s)", q.key, q.street)
            out[q.key] = MISS
    return out


#: What the geocoder's answer did to a stored address.
VERDICTS = ("adopted", "unchanged", "inexact", "unmatched")


@dataclass(frozen=True)
class Resolution:
    """What one geocoder answer means for one stored row."""

    key: str
    verdict: str  # one of VERDICTS
    street: str
    city: str
    postal: str | None

    @property
    def changed(self) -> bool:
        return self.verdict == "adopted"


def resolve(key: str, match: Match | None, street: str, city: str,
            postal: str | None) -> Resolution:
    """Decide the stored address in light of what the geocoder said.

    Only an exact match is adopted. A non-exact one is a guess dressed as
    an answer — "285 South Broadway, Long Isand" comes back as a real
    address in a town twenty miles away — so those rows are reported and
    left for a human.

    The adopted street keeps our own casing wherever we already had the
    token, because Census answers in capitals and would otherwise turn
    "MacArthur" into "MACARTHUR".
    """
    unchanged = Resolution(key, "unchanged", street, city, postal)
    if match is None or not match.matched:
        return replace(unchanged, verdict="unmatched")
    if not match.exact:
        return replace(unchanged, verdict="inexact")

    line, unit = split_unit(street)
    new_line = recase(match.street or line, line)
    # The geocoder drops the unit, so put ours back on the end.
    new_street = f"{new_line} {unit}".strip()
    new_city = recase(match.city or city, city)
    new_postal = match.postal or postal

    if (new_street, new_city, new_postal) == (street, city, postal):
        return unchanged
    return Resolution(key, "adopted", new_street, new_city, new_postal)


class MatchCache:
    """Answers already paid for, kept on disk between runs.

    Keyed by the query rather than the store, so re-running costs nothing
    and a corrected address is looked up afresh.
    """

    def __init__(self, path: Path):
        self.path = path
        self._entries: dict[str, Match] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._entries = {k: Match(**v) for k, v in raw.items()}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, query: Query) -> Match | None:
        return self._entries.get(query.cache_key())

    def put(self, query: Query, match: Match) -> None:
        self._entries[query.cache_key()] = match

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {k: asdict(v) for k, v in sorted(self._entries.items())},
                indent=1,
            ),
            encoding="utf-8",
        )


def lookup_cached(
    queries: Iterable[Query],
    cache: MatchCache,
    *,
    post: Post | None = None,
) -> dict[str, Match]:
    """Look up only what the cache has not already answered."""
    queries = list(queries)
    out: dict[str, Match] = {}
    fresh: list[Query] = []
    for q in queries:
        hit = cache.get(q)
        if hit is None:
            fresh.append(q)
        else:
            out[q.key] = hit
    if fresh:
        log.info("census: %d addresses to look up, %d already cached",
                 len(fresh), len(queries) - len(fresh))
        found = lookup(fresh, post=post)
        for q in fresh:
            match = found[q.key]
            cache.put(q, match)
            out[q.key] = match
        cache.save()
    return out
