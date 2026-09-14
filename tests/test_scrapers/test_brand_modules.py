"""Every brand module follows the same shape.

One module per brand under `makhaa_report.scrapers.brands`, named by the
brand's registry slug, holding exactly one `Scraper` subclass whose `slug`
matches the module name and whose `scrape` classmethod is what the
registry dispatches to.
"""

import inspect
import pkgutil

from makhaa_report.scrapers import SCRAPERS, brands
from makhaa_report.scrapers.base import Scraper


def _brand_modules():
    return list(pkgutil.iter_modules(brands.__path__))


def test_brands_package_has_at_least_one_module():
    assert _brand_modules(), "expected at least one brand module"


def test_each_brand_module_defines_one_matching_scraper():
    for module_info in _brand_modules():
        module = __import__(
            f"{brands.__name__}.{module_info.name}", fromlist=["_"]
        )

        scraper_classes = [
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, Scraper)
            and obj is not Scraper
            and obj.__module__ == module.__name__
        ]

        assert len(scraper_classes) == 1, (
            f"{module.__name__} must define exactly one Scraper subclass"
        )
        cls = scraper_classes[0]
        assert cls.slug == module_info.name
        # Bound classmethods aren't `is`-identical across attribute
        # accesses, only equal.
        assert SCRAPERS[cls.slug] == cls.scrape
