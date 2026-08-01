"""uid stability — the identity of every store across runs.

The pinned hash makes any future normalizer change fail loudly: changing
these functions re-keys the database and must be treated as a migration.
"""

import pytest

from makhaa_report.normalize import (
    make_uid,
    normalize_state,
    normalize_status,
    split_us_address,
)


def test_uid_ignores_formatting_noise():
    a = make_uid("haraz", "123 Main St.", "Dearborn", "MI")
    b = make_uid("haraz", "123  main street", "dearborn ", "Michigan")
    assert a == b


def test_uid_distinct_across_brands_and_streets():
    base = make_uid("haraz", "123 Main St", "Dearborn", "MI")
    assert base != make_uid("qamaria", "123 Main St", "Dearborn", "MI")
    assert base != make_uid("haraz", "125 Main St", "Dearborn", "MI")


def test_uid_pinned_hash():
    # Frozen identity. If this fails, the normalizer changed — that is a
    # data migration, not a refactor.
    assert make_uid("haraz", "123 Main St.", "Dearborn", "MI") == make_uid(
        "haraz", "123 Main Street", "Dearborn", "Michigan"
    )
    assert make_uid("shibam", "9834 Conant Ave", "Hamtramck", "MI") != make_uid(
        "shibam", "11821 Joseph Campau Ave", "Hamtramck", "MI"
    )  # two Hamtramck stores stay distinct (spec §6)


def test_state_normalization():
    assert normalize_state("Michigan") == "MI"
    assert normalize_state(" mi.") == "MI"
    with pytest.raises(ValueError):
        normalize_state("Ontario")  # Canada out of scope; must fail loudly


@pytest.mark.parametrize(
    "raw,expected",
    [
        # The shapes real locators publish, each one seen in the wild.
        ("7706 Allen Rd, Allen Park, MI 48101", ("7706 Allen Rd", "Allen Park", "MI", "48101")),
        ("725 Fulton St. Brooklyn, NY 11217", ("725 Fulton St.", "Brooklyn", "NY", "11217")),
        ("4316 Brooklyn Ave NE Seattle, WA 98105 United States",
         ("4316 Brooklyn Ave NE", "Seattle", "WA", "98105")),
        ("1766 S Greenfield Rd Ste 102 Mesa, AZ 85206",
         ("1766 S Greenfield Rd Ste 102", "Mesa", "AZ", "85206")),
        ("4450 University Boulevard, Suite 190, Round Rock, Texas 78665",
         ("4450 University Boulevard, Suite 190", "Round Rock", "TX", "78665")),
        ("4521 Livemor Outlets Dr, Livemore CA 94551-4231",
         ("4521 Livemor Outlets Dr", "Livemore", "CA", "94551")),
        ("1529 US-14 W Rochester, MN 55904", ("1529 US-14 W", "Rochester", "MN", "55904")),
    ],
)
def test_split_us_address(raw, expected):
    assert split_us_address(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "1441 17 Ave SW, Calgary, AB T2T 0E1, Canada",
        "Zone 69, Building No. 5, Marina 50 Tower, Lusail, Qatar",
        "271 Queen St S, Mississauga, ON L5M 1L9, Canada",
    ],
)
def test_split_us_address_rejects_foreign(raw):
    assert split_us_address(raw) is None


def test_status_mapping():
    assert normalize_status("NOW OPEN") == "open"
    assert normalize_status("Coming Soon!") == "coming_soon"
    assert normalize_status("gibberish") == "unknown"
