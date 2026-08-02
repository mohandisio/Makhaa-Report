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
#: Spelled-out state names, for callers matching them in slugs or prose.
US_STATE_NAMES = frozenset(_STATES)

# Canonical short forms for the street tokens locators actually vary on.
# These decide identity, so they have to cover both how a locator writes a
# street and how a geocoder answers: "Alafaya Trail" and "Alafaya Trl" are
# one store, and if they hash differently a corrected row comes back as a
# second store on the next scrape.
_STREET_ABBREV = {
    "street": "st", "avenue": "ave", "av": "ave", "boulevard": "blvd",
    "road": "rd", "drive": "dr", "lane": "ln", "court": "ct",
    "place": "pl", "parkway": "pkwy", "highway": "hwy", "suite": "ste",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
    # USPS suffix forms a geocoder answers with.
    "trail": "trl", "plaza": "plz", "circle": "cir", "terrace": "ter",
    "square": "sq", "freeway": "fwy", "expressway": "expy",
    "turnpike": "tpke", "center": "ctr", "centre": "ctr", "crossing": "xing",
    "junction": "jct", "extension": "ext", "heights": "hts", "landing": "lndg",
    "station": "sta", "village": "vlg", "manor": "mnr", "ridge": "rdg",
}

# Multi-token names a geocoder collapses. Applied before tokenizing,
# because no per-token rule can turn "Farm To Market 544" into "FM 544".
_STREET_PHRASES = ((re.compile(r"\bfarm to market\b"), "fm"),)

# City spellings that mean one place. "St Paul" and "Saint Paul" are the
# same city, and the uid must not care which the locator used.
_CITY_ABBREV = {"saint": "st", "mount": "mt", "fort": "ft"}

# Matching is substring-based; "soon"/"opening" checked before "open".
_OPEN_WORDS = ("open",)
_SOON_WORDS = ("soon", "opening")


def normalize_street(raw: str) -> str:
    s = raw.casefold().strip()
    # The hyphen is punctuation here: "Troy-Schenectady Rd" and
    # "Troy Schenectady Rd" are the same road.
    s = re.sub(r"[.,#-]", " ", s)
    for pattern, short in _STREET_PHRASES:
        s = pattern.sub(short, s)
    tokens = [_STREET_ABBREV.get(t, t) for t in s.split()]
    return " ".join(tokens)


def normalize_city_key(raw: str) -> str:
    """The form of a city name used for identity, not for display."""
    s = re.sub(r"[.,'’-]", " ", raw.casefold())
    return " ".join(_CITY_ABBREV.get(t, t) for t in s.split())


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
    # ZIP+4 arrives hyphenated or, on at least one site, as nine digits
    # run together; either way only the five-digit ZIP is kept.
    rf"(?:,?\s+(?P<postal>\d{{5}})(?:-?\d{{4}})?)?\.?$",
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
# The same thing written as two tokens: "1336 Illinois Rte 59 Naperville".
_ROUTE_WORDS = {"rt", "rte", "route", "hwy", "highway", "us", "sr", "fm", "cr", "county"}
_ROUTE_NUMBER = re.compile(r"^\d+[a-z]?$", re.I)


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
        word = token.strip(".").casefold()
        if word in _STREET_TYPES or _HIGHWAY.match(token):
            cut = i + 1
        elif (
            word in _ROUTE_WORDS
            and i + 1 < len(tokens)
            and _ROUTE_NUMBER.match(tokens[i + 1])
        ):
            cut = i + 2
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
    # A bare suite letter with no marker: "6311 Stadium Dr B Clemmons".
    # Directionals were already consumed above, so anything left that is
    # a single letter belongs to the street, not the city.
    if cut + 1 < len(tokens) and len(tokens[cut].strip(".")) == 1 and tokens[cut][0].isalpha():
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
    cleaned = " ".join(raw.split())
    # A pipe never appears inside an address; sites use it to prefix a
    # label ("| Buffalo, NY | 1185 Sweet Home Rd, ..."), so the address
    # is whatever follows the last one.
    if "|" in cleaned:
        cleaned = cleaned.rpartition("|")[2]
    # Bullets and middots stand in for the comma between street and city.
    cleaned = re.sub(r"\s*[·•]\s*", ", ", cleaned)
    cleaned = _COUNTRY_SUFFIX.sub("", cleaned.strip(" ,"))
    match = _US_TAIL.match(cleaned)
    if match is None:
        return None
    parts = _split_street_city(match["head"])
    if parts is None:
        return None
    street, city = (part.strip(" ,") for part in parts)
    if not street or not city:
        return None
    if len(city) == 2 and city.isupper():
        # A bare code where the city should be means the tail matched a
        # foreign province ("Toronto, ON, CA"), not a US city and state.
        return None
    return street, city, normalize_state(match["state"]), match["postal"]


