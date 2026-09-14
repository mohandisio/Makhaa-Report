"""Qishr Coffee House."""

import re

from ..base import Scraper
from ..extract import bundle_source

# A street literal followed within a few hundred characters by a
# "City, ST 12345" literal — how an address split across JSX children
# appears once minified.
_SPLIT_ADDRESS = re.compile(
    r'"(?P<street>\d{1,6}[^"]{3,44}?)"'
    r'.{0,240}?'  # the line-break element between them carries its own quotes
    r'"(?P<tail>[A-Za-z .\'-]{3,40},\s*[A-Z]{2}\s+\d{5})"',
    re.S,
)


class Qishr(Scraper):
    """Qishr Coffee House.

    No store list — the single cafe's address is written straight into
    the footer markup, so it arrives as two adjacent string literals,
    street then "City, ST ZIP".
    """

    slug = "qishr"
    url = "https://qishrcoffeehouse.co"
    quiet = True

    def collect(self) -> None:
        for match in _SPLIT_ADDRESS.finditer(bundle_source(self.fetch, self.url)):
            self.add(
                f"{match['street']}, {match['tail']}",
                fragment=match.group(0),
            )
