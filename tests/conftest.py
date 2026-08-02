from pathlib import Path

import pytest

from makhaa_report.fetch import fixture_fetcher

FIXTURES = Path(__file__).parent / "fixtures"


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
