from pathlib import Path

import pytest

from makhaa_report import config
from makhaa_report.fetch import fixture_fetcher

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """Keep every test out of the real data/ directory.

    Nothing under test should be able to read or write the repo's actual
    manual CSVs, overrides.csv, geocode cache, exports, or database — a
    test that reaches config.OVERRIDES_PATH etc. without this would patch
    the real file on disk instead of a throwaway one.
    """
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "data" / "makhaa.sqlite")
    monkeypatch.setattr(config, "MANUAL_DIR", tmp_path / "data" / "manual")
    monkeypatch.setattr(config, "OVERRIDES_PATH", tmp_path / "data" / "overrides.csv")
    monkeypatch.setattr(config, "EXPORT_DIR", tmp_path / "data" / "exports")
    monkeypatch.setattr(config, "GEO_DIR", tmp_path / "data" / "geo")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly instead of calling a live geocoder.

    A test that reaches the network is slow, flaky, and rude to a free
    public service. Anything needing a response injects a stub.
    """

    def blocked(*args, **kwargs):
        raise AssertionError("test attempted a live HTTP request")

    monkeypatch.setattr("makhaa_report.geo._requests_get", blocked)
    monkeypatch.setattr("makhaa_report.geo._requests_post", blocked)


@pytest.fixture
def fixture_fetch():
    """Serve a brand's saved pages: fixture_fetch("qamaria") -> Fetch."""
    return lambda brand: fixture_fetcher(FIXTURES / brand)
