"""MoQana Coffee."""

import json

from ..base import Scraper


class Moqana(Scraper):
    """MoQana Coffee.

    Built on the base44.com no-code app platform: the server HTML is only
    an SEO snapshot shell, and every real page (including the locations
    list) is rendered client-side from a JS bundle that calls
    `base44.entities.Location.filter({})`. That resolves to a plain JSON
    GET on the app's own backend, with no auth or map widget involved —
    the closest existing shape is qamaria.py's single-fetch, iterate,
    `self.add()` pattern, not a third-party locator embed.

    Each record carries both a `status` string ("open"/"coming_soon") and
    a separate `active` boolean. In every record seen so far `active` is
    true regardless of `status`, including the coming-soon store, so it
    tracks something like "listed at all" rather than open-for-business;
    `status` is the field that actually distinguishes coming-soon from
    open and is what drives `add()`'s `status` argument here.
    """

    slug = "moqana"
    # base44 app id, found in the home page shell's <meta>/JS bundle path
    # (index-*.js), not hardcoded anywhere else on the site. The
    # Locations page's own chunk confirms the entity name `Location`. The
    # storefront domain is moqana.com — moqana.coffee just 301s here.
    url = "https://moqana.com/api/apps/69cbe4b77d735471b5556f84/entities/Location"

    def collect(self) -> None:
        records = json.loads(self.fetch(self.url))

        for record in records:
            address = " ".join((record.get("address") or "").split())
            city = record.get("city") or ""
            state = record.get("state") or ""
            zip_code = record.get("zip") or ""
            raw_address = f"{address}, {city}, {state} {zip_code}".strip()

            self.add(
                raw_address,
                status=record.get("status") or "open",
                coords=(record.get("lat"), record.get("lng")),
                phone=(record.get("phone") or "").strip() or None,
                hours=(record.get("hours") or "").strip() or None,
                fragment=json.dumps(record, sort_keys=True),
            )
