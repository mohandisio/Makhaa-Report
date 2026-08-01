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


_COUNTRY_SUFFIX = re.compile(
    r",?\s*(united states(\s+of\s+america)?|u\.?s\.?a\.?|u\.?s\.?)\.?$", re.I
)

# Anchored on the state-plus-ZIP tail, which every US address has and no
# foreign one does. State may be a code or a full name; the comma before
# it is optional because locators drop it constantly.
_STATE_PATTERN = "|".join(
    re.escape(name) for name in sorted(set(_STATES) | {c.lower() for c in _STATE_CODES},
                                       key=len, reverse=True)
)
# The ZIP is optional: several brands publish "street, city, ST, USA".
# postal is nullable and plays no part in the uid, so its absence costs
# nothing but the postcode itself.
_US_TAIL = re.compile(
    rf"^(?P<head>.+?),?\s+(?P<state>{_STATE_PATTERN})"
    rf"(?:,?\s+(?P<postal>\d{{5}})(?:-\d{{4}})?)?\.?$",
    re.I,
)

# Tokens that end a street name. Used only when the address has no comma
# separating street from city ("725 Fulton St. Brooklyn"), which is common
# enough that rejecting those rows would lose real stores.
_STREET_TYPES = {
    "st", "street", "ave", "avenue", "av", "blvd", "boulevard", "rd", "road",
    "dr", "drive", "ln", "lane", "ct", "court", "pl", "place", "pkwy",
    "parkway", "hwy", "highway", "way", "sq", "square", "ter", "terrace",
    "cir", "circle", "plaza", "trl", "trail", "loop", "pike", "row",
    "expy", "expressway", "tpke", "turnpike", "broadway", "walk", "run",
}
_DIRECTIONALS = {"n", "s", "e", "w", "ne", "nw", "se", "sw"}
_UNIT_MARKERS = {
    "ste", "suite", "unit", "apt", "apartment", "fl", "floor", "bldg",
    "building", "rm", "room", "no", "#",
}
_UNIT_ID = re.compile(r"^#?[\w-]{1,8}$")
# Numbered routes stand in for a street type: "1529 US-14 W Rochester".
_HIGHWAY = re.compile(r"^(us|sr|fm|rt|rte|route|hwy|highway|county|cr|m)[-\s]?\d+[a-z]?$", re.I)


def _split_street_city(head: str) -> tuple[str, str] | None:
    """Separate street from city in the part preceding the state."""
    if "," in head:
        street, _, city = head.rpartition(",")
        street, city = street.strip(), city.strip()
        # "1300 Main Street, Unit T Lombard" puts the unit on the city's
        # side of the comma; move it back so the city is just the city.
        tokens = city.split()
        while len(tokens) > 1 and tokens[0].strip(".#").casefold() in _UNIT_MARKERS:
            moved, tokens = tokens[0], tokens[1:]
            if len(tokens) > 1 and _UNIT_ID.match(tokens[0]):
                moved, tokens = f"{moved} {tokens[0]}", tokens[1:]
            street = f"{street} {moved}".strip()
        return street, " ".join(tokens)

    # No comma: cut after the last street-type token, then step past any
    # directional or unit designator trailing it, so "Ave NE Seattle" and
    # "Rd Ste 102 Mesa" both leave the city alone.
    tokens = head.split()
    cut = None
    for i, token in enumerate(tokens):
        if token.strip(".").casefold() in _STREET_TYPES or _HIGHWAY.match(token):
            cut = i + 1
    if cut is None or cut >= len(tokens):
        return None
    if tokens[cut].strip(".").casefold() in _DIRECTIONALS and cut + 1 < len(tokens):
        cut += 1
    while cut + 1 < len(tokens) and tokens[cut].strip(".#").casefold() in _UNIT_MARKERS:
        cut += 1
        if cut + 1 < len(tokens) and _UNIT_ID.match(tokens[cut]):
            cut += 1
    while cut + 1 < len(tokens) and tokens[cut].startswith("#"):
        cut += 1
    if cut >= len(tokens):
        return None
    return " ".join(tokens[:cut]), " ".join(tokens[cut:])


def split_us_address(raw: str) -> tuple[str, str, str, str] | None:
    """Split a one-line US address into (street, city, state, postal).

    Returns None when the string isn't a US address — Canadian and Gulf
    stores appear in several brands' feeds and are out of scope — or when
    street and city can't be told apart, which is worth losing a row over
    rather than guessing at the uid.
    """
    cleaned = _COUNTRY_SUFFIX.sub("", " ".join(raw.split()))
    match = _US_TAIL.match(cleaned)
    if match is None:
        return None
    parts = _split_street_city(match["head"])
    if parts is None:
        return None
    street, city = parts
    if not street or not city:
        return None
    if len(city) == 2 and city.isupper():
        # A bare code where the city should be means the tail matched a
        # foreign province ("Toronto, ON, CA"), not a US city and state.
        return None
    return street, city, normalize_state(match["state"]), match["postal"]


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
