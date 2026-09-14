"""Qamaria Yemeni Coffee."""

import json

from ..base import Scraper

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _hours(record: dict) -> str | None:
    """Weekday opening hours, joined verbatim and unparsed."""
    parts = [f"{day}: {record[day]}" for day in _WEEKDAYS if record.get(day)]
    return "; ".join(parts) or None


class Qamaria(Scraper):
    """Qamaria Yemeni Coffee.

    Two kinds of entry are dropped: rows tagged `catering`, which are
    service-area listings that repeat an existing cafe's address and would
    double-count, and non-US rows (Canada, Saudi Arabia, Qatar).

    The feed carries no open/coming-soon flag, so every row is recorded as
    open — Qamaria's announced pipeline is not visible here.
    """

    slug = "qamaria"
    # Qamaria's /cafes page embeds a Storepoint map widget; the widget's
    # own API returns the full location list. The map id comes from the
    # embed's data-map-id attribute and changes only if they rebuild the
    # map.
    url = "https://api.storepoint.co/v1/165c3af3b9c727/locations"
    quiet = True  # non-US rows are dropped silently, not warned about

    def collect(self) -> None:
        payload = json.loads(self.fetch(self.url))

        for record in payload["results"]["locations"]:
            if "catering" in (record.get("tags") or ""):
                continue
            self.add(
                record.get("streetaddress") or "",
                status="open",
                coords=(record.get("loc_lat"), record.get("loc_long")),
                phone=(record.get("phone") or "").strip() or None,
                hours=_hours(record),
                fragment=json.dumps(record, sort_keys=True),
            )
