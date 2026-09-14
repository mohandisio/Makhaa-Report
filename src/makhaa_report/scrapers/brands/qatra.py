"""Qatra Coffee."""

from ..base import Scraper
from ..extract import LOOKS_LIKE_ADDRESS, drop_tags, one_line, schema_records
from ...normalize import split_us_address


class Qatra(Scraper):
    """Qatra Coffee.

    There is no locations page — /locations returns 404 — so the stores
    are read off the home page, where each address appears several times
    across header, cards and footer. Addresses are collected wherever
    they appear and deduplicated.

    One store publishes coordinates in a schema.org block; the others
    have none. No announced stores are published.
    """

    # The Yemeni brand is qatracoffee.com. qatracafe.com is an unrelated
    # Afghan chai cafe — see the exclusions in the registry.
    slug = "qatra"
    url = "https://qatracoffee.com/"
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)

        points: dict[str, tuple[float, float]] = {}
        for record in schema_records(soup, "CafeOrCoffeeShop"):
            address = record.get("address") or {}
            geo = record.get("geo") or {}
            if geo.get("latitude"):
                points[address.get("streetAddress", "").casefold()] = (
                    geo["latitude"],
                    geo["longitude"],
                )

        drop_tags(soup, "script", "style")

        for node in soup.find_all(string=LOOKS_LIKE_ADDRESS):
            raw = one_line(str(node))
            # The coordinate lookup needs the street before add() parses
            # it, so the address is parsed twice here — the only brand
            # that does.
            address = split_us_address(raw)
            street = address[0] if address else None
            self.add(raw, coords=points.get(street.casefold()) if street else None)
