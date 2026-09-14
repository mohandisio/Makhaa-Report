"""Sana'a Cafe."""

import re

from ..base import Scraper
from ..extract import text
from ...normalize import split_us_address

# Leading digits of a street, used only to line up the same store between
# the grid and the carousel — not a replacement for the base class's own
# exact-address dedupe.
_HOUSE_NUMBER = re.compile(r"^\d+")


class SanaaCafe(Scraper):
    """Sana'a Cafe.

    The locations page has no API, no CPT, no sitemap — both sections
    below are hand-pasted HTML, kept in sync by hand and prone to
    drifting apart, so both are read rather than picking one and
    hoping it is current.

    The "Find Your Nearest Location" grid is a run of Divi blurbs, four
    per store in a fixed order — heading, address, phone, hours — with a
    photo and usually a clean, fully spelled-out address. Near the
    footer, "Find A Sana'a Cafe Near You" repeats the same stores three
    at a time in a slick carousel (`.location-card`), with each field in
    its own labelled `.info-row`; how many cards it carries varies
    between fetches. Its addresses are sometimes crude — all caps, a
    truncated street ("9135 WEST STOCKTON BOULE"), a run-together ZIP+4
    ("926301791") — because it is maintained separately from the grid.

    Read the grid first, then the carousel. A carousel card is skipped
    when its house number, city, and state already match a row the grid
    added — so a store listed in both keeps the grid's spelling — and is
    otherwise added as its own row, carousel spelling and all: a store
    the grid dropped (Elk Grove, at least once seen) still needs to be
    counted, and hand-normalizing "BOULE" or the like here would just
    hide a bad address instead of fixing it. The address confirmer
    canonicalizes carousel-only spellings against Census data later.

    The site sits behind a WAF that always answers in Brotli, which is
    why it needs the brotli decoder to read at all.

    Treat the total as a floor rather than a count — the locator omits
    stores the press confirms are trading.
    """

    slug = "sanaa_cafe"
    url = "https://thesanaacafe.com/locations/"

    def collect(self) -> None:
        soup = self.page(self.url)
        self._read_grid(soup)
        self._read_carousel(soup)

    def _read_grid(self, soup) -> None:
        heading = soup.find(
            ["h1", "h2", "h3"],
            string=lambda s: s and "find your nearest location" in s.casefold(),
        )
        grid = heading.find_parent("div", class_="et_pb_section") if heading else soup

        for column in grid.select(".et_pb_column"):
            blurbs = column.select(".et_pb_blurb")
            if not blurbs or blurbs[0].find("h4") is None:
                continue

            descriptions = [
                text(description)
                for blurb in blurbs[1:]
                if (description := blurb.find("div", class_="et_pb_blurb_description"))
            ]
            address = descriptions[0] if descriptions else ""
            phone = descriptions[1] if len(descriptions) > 1 else None
            hours = descriptions[2] if len(descriptions) > 2 else None

            self.add(
                address,
                status="open",
                phone=phone,
                hours=hours,
                fragment=text(column, " | "),
            )

    def _read_carousel(self, soup) -> None:
        already_placed = {
            (_HOUSE_NUMBER.match(row.street).group(), row.city.casefold(), row.state)
            for row in self.rows
            if _HOUSE_NUMBER.match(row.street)
        }

        for card in soup.select(".location-card"):
            fields: dict[str, str] = {}
            for row in card.select(".info-row"):
                label = row.find("h4")
                if label is None:
                    continue
                body = row.find("div")
                body_text = text(body) if body else ""
                heading_text = label.get_text(strip=True)
                fields[heading_text.casefold()] = body_text.removeprefix(heading_text).strip()

            raw_address = fields.get("location", "")
            parsed = split_us_address(raw_address)
            if parsed is not None:
                street, city, state, _ = parsed
                match = _HOUSE_NUMBER.match(street)
                if match and (match.group(), city.casefold(), state) in already_placed:
                    continue

            self.add(
                raw_address,
                # A "Coming Soon" button here sits in the order-button
                # slot and can mean online ordering is not live yet, so
                # it is not read as a store status.
                status="open",
                phone=fields.get("phone") or None,
                hours=fields.get("timing") or None,
                fragment=text(card, " | "),
            )
