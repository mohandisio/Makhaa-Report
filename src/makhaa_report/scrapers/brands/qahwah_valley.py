"""Qahwah Valley."""

import json

from .. import extract
from ..base import Scraper


class QahwahValley(Scraper):
    """Qahwah Valley.

    New York City coffee shops, all published in a single
    schema.org `Organization` block embedded on the home page — there is
    no dedicated locations page in the nav. The `location` array holds
    one `Restaurant` entry per store, each carrying a `PostalAddress`
    (street, city, region, ZIP), a `GeoCoordinates` pair, and a direct
    telephone number.

    The page has no coming-soon or closed marker anywhere in the feed, so
    every row is recorded as open. It also publishes no hours field here
    (a "Store hours" carousel exists but renders client-side, outside
    this block), so hours are left unset.
    """

    slug = "qahwah_valley"
    url = "https://qahwahvalley.com/"

    def collect(self) -> None:
        soup = self.page(self.url)

        for record in extract.schema_records(soup, "Organization"):
            for store in record.get("location") or []:
                address = store.get("address") or {}
                geo = store.get("geo") or {}

                raw_address = extract.postal_address(address)

                self.add(
                    raw_address,
                    status="open",
                    coords=(geo.get("latitude"), geo.get("longitude")),
                    phone=store.get("telephone") or None,
                    source_url=store.get("url") or self.url,
                    fragment=json.dumps(store, sort_keys=True),
                )
