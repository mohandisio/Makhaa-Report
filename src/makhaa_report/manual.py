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
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import config
from .models import Location, RawLocation
from .normalize import address_key, to_location

log = logging.getLogger("makhaa")

MANUAL_FIELDS = (
    "street", "city", "state", "postal", "status", "status_note",
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


#: Column order written into overrides.csv.
OVERRIDE_FIELDS = ("action", "uid", "brand", *MANUAL_FIELDS, "note")


def append_override(uid: str, fields: dict[str, str], note: str,
                    path: Path | None = None) -> bool:
    """Record a patch in overrides.csv. False when it is already there.

    A correction written only to the database is undone by the next
    scrape, because the scraper is the source of truth for the rows it
    produces. Overrides are applied last on every run, so this is what
    makes a correction outlive the scrape that contradicts it.

    An existing file keeps its own column order, so a file written before
    a field was added or dropped still round-trips.
    """
    path = path or config.OVERRIDES_PATH
    row = {"action": "patch", "uid": uid, "note": note,
           **{k: v for k, v in fields.items() if v not in (None, "")}}

    columns = list(OVERRIDE_FIELDS)
    existing: list[dict[str, str]] = []
    if path.is_file():
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames or columns
            existing = list(reader)
    unknown = set(row) - set(columns)
    if unknown:
        raise ManualEntryError(
            f"overrides.csv has no column for: {', '.join(sorted(unknown))}"
        )
    for old in existing:
        if old.get("uid") == uid and all(
            (old.get(k) or "") == v for k, v in row.items() if k != "note"
        ):
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.is_file()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if is_new:
            writer.writeheader()
        writer.writerow({c: row.get(c, "") for c in columns})
    return True


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

    The CSV is the durable copy. Scraped rows can be rebuilt by running
    again; these cannot, and nothing under data/ is in git, so the
    directory needs its own backup.
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
    # Follow the header the file already has. Some were written while
    # `name` was still a column, and appending MANUAL_FIELDS to one of
    # those shifts every value a column left — the street lands in the
    # name, the postal in the state. load_manual_brands reads by header
    # too, so a shifted row is silently wrong rather than rejected.
    columns = list(MANUAL_FIELDS)
    if not is_new:
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), None)
        if header:
            columns = header
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow({k: record.get(k, "") for k in columns})
    return path


_MERGEABLE = (
    "street", "city", "state", "postal", "status", "status_note",
    "lat", "lon", "phone", "hours", "source_url",
)


def _digits(value: str | None) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def _find_target(
    entry: Location, raw: RawLocation, locations: dict[str, Location]
) -> str | None:
    """The scraped row a manual entry is correcting, if there is one.

    The uid is a hash of the whole address, so an entry that fixes a wrong
    address cannot match on it — that is the whole point of the entry.
    The house number and state survive a correction, since what gets
    rewritten is how a street is spelled and which city it claims, not
    which building it is. Phone is the last resort, for when the house
    number itself was mistyped. Each is used only when it identifies
    exactly one row.
    """
    if entry.uid in locations:
        return entry.uid

    candidates: list[str] = []
    wanted_key = address_key(raw.brand, raw.street, raw.state)
    if wanted_key is not None:
        candidates = [
            uid for uid, loc in locations.items()
            if address_key(loc.brand, loc.street, loc.state) == wanted_key
        ]
    if len(candidates) != 1 and _digits(raw.phone):
        wanted_phone = _digits(raw.phone)
        candidates = [
            uid for uid, loc in locations.items()
            if loc.brand == raw.brand and _digits(loc.phone) == wanted_phone
        ]
    return candidates[0] if len(candidates) == 1 else None


def apply_manual_entries(
    locations: dict[str, Location], manual_rows: list[RawLocation], now_iso: str
) -> None:
    """Merge manual entries over the scraped rows, in place.

    An entry supplies corrections, not a replacement row: whatever it
    states wins, and every field it leaves blank keeps the scraped value.
    That way fixing a mistyped street does not discard the coordinates,
    hours or phone the scraper collected for the same store.
    """
    for raw in manual_rows:
        entry = to_location(raw, now_iso, is_manual=True)
        target_uid = _find_target(entry, raw, locations)

        if target_uid is None:
            locations[entry.uid] = entry
            continue

        merged = locations.pop(target_uid)
        supplied = {
            field: getattr(raw, field)
            for field in _MERGEABLE
            if (getattr(raw, field) or "") != ""
        }
        for field, value in supplied.items():
            setattr(merged, field, getattr(entry, field))
        if "lat" in supplied or "lon" in supplied:
            merged.geocode_source = "manual"
        merged.is_manual = True
        merged.last_seen = now_iso
        # The address may have changed, which re-keys the row.
        merged.uid = entry.uid
        if target_uid != entry.uid:
            log.info(
                "manual entry corrects %s -> %s (%s)",
                target_uid, entry.uid, ", ".join(sorted(supplied)),
            )
        locations[entry.uid] = merged
