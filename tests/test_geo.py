"""Census lookup, offline.

census_batch.csv is a verbatim response from the live service, so the
parser is tested against what Census actually sends rather than what the
documentation describes.
"""

import json
from pathlib import Path

import pytest

from makhaa_report import geo
from makhaa_report.normalize import recase, split_unit

FIXTURE = Path(__file__).parent / "fixtures" / "geo" / "census_batch.csv"


@pytest.fixture
def batch() -> dict[str, geo.Match]:
    return geo.parse_batch(FIXTURE.read_text(encoding="utf-8"))


# --- split_unit ---------------------------------------------------------

@pytest.mark.parametrize("street, expected", [
    ("1561 Lee Rd Ste 102", ("1561 Lee Rd", "Ste 102")),
    ("1700 Camden Rd STE 101", ("1700 Camden Rd", "STE 101")),
    ("414 S Main St suite 100", ("414 S Main St", "suite 100")),
    ("10907 Culebra Rd suit 120", ("10907 Culebra Rd", "suit 120")),
    ("6694 Amador Plaza Rd Suit W", ("6694 Amador Plaza Rd", "Suit W")),
    ("10009 N MacArthur Blvd #101", ("10009 N MacArthur Blvd", "#101")),
    ("3980 Southside Blvd #207-208", ("3980 Southside Blvd", "#207-208")),
    ("2505 S 38th St Suite A100A", ("2505 S 38th St", "Suite A100A")),
    ("12301 W Parmer Ln Unit 206 Bldg 2", ("12301 W Parmer Ln", "Unit 206 Bldg 2")),
    ("4000 North Point Pkwy Suite #900", ("4000 North Point Pkwy", "Suite #900")),
    ("1300 Main Street Unit T", ("1300 Main Street", "Unit T")),
    # The comma belongs to the separator, not to the street.
    ("4100 W Willow Knolls, Suite C2", ("4100 W Willow Knolls", "Suite C2")),
    ("1901 Manhattan Blvd Bldg B, Suite 100", ("1901 Manhattan Blvd", "Bldg B, Suite 100")),
    # A suite written as a bare letter, with no marker to cut on.
    ("6311 Stadium Dr B", ("6311 Stadium Dr", "B")),
    ("8320 University Executive Park Dr B", ("8320 University Executive Park Dr", "B")),
    ("3441 South Blvd C", ("3441 South Blvd", "C")),
    ("1950 Market St b", ("1950 Market St", "b")),
])
def test_split_unit_separates_the_unit(street, expected):
    assert split_unit(street) == expected


@pytest.mark.parametrize("street", [
    "2138 Caton Ave",
    "725 Fulton St.",
    "285 South Broadway, Hicksville",
    # Trailing directionals are part of the street, not suites.
    "1529 US-14 W",
    "3005 Lyndale Ave S",
    "229 E Commonwealth Ave E",
    "3 Little Canada Rd E",
    # The letter IS the street name here; a street keeps a name and a type.
    "123 Avenue A",
])
def test_split_unit_leaves_a_unitless_street_alone(street):
    assert split_unit(street) == (street, "")


def test_split_unit_ignores_a_marker_in_the_street_name():
    # Cutting here would truncate the street to its house number.
    assert split_unit("501 Floor Rd") == ("501 Floor Rd", "")


# --- recase -------------------------------------------------------------

@pytest.mark.parametrize("canonical, original, expected", [
    # A token we already had keeps our spelling, however Census shouts it.
    ("10009 N MACARTHUR BLVD", "10009 N MacArthur Blvd", "10009 N MacArthur Blvd"),
    ("15174 LAGRANGE RD", "15174 LaGrange Rd", "15174 LaGrange Rd"),
    ("9325 JW CLAY BLVD", "9325 JW Clay Blvd.", "9325 JW Clay Blvd"),
    # A street type has one right spelling, so ours does not get to keep
    # shouting it even when the rest of the address is cased normally.
    ("6124 N CANTON CENTER RD", "6124 N. Canton Center RD", "6124 N Canton Center Rd"),
    # A token Census introduced is title-cased.
    ("1737 N ALAFAYA TRL", "1737 N Alafaya Trail", "1737 N Alafaya Trl"),
    ("408 SUNCREST TOWNE CENTRE DR", "408 Suncrest Towne Centre Drive",
     "408 Suncrest Towne Centre Dr"),
    ("SAINT PAUL", "St Paul", "Saint Paul"),
    # Directionals and route prefixes stay capitalised.
    ("17585 NE 67TH CT", "17585 Northeast 67th Court", "17585 NE 67th Ct"),
    ("222 E FM 544", "222 E Farm To Market 544", "222 E FM 544"),
    # An original that shouts carries no casing worth keeping.
    ("LOS ANGELES", "LOS ANGELES", "Los Angeles"),
    ("22621 LAKE FOREST DR", "22621 LAKE FOREST DR", "22621 Lake Forest Dr"),
    ("9135 W STOCKTON BLVD", "9135 WEST STOCKTON BOULE", "9135 W Stockton Blvd"),
])
def test_recase(canonical, original, expected):
    assert recase(canonical, original) == expected


def test_recase_lowers_an_ordinal_rather_than_title_casing_it():
    # title() would give "14Th".
    assert recase("1529 14TH ST NW", "1529 US-14 W") == "1529 14th St NW"


# --- parsing ------------------------------------------------------------

