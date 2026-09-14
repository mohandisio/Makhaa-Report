"""AddressConfirmer: confirm a scraped address against Census before the uid is hashed."""

import json

from makhaa_report import geo
from makhaa_report.confirm import AddressConfirmer
from makhaa_report.models import RawLocation
from makhaa_report.normalize import make_uid


def _row(**kwargs):
    defaults = dict(brand="haraz", street="1737 N Alafaya Trail", city="Orlando",
                     state="FL", postal="32826")
    defaults.update(kwargs)
    return RawLocation(**defaults)


def _responder(rows: dict[str, str]):
    """Answer a batch from {street queried: matched address}, else No_Match.

    Shape copied from tests/test_geocode.py's own Census-CSV stub.
    """

    def post(body: str) -> str:
        out = []
        for line in body.splitlines():
            if not line:
                continue
            key, street, *_ = line.split(",")
            matched = rows.get(street)
            if matched is None:
                out.append(f'"{key}","echo","No_Match"')
            else:
                out.append(
                    f'"{key}","echo","Match","Exact","{matched}",'
                    f'"-81.2,28.6","1","R"'
                )
        return "\n".join(out) + "\n"

    return post


def _osm(results: dict[str, tuple[float, float]] | None = None):
    """Stand in for Nominatim: {street queried: (lat, lon)}, else no result.

    Shape copied from tests/test_geocode.py's own stub.
    """
    results = results or {}

    def get(url: str, params: dict[str, str]) -> str:
        point = results.get(params["street"])
        if point is None:
            return "[]"
        return json.dumps([{"lat": str(point[0]), "lon": str(point[1])}])

    return get


def test_adoption_keeps_casing_and_unit_and_sets_published_uid(tmp_path):
    # "Broadhollow" splitting into two words is a real address change, not
    # an abbreviation the uid already treats as identical, so the uid moves.
    row = _row(street="606 Broadhollow Rd Ste 12", city="Melville",
               state="NY", postal="11747")
    old_uid = make_uid(row.brand, row.street, row.city, row.state)
    post = _responder({"606 Broadhollow Rd": "606 BROAD HOLLOW RD, MELVILLE, NY, 11747"})

    out = AddressConfirmer(tmp_path, post=post).confirm([row])

    assert out[0].street == "606 Broad Hollow Rd Ste 12"
    assert out[0].city == "Melville"
    new_uid = make_uid(row.brand, out[0].street, out[0].city, row.state)
    assert new_uid != old_uid
    assert out[0].published_uid == old_uid


def test_adoption_that_only_fills_the_postal_leaves_the_uid_alone(tmp_path):
    row = _row(street="1737 N Alafaya Trl", city="Orlando", state="FL", postal=None)
    post = _responder({"1737 N Alafaya Trl": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    out = AddressConfirmer(tmp_path, post=post).confirm([row])

    assert out[0].postal == "32826"
    assert out[0].street == "1737 N Alafaya Trl"
    assert out[0].published_uid is None


def test_non_exact_match_keeps_the_address_and_flags(tmp_path):
    # Same verdict Census gives for "285 South Broadway, Long Isand": a
    # real address in the wrong place, so the correction is not adopted.
    row = _row(street="4341 14th St", city="Plano", state="TX", postal="75074")

    def post(body: str) -> str:
        key = body.split(",")[0]
        return (f'"{key}","echo","Match","Non_Exact","4341 14TH PL, PLANO, TX, 75074",'
                f'"-81.2,28.6","1","R"\n')

    out = AddressConfirmer(tmp_path, post=post, get=_osm(), sleep=lambda _s: None).confirm([row])

    assert (out[0].street, out[0].city) == ("4341 14th St", "Plano")
    assert out[0].geocode_flagged is True
    assert out[0].published_uid is None


def test_unmatched_keeps_the_address_and_flags(tmp_path):
    row = _row(street="21788 Katy Freeway Suite 400", city="Katy",
               state="TX", postal="77449")
    post = _responder({})

    out = AddressConfirmer(tmp_path, post=post, get=_osm(), sleep=lambda _s: None).confirm([row])

    assert out[0].street == "21788 Katy Freeway Suite 400"
    assert out[0].geocode_flagged is True


def test_coordinates_filled_only_when_the_row_had_none(tmp_path):
    row = _row()  # lat/lon default to None
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    out = AddressConfirmer(tmp_path, post=post).confirm([row])

    assert (round(out[0].lat, 1), round(out[0].lon, 1)) == (28.6, -81.2)
    assert out[0].geocode_source == "census"
    assert out[0].geocode_flagged is False


def test_locator_coords_within_tolerance_are_kept(tmp_path):
    # Census answers -81.2,28.6; a locator pin a few meters off is fine.
    row = _row(lat=28.60001, lon=-81.20001)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    out = AddressConfirmer(tmp_path, post=post).confirm([row])

    assert (out[0].lat, out[0].lon) == (28.60001, -81.20001)
    assert out[0].geocode_source is None
    assert out[0].geocode_flagged is False


def test_a_locator_pin_371_km_off_is_replaced_with_the_census_point(tmp_path):
    # 28.6,-81.2 (Orlando) vs 25.76,-80.19 (Miami) is ~371 km.
    row = _row(lat=25.76, lon=-80.19)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    out = AddressConfirmer(tmp_path, post=post).confirm([row])

    assert (round(out[0].lat, 1), round(out[0].lon, 1)) == (28.6, -81.2)
    assert out[0].geocode_source == "census"
    assert out[0].geocode_flagged is False


def test_a_pin_outside_the_us_is_replaced(tmp_path):
    # A locator once published a New Jersey store's coordinates in Lebanon.
    row = _row(lat=33.8915, lon=35.5024)
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    out = AddressConfirmer(tmp_path, post=post).confirm([row])

    assert (round(out[0].lat, 1), round(out[0].lon, 1)) == (28.6, -81.2)
    assert out[0].geocode_source == "census"
    assert out[0].geocode_flagged is False


def test_one_post_per_run_then_zero(tmp_path):
    row = _row()
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})

    AddressConfirmer(tmp_path, post=post).confirm([row])

    def boom(body: str) -> str:
        raise AssertionError("re-ran a lookup the cache already answered")

    out = AddressConfirmer(tmp_path, post=boom).confirm([row])
    assert out[0].street == "1737 N Alafaya Trl"


