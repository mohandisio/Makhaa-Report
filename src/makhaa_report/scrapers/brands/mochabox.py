"""MochaBox Coffee."""

import logging
import re

from ..base import Scraper
from ..extract import drop_tags

log = logging.getLogger("makhaa")

URL = "https://mochaboxcoffee.com"

# A line that opens like a street: "1050 Haywood Rd."
_STREET_START = re.compile(r"^\d{1,6}\s+\S+", re.I)

# A postcode with too many digits: real on MochaBox's site, and worth
# dropping rather than truncating into a plausible-looking wrong ZIP.
_BAD_POSTAL = re.compile(r",?\s*\d{6,}\s*$")


class Mochabox(Scraper):
    """MochaBox Coffee.

    Wix, with the street and the city line in separate elements, so the
    two are joined before parsing. The site publishes a six-digit
    postcode; it is dropped rather than trimmed into a wrong ZIP, which
    costs nothing since the address parses without one.
    """

    slug = "mochabox"
    url = URL
    quiet = True

    def collect(self) -> None:
        soup = self.page(self.url)
        drop_tags(soup, "script", "style", "title")

        texts = [
            " ".join(str(node).split())
            for node in soup.find_all(string=True)
            if str(node).strip()
        ]

        for index, text in enumerate(texts):
            if not _STREET_START.match(text):
                continue
            for tail in texts[index + 1 : index + 4]:
                candidate = f"{text.rstrip('.')}, {_BAD_POSTAL.sub('', tail)}"
                if self.add(candidate, fragment=f"{text} | {tail}"):
                    return

        if not self.rows:
            log.warning("mochabox: no address found")
