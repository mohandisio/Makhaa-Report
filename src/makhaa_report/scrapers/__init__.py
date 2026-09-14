"""Scraper registry: brand slug -> scrape function.

One module per brand lives under `brands/`, named by its registry slug,
each holding one `Scraper` subclass. SCRAPERS is built from those
classes. Brands absent from this dict are reported as "no scraper" and
skipped; the pipeline still runs on the manual-entry CSVs.
"""

from typing import Callable

from ..fetch import Fetch
from ..models import RawLocation
from .brands.albunn import Albunn
from .brands.arwa import Arwa
from .brands.bayt_almocha import BaytAlmocha
from .brands.biladi import Biladi
from .brands.caffeena import Caffeena
from .brands.delah import Delah
from .brands.haraz import Haraz
from .brands.heyma import Heyma
from .brands.house_of_mokhah import HouseOfMokhah
from .brands.jabal import Jabal
from .brands.matari import Matari
from .brands.mocha_point import MochaPoint
from .brands.mochabox import Mochabox
from .brands.moka_and_co import MokaAndCo
from .brands.mokafe import Mokafe
from .brands.moqana import Moqana
from .brands.original_mocha import OriginalMocha
from .brands.port import Port
from .brands.qahwah_house import QahwahHouse
from .brands.qahwah_valley import QahwahValley
from .brands.qamaria import Qamaria
from .brands.qatra import Qatra
from .brands.qishr import Qishr
from .brands.queen import Queen
from .brands.raha import Raha
from .brands.sanaa_cafe import SanaaCafe
from .brands.shibam import Shibam
from .brands.socotra import Socotra
from .brands.yafa import Yafa

ScrapeFn = Callable[[Fetch], list[RawLocation]]

SCRAPERS: dict[str, ScrapeFn] = {s.slug: s.scrape for s in (
    Albunn,
    Arwa,
    BaytAlmocha,
    Biladi,
    Caffeena,
    Delah,
    Haraz,
    Heyma,
    HouseOfMokhah,
    Jabal,
    Matari,
    MochaPoint,
    Mochabox,
    MokaAndCo,
    Mokafe,
    Moqana,
    OriginalMocha,
    Port,
    QahwahHouse,
    QahwahValley,
    Qamaria,
    Qatra,
    Qishr,
    Queen,
    Raha,
    SanaaCafe,
    Shibam,
    Socotra,
    Yafa,
)}