def test_leave_rows_come_back_untouched_and_never_hit_the_network(tmp_path):
    row = _row()
    published = make_uid(row.brand, row.street, row.city, row.state)

    def boom(body: str) -> str:
        raise AssertionError("a left-alone row must never be looked up")

    out = AddressConfirmer(tmp_path, post=boom).confirm([row], leave={published})

    assert out[0] == row
    assert out[0] is row


def test_a_failing_post_keeps_cached_adoptions_and_flags_the_rest(tmp_path):
    cached_row = _row(street="1737 N Alafaya Trail", city="Orlando",
                       state="FL", postal="32826")
    new_row = _row(street="99999 Fakery Blvd", city="Nowhere",
                    state="TX", postal="77449")
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})
    AddressConfirmer(tmp_path, post=post).confirm([cached_row])

    def broken(body: str) -> str:
        raise OSError("connection reset")

    out = AddressConfirmer(tmp_path, post=broken).confirm([cached_row, new_row])

    assert len(out) == 2
    assert out[0].street == "1737 N Alafaya Trl", "the cached adoption still applies"
    assert out[0].geocode_flagged is False
    assert out[1].street == "99999 Fakery Blvd", "unanswered rows are left alone"
    assert out[1].geocode_flagged is True


def test_a_failing_post_warns_about_only_the_uncached_rows(caplog, tmp_path):
    cached_row_a = _row(street="1737 N Alafaya Trail", city="Orlando",
                         state="FL", postal="32826")
    cached_row_b = _row(street="4341 14th St", city="Plano",
                         state="TX", postal="75074")
    new_row = _row(street="99999 Fakery Blvd", city="Nowhere",
                    state="TX", postal="77449")
    post = _responder({
        "1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826",
        "4341 14th St": "4341 14TH PL, PLANO, TX, 75074",
    })
    AddressConfirmer(tmp_path, post=post, get=_osm(), sleep=lambda _s: None).confirm(
        [cached_row_a, cached_row_b]
    )

    def broken(body: str) -> str:
        raise OSError("connection reset")

    caplog.set_level("WARNING", logger="makhaa")
    out = AddressConfirmer(tmp_path, post=broken, get=_osm(), sleep=lambda _s: None).confirm(
        [cached_row_a, cached_row_b, new_row]
    )

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "1 " in warnings[0].getMessage() or "1 address" in warnings[0].getMessage()
    assert "3" not in warnings[0].getMessage()
    assert out[0].street == "1737 N Alafaya Trl"
    assert out[0].geocode_flagged is False
    assert out[1].street == "4341 14th Pl"
    assert out[1].geocode_flagged is False
    assert out[2].street == "99999 Fakery Blvd"
    assert out[2].geocode_flagged is True


def test_output_order_and_length_match_the_input(tmp_path):
    rows = [
        _row(brand="haraz", street="1737 N Alafaya Trail", city="Orlando",
             state="FL", postal="32826"),
        _row(brand="qamaria", street="4341 14th St", city="Plano",
             state="TX", postal="75074"),
        _row(brand="mohka_house", street="21788 Katy Freeway", city="Katy",
             state="TX", postal="77449"),
    ]
    post = _responder({
        "1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826",
        "4341 14th St": "4341 14TH PL, PLANO, TX, 75074",
    })

    out = AddressConfirmer(tmp_path, post=post, get=_osm(), sleep=lambda _s: None).confirm(rows)

    assert len(out) == len(rows)
    assert [r.brand for r in out] == [r.brand for r in rows]


