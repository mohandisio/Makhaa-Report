"""The smaller brands: one or two stores each, every site built
differently. Each test pins the quirk that made its scraper necessary.
"""

import pytest

from makhaa_report.scrapers.single_page import (
    scrape_mochabox,
    scrape_socotra,
)

CASES = [
    ("socotra", scrape_socotra, 1, "3130 Packard St", "Ann Arbor", "MI", "48108"),
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