def test_parses_every_row(batch):
    assert len(batch) == 16


def test_exact_match_carries_the_standardized_address(batch):
    m = batch["1"]
    assert (m.matched, m.exact) == (True, True)
    assert (m.street, m.city, m.state, m.postal) == (
        "6124 N CANTON CENTER RD", "CANTON", "MI", "48187"
    )


def test_coordinates_are_read_as_lat_lon_not_lon_lat(batch):
    # Census sends "lon,lat". Reversing them silently puts Michigan in Iraq.
    m = batch["1"]
    assert m.lat == pytest.approx(42.327, abs=1e-3)
    assert m.lon == pytest.approx(-83.488, abs=1e-3)


def test_missing_zip_is_filled_in_by_the_service(batch):
    assert batch["9"].postal == "90028"


def test_non_exact_match_is_reported_as_matched_but_not_exact(batch):
    m = batch["3"]
    assert (m.matched, m.exact) == (True, False)
    # A guess: the real store is on South Broadway in Hicksville. Adopting
    # this would move it to another town, which is why exactness is tracked.
    assert m.city == "ISLAND PARK"


def test_no_match_rows_are_misses(batch):
    for key in ("11", "12", "13", "14", "16"):
        assert batch[key] == geo.MISS


def test_a_unit_in_the_street_downgrades_the_match():
    # Row 15 kept its unit and came back Non_Exact; the same address
    # without one is Exact. This is why split_unit runs before lookup.
    b = geo.parse_batch(FIXTURE.read_text(encoding="utf-8"))
    assert b["15"].matched and not b["15"].exact


# --- request assembly ---------------------------------------------------

def test_csv_has_five_unheaded_columns_and_no_stray_commas():
    body = geo._to_csv([
        geo.Query("a", "285 South Broadway, Hicksville", "Hicksville", "NY", "11801"),
        geo.Query("b", "1561 Lee Rd", "Winter Park", "FL", None),
    ])
    rows = [r for r in body.splitlines() if r]
    assert rows[0] == "a,285 South Broadway  Hicksville,Hicksville,NY,11801"
    assert rows[1] == "b,1561 Lee Rd,Winter Park,FL,"


def test_lookup_batches_at_the_service_limit():
    sent: list[int] = []

    def post(body: str) -> str:
        lines = [r for r in body.splitlines() if r]
        sent.append(len(lines))
        return "".join(f'"{r.split(",")[0]}","x","No_Match"\n' for r in lines)

    queries = [geo.Query(str(i), "1 Main St", "Springfield", "IL") for i in range(25_000)]
    geo.lookup(queries, post=post)
    assert sent == [geo.CENSUS_BATCH_LIMIT, geo.CENSUS_BATCH_LIMIT, 5_000]


def test_a_row_the_service_drops_becomes_a_miss():
    result = geo.lookup([geo.Query("ghost", "1 Main St", "Springfield", "IL")],
                        post=lambda body: "")
    assert result["ghost"] == geo.MISS


# --- nominatim ------------------------------------------------------------

def test_nominatim_search_lets_a_transport_error_propagate():
    def broken(url, params):
        raise OSError("connection reset")

    query = geo.Query("k", "21788 Katy Freeway", "Katy", "TX", "77449")
    with pytest.raises(OSError):
        geo.nominatim_search(query, get=broken)


def test_nominatim_lookup_still_reports_a_transport_error_as_a_miss():
    def broken(url, params):
        raise OSError("connection reset")

    query = geo.Query("k", "21788 Katy Freeway", "Katy", "TX", "77449")
    assert geo.nominatim_lookup(query, get=broken) == geo.MISS


# --- cache --------------------------------------------------------------

def test_cache_spares_the_service_a_second_lookup(tmp_path):
    cache = geo.MatchCache(tmp_path / "census.json")
    query = geo.Query("k", "1561 Lee Rd", "Winter Park", "FL", "32789")
    calls: list[str] = []

    def post(body: str) -> str:
        calls.append(body)
        return '"k","echo","Match","Exact","1561 LEE RD, WINTER PARK, FL, 32789","-81.3,28.6","1","R"\n'

    first = geo.lookup_cached([query], cache, post=post)
    second = geo.lookup_cached([query], geo.MatchCache(tmp_path / "census.json"), post=post)

    assert len(calls) == 1
    assert first == second
    assert second["k"].street == "1561 LEE RD"


def test_cache_key_ignores_case_but_not_the_address(tmp_path):
    cache = geo.MatchCache(tmp_path / "census.json")
    cache.put(geo.Query("a", "1561 Lee Rd", "Winter Park", "FL", "32789"), geo.MISS)
    assert cache.get(geo.Query("b", "1561 LEE RD", "WINTER PARK", "fl", "32789")) is geo.MISS
    assert cache.get(geo.Query("c", "1562 Lee Rd", "Winter Park", "FL", "32789")) is None


def test_cache_survives_a_round_trip_through_disk(tmp_path):
    path = tmp_path / "census.json"
    cache = geo.MatchCache(path)
    query = geo.Query("k", "2138 Caton Ave", "Brooklyn", "NY", "11226")
    cache.put(query, geo.Match(True, True, "2138 CATON AVE", "BROOKLYN", "NY",
                               "11226", 40.65, -73.96))
    cache.save()

    reloaded = geo.MatchCache(path)
    assert reloaded.get(query) == cache.get(query)
    assert json.loads(path.read_text())  # readable by hand, not a pickle
