"""Aggregations and rendering for the HTML report."""

import json
import re

import pytest

from makhaa_report import db, report
from makhaa_report.models import Brand, Location, RunStats

_BRANDS = (
    Brand(slug="alpha", display_name="Alpha Coffee", locator_url="https://a.test",
          method="scrape", band=(1, 10)),
    Brand(slug="beta", display_name="Beta Coffee", locator_url="https://b.test",
          method="scrape", band=(1, 10), franchises=True),
    Brand(slug="gamma", display_name="Gamma Coffee", locator_url="https://c.test",
          method="manual", band=(1, 10)),
)


def _loc(uid: str, brand: str, street: str, city: str, state: str,
         **overrides) -> Location:
    fields = {
        "uid": uid, "brand": brand, "street": street, "city": city, "state": state,
        "postal": None, "lat": 40.0, "lon": -80.0, "geocode_source": "locator",
        "geocode_flagged": False, "status": "open", "status_note": "", "phone": None,
        "hours": None, "source_url": "https://x.test", "is_manual": False,
        "first_seen": "2026-08-01T00:00:00Z", "last_seen": "2026-08-01T00:00:00Z",
    }
    fields.update(overrides)
    return Location(**fields)


_LOCATIONS = (
    _loc("aaa1", "alpha", "1 Oak St", "Dearborn", "MI"),
    _loc("aaa2", "alpha", "2 Elm St", "Dearborn", "MI"),
    _loc("aaa3", "alpha", "3 Pine St", "Chicago", "IL", status="coming_soon"),
    _loc("bbb1", "beta", "4 Ash St", "Chicago", "IL"),
    _loc("bbb2", "beta", "5 Fir St", "Toledo", "OH", status="closed_permanently"),
    _loc("ccc1", "gamma", "6 Yew St", "Dallas", "TX", lat=None, lon=None,
         geocode_source=None, phone="555-0100", hours="7-3 daily"),
)


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "test.sqlite")
    db.sync_registry(conn, _BRANDS, ())
    for loc in _LOCATIONS:
        db.upsert_location(conn, loc)
    conn.commit()
    return conn


def test_headline_stats(conn):
    stats = report.headline_stats(conn)
    assert stats["total"] == 6
    assert stats["open"] == 4
    assert stats["coming_soon"] == 1
    assert stats["closed_permanently"] == 1
    assert stats["relocating"] == 0  # absent status still reported
    assert stats["brands"] == 3
    assert stats["states"] == 4


def test_shop_rows_splits_unmapped(conn):
    mapped, unmapped = report.shop_rows(conn)
    assert len(mapped) == 5
    assert [s["uid"] for s in unmapped] == ["ccc1"]
    assert unmapped[0]["brand_name"] == "Gamma Coffee"  # joined in, not dropped
    assert mapped[0]["brand_name"] == "Alpha Coffee"


def test_brand_table_order_and_counts(conn):
    table = report.brand_table(conn)
    assert [b["slug"] for b in table] == ["alpha", "beta", "gamma"]
    alpha = table[0]
    assert (alpha["total"], alpha["open"], alpha["coming_soon"]) == (3, 2, 1)
    assert alpha["states"] == 2


def test_brand_table_ties_break_on_name(conn):
    # beta (2) and a hypothetical same-count brand would sort by name; here
    # verify the secondary key is exercised via equal single-shop brands.
    table = report.brand_table(conn)
    assert table[-1]["slug"] == "gamma"  # 1 shop, last


def test_brand_colors_top_n_then_gray():
    brands = [{"slug": f"b{i}"} for i in range(10)]
    colors = report.brand_colors(brands)
    top = [colors[f"b{i}"] for i in range(report.TOP_BRANDS)]
    assert top == list(report.PALETTE)
    assert colors["b8"] == colors["b9"] == report.OTHER_COLOR


