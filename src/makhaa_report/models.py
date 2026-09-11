"""Dataclasses and vocabulary shared across the pipeline."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

STATUSES = ("coming_soon", "open", "relocating", "closed_permanently", "unknown")
GEOCODE_SOURCES = ("locator", "census", "nominatim", "manual")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RawLocation:
    """Scraper or manual-CSV output, pre-normalization."""

    brand: str
    street: str
    city: str
    state: str
    postal: str | None = None
    status: str = "open"
    status_note: str = ""
    lat: float | None = None  # only if the locator itself publishes coordinates
    lon: float | None = None
    phone: str | None = None
    hours: str | None = None  # verbatim, never parsed
    source_url: str = ""
    fragment: str = ""  # verbatim scraped snippet, lands in snapshots


@dataclass
class Location:
    """Normalized row mirroring the locations table."""

    uid: str
    brand: str
    street: str
    city: str
    state: str
    postal: str | None
    lat: float | None
    lon: float | None
    geocode_source: str | None  # one of GEOCODE_SOURCES
    geocode_flagged: bool
    status: str
    status_note: str
    phone: str | None
    hours: str | None
    source_url: str
    is_manual: bool
    first_seen: str
    last_seen: str
    # When the store opened, as YYYY-MM. Sourced from permit and licence
    # records, never from a scrape, so a re-scrape must leave it alone —
    # that is why these are absent from db._MUTABLE. Accurate to about a
    # month: the underlying records date a permit, not a first coffee.
    opened_date: str | None = None
    opened_confidence: str | None = None  # confirmed | high | medium | low
    opened_source: str | None = None
    fragment: str = ""  # transient; persisted only via snapshots


@dataclass(frozen=True)
class Brand:
    slug: str
    display_name: str
    locator_url: str
    method: Literal["scrape", "manual"]
    franchises: bool = False
    hq: str = ""
    alt_domains: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Exclusion:
    """Known lookalike domains that must never enter the registry."""

    domain: str
    reason: str
    related_brand: str | None = None


BrandOutcome = Literal["ok", "error", "no_scraper"]


@dataclass(frozen=True)
class BrandResult:
    """What happened to one brand during a run."""

    slug: str
    outcome: BrandOutcome
    rows: int = 0
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


@dataclass
class RunStats:
    run_id: int
    results: list[BrandResult] = field(default_factory=list)
    total_rows: int = 0

    @property
    def brands_succeeded(self) -> list[str]:
        return [r.slug for r in self.results if r.ok]

    @property
    def brands_failed(self) -> list[str]:
        return [r.slug for r in self.results if r.outcome == "error"]
