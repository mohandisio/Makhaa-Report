"""Bayt Almocha."""

import html
import json
import re

from ..base import Scraper

_MARKER = "staticPoints = ["

# 655 S 4th St's own record publishes two ZIPs on the same tail
# ("KY 40202, 40204 USA"); the one adjacent to the state is real, so it
# is kept and the second is dropped rather than losing the row.
_DOUBLE_ZIP = re.compile(r"(\d{5}), \d{5}\b")


def _static_points(page: str) -> list[dict]:
    """Balanced-bracket slice of the inline `staticPoints` array.

    The array is HTML-entity-escaped JSON sitting inside an Alpine.js
    `x-init` attribute value, so a non-greedy regex across it stops at
    the first `]` it meets — several store addresses would truncate
    right there. Counting bracket depth instead finds the array's real
    end regardless of what punctuation the addresses carry.
    """
    start = page.index(_MARKER) + len(_MARKER) - 1
    depth = 0
    for i, char in enumerate(page[start:], start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html.unescape(page[start : i + 1]))
    raise ValueError("unterminated staticPoints array")


class BaytAlmocha(Scraper):
    """Bayt Almocha.

    The /find-location page carries every store's coordinates and
    address as one inline `staticPoints` array, embedded directly in the
    server-rendered HTML rather than fetched from a separate API. Its
    punctuation is inconsistent from record to record: some addresses
    drop the comma that would separate the street from the city, and one
    glues a second ZIP onto the state/ZIP tail — the ZIP next to the
    state is kept and the second is dropped before parsing.

    Each store card also shows a live "Closed" / "Open until ..." label
    driven by the time of day, not a permanent status, and the page
    carries no separate coming-soon marker, so every row is recorded
    open.
    """

    slug = "bayt_almocha"
    url = "https://baytalmocha.com/find-location"

    def collect(self) -> None:
        for record in _static_points(self.fetch(self.url)):
            address = _DOUBLE_ZIP.sub(r"\1", record.get("address", ""))
            self.add(
                address,
                coords=(record.get("lat"), record.get("lng")),
                fragment=json.dumps(record, sort_keys=True),
            )
