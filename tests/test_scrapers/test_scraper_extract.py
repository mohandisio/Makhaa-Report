"""Shared scraper helpers used by two or more brand scrapers."""

from bs4 import BeautifulSoup

from makhaa_report.scrapers.extract import (
    bundle_source,
    drop_tags,
    innermost_address_texts,
    one_line,
    place_coords,
    postal_address,
    schema_records,
    text,
)


def test_postal_address_joins_a_full_schema_org_address():
    address = {
        "streetAddress": "123 Main St",
        "addressLocality": "Springfield",
        "addressRegion": "MI",
        "postalCode": "48001",
    }
    assert postal_address(address) == "123 Main St, Springfield, MI 48001"


def test_postal_address_omits_a_missing_postal_code():
    address = {
        "streetAddress": "123 Main St",
        "addressLocality": "Springfield",
        "addressRegion": "MI",
    }
    assert postal_address(address) == "123 Main St, Springfield, MI"


def test_one_line_collapses_whitespace():
    assert one_line("  a\n  b\t c  ") == "a b c"


def test_text_joins_with_the_separator():
    soup = BeautifulSoup("<p>a <b>b</b> c</p>", "lxml")
    assert text(soup.p, separator=" | ") == "a | b | c"


def test_text_with_empty_separator():
    soup = BeautifulSoup("<p>a <b>b</b> c</p>", "lxml")
    assert text(soup.p, separator="") == "abc"


def test_drop_tags_removes_script_style_title():
    soup = BeautifulSoup(
        "<html><head><title>T</title><style>s</style></head>"
        "<body><script>s</script><p>hello</p></body></html>",
        "lxml",
    )
    drop_tags(soup, "script", "style", "title")

    assert soup.find(["script", "style", "title"]) is None
    assert soup.find("p").get_text() == "hello"


def test_place_coords_on_a_place_url():
    url = "https://maps.google.com/?cid=1!3d42.331!4d-83.045"
    assert place_coords(url) == (42.331, -83.045)


def test_place_coords_on_an_embed_url_returns_none():
    # Embed urls order coords the other way round: !2d is longitude,
    # !3d is latitude, and there is no !4d for place_coords to match.
    url = "https://www.google.com/maps/embed?pb=!2d-83.1!3d42.3"
    assert place_coords(url) is None


def test_place_coords_with_no_coords_returns_none():
    assert place_coords("https://example.com/no-coords-here") is None


def test_innermost_address_texts_picks_the_innermost_element():
    soup = BeautifulSoup(
        "<div><p>123 Main St, Springfield, MI 48001</p></div>",
        "lxml",
    )
    texts = innermost_address_texts(soup)

    assert texts == ["123 Main St, Springfield, MI 48001"]


def test_text_node_scan_needs_str_not_text():
    # A text-node scan (`soup.find_all(string=...)`) yields NavigableString
    # objects, including HTML comments. one_line(str(node)) captures a
    # comment's text; text(node) on a Comment returns "" because
    # Comment has no children to join — this is why address scrapers
    # that scan comments must use str(node), not text(node).
    soup = BeautifulSoup(
        "<div><!-- 123 Main St, Springfield, MI 48001 --></div>",
        "lxml",
    )
    from makhaa_report.scrapers.extract import LOOKS_LIKE_ADDRESS

    node = soup.find(string=LOOKS_LIKE_ADDRESS)

    assert one_line(str(node)) == "123 Main St, Springfield, MI 48001"
    assert text(node) == ""


def test_schema_records_returns_matching_types_and_skips_broken_json():
    soup = BeautifulSoup(
        """
        <script type="application/ld+json">{"@type": "CafeOrCoffeeShop", "name": "A"}</script>
        <script type="application/ld+json">{"@type": "Other", "name": "B"}</script>
        <script type="application/ld+json">not json</script>
        """,
        "lxml",
    )

    records = schema_records(soup, "CafeOrCoffeeShop")

    assert records == [{"@type": "CafeOrCoffeeShop", "name": "A"}]


def test_bundle_source_fetches_the_referenced_asset():
    pages = {
        "https://example.com": '<html><script src="/assets/index-abc.js"></script></html>',
        "https://example.com/assets/index-abc.js": "console.log(1)",
    }

    assert bundle_source(pages.__getitem__, "https://example.com") == "console.log(1)"


def test_bundle_source_raises_when_no_bundle_is_referenced():
    import pytest

    def fetch(_url):
        return "<html><body>no scripts here</body></html>"

    with pytest.raises(ValueError):
        bundle_source(fetch, "https://example.com")
