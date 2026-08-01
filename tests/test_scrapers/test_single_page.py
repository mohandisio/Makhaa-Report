"""Offline parse checks against saved locator pages.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.registry import get_brand
from makhaa_report.scrapers.single_page import scrape_arwa, scrape_moka_and_co


def test_moka_parses_open_and_coming_soon(fixture_fetch):
    rows = scrape_moka_and_co(fixture_fetch("moka_and_co"))

    low, high = get_brand("moka_and_co").band
    assert low <= len(rows) <= high
    assert {r.status for r in rows} == {"open", "coming_soon"}

    dearborn = next(r for r in rows if r.city == "Dearborn")
    assert dearborn.street == "12921 Michigan Ave"
    assert dearborn.state == "MI"
    assert dearborn.status == "open"
    assert dearborn.source_url == "https://mokanco.com/dearborn/"

    somerville = next(r for r in rows if r.city == "Somerville")
    assert somerville.status == "coming_soon"


def test_moka_deduplicates_and_skips_hq_block(fixture_fetch):
    rows = scrape_moka_and_co(fixture_fetch("moka_and_co"))

    # A store listed under two groupings must not be counted twice.
    addresses = [(r.street, r.city) for r in rows]
    assert len(addresses) == len(set(addresses))

    # The mobile menu's corporate contact block carries HQ addresses that
    # are not stores; reading only post blocks keeps them out.
    assert not any(r.city == "Melvindale" for r in rows)


def test_arwa_parses_sections_with_coordinates(fixture_fetch):
    rows = scrape_arwa(fixture_fetch("arwa"))

    low, high = get_brand("arwa").band
    assert low <= len(rows) <= high

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
    rows = scrape_arwa(fixture_fetch("arwa"))

    sunnyvale = next(r for r in rows if r.city == "Sunnyvale")
    assert sunnyvale.state == "CA"
