"""Offline parse check against a saved locator page.

When Moka & Co redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.moka_and_co import MokaAndCo


def test_moka_parses_open_and_coming_soon(fixture_fetch):
    rows = MokaAndCo.scrape(fixture_fetch("moka_and_co"))

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
    rows = MokaAndCo.scrape(fixture_fetch("moka_and_co"))

    # A store listed under two groupings must not be counted twice.
    addresses = [(r.street, r.city) for r in rows]
    assert len(addresses) == len(set(addresses))

    # The mobile menu's corporate contact block carries HQ addresses that
    # are not stores; reading only post blocks keeps them out.
    assert not any(r.city == "Melvindale" for r in rows)
