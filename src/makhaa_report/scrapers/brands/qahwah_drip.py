"""Qahwah Drip."""

import json
import logging

from .. import extract
from ..base import Scraper

log = logging.getLogger("makhaa")


def _opening_hours(record: dict) -> str | None:
    """Opening hours joined verbatim from the schema.org specification.

    `dayOfWeek` here is a plain day name or a list of them (never the
    `https://schema.org/Monday` URI form qahwah_house's page uses), so
    each entry is joined into one line rather than split on "/".
    """
    spec = record.get("openingHoursSpecification") or []
    parts = []
    for entry in spec:
        opens = entry.get("opens")
        if not opens:
            continue
        days = entry.get("dayOfWeek") or []
        if isinstance(days, str):
            days = [days]
        day_str = ", ".join(day.rsplit("/", 1)[-1] for day in days)
        parts.append(f"{day_str}: {opens}-{entry.get('closes')}")
    return "; ".join(parts) or None


class QahwahDrip(Scraper):
    """Qahwah Drip.

    A single-page site for one store. The head carries one schema.org
    CafeOrCoffeeShop block with the address, phone, coordinates and
    opening hours — everything the page publishes about the store — so
    there is nothing else to crawl and no per-store page to fetch.

    The page has no coming-soon marker of any kind (the copy just says
    "Now open"), so the row is always recorded as open.
    """

    slug = "qahwah_drip"
    url = "https://qahwahdrip.com"

    def collect(self) -> None:
        soup = self.page(self.url)

        for block in soup.find_all("script", type="application/ld+json"):
            try:
                record = json.loads(block.string or "{}")
            except json.JSONDecodeError:
                log.warning("qahwah_drip: unreadable ld+json block")
                continue
            if record.get("@type") != "CafeOrCoffeeShop":
                continue

            address = record.get("address") or {}
            raw_address = extract.postal_address(address)
            geo = record.get("geo") or {}
            hours = (
                _opening_hours(record)
                if "openingHoursSpecification" in record
                else None
            )

            self.add(
                raw_address,
                status="open",
                coords=(geo.get("latitude"), geo.get("longitude")),
                phone=record.get("telephone") or None,
                hours=hours,
                source_url=record.get("url") or self.url,
                fragment=json.dumps(record, sort_keys=True),
            )
