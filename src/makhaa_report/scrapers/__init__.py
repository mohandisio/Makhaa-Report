"""Scraper registry: brand slug -> scrape function.

Brand scrapers are grouped by site type (json_sites, single_page,
multi_page). Brands absent from this dict are reported as "no scraper"
and skipped; the pipeline still runs on the hand-maintained CSVs.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation
from .json_sites import scrape_qahwah_house, scrape_qamaria, scrape_shibam
from .multi_page import scrape_haraz
from .single_page import (
    scrape_arwa,
    scrape_caffeena,
    scrape_delah,
    scrape_heyma,
    scrape_matari,
    scrape_moka_and_co,
    scrape_qatra,
)

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {
    "arwa": scrape_arwa,
    "caffeena": scrape_caffeena,
    "delah": scrape_delah,
    "haraz": scrape_haraz,
    "heyma": scrape_heyma,
    "matari": scrape_matari,
    "moka_and_co": scrape_moka_and_co,
    "qahwah_house": scrape_qahwah_house,
    "qamaria": scrape_qamaria,
    "qatra": scrape_qatra,
    "shibam": scrape_shibam,
}
