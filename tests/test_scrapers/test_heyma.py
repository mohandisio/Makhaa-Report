"""Offline parse check against a saved locator page.

When Heyma redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.heyma import Heyma


def test_heyma_reads_address_and_coordinates_from_the_map_link(fixture_fetch):
    rows = Heyma.scrape(fixture_fetch("heyma"))

    assert len(rows) == 2
    assert all(r.lat is not None for r in rows)

    berkeley = next(r for r in rows if r.city == "Berkeley")
    assert berkeley.street == "1122 University Avenue"
    # Published with a ZIP+4.
    assert berkeley.postal == "94702"
    assert (berkeley.lat, berkeley.lon) == (37.8690241, -122.2909521)

    # The tel: links share the same markup and must not become stores.
    assert all(r.street for r in rows)
