"""Behaviour of the thin Scraper base class shared by every brand scraper."""

import pytest

from makhaa_report.fetch import FetchError
from makhaa_report.models import RawLocation
from makhaa_report.scrapers.base import Scraper


def fake_fetch(pages: dict[str, str]):
    def fetch(url: str) -> str:
        return pages[url]

    return fetch


class Widget(Scraper):
    slug = "widget"
    url = "https://widget.example/locations"


def test_add_populates_the_row_with_brand_and_default_source_url():
    s = Widget(fake_fetch({}))

    assert s.add("123 Main St, Springfield, IL") is True
    assert len(s.rows) == 1
    row = s.rows[0]
    assert row.brand == "widget"
    assert row.street == "123 Main St"
    assert row.city == "Springfield"
    assert row.state == "IL"
    assert row.source_url == "https://widget.example/locations"


def test_add_warns_and_returns_false_on_an_unparseable_address(caplog):
    s = Widget(fake_fetch({}))

    with caplog.at_level("WARNING", logger="makhaa"):
        result = s.add("not an address")

    assert result is False
    assert s.rows == []
    assert "widget" in caplog.text
    assert "not an address" in caplog.text


def test_quiet_scraper_skips_unparseable_addresses_silently(caplog):
    class QuietWidget(Scraper):
        slug = "quiet_widget"
        url = "https://quiet.example/locations"
        quiet = True

    s = QuietWidget(fake_fetch({}))

    with caplog.at_level("WARNING", logger="makhaa"):
        result = s.add("not an address")

    assert result is False
    assert caplog.text == ""


def test_add_dedupes_case_insensitive_street_and_city_keeping_the_first():
    s = Widget(fake_fetch({}))

    first = s.add("123 Main St, Springfield, IL", phone="555-1111")
    second = s.add("123 MAIN ST, SPRINGFIELD, IL", phone="555-2222")

    assert first is True
    assert second is False
    assert len(s.rows) == 1
    assert s.rows[0].phone == "555-1111"


def test_add_keeps_same_street_and_city_in_two_different_states():
    s = Widget(fake_fetch({}))

    first = s.add("123 Main St, Springfield, IL")
    second = s.add("123 Main St, Springfield, MO")

    assert first is True
    assert second is True
    assert len(s.rows) == 2


def test_add_sets_lat_and_lon_from_coords():
    s = Widget(fake_fetch({}))

    s.add("123 Main St, Springfield, IL", coords=(39.78, -89.65))

    row = s.rows[0]
    assert row.lat == 39.78
    assert row.lon == -89.65


def test_add_honors_explicit_source_url_and_fragment():
    s = Widget(fake_fetch({}))

    s.add(
        "123 Main St, Springfield, IL",
        source_url="https://widget.example/il/springfield",
        fragment="<li>123 Main St</li>",
    )

    row = s.rows[0]
    assert row.source_url == "https://widget.example/il/springfield"
    assert row.fragment == "<li>123 Main St</li>"


def test_add_defaults_fragment_to_the_raw_address():
    s = Widget(fake_fetch({}))

    s.add("123 Main St, Springfield, IL")

    assert s.rows[0].fragment == "123 Main St, Springfield, IL"


def test_scrape_returns_whatever_collect_added():
    class CollectingWidget(Scraper):
        slug = "widget"
        url = "https://widget.example/locations"

        def collect(self):
            self.add("123 Main St, Springfield, IL")
            self.add("456 Oak Ave, Chicago, IL")

    rows = CollectingWidget.scrape(fake_fetch({}))

    assert len(rows) == 2
    assert all(isinstance(r, RawLocation) for r in rows)


def test_page_parses_html_with_lxml():
    fetch = fake_fetch({"https://widget.example/locations": "<p>hello</p>"})
    s = Widget(fetch)

    soup = s.page("https://widget.example/locations")

    assert soup.find("p").get_text() == "hello"


def test_page_parses_a_sitemap_with_the_xml_parser():
    sitemap = "<urlset><url><loc>https://widget.example/a</loc></url></urlset>"
    fetch = fake_fetch({"https://widget.example/sitemap.xml": sitemap})
    s = Widget(fetch)

    soup = s.page("https://widget.example/sitemap.xml", parser="xml")

    assert soup.find("loc").get_text() == "https://widget.example/a"


def test_scrape_propagates_a_fetch_error():
    def raising_fetch(url: str) -> str:
        raise FetchError(f"boom: {url}")

    class FailingWidget(Scraper):
        slug = "widget"
        url = "https://widget.example/locations"

        def collect(self):
            self.page(self.url)

    with pytest.raises(FetchError):
        FailingWidget.scrape(raising_fetch)


def test_collect_is_not_implemented_by_default():
    s = Widget(fake_fetch({}))

    with pytest.raises(NotImplementedError):
        s.collect()