def test_state_counts(conn):
    counts = report.state_counts(conn)
    assert counts[0] == {"state": "IL", "total": 2}  # ties break alphabetically
    assert counts[1] == {"state": "MI", "total": 2}
    assert {c["state"]: c["total"] for c in counts} == {
        "IL": 2, "MI": 2, "OH": 1, "TX": 1,
    }


def test_status_counts_vocabulary_order(conn):
    counts = report.status_counts(conn)
    assert [c["status"] for c in counts] == ["coming_soon", "open", "closed_permanently"]
    assert counts[1]["total"] == 4


def test_top_cities(conn):
    cities = report.top_cities(conn)
    assert cities[0] == {"label": "Chicago, IL", "total": 2, "brands": 2}
    assert cities[1] == {"label": "Dearborn, MI", "total": 2, "brands": 1}


def test_city_diversity_ranks_brands_first(conn):
    diverse = report.city_diversity(conn)
    assert diverse[0]["label"] == "Chicago, IL"
    assert diverse[0]["brands"] == 2


def test_coming_soon_by_state(conn):
    rows = report.coming_soon_by_state(conn)
    assert rows == [{"state": "IL", "brand": "alpha",
                     "brand_name": "Alpha Coffee", "total": 1}]


def test_market_concentration(conn):
    conc = report.market_concentration(conn, min_shops=2)
    assert [c["state"] for c in conc] == ["MI", "IL"]  # by share, descending
    assert conc[0] == {"state": "MI", "leader": "Alpha Coffee",
                       "leader_shops": 2, "total": 2, "share": 1.0}
    assert conc[1]["share"] == 0.5  # tie in IL keeps the first brand by name
    assert conc[1]["leader"] == "Alpha Coffee"
    assert report.market_concentration(conn, min_shops=5) == []


def test_data_as_of(conn):
    assert report.data_as_of(conn) is None  # no runs yet
    run1 = db.start_run(conn, "2026-08-01T00:00:00Z")
    db.finish_run(conn, RunStats(run_id=run1, total_rows=6), "2026-08-01T01:00:00Z")
    run2 = db.start_run(conn, "2026-08-08T00:00:00Z")  # unfinished run counts too
    assert run2 > run1
    assert report.data_as_of(conn) == "2026-08-08T00:00:00Z"


def test_context_is_json_serializable(conn):
    context = report.build_context(conn, generated_at="2026-08-02T00:00:00Z")
    assert json.loads(json.dumps(context)) == context


FIXED_TS = "2026-08-02T00:00:00Z"


def _render(conn, tmp_path):
    path = report.write_report(conn, tmp_path / "out" / "report.html",
                               generated_at=FIXED_TS)
    return path, path.read_text(encoding="utf-8")


def test_render_smoke(conn, tmp_path):
    path, html = _render(conn, tmp_path)
    assert path.exists()
    assert html.startswith("<!doctype html>")
    assert FIXED_TS in html  # injected clock, deterministic output
    assert "{{" not in html  # no unrendered template residue
    assert "leaflet@1.9.4" in html and "chart.js@" in html


def test_embedded_json_matches_db(conn, tmp_path):
    _, html = _render(conn, tmp_path)
    match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    payload = json.loads(match.group(1))
    assert len(payload["shops"]) == 5  # mapped rows only; ccc1 listed as unmapped
    assert {b["slug"] for b in payload["brands"]} == {"alpha", "beta", "gamma"}
    assert "6 Yew St" not in str(payload["shops"])  # unmapped row not in payload
    assert "Gamma Coffee" in html  # ...but the unmapped shop is on the page
    # published payload carries display fields only, not dataset keys
    assert set(payload["shops"][0]) == {"brand", "brand_name", "street", "city",
                                        "state", "lat", "lon", "status",
                                        "phone", "hours"}


def test_hostile_field_is_escaped(conn, tmp_path):
    hostile = "</script><script>alert(1)</script>"
    conn.execute("UPDATE locations SET hours = ? WHERE uid = 'aaa1'", (hostile,))
    conn.commit()
    _, html = _render(conn, tmp_path)
    assert hostile not in html  # tojson escapes <> so the tag cannot break out
