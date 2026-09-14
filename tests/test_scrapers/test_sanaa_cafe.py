"""Offline parse check against a saved locator page.

When Sana'a Cafe redesigns its locator: re-save the fixture, fix the
scraper, and update the expectations here.
"""

from makhaa_report.scrapers.brands.sanaa_cafe import SanaaCafe


def test_sanaa_reads_the_grid_and_the_carousel(fixture_fetch):
    rows = SanaaCafe.scrape(fixture_fetch("sanaa_cafe"))

    assert len(rows) == 8

    flagship = next(r for r in rows if r.city == "San Francisco")
    assert flagship.street == "199 New Montgomery St"
    assert flagship.phone == "+1 (415) 932-6935"
    assert flagship.hours == "Mon-Sun: 6:00 AM – 12:00 AM"


def test_sanaa_carousel_only_store_keeps_its_published_spelling(fixture_fetch):
    rows = SanaaCafe.scrape(fixture_fetch("sanaa_cafe"))

    # Elk Grove isn't in the grid at all; the carousel is its only source,
    # crude spelling and all -- the address confirmer canonicalizes it later.
    elk_grove = next(r for r in rows if "stockton" in r.street.casefold())
    assert elk_grove.street == "9135 WEST STOCKTON BOULE"
    assert elk_grove.city.casefold() == "elk grove"

    # The carousel's real address for a grid-omitted store shows up too.
    sacramento = next(r for r in rows if r.city == "Sacramento")
    assert sacramento.street == "901 K St"


def test_sanaa_grid_spelling_wins_over_the_carousel(fixture_fetch):
    rows = SanaaCafe.scrape(fixture_fetch("sanaa_cafe"))

    # Telegraph is in both sections. The grid's own text has no ZIP; the
    # carousel's has one ("94609"), but the grid's spelling is what wins,
    # and the row appears exactly once.
    telegraph = [r for r in rows if r.street == "4770 Telegraph Ave"]
    assert len(telegraph) == 1
    assert telegraph[0].postal is None
    assert not any(r.postal == "94609" for r in rows)
