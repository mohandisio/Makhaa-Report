"""Offline parse checks against saved Shibam locator payloads.

When the brand redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.shibam import Shibam


def test_shibam_parses_cards_from_rendered_html(fixture_fetch):
    rows = Shibam.scrape(fixture_fetch("shibam"))

    assert len(rows) == 20

    dearborn = next(r for r in rows if r.street == "5461 Schaefer Rd")
    assert dearborn.city == "Dearborn"
    assert dearborn.state == "MI"
    assert dearborn.postal == "48126"
    assert dearborn.phone == "+13136331624"
    assert dearborn.hours.startswith("Sun – Thu:")


def test_shibam_reads_status_from_prose(fixture_fetch):
    rows = Shibam.scrape(fixture_fetch("shibam"))

    # Announced with wording, not a marker: "Soft opening coming soon!!"
    ann_arbor = next(r for r in rows if r.city == "Ann Arbor")
    assert ann_arbor.status == "coming_soon"
    assert sum(r.status == "coming_soon" for r in rows) == 1


def test_shibam_trusts_the_address_over_the_heading(fixture_fetch):
    rows = Shibam.scrape(fixture_fetch("shibam"))

    # Headings are regional labels: this card is headed "CLEVELAND, OH"
    # but the address is the truth.
    north_olmsted = next(r for r in rows if r.street == "26745 Brookpark Ext")
    assert north_olmsted.city == "North Olmsted"
