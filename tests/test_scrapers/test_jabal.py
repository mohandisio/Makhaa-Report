"""Offline parse check against a saved locator page.

When Jabal redesigns its locator: re-save the fixture, fix the scraper,
and update the expectations here.
"""

from makhaa_report.scrapers.brands.jabal import Jabal


def test_jabal_parses_open_and_announced_stores(fixture_fetch):
    rows = Jabal.scrape(fixture_fetch("jabal"))

    assert len(rows) == 6

    dearborn = next(r for r in rows if r.city == "Dearborn")
    assert dearborn.street == "1031 Mason St"
    assert dearborn.state == "MI"
    assert dearborn.postal == "48124"
    assert dearborn.status == "open"

    # Toledo has a full street address and is trading ("Soft Opening"
    # means open, not announced); Lombard's "Coming Summer 2026" is the
    # only wording that marks a row coming_soon.
    assert sum(r.status == "coming_soon" for r in rows) == 1
    toledo = next(r for r in rows if r.city == "Toledo")
    assert toledo.status == "open"
    lombard = next(r for r in rows if r.city == "Lombard")
    assert lombard.status == "coming_soon"


def test_jabal_excludes_the_canadian_stores(fixture_fetch):
    rows = Jabal.scrape(fixture_fetch("jabal"))

    # Mississauga, Vancouver and London fall out of the US address parse;
    # no special case needed.
    assert not any(r.city in ("Mississauga", "Vancouver", "London") for r in rows)
    assert all(r.state != "ON" for r in rows)


def test_jabal_skips_cities_announced_without_a_street(fixture_fetch):
    rows = Jabal.scrape(fixture_fetch("jabal"))

    # Tampa, Columbus, Dublin, Duluth, Lower Manhattan, North Olmsted,
    # Tustin, Philadelphia, New Haven, Long Island and Houston are only
    # "City, ST" with no street, so they cannot be identified as stores.
    announced_cities = {
        "Tampa", "Columbus", "Dublin", "Duluth", "Lower Manhattan",
        "North Olmsted", "Tustin", "Philadelphia", "New Haven",
        "Long Island", "Houston",
    }
    assert not any(r.city in announced_cities for r in rows)


def test_jabal_skips_streetless_teasers_without_warning(fixture_fetch, caplog):
    with caplog.at_level("WARNING", logger="makhaa"):
        rows = Jabal.scrape(fixture_fetch("jabal"))

    assert len(rows) == 6
    # City-only teasers are announcements by design, not broken
    # addresses, so they're filtered out before add() and never warn.
    assert "Tampa" not in caplog.text
    assert "Columbus" not in caplog.text

    # A real address that fails to parse (the Canadian store) still
    # warns — the class stays non-quiet.
    assert "Mississauga" in caplog.text
