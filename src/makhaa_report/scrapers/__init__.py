"""Scraper registry: brand slug -> scrape function.

Most brands live under `brands/`, one module each; a few still share a
module grouped by site type (single_page). Brands absent from this dict
are reported as "no scraper" and skipped; the pipeline still runs on the
manual-entry CSVs.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation
from .brands.arwa import Arwa
from .brands.delah import Delah
from .brands.haraz import Haraz
from .brands.biladi import Biladi
from .brands.house_of_mokhah import HouseOfMokhah
from .brands.matari import Matari
from .brands.mochabox import Mochabox
from .brands.moka_and_co import MokaAndCo
from .brands.original_mocha import OriginalMocha
from .brands.port import Port
from .brands.qahwah_house import QahwahHouse
from .brands.qamaria import Qamaria
from .brands.queen import Queen
from .brands.qishr import Qishr
from .brands.sanaa_cafe import SanaaCafe
from .brands.shibam import Shibam
from .brands.socotra import Socotra
from .single_page import (
    scrape_caffeena,
    scrape_heyma,
    scrape_mokafe,
    scrape_qatra,
)

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {
    "socotra": Socotra.scrape,
    "queen": Queen.scrape,
    "original_mocha": OriginalMocha.scrape,
    "mochabox": Mochabox.scrape,
    "house_of_mokhah": HouseOfMokhah.scrape,
    "biladi": Biladi.scrape,
    "arwa": Arwa.scrape,
    "caffeena": scrape_caffeena,
    "delah": Delah.scrape,
    "haraz": Haraz.scrape,
    "heyma": scrape_heyma,
    "matari": Matari.scrape,
    "moka_and_co": MokaAndCo.scrape,
    "mokafe": scrape_mokafe,
    "qahwah_house": QahwahHouse.scrape,
    "qamaria": Qamaria.scrape,
    "port": Port.scrape,
    "qatra": scrape_qatra,
    "qishr": Qishr.scrape,
    "sanaa_cafe": SanaaCafe.scrape,
    "shibam": Shibam.scrape,
}
