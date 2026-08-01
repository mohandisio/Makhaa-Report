"""Scraper registry: brand slug -> scrape function.

Brand scrapers are grouped by site type (json_sites, single_page,
multi_page). Brands absent from this dict are reported as "no scraper"
and skipped; the pipeline still runs on the hand-maintained CSVs.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation
from .json_sites import scrape_qamaria
from .multi_page import scrape_haraz
from .single_page import scrape_moka_and_co

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {
    "haraz": scrape_haraz,
    "moka_and_co": scrape_moka_and_co,
    "qamaria": scrape_qamaria,
}
