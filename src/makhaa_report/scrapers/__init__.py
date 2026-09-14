"""Scraper registry: brand slug -> scrape function.

Most brands live under `brands/`, one module each; a few still share a
module grouped by site type (single_page). Brands absent from this dict
are reported as "no scraper" and skipped; the pipeline still runs on the
manual-entry CSVs.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation
from .brands.haraz import Haraz
from .brands.biladi import Biladi
from .brands.house_of_mokhah import HouseOfMokhah
from .brands.mochabox import Mochabox
from .brands.original_mocha import OriginalMocha
from .brands.port import Port
from .brands.qahwah_house import QahwahHouse
from .brands.qamaria import Qamaria
from .brands.queen import Queen
from .brands.qishr import Qishr
from .brands.shibam import Shibam
from .brands.socotra import Socotra
from .single_page import (
    scrape_arwa,
    scrape_caffeena,
    scrape_delah,
    scrape_heyma,
    scrape_matari,
    scrape_moka_and_co,
    scrape_mokafe,
    scrape_qatra,
    scrape_sanaa_cafe,
)

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {
    "socotra": Socotra.scrape,
    "queen": Queen.scrape,
    "original_mocha": OriginalMocha.scrape,
    "mochabox": Mochabox.scrape,
    "house_of_mokhah": HouseOfMokhah.scrape,
    "biladi": Biladi.scrape,
    "arwa": scrape_arwa,
    "caffeena": scrape_caffeena,
    "delah": scrape_delah,
    "haraz": Haraz.scrape,
    "heyma": scrape_heyma,
    "matari": scrape_matari,
    "moka_and_co": scrape_moka_and_co,
    "mokafe": scrape_mokafe,
    "qahwah_house": QahwahHouse.scrape,
    "qamaria": Qamaria.scrape,
    "port": Port.scrape,
    "qatra": scrape_qatra,
    "qishr": Qishr.scrape,
    "sanaa_cafe": scrape_sanaa_cafe,
    "shibam": Shibam.scrape,
}
