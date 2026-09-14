"""Offline parse check against a saved locator page.

When Matari redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.matari import Matari


def test_matari_parses_open_and_announced_stores(fixture_fetch):
    rows = Matari.scrape(fixture_fetch("matari"))

    assert len(rows) == 11

    skokie = next(r for r in rows if r.city == "Skokie")
    assert skokie.street == "8800 Gross Point Rd"
    assert skokie.postal == "60077"
    assert skokie.phone == "+18477793141"
    assert skokie.status == "open"

    assert sum(r.status == "coming_soon" for r in rows) == 3


def test_matari_excludes_the_canadian_store(fixture_fetch):
    rows = Matari.scrape(fixture_fetch("matari"))

    # Mississauga falls out of the US address parse; no special case.
    assert not any(r.city == "Mississauga" for r in rows)
    assert all(r.state != "ON" for r in rows)


def test_matari_skips_markets_announced_without_an_address(fixture_fetch):
    rows = Matari.scrape(fixture_fetch("matari"))

    # "Dallas, TX", "Houston, TX" and "Atlanta, GA" carry no street, so
    # they cannot be identified as stores and are dropped.
    assert not any(r.state in ("TX", "GA") for r in rows)
