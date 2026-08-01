"""Brands whose locator is backed by a JSON endpoint."""

import json
import logging

from ..fetch import Fetch
from ..models import RawLocation
from ..normalize import split_us_address

log = logging.getLogger("makhaa")

# Qamaria's /cafes page embeds a Storepoint map widget; the widget's own
# API returns the full location list. The map id comes from the embed's
# data-map-id attribute and changes only if they rebuild the map.
QAMARIA_URL = "https://api.storepoint.co/v1/165c3af3b9c727/locations"

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _hours(record: dict) -> str | None:
    """Weekday opening hours, joined verbatim and unparsed."""
    parts = [f"{day}: {record[day]}" for day in _WEEKDAYS if record.get(day)]
    return "; ".join(parts) or None


def scrape_qamaria(fetch: Fetch) -> list[RawLocation]:
    """Qamaria Yemeni Coffee.

    Two kinds of entry are dropped: rows tagged `catering`, which are
    service-area listings that repeat an existing cafe's address and would
    double-count, and non-US rows (Canada, Saudi Arabia, Qatar).

    The feed carries no open/coming-soon flag, so every row is recorded as
    open — Qamaria's announced pipeline is not visible here.
    """
    payload = json.loads(fetch(QAMARIA_URL))
    rows: list[RawLocation] = []

    for record in payload["results"]["locations"]:
        if "catering" in (record.get("tags") or ""):
            continue
        address = split_us_address(record.get("streetaddress") or "")
        if address is None:
            continue  # non-US store
        street, city, state, postal = address
        rows.append(
            RawLocation(
                brand="qamaria",
                name=(record.get("name") or "").strip(),
                street=street,
                city=city,
                state=state,
                postal=postal,
                status="open",
                lat=record.get("loc_lat"),
                lon=record.get("loc_long"),
                phone=(record.get("phone") or "").strip() or None,
                hours=_hours(record),
                source_url=QAMARIA_URL,
                fragment=json.dumps(record, sort_keys=True),
            )
        )

    return rows
