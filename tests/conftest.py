from pathlib import Path

import pytest

from makhaa_report.fetch import fixture_fetcher

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_fetch():
    """Serve a brand's saved pages: fixture_fetch("qamaria") -> Fetch."""
    return lambda brand: fixture_fetcher(FIXTURES / brand)
