from makhaa_report.registry import BRANDS
from makhaa_report.scrapers import SCRAPERS


def test_every_scraped_brand_has_a_scraper_and_nothing_else():
    registry_scraped = {b.slug for b in BRANDS if b.method == "scrape"}
    registered_scrapers = set(SCRAPERS.keys())

    assert registry_scraped == registered_scrapers
