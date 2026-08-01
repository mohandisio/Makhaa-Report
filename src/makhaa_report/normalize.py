"""Address/status normalization and the deterministic location uid.

The uid is the identity of a store across runs. Changing any function that
feeds make_uid() re-keys every location and orphans snapshot history —
once real data exists, treat changes here as migrations rather than
refactors.
"""

import hashlib
import re

from .models import Location, RawLocation, STATUSES

_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC", "d.c.": "DC",
}
_STATE_CODES = set(_STATES.values())

# Canonical short forms for the street tokens locators actually vary on.
_STREET_ABBREV = {
    "street": "st", "avenue": "ave", "av": "ave", "boulevard": "blvd",
    "road": "rd", "drive": "dr", "lane": "ln", "court": "ct",
    "place": "pl", "parkway": "pkwy", "highway": "hwy", "suite": "ste",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}

# Matching is substring-based; "soon"/"opening" checked before "open".
_OPEN_WORDS = ("open",)
_SOON_WORDS = ("soon", "opening")


def normalize_street(raw: str) -> str:
    s = raw.casefold().strip()
    s = re.sub(r"[.,#]", " ", s)
    tokens = [_STREET_ABBREV.get(t, t) for t in s.split()]
    return " ".join(tokens)


def normalize_state(raw: str) -> str:
    s = raw.strip().rstrip(".").strip()
    if s.upper() in _STATE_CODES:
        return s.upper()
    key = s.casefold()
    if key in _STATES:
        return _STATES[key]
    raise ValueError(f"unrecognized state: {raw!r}")


# "7706 Allen Rd, Allen Park, MI 48101" and the comma-less variants
# locators publish. Anything without a two-letter state plus ZIP is not a
# US address and is rejected rather than guessed at.
_US_ADDRESS = re.compile(
    r"^(?P<street>.+?),?\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<postal>\d{5})(?:-\d{4})?\.?$"
)


def split_us_address(raw: str) -> tuple[str, str, str, str] | None:
    """Split a one-line US address into (street, city, state, postal).

    Returns None when the string isn't a US address — Canadian and Gulf
    stores appear in several brands' feeds and are out of scope.
    """
    match = _US_ADDRESS.match(" ".join(raw.split()))
    if match is None:
        return None
    return (
        match["street"].strip(),
        match["city"].strip(),
        match["state"],
        match["postal"],
    )


def normalize_postal(raw: str | None) -> str | None:
    if not raw:
        return None
    m = re.search(r"\d{5}", raw)
    return m.group(0) if m else None


def normalize_status(raw: str) -> str:
    s = raw.casefold().strip()
    if s in STATUSES:
        return s
    if any(w in s for w in _SOON_WORDS):
        return "coming_soon"
    if any(w in s for w in _OPEN_WORDS):
        return "open"
    if "relocat" in s:
        return "relocating"
    if "closed" in s:
        return "closed_permanently"
    return "unknown"


def make_uid(brand: str, street: str, city: str, state: str) -> str:
    # postal deliberately excluded: locators omit/typo ZIPs; street+city+state
    # is the stable identity.
    key = "|".join(
        (brand, normalize_street(street), city.casefold().strip(), normalize_state(state))
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def to_location(raw: RawLocation, now_iso: str, *, is_manual: bool = False) -> Location:
    state = normalize_state(raw.state)
    return Location(
        uid=make_uid(raw.brand, raw.street, raw.city, raw.state),
        brand=raw.brand,
        name=raw.name.strip(),
        street=" ".join(raw.street.split()),
        city=raw.city.strip(),
        state=state,
        postal=normalize_postal(raw.postal),
        lat=raw.lat,
        lon=raw.lon,
        geocode_source=(
            ("manual" if is_manual else "locator")
            if raw.lat is not None and raw.lon is not None
            else None
        ),
        geocode_flagged=False,
        county=None,
        tract=None,
        cbsa=None,
        status=normalize_status(raw.status),
        status_note=raw.status_note.strip(),
        phone=raw.phone,
        hours=raw.hours,
        source_url=raw.source_url,
        is_manual=is_manual,
        first_seen=now_iso,
        last_seen=now_iso,
        fragment=raw.fragment,
    )
