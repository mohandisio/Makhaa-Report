"""cli.py wires an AddressConfirmer into every run_scrape call."""

import pytest

from makhaa_report import cli
from makhaa_report.confirm import AddressConfirmer
from makhaa_report.models import RunStats


@pytest.fixture
def recorder(monkeypatch):
    """Stub run_scrape: capture kwargs, return a minimal RunStats."""
    calls = []

    def fake_run_scrape(conn, **kwargs):
        calls.append(kwargs)
        return RunStats(run_id=1)

    monkeypatch.setattr("makhaa_report.pipeline.run_scrape", fake_run_scrape)
    monkeypatch.setattr("makhaa_report.db.connect", lambda *a, **k: "fake-conn")
    return calls


@pytest.fixture(autouse=True)
def tmp_geo_dir(tmp_path, monkeypatch):
    geo_dir = tmp_path / "geo"
    monkeypatch.setattr("makhaa_report.config.GEO_DIR", geo_dir)
    return geo_dir


def test_scrape_passes_confirmer(recorder, tmp_geo_dir):
    assert cli.main(["scrape"]) == 0
    assert len(recorder) == 1
    confirmer = recorder[0]["confirmer"]
    assert isinstance(confirmer, AddressConfirmer)
    assert confirmer._cache.path.parent == tmp_geo_dir


def test_scrape_brand_passes_brands_and_confirmer(recorder, tmp_geo_dir):
    assert cli.main(["scrape", "--brand", "haraz"]) == 0
    assert len(recorder) == 1
    kwargs = recorder[0]
    assert kwargs["brands"] == ["haraz"]
    confirmer = kwargs["confirmer"]
    assert isinstance(confirmer, AddressConfirmer)
    assert confirmer._cache.path.parent == tmp_geo_dir


def test_manual_entry_passes_confirmer(recorder, tmp_geo_dir, monkeypatch):
    monkeypatch.setattr(
        "makhaa_report.manual.parse_entry",
        lambda fields: {"brand": "mohka_house", "street": "123 Grand Ave",
                        "city": "Oakland", "state": "CA"},
    )
    monkeypatch.setattr(
        "makhaa_report.manual.append_entry",
        lambda record, manual_dir=None: tmp_geo_dir / "manual" / "mohka_house.csv",
    )

    assert cli.main([
        "manual-entry", "brand=mohka_house", 'street="123 Grand Ave"',
        "city=Oakland", "state=CA",
    ]) == 0
    assert len(recorder) == 1
    confirmer = recorder[0]["confirmer"]
    assert isinstance(confirmer, AddressConfirmer)
    assert confirmer._cache.path.parent == tmp_geo_dir
