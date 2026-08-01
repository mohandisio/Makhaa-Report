"""Hand-maintained data: per-brand manual CSVs and the overrides file.

Manual CSVs (data/manual/<slug>.csv) hold brands with no scrapable locator.
Columns are MANUAL_FIELDS; the filename stem is the brand slug.

overrides.csv rows patch/add/drop rows after every scrape; manual edits win.
Its columns are action,uid + the MANUAL_FIELDS (plus brand and a free-text
note). patch/drop need uid; add computes one.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import config
from .models import Location, RawLocation
from .normalize import to_location

MANUAL_FIELDS = (
    "name", "street", "city", "state", "postal", "status", "status_note",
    "lat", "lon", "phone", "hours", "source_url",
)


@dataclass(frozen=True)
class Override:
    action: Literal["patch", "add", "drop"]
    uid: str | None  # required for patch/drop; blank for add (uid computed)
    fields: dict[str, str]  # non-empty cells only; these win


def _float_or_none(v: str | None) -> float | None:
    return float(v) if v and v.strip() else None


def raw_from_record(brand: str, rec: dict[str, str], fragment: str) -> RawLocation:
    """One conversion from a str-dict (CSV row or override cells) to RawLocation."""
    return RawLocation(
        brand=brand,
        name=(rec.get("name") or "").strip(),
        street=(rec.get("street") or "").strip(),
        city=(rec.get("city") or "").strip(),
        state=(rec.get("state") or "").strip(),
        postal=rec.get("postal") or None,
        status=(rec.get("status") or "").strip() or "open",
        status_note=(rec.get("status_note") or "").strip(),
        lat=_float_or_none(rec.get("lat")),
        lon=_float_or_none(rec.get("lon")),
        phone=rec.get("phone") or None,
        hours=rec.get("hours") or None,
        source_url=(rec.get("source_url") or "").strip(),
        fragment=fragment,
    )


def load_manual_brands(manual_dir: Path | None = None) -> list[RawLocation]:
    manual_dir = manual_dir or config.MANUAL_DIR  # resolved at call time so tests can repoint config
    rows: list[RawLocation] = []
    if not manual_dir.is_dir():
        return rows
    for csv_path in sorted(manual_dir.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for rec in csv.DictReader(f):
                if not (rec.get("street") or "").strip():
                    continue  # skip blank/template lines
                rows.append(raw_from_record(csv_path.stem, rec, f"manual:{csv_path.name}"))
    return rows


def load_overrides(path: Path | None = None) -> list[Override]:
    path = path or config.OVERRIDES_PATH
    overrides: list[Override] = []
    if not path.is_file():
        return overrides
    with open(path, newline="", encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            action = (rec.get("action") or "").strip()
            if action not in ("patch", "add", "drop"):
                continue
            fields = {
                k: v.strip()
                for k, v in rec.items()
                if k not in ("action", "uid") and v and v.strip()
            }
            overrides.append(
                Override(action=action, uid=(rec.get("uid") or "").strip() or None,
                         fields=fields)
            )
    return overrides


def apply_overrides(locations: dict[str, Location], now_iso: str) -> None:
    """Merge overrides.csv into this run's row set, in place. Manual edits win."""
    for ov in load_overrides():
        if ov.action == "drop" and ov.uid:
            locations.pop(ov.uid, None)
        elif ov.action == "patch" and ov.uid and ov.uid in locations:
            loc = locations[ov.uid]
            for k, v in ov.fields.items():
                if hasattr(loc, k):
                    setattr(loc, k, float(v) if k in ("lat", "lon") else v)
            if "lat" in ov.fields or "lon" in ov.fields:
                loc.geocode_source = "manual"
            loc.is_manual = True
        elif ov.action == "add":
            raw = raw_from_record(ov.fields.get("brand", ""), ov.fields, "override:add")
            loc = to_location(raw, now_iso, is_manual=True)
            locations[loc.uid] = loc
