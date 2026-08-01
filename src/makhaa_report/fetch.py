"""HTTP fetching. Two implementations of the same Fetch contract:
a polite rate-limited live fetcher, and a fixture-backed one for tests.
"""

import json
import time
from pathlib import Path
from typing import Callable

import requests

from . import config

Fetch = Callable[[str], str]  # url -> response body text


class FetchError(Exception):
    pass


def make_fetcher(
    delay_s: float = config.RATE_DELAY_S,
    user_agent: str = config.USER_AGENT,
    timeout_s: float = config.TIMEOUT_S,
) -> Fetch:
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    last_request = 0.0

    def fetch(url: str) -> str:
        # 1 req/s ceiling, single-threaded — crawl posture per spec. Sleeps
        # only the remainder, and not at all before the first request.
        nonlocal last_request
        wait = delay_s - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        last_request = time.monotonic()
        try:
            resp = session.get(url, timeout=timeout_s)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FetchError(f"{url}: {exc}") from exc
        return resp.text

    return fetch


def fixture_fetcher(fixture_dir: Path) -> Fetch:
    """Serve saved pages from fixture_dir/manifest.json ({url: filename})."""
    manifest = json.loads((fixture_dir / "manifest.json").read_text())

    def fetch(url: str) -> str:
        if url not in manifest:
            raise FetchError(f"no fixture for {url} in {fixture_dir}")
        return (fixture_dir / manifest[url]).read_text(encoding="utf-8")

    return fetch
