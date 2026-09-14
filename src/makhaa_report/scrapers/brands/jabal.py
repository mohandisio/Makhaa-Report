"""Jabal Coffee House."""

import re

from ..base import Scraper
from ..extract import one_line

# A street line always carries a house number; a "City, ST" teaser never
# does. Cheaper and more direct than trying every card through the full
# address parser just to throw the streetless ones away.
_HAS_STREET_NUMBER = re.compile(r"\d")

# The card's second paragraph, when present, announces the store rather
# than giving it a marker keyword: "Coming Summer 2026", "Coming Fall
# 2026" or "Coming Spring 2027". "Soft Opening" (Toledo) means the store
# is already trading, so only "coming" wording counts as an announcement.
_COMING = re.compile(r"\bcoming\b", re.I)


class Jabal(Scraper):
    """Jabal Coffee House.

    A Shopify "map section" on the locations page holds one card per
    store: `div.map-section__overlay` with an `h3` name and, under
    `div.rte-setting`, a `<p>` whose street/city-state-zip/country lines
    are joined by `<br>` rather than split into separate elements. A
    second `<p>` in that div, when present, carries the announcement
    text above instead of a dedicated status field.

    Ten-plus "coming soon" entries publish only "City, ST" with no
    street; a card whose first paragraph has no house number is a teaser
    like that, not a broken address, so it's skipped before add() rather
    than logged as one. Three Canadian stores (Mississauga full-address,
    Vancouver and London city-only) are real addresses that fail the US
    parse instead — those still go through add() and warn, same as any
    other brand's unparseable row. No coordinates, phone or hours are
    published on this page.
    """

    slug = "jabal"
    url = "https://jabalcoffeehouse.com/pages/locations"

    def collect(self) -> None:
        soup = self.page(self.url)

        for card in soup.select("div.map-section__overlay"):
            address_div = card.select_one("div.rte-setting")
            if address_div is None:
                continue
            paragraphs = address_div.find_all("p")
            if not paragraphs:
                continue

            raw_address = one_line(paragraphs[0].get_text(", "))
            if not _HAS_STREET_NUMBER.search(raw_address):
                continue
            marker = one_line(
                " ".join(p.get_text(" ") for p in paragraphs[1:])
            )

            self.add(
                raw_address,
                status="coming_soon" if _COMING.search(marker) else "open",
                fragment=one_line(card.get_text(" ")),
            )
