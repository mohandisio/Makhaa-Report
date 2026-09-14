"""Offline parse check against a saved locator page.

When Raha redesigns its site: re-save the fixture, fix the scraper, and
update the expectations here.
"""

from makhaa_report.scrapers.brands.raha import Raha


def test_raha_dedupes_the_repeated_footer_address(fixture_fetch):
    # The home page repeats its one address in both the "Visit Our Cafe"
    # widget and the site-wide "Contact Info" footer widget; both must
    # collapse into a single store rather than double-counting it.
    rows = Raha.scrape(fixture_fetch("raha"))

    assert len(rows) == 1

    store = rows[0]
    assert store.street == "370 Amherst St"
    assert store.city == "Buffalo"
    assert store.state == "NY"
    assert store.postal == "14207"
    assert store.status == "open"
    assert store.brand == "raha"
