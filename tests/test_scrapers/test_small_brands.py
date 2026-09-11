"""The smaller brands: one or two stores each, every site built
differently. Each test pins the quirk that made its scraper necessary.
"""

import pytest

from makhaa_report.scrapers.multi_page import scrape_original_mocha
from makhaa_report.scrapers.single_page import (
    scrape_biladi,
    scrape_house_of_mokhah,
    scrape_mochabox,
    scrape_queen,
    scrape_socotra,
)

CASES = [
    ("socotra", scrape_socotra, 1, "3130 Packard St", "Ann Arbor", "MI", "48108"),
    ("queen", scrape_queen, 1, "4753 N. Broadway", "Chicago", "IL", "60640"),
    ("biladi", scrape_biladi, 1, "1185 Sweet Home Rd", "Buffalo", "NY", "14226"),
    ("house_of_mokhah", scrape_house_of_mokhah, 1, "137 North Main Street", "Manteca", "CA", "95336"),
    ("mochabox", scrape_mochabox, 1, "1050 Haywood Rd", "Asheville", "NC", None),
]


@pytest.mark.parametrize("slug,scrape,count,street,city,state,postal", CASES)
def test_small_brand_parses_its_store(
    fixture_fetch, slug, scrape, count, street, city, state, postal
):
    rows = scrape(fixture_fetch(slug))

    assert len(rows) == count

    store = next(r for r in rows if r.street == street)
    assert (store.city, store.state, store.postal) == (city, state, postal)
    assert store.brand == slug


def test_mochabox_drops_its_six_digit_postcode(fixture_fetch):
    rows = scrape_mochabox(fixture_fetch("mochabox"))

    # The site publishes "Asheville, NC 208806". Truncating that to a
    # five-digit ZIP would invent a plausible-looking wrong postcode.
    assert rows[0].postal is None


def test_original_mocha_finds_store_pages_by_slug(fixture_fetch):
    rows = scrape_original_mocha(fixture_fetch("original_mocha"))

    assert len(rows) == 2
    assert {r.city for r in rows} == {"Murphy", "Tinley Park"}
    # Each store's own page is its provenance, not the home page.
    assert all(r.source_url.rstrip("/").endswith(r.city.lower().replace(" ", "-") + {
        "Murphy": "-texas", "Tinley Park": "-illinois"}[r.city]) for r in rows)
