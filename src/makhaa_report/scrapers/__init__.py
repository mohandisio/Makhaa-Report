"""Scraper registry: brand slug -> scrape function.

Brand scrapers are grouped by site type (json_sites, single_page,
multi_page). Brands absent from this dict are reported as "no scraper"
and skipped; the pipeline still runs on the manual-entry CSVs.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation
from .brands.qahwah_house import QahwahHouse
from .brands.qamaria import Qamaria
from .json_sites import scrape_shibam
from .multi_page import scrape_haraz, scrape_original_mocha
from .spa_bundle import scrape_port, scrape_qishr
from .single_page import (
    scrape_arwa,
    scrape_biladi,
    scrape_caffeena,
    scrape_delah,
    scrape_heyma,
    scrape_house_of_mokhah,
    scrape_matari,
    scrape_mochabox,
    scrape_moka_and_co,
    scrape_mokafe,
    scrape_qatra,
    scrape_queen,
    scrape_sanaa_cafe,
    scrape_socotra,
)

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {
    "socotra": scrape_socotra,
    "queen": scrape_queen,
    "original_mocha": scrape_original_mocha,
    "mochabox": scrape_mochabox,
    "house_of_mokhah": scrape_house_of_mokhah,
    "biladi": scrape_biladi,
    "arwa": scrape_arwa,
    "caffeena": scrape_caffeena,
    "delah": scrape_delah,
    "haraz": scrape_haraz,
    "heyma": scrape_heyma,
    "matari": scrape_matari,
    "moka_and_co": scrape_moka_and_co,
    "mokafe": scrape_mokafe,
    "qahwah_house": QahwahHouse.scrape,
    "qamaria": Qamaria.scrape,
    "port": scrape_port,
    "qatra": scrape_qatra,
    "qishr": scrape_qishr,
    "sanaa_cafe": scrape_sanaa_cafe,
    "shibam": scrape_shibam,
}
