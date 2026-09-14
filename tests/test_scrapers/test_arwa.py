"""Offline parse check against a saved locator page.

When Arwa redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.arwa import Arwa


def test_arwa_parses_sections_with_coordinates(fixture_fetch):
    rows = Arwa.scrape(fixture_fetch("arwa"))

    assert len(rows) == 12

    # Every store embeds a map, so none of these need geocoding.
    assert all(r.lat is not None and r.lon is not None for r in rows)

    richardson = next(r for r in rows if r.city == "Richardson")
    assert richardson.street == "888 S Greenville Ave Suite 223"
    assert richardson.postal == "75081"
    assert richardson.phone == "(214) 782-9749"
    # Embed URLs put longitude in !2d and latitude in !3d; swapping them
    # would drop every store into the Indian Ocean.
    assert (round(richardson.lat, 3), round(richardson.lon, 3)) == (32.938, -96.737)


def test_arwa_handles_a_spelled_out_state(fixture_fetch):
    rows = Arwa.scrape(fixture_fetch("arwa"))

    sunnyvale = next(r for r in rows if r.city == "Sunnyvale")
    assert sunnyvale.state == "CA"
