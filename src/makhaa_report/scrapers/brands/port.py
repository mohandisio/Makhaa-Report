"""Port Coffee Co."""

import re

from ..base import Scraper
from ..extract import bundle_source

# Minified object literals: {id:"...",region:"...",name:"...",address:"...",...}
# The bundle was rebuilt once already, changing this shape from the previous
# numeric-id, flat-string-hours version — expect it to move again. A store's
# own coordinates come from its `position` literal rather than its Maps link,
# since `position` is always present and needs no URL-format parsing; the
# "future market" entries elsewhere in the bundle have no `address` field and
# so never match this pattern. Non-greedy up to the closing `position` object
# keeps the match from running past this record's own boundary, since the
# `hours` array holds `}` characters of its own.
_RECORD = re.compile(
    r'\{id:"[^"]+",region:"[^"]*",name:"[^"]*",address:"[^"]*".*?'
    r"position:\{lat:(-?[\d.]+),lng:(-?[\d.]+)\}\}",
    re.S,
)
_FIELD = re.compile(r'(\w+):"([^"]*)"')
_HOURS_ENTRY = re.compile(r'\{label:"([^"]*)",value:"([^"]*)"\}')


class Port(Scraper):
    """Port Coffee Co.

    Stores are object literals in the bundle carrying name, address, phone,
    an hours array of `{label, value}` pairs, and a `position` coordinate
    literal. No status or comingSoon field exists on these records any
    more, so every store here reads as open.
    """

    slug = "port"
    url = "https://portcoffeeco.com"

    def collect(self) -> None:
        source = bundle_source(self.fetch, self.url)
        for record in _RECORD.finditer(source):
            fields = dict(_FIELD.findall(record.group(0)))
            hours = None
            hours_block = re.search(r"hours:\[(.*?)\]", record.group(0), re.S)
            if hours_block:
                entries = _HOURS_ENTRY.findall(hours_block.group(1))
                if entries:
                    hours = "; ".join(f"{label}: {value}" for label, value in entries)
            self.add(
                fields.get("address", ""),
                status="open",
                coords=(float(record.group(1)), float(record.group(2))),
                phone=fields.get("phone") or None,
                hours=hours,
                fragment=record.group(0),
            )
