"""Matari Coffee."""

from ..base import Scraper
from ..extract import text


class Matari(Scraper):
    """Matari Coffee.

    One card per store: a title link carrying the store name and phone,
    an <address>, and "coming soon" wording for announced stores.

    Two kinds of card produce no row. The Mississauga store is Canadian
    and falls out of the US address parse on its own. Three announced
    markets are published as a bare "Dallas, TX" with no street; they are
    logged and skipped, so Matari's announced presence in Texas and
    Georgia is not represented here.
    """

    slug = "matari"
    url = "https://mataricoffee.com/locations"

    def collect(self) -> None:
        soup = self.page(self.url)

        for card in soup.select("div.service__item-3"):
            block = card.find("address")
            if block is None:
                continue
            raw_address = text(block)

            link = card.select_one("a.woocomerce__feature-producttitle")
            phone = None
            if link is not None:
                phone = next(
                    (t for t in text(link).split() if t.startswith("+")),
                    None,
                )
            card_text = text(card)

            self.add(
                raw_address,
                status="coming_soon" if "coming soon" in card_text.casefold() else "open",
                phone=phone,
                source_url=link["href"] if link and link.get("href") else self.url,
                fragment=card_text,
            )
