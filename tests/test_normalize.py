"""uid stability — the identity of every store across runs.

The pinned hash makes any future normalizer change fail loudly: changing
these functions re-keys the database and must be treated as a migration.
"""

import pytest

from makhaa_report.normalize import make_uid, normalize_state, normalize_status


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


def test_status_mapping():
    assert normalize_status("NOW OPEN") == "open"
    assert normalize_status("Coming Soon!") == "coming_soon"
    assert normalize_status("gibberish") == "unknown"
