"""Sana'a Cafe."""

from ..base import Scraper
from ..extract import text


class SanaaCafe(Scraper):
    """Sana'a Cafe.

    One card per store, each field in its own labelled info-row. The page
    also still carries an older Divi blurb layout listing fewer stores
    and a stale Sacramento address; the cards are current, so the blurbs
    are ignored.

    The site sits behind a WAF that always answers in Brotli, which is
    why it needs the brotli decoder to read at all.

    Treat the total as a floor rather than a count — the locator omits
    stores the press confirms are trading.
    """

    slug = "sanaa_cafe"
    url = "https://thesanaacafe.com/locations/"

    def collect(self) -> None:
        soup = self.page(self.url)

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

            self.add(
                fields.get("location", ""),
                # A "Coming Soon" button here sits in the order-button
                # slot and can mean online ordering is not live yet, so
                # it is not read as a store status.
                status="open",
                phone=fields.get("phone") or None,
                hours=fields.get("timing") or None,
                fragment=text(card, " | "),
            )
