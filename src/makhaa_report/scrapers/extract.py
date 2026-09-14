"""Helpers used by two or more brand scrapers.

A helper used by a single brand stays in that brand's own module; only
what several scrapers share moves here.
"""

import json
import re

from ..fetch import Fetch

# Cheap pre-filter for text nodes worth handing to the address parser.
LOOKS_LIKE_ADDRESS = re.compile(r"\b[A-Z]{2}\s+\d{5}\b")

# Google Maps *place* links carry the store's coordinates as !3d(lat)!4d(lon).
# Embed URLs use !2d(lon)!3d(lat) instead and have no !4d, so they never
# match here — arwa's own _EMBED_COORDS handles those.
_PLACE_COORDS = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")

# The shell page's <script src="/assets/*.js"> pointing at the app bundle.
_BUNDLE = re.compile(r'src="(/assets/[^"]+\.js)"')


def one_line(value: str) -> str:
    """Collapse any run of whitespace to single spaces."""
    return " ".join(value.split())


def text(element, separator: str = " ") -> str:
    """One-line text of an element, joined with `separator` between parts."""
    return one_line(element.get_text(separator, strip=True))


def drop_tags(soup, *names: str) -> None:
    """Remove every tag whose name is in `names`, in place."""
    for tag in soup.find_all(list(names)):
        tag.decompose()


def place_coords(url: str) -> tuple[float, float] | None:
    """(lat, lon) from a Google Maps place link's !3d/!4d pair, or None."""
    match = _PLACE_COORDS.search(url)
    if match is None:
        return None
    return float(match.group(1)), float(match.group(2))


def innermost_address_texts(soup) -> list[str]:
    """Text of the smallest elements that still contain a whole address.

    Reading raw text nodes misses addresses split across children — a
    street and its city line inside one element — while reading every
    element would join unrelated stores together. The innermost element
    that matches is the one that holds exactly one address.
    """
    texts: list[str] = []
    for element in soup.find_all(True):
        candidate = text(element)
        if not LOOKS_LIKE_ADDRESS.search(candidate):
            continue
        if any(
            LOOKS_LIKE_ADDRESS.search(text(child))
            for child in element.find_all(True)
        ):
            continue
        texts.append(candidate)
    return texts


def postal_address(address: dict) -> str:
    """Join a schema.org `PostalAddress` into one line.

    `"<street>, <locality>, <region> <postal>"`, with any missing part
    dropped cleanly rather than leaving a stray comma or space behind.
    """
    tail = " ".join(
        part
        for part in (address.get("addressRegion"), address.get("postalCode"))
        if part
    )
    return ", ".join(
        part
        for part in (address.get("streetAddress"), address.get("addressLocality"), tail)
        if part
    )


def schema_records(soup, type_name: str) -> list[dict]:
    """Parsed `<script type="application/ld+json">` blocks matching `@type`.

    A block whose JSON does not parse is skipped silently. A caller that
    wants to warn about an unreadable block (qahwah_house does) iterates
    the script tags itself instead of calling this helper.
    """
    records = []
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            record = json.loads(block.string or "{}")
        except json.JSONDecodeError:
            continue
        if record.get("@type") == type_name:
            records.append(record)
    return records


def bundle_source(fetch: Fetch, base_url: str) -> str:
    """Fetch the app bundle the shell page loads."""
    match = _BUNDLE.search(fetch(base_url))
    if match is None:
        raise ValueError(f"{base_url}: no app bundle found in the page shell")
    return fetch(base_url.rstrip("/") + match.group(1))
