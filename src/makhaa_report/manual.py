"""Manual-entry data: per-brand CSVs and the overrides file.

Manual CSVs (data/manual/<slug>.csv) hold brands with no scrapable
locator, filled in through the manual-entry command.
Columns are MANUAL_FIELDS; the filename stem is the brand slug.

overrides.csv rows patch/add/drop rows after every scrape; manual edits win.
Its columns are action,uid + the MANUAL_FIELDS (plus brand and a free-text
note). patch/drop need uid; add computes one.
"""

import csv
import json
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


class ManualEntryError(ValueError):
    """The record cannot be turned into a store row."""


def parse_entry(tokens: list[str]) -> dict[str, str]:
    """Read one record from the command line.

    Accepts either JSON — `{"brand": "mohka_house", "city": "Oakland"}` —
    or shell-friendly `key=value` pairs, which avoid quoting braces.
    """
    text = " ".join(tokens).strip()
    if text.startswith("{"):
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManualEntryError(f"not valid JSON: {exc}") from exc
        return {str(k).strip(): str(v).strip() for k, v in record.items()}

    record: dict[str, str] = {}
    for token in tokens:
        key, separator, value = token.partition("=")
        if not separator:
            raise ManualEntryError(
                f"expected key=value or JSON, got {token!r}"
            )
        record[key.strip()] = value.strip()
    return record


def append_entry(record: dict[str, str], manual_dir: Path | None = None) -> Path:
    """Write one manual-entry row to its brand's CSV, creating it if needed.

    The CSV is the durable copy: the database is rebuildable, but these
    rows exist nowhere else, so they are committed to git.
    """
    manual_dir = manual_dir or config.MANUAL_DIR
    unknown = set(record) - {"brand", *MANUAL_FIELDS}
    if unknown:
        raise ManualEntryError(
            f"unknown field(s): {', '.join(sorted(unknown))}. "
            f"Allowed: brand, {', '.join(MANUAL_FIELDS)}"
        )
    brand = record.get("brand", "").strip()
    if not brand:
        raise ManualEntryError("brand is required")
    from .registry import BRANDS  # imported here to keep the module import-light

    known = {b.slug for b in BRANDS}
    if brand not in known:
        raise ManualEntryError(
            f"unknown brand {brand!r} — add it to the registry first. "
            f"Known slugs: {', '.join(sorted(known))}"
        )
    if not record.get("street", "").strip():
        raise ManualEntryError("street is required — a store needs an address")
    if not record.get("city", "").strip() or not record.get("state", "").strip():
        raise ManualEntryError("city and state are required")

    manual_dir.mkdir(parents=True, exist_ok=True)
    path = manual_dir / f"{brand}.csv"
    is_new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(MANUAL_FIELDS))
        if is_new:
            writer.writeheader()
        writer.writerow({k: record.get(k, "") for k in MANUAL_FIELDS})
    return path
