"""Paths and crawl settings."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "makhaa.sqlite"
MANUAL_DIR = DATA_DIR / "manual"
OVERRIDES_PATH = DATA_DIR / "overrides.csv"
EXPORT_DIR = DATA_DIR / "exports"

USER_AGENT = (
    "makhaa-report/0.1 (Yemeni coffee chain census; "
    "contact: erasers.breezes_0m@icloud.com)"
)
RATE_DELAY_S = 1.0
TIMEOUT_S = 30.0
