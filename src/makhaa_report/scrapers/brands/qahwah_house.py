"""Qahwah House."""

import json
import logging

from ..base import Scraper

log = logging.getLogger("makhaa")


def _opening_hours(record: dict) -> str | None:
    """Opening hours joined verbatim from the schema.org specification."""
    spec = record.get("openingHoursSpecification") or []
    parts = [
        f"{entry.get('dayOfWeek', '').rsplit('/', 1)[-1]}: "
        f"{entry.get('opens')}-{entry.get('closes')}"
        for entry in spec
        if entry.get("opens")
    ]
    return "; ".join(parts) or None


class QahwahHouse(Scraper):
    """Qahwah House.

    The locations page embeds one schema.org CafeOrCoffeeShop block per
    store, carrying the address, phone, hours and coordinates — so no
    per-store page needs fetching. The sitemap lists no store pages, and
    several stores share a URL, which makes the address the identity.

    Nothing in the markup distinguishes an announced store from a trading
    one, so every row is recorded as open.
    """

    slug = "qahwah_house"
    url = "https://qahwahhouse.com/locations"

    def collect(self) -> None:
        soup = self.page(self.url)

        for block in soup.find_all("script", type="application/ld+json"):
            try:
                record = json.loads(block.string or "{}")
            except json.JSONDecodeError:
                log.warning("qahwah_house: unreadable ld+json block")
                continue
            if record.get("@type") != "CafeOrCoffeeShop":
                continue

            raw_address = (record.get("address") or {}).get("streetAddress", "")
            geo = record.get("geo") or {}

            self.add(
                raw_address,
                status="open",
                coords=(geo.get("latitude"), geo.get("longitude")),
                phone=record.get("telephone") or None,
                hours=_opening_hours(record),
                source_url=record.get("url") or self.url,
                fragment=json.dumps(record, sort_keys=True),
            )
