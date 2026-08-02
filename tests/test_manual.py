"""Manual entry: the path for brands with no scrapable locator."""

import pytest

from makhaa_report import manual
from makhaa_report.manual import ManualEntryError, append_entry, parse_entry


def test_parse_entry_accepts_key_value_and_json():
    pairs = parse_entry(["brand=mohka_house", "city=Oakland", "state=CA"])
    assert pairs == {"brand": "mohka_house", "city": "Oakland", "state": "CA"}

    blob = parse_entry(['{"brand": "mohka_house", "city": "Oakland"}'])
    assert blob == {"brand": "mohka_house", "city": "Oakland"}


def test_append_entry_writes_a_loadable_row(tmp_path):
    record = {
        "brand": "mohka_house",
        "street": "1 Example St",
        "city": "Oakland",
        "state": "CA",
    }
    path = append_entry(record, manual_dir=tmp_path)
    assert path.name == "mohka_house.csv"

    rows = manual.load_manual_brands(tmp_path)
    assert len(rows) == 1
    assert rows[0].brand == "mohka_house"
    assert rows[0].street == "1 Example St"

    # A second entry appends rather than replacing the file.
    append_entry({**record, "street": "2 Example St"}, manual_dir=tmp_path)
    assert len(manual.load_manual_brands(tmp_path)) == 2


@pytest.mark.parametrize(
    "record,message",
    [
        ({"brand": "mohka_house", "city": "Oakland", "state": "CA"}, "street"),
        ({"brand": "mohka_house", "street": "1 Example St"}, "city and state"),
        ({"street": "1 Example St", "city": "Oakland", "state": "CA"}, "brand is required"),
        (
            {"brand": "not_a_brand", "street": "1 St", "city": "Oakland", "state": "CA"},
            "unknown brand",
        ),
        (
            {"brand": "mohka_house", "street": "1 St", "city": "X", "state": "CA", "zip": "9"},
            "unknown field",
        ),
    ],
)
def test_append_entry_rejects_bad_records(tmp_path, record, message):
    with pytest.raises(ManualEntryError, match=message):
        append_entry(record, manual_dir=tmp_path)