# Unit designators worth cutting on. Deliberately narrower than
# _UNIT_MARKERS: "no" is dropped because a street can legitimately start
# with it, and a false cut silently truncates the street.
_UNIT_WORDS = {
    "ste", "suite", "suit", "unit", "apt", "apartment", "fl", "floor",
    "bldg", "building", "rm", "room", "lot", "spc", "trlr",
}


def split_unit(street: str) -> tuple[str, str]:
    """Separate the street line from its unit: '12 Lee Rd Ste 102' -> ('12 Lee Rd', 'Ste 102').

    Geocoders match on the street line and drop the unit from their
    output, so the unit has to travel separately and be re-appended. The
    cut is only taken from the third token onwards, which keeps a street
    genuinely named "Floor" or "Building" intact.
    """
    tokens = street.split()
    for i, token in enumerate(tokens):
        if i < 2:
            continue
        if token.startswith("#") or token.strip(".,").casefold() in _UNIT_WORDS:
            return " ".join(tokens[:i]).strip(" ,"), " ".join(tokens[i:])

    # A suite written as a bare letter, which several locators do:
    # "6311 Stadium Dr B". Census answers those Non_Exact and matches the
    # street without it, so leaving it on costs the row its verification.
    # Two things must hold before cutting. A directional is not a suite —
    # "3005 Lyndale Ave S" is a street. And a street keeps its name as
    # well as its type, so "123 Avenue A" is left whole: that letter is
    # the name.
    if len(tokens) >= 4:
        last = tokens[-1].strip(".,")
        if (len(last) == 1 and last.isalpha()
                and last.casefold() not in _DIRECTIONALS):
            return " ".join(tokens[:-1]).strip(" ,"), tokens[-1]
    return street.strip(), ""


# Tokens that stay capitalised when a geocoder introduces them, because
# title-casing turns "NE" into "Ne" and "FM 544" into "Fm 544".
_KEEP_UPPER = _DIRECTIONALS | {"fm", "us", "sr", "cr", "rr", "i"}


def recase(canonical: str, original: str) -> str:
    """Re-case a geocoder's shouted output using the original's spelling.

    Census answers in capitals, so adopting its address verbatim would
    shout the whole dataset and flatten "MacArthur" to "Macarthur". A
    token the original already had keeps the original's casing; a token
    the geocoder introduced ("TRAIL" -> "TRL") is title-cased.
    """
    seen: dict[str, str] = {}
    # An original with no lowercase anywhere is shouting too, and has no
    # casing worth keeping. Judged over the whole string, not per token,
    # so "JW" survives in "JW Clay Blvd" without rescuing the "DR" in
    # "LAKE FOREST DR".
    if any(c.islower() for c in original):
        for token in original.split():
            # A street type has one right spelling, so let the canonical
            # form win: preserving ours leaves "Canton Center RD" shouting
            # inside an otherwise ordinary address. Proper nouns are what
            # this is protecting.
            if token.casefold() in _STREET_TYPES:
                continue
            seen.setdefault(token.casefold(), token)
    out = []
    for token in canonical.split():
        key = token.casefold()
        if key in seen:
            out.append(seen[key])
        elif key in _KEEP_UPPER:
            out.append(token.upper())
        elif token[:1].isdigit():
            # title() would make "14TH" into "14Th"; an ordinal only ever
            # wants its letters lowered.
            out.append(token.capitalize())
        else:
            out.append(token.title())
    return " ".join(out)


_HOUSE_NUMBER = re.compile(r"^\s*(\d[\d-]*)")


def address_key(brand: str, street: str, state: str) -> tuple[str, str, str] | None:
    """A store's identity without the parts a correction rewrites.

    The uid hashes the whole address, so it cannot match a manual entry
    that exists precisely to fix that address. The house number and state
    are what survive: a correction changes how a street is spelled and
    which city it claims, not which building it is. Unique across the
    census as it stands, and returns None when the street has no leading
    number to key on.
    """
    match = _HOUSE_NUMBER.match(street)
    if match is None:
        return None
    return (brand, match.group(1), normalize_state(state))


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
        (brand, normalize_street(street), normalize_city_key(city), normalize_state(state))
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def to_location(raw: RawLocation, now_iso: str, *, is_manual: bool = False) -> Location:
    state = normalize_state(raw.state)
    return Location(
        uid=make_uid(raw.brand, raw.street, raw.city, raw.state),
        brand=raw.brand,
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
