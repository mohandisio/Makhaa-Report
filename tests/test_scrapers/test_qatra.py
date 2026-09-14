"""Offline parse check against a saved locator page.

When Qatra redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.qatra import Qatra


def test_qatra_deduplicates_addresses_repeated_across_the_page(fixture_fetch):
    rows = Qatra.scrape(fixture_fetch("qatra"))

    assert len(rows) == 3

    addresses = [(r.street, r.city) for r in rows]
    assert len(addresses) == len(set(addresses))

    # Published both as "Stadium Dr B, Clemmons" and "Stadium Dr B
    # Clemmons"; the suite letter belongs to the street either way.
    clemmons = next(r for r in rows if r.city == "Clemmons")
    assert clemmons.street == "6311 Stadium Dr B"

    # Two San Antonio stores stay distinct.
    assert sum(r.city == "San Antonio" for r in rows) == 2


def test_qatra_takes_coordinates_from_the_schema_block(fixture_fetch):
    rows = Qatra.scrape(fixture_fetch("qatra"))

    louis_pasteur = next(r for r in rows if r.street.startswith("7302"))
    assert (louis_pasteur.lat, louis_pasteur.lon) == (29.5021063, -98.5756263)
    assert sum(r.lat is None for r in rows) == 2
