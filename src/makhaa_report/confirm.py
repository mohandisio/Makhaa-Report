"""Confirm scraped addresses against the Census geocoder before the uid is hashed.

Runs ahead of normalize.to_location, so a corrected address is what gets
hashed into the uid in the first place — no re-keying, no orphaned history.
Composes geo.py and geocode.py's own pieces (lookup_cached, resolve, the
bounds/tolerance check) rather than re-deriving any of them.
"""

import csv
import logging
import time
from collections.abc import Collection
from dataclasses import replace
from pathlib import Path
from typing import Callable

from . import config, geo
from .models import RawLocation
from .normalize import make_uid, normalize_postal, normalize_state, split_unit

log = logging.getLogger("makhaa")


class AddressConfirmer:
    """Confirm scraped addresses against the Census geocoder before the uid is hashed."""

    def __init__(
        self,
        geo_dir: Path,
        *,
        post: geo.Post | None = None,
        get: geo.Get | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._cache = geo.MatchCache(geo_dir / "census.json")
        self._osm_cache = geo.MatchCache(geo_dir / "nominatim.json")
        self._post = post
        self._get = get
        self._sleep = sleep

    def confirm(self, rows: list[RawLocation], *, leave: Collection[str] = ()) -> list[RawLocation]:
        published = [
            make_uid(row.brand, row.street, row.city, row.state) for row in rows
        ]
        queries: dict[str, geo.Query] = {}
        for i, row in enumerate(rows):
            if published[i] in leave:
                continue
            street_line = split_unit(" ".join(row.street.split()))[0]
            queries[str(i)] = geo.Query(
                key=str(i),
                street=street_line,
                city=row.city.strip(),
                state=normalize_state(row.state),
                postal=normalize_postal(row.postal),
            )

        matches: dict[str, geo.Match] = {}
        if queries:
            try:
                matches = geo.lookup_cached(
                    list(queries.values()), self._cache, post=self._post
                )
            except (OSError, ValueError, csv.Error) as exc:
                log.warning(
                    "census: lookup failed for %d addresses — %s", len(queries), exc
                )
                matches = {}
                for key, q in queries.items():
                    hit = self._cache.get(q)
                    if hit is not None:
                        matches[key] = hit

        counts = {"confirmed": 0, "adopted": 0, "unconfirmed": 0, "unanswered": 0}
        osm_pending: list[int] = []
        out: list[RawLocation] = []
        for i, row in enumerate(rows):
            key = str(i)
            if published[i] in leave:
                out.append(row)
                continue

            match = matches.get(key)
            if match is None:
                counts["unanswered"] += 1
                out.append(replace(row, geocode_flagged=True))
                continue

            street_full = " ".join(row.street.split())
            postal = normalize_postal(row.postal)
            resolution = geo.resolve(key, match, street_full, row.city.strip(), postal)
            confirmed = resolution.verdict in ("adopted", "unchanged")
            if confirmed:
                counts["confirmed"] += 1
            else:
                counts["unconfirmed"] += 1
                osm_pending.append(i)

            new_row = row
            if resolution.verdict == "adopted":
                counts["adopted"] += 1
                new_published = make_uid(
                    row.brand, resolution.street, resolution.city, row.state
                )
                new_row = replace(
                    new_row,
                    street=resolution.street,
                    city=resolution.city,
                    postal=resolution.postal,
                    published_uid=(
                        published[i] if new_published != published[i] else None
                    ),
                )

            lat, lon, source = new_row.lat, new_row.lon, new_row.geocode_source
            if confirmed and match.lat is not None:
                if lat is None:
                    lat, lon, source = match.lat, match.lon, "census"
                elif (
                    not geo.in_us(lat, lon)
                    or geo.distance_km(lat, lon, match.lat, match.lon)
                    > geo.COORDINATE_TOLERANCE_KM
                ):
                    log.info(
                        "%s: %s is %.1f km from the Census match — replaced",
                        row.brand, new_row.street,
                        geo.distance_km(lat, lon, match.lat, match.lon),
                    )
                    lat, lon, source = match.lat, match.lon, "census"

            flagged = (not confirmed) or lat is None or not geo.in_us(lat, lon)
            out.append(replace(
                new_row, lat=lat, lon=lon, geocode_source=source,
                geocode_flagged=flagged,
            ))

        osm_asked = 0
        osm_confirmed = 0
        stopped = False
        for i in osm_pending:
            if stopped:
                break
            query = queries[str(i)]
            osm_asked += 1
            match = self._osm_cache.get(query)
            if match is None:
                try:
                    match = geo.nominatim_search(query, get=self._get)
                except geo.NOMINATIM_ERRORS as exc:
                    log.warning(
                        "nominatim: %s (%s) — %s", query.street, query.city, exc
                    )
                    stopped = True
                    continue
                self._osm_cache.put(query, match)
                self._osm_cache.save()
                self._sleep(config.RATE_DELAY_S)

            if match.matched:
                osm_confirmed += 1
                row = out[i]
                lat, lon, source = row.lat, row.lon, row.geocode_source
                if lat is None and match.lat is not None:
                    lat, lon, source = match.lat, match.lon, "nominatim"
                out[i] = replace(
                    row, lat=lat, lon=lon, geocode_source=source,
                    geocode_flagged=False,
                )

        log.info(
            "census: %d confirmed (%d adopted), %d unconfirmed, %d unanswered; "
            "osm: %d asked, %d confirmed",
            counts["confirmed"], counts["adopted"],
            counts["unconfirmed"], counts["unanswered"],
            osm_asked, osm_confirmed,
        )
        return out
