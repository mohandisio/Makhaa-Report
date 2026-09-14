"""Offline parse checks against saved locator pages.

When a brand redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.single_page import (
    scrape_caffeena,
    scrape_delah,
    scrape_heyma,
    scrape_moka_and_co,
    scrape_mokafe,
    scrape_qatra,
    scrape_sanaa_cafe,
)


def test_moka_parses_open_and_coming_soon(fixture_fetch):
    rows = scrape_moka_and_co(fixture_fetch("moka_and_co"))

    assert len(rows) == 41
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


def test_delah_reads_the_icon_list(fixture_fetch):
    rows = scrape_delah(fixture_fetch("delah"))

    assert len(rows) == 7

    # Phone, email and social entries share the same markup and must not
    # become stores.
    assert all(r.street for r in rows)

    naperville = next(r for r in rows if r.city == "Naperville")
    assert naperville.street == "1336 Illinois Rte 59"
    assert naperville.state == "IL"

    # Two San Francisco stores stay distinct.
    assert sum(r.city == "San Francisco" for r in rows) == 2


def test_delah_takes_coordinates_only_from_place_links(fixture_fetch):
    rows = scrape_delah(fixture_fetch("delah"))

    san_diego = next(r for r in rows if r.city == "San Diego")
    assert san_diego.lat == 32.7494607

    # The rest link to shortened g.co URLs, which carry no coordinates.
    assert sum(r.lat is None for r in rows) == 6


def test_qatra_deduplicates_addresses_repeated_across_the_page(fixture_fetch):
    rows = scrape_qatra(fixture_fetch("qatra"))

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
    rows = scrape_qatra(fixture_fetch("qatra"))

    louis_pasteur = next(r for r in rows if r.street.startswith("7302"))
    assert (louis_pasteur.lat, louis_pasteur.lon) == (29.5021063, -98.5756263)
    assert sum(r.lat is None for r in rows) == 2


def test_heyma_reads_address_and_coordinates_from_the_map_link(fixture_fetch):
    rows = scrape_heyma(fixture_fetch("heyma"))

    assert len(rows) == 2
    assert all(r.lat is not None for r in rows)

    berkeley = next(r for r in rows if r.city == "Berkeley")
    assert berkeley.street == "1122 University Avenue"
    # Published with a ZIP+4.
    assert berkeley.postal == "94702"
    assert (berkeley.lat, berkeley.lon) == (37.8690241, -122.2909521)

    # The tel: links share the same markup and must not become stores.
    assert all(r.street for r in rows)


def test_caffeena_reads_status_from_the_section_heading(fixture_fetch):
    rows = scrape_caffeena(fixture_fetch("caffeena"))

    assert len(rows) == 7

    # One trading store, the rest announced under "Coming Soon Locations".
    open_rows = [r for r in rows if r.status == "open"]
    assert len(open_rows) == 1
    assert open_rows[0].street == "3101 Griffith St"
    assert sum(r.status == "coming_soon" for r in rows) == 6

    # Both Charlotte stores are listed, one per section.
    charlotte = [r for r in rows if r.city == "Charlotte"]
    assert {r.status for r in charlotte} == {"open", "coming_soon"}


def test_mokafe_splits_name_from_address(fixture_fetch):
    rows = scrape_mokafe(fixture_fetch("mokafe"))

    assert len(rows) == 10

    paterson = next(r for r in rows if r.city == "Paterson")
    assert paterson.street == "1022 Main St"

    # One store carries no colon, so the bullet separates the label from
    # the address instead.
    melville = next(r for r in rows if r.city == "Melville")
    assert melville.street == "606 Broadhollow Rd"

    # Two Brooklyn stores share Manhattan Ave; both must survive.
    manhattan_ave = [r for r in rows if r.street.endswith("Manhattan Ave")]
    assert len(manhattan_ave) == 2


def test_sanaa_reads_the_current_location_cards(fixture_fetch):
    rows = scrape_sanaa_cafe(fixture_fetch("sanaa_cafe"))

    assert len(rows) == 8

    flagship = next(r for r in rows if r.city == "San Francisco")
    assert flagship.street == "199 New Montgomery St"
    assert flagship.phone == "+1 (415) 932-6935"
    assert flagship.hours == "Mon-Sun: 6:00 AM - 12:00 AM"

    # The cards carry Sacramento's real address; the older blurb layout
    # still on the page gives it Oakland Broadway's, and is ignored.
    sacramento = next(r for r in rows if r.city == "Sacramento")
    assert sacramento.street == "901 K St"
    assert sum(r.street == "801 Broadway" for r in rows) == 1


def test_sanaa_handles_a_run_together_zip_plus_four(fixture_fetch):
    rows = scrape_sanaa_cafe(fixture_fetch("sanaa_cafe"))

    # Published as "LAKE FOREST CA, 926301791, US".
    lake_forest = next(r for r in rows if r.city.casefold() == "lake forest")
    assert lake_forest.postal == "92630"
