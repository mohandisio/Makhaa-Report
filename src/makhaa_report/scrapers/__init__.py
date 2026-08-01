"""Scraper registry: brand slug -> scrape function.

Brand scrapers are grouped by site type (json_sites, single_page,
multi_page). While the dict is empty the pipeline runs on the
hand-maintained CSVs alone.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {}