# --- OpenStreetMap fallback ----------------------------------------------

def test_osm_confirms_and_places_a_row_census_could_not(tmp_path):
    row = _row(street="21788 Katy Freeway Suite 400", city="Katy",
               state="TX", postal="77449")
    post = _responder({})
    get = _osm({"21788 Katy Freeway": (29.78, -95.76)})

    out = AddressConfirmer(tmp_path, post=post, get=get, sleep=lambda _s: None).confirm([row])

    assert out[0].street == "21788 Katy Freeway Suite 400"
    assert (round(out[0].lat, 2), round(out[0].lon, 2)) == (29.78, -95.76)
    assert out[0].geocode_source == "nominatim"
    assert out[0].geocode_flagged is False


def test_osm_hit_on_a_row_with_locator_coords_keeps_them(tmp_path):
    row = _row(street="21788 Katy Freeway Suite 400", city="Katy",
               state="TX", postal="77449", lat=29.786, lon=-95.734)
    post = _responder({})
    get = _osm({"21788 Katy Freeway": (29.78, -95.76)})

    out = AddressConfirmer(tmp_path, post=post, get=get, sleep=lambda _s: None).confirm([row])

    assert (out[0].lat, out[0].lon) == (29.786, -95.734)
    assert out[0].geocode_source is None
    assert out[0].geocode_flagged is False


def test_osm_is_asked_only_for_census_unconfirmed_rows(tmp_path):
    exact_row = _row()  # Census will confirm this one exactly
    unmatched_row = _row(brand="qamaria", street="21788 Katy Freeway Suite 400",
                          city="Katy", state="TX", postal="77449")
    post = _responder({"1737 N Alafaya Trail": "1737 N ALAFAYA TRL, ORLANDO, FL, 32826"})
    calls: list[str] = []

    def counting_get(url, params):
        calls.append(params["street"])
        return "[]"

    AddressConfirmer(tmp_path, post=post, get=counting_get,
                      sleep=lambda _s: None).confirm([exact_row, unmatched_row])

    assert calls == ["21788 Katy Freeway"]


def test_a_cached_osm_answer_costs_no_request_on_the_second_run(tmp_path):
    row = _row(street="21788 Katy Freeway Suite 400", city="Katy",
               state="TX", postal="77449")
    post = _responder({})
    get = _osm({"21788 Katy Freeway": (29.78, -95.76)})

    AddressConfirmer(tmp_path, post=post, get=get, sleep=lambda _s: None).confirm([row])

    def boom(url, params):
        raise AssertionError("re-asked OSM for an address the cache already answered")

    out = AddressConfirmer(tmp_path, post=post, get=boom,
                            sleep=lambda _s: None).confirm([row])
    assert out[0].geocode_source == "nominatim"


def test_a_failing_osm_request_stops_further_requests_and_caches_nothing(tmp_path):
    rows = [
        _row(brand="haraz", street="21788 Katy Freeway Suite 400", city="Katy",
             state="TX", postal="77449"),
        _row(brand="qamaria", street="99999 Fakery Blvd", city="Nowhere",
             state="TX", postal="77449"),
    ]
    post = _responder({})
    calls: list[str] = []

    def broken(url, params):
        calls.append(params["street"])
        raise OSError("connection reset")

    out = AddressConfirmer(tmp_path, post=post, get=broken,
                            sleep=lambda _s: None).confirm(rows)

    assert len(calls) == 1, "the second row must not be asked after the first fails"
    assert out[0].geocode_flagged is True
    assert out[1].geocode_flagged is True

    # Nothing was cached, so a second run with a working get asks again.
    out2 = AddressConfirmer(tmp_path, post=post,
                             get=_osm({"21788 Katy Freeway": (29.78, -95.76)}),
                             sleep=lambda _s: None).confirm(rows)
    assert out2[0].geocode_source == "nominatim"


def test_rows_census_never_answered_are_not_sent_to_osm(tmp_path):
    row = _row()

    def broken_post(body: str) -> str:
        raise OSError("connection reset")

    def boom_get(url, params):
        raise AssertionError("an unanswered row must never be sent to OSM")

    out = AddressConfirmer(tmp_path, post=broken_post, get=boom_get,
                            sleep=lambda _s: None).confirm([row])

    assert out[0].geocode_flagged is True


def test_sleep_is_called_once_per_real_osm_request_only(tmp_path):
    rows = [
        _row(brand="haraz", street="21788 Katy Freeway Suite 400", city="Katy",
             state="TX", postal="77449"),
        _row(brand="qamaria", street="21788 Katy Freeway Suite 400", city="Katy",
             state="TX", postal="77449"),
    ]
    post = _responder({})
    get = _osm({"21788 Katy Freeway": (29.78, -95.76)})
    sleeps: list[float] = []

    AddressConfirmer(tmp_path, post=post, get=get, sleep=sleeps.append).confirm(rows)

    assert len(sleeps) == 1, "the second row's query is identical, so it's a cache hit"
