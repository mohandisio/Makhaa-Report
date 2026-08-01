"""Brand registry: the 14 known chains, drift bands, and lookalike exclusions.

Bands are guardrails, not counts. They exist to catch a scrape that has
gone wrong, and are reset from what the scraper actually returns — never
from a number read off a website by hand, which is stale the moment it is
written. The scrape is the source of truth for how many stores a brand has;
nothing in this file should claim to know that.

Notes record structure and traps: where the data lives, what has to be
excluded, what the locator cannot tell us.
"""

from .models import Brand, Exclusion

BRANDS: tuple[Brand, ...] = (
    Brand(
        slug="haraz",
        display_name="Haraz Coffee House",
        locator_url="https://harazcoffeehouse.com",
        method="scrape",
        band=(55, 75),
        franchises=True,
        notes=(
            "One /pages/<state>-locations page per state, discovered from "
            "the sitemap so a new state cannot be missed; the all-states "
            "summary page is stale and skipped. Card headings are wrong on "
            "at least one store, so the address is the identity. Roughly a "
            "third of the cards link to a Maps search rather than a place "
            "and carry no coordinates. No coming-soon markers appear here."
        ),
    ),
    Brand(
        slug="qamaria",
        display_name="Qamaria Yemeni Coffee",
        locator_url="https://www.qamariacoffee.com/cafes",
        method="scrape",
        band=(44, 60),
        franchises=True,
        notes=(
            "Storepoint map widget; data comes from its API, not Squarespace. "
            "Catering service-area rows and non-US stores are excluded. The "
            "feed carries no coming-soon flag, so the announced pipeline is "
            "invisible for this brand."
        ),
    ),
    Brand(
        slug="qahwah_house",
        display_name="Qahwah House",
        locator_url="https://qahwahhouse.com/locations",
        method="scrape",
        band=(24, 35),
        notes=(
            "One schema.org CafeOrCoffeeShop block per store on the "
            "locations page, with coordinates, phone and hours; the "
            "sitemap lists no per-store pages and several stores share a "
            "URL. One store publishes a street with no city or state and "
            "is skipped — add it through overrides.csv if it matters. No "
            "coming-soon markers appear here."
        ),
    ),
    Brand(
        slug="moka_and_co",
        display_name="Moka & Co",
        locator_url="https://mokanco.com/locations/",
        method="scrape",
        band=(35, 50),
        notes=(
            "WordPress; /pages/locations redirects to /locations/. Every "
            "address is on that one page, so the per-store detail pages at "
            "/<slug>/ are deliberately not fetched — reading both would "
            "double-count. Marks its pipeline with a Coming Soon term."
        ),
    ),
    Brand(
        slug="shibam",
        display_name="Shibam Coffee Co.",
        locator_url="https://shibamcoffee.com",
        method="scrape",
        band=(18, 26),
        notes="WP REST /wp-json/wp/v2/pages?slug=our-locations&_fields=content.",
    ),
    Brand(
        slug="arwa",
        display_name="Arwa Yemeni Coffee",
        locator_url="https://arwacoffee.com/locations",
        method="scrape",
        band=(10, 18),
    ),
    Brand(
        slug="matari",
        display_name="Matari Coffee",
        locator_url="https://mataricoffee.com/locations",
        method="scrape",
        band=(6, 12),
        notes="US census: exclude the Mississauga ON store.",
    ),
    Brand(
        slug="delah",
        display_name="Delah Coffee",
        locator_url="https://delahcoffee.com/pages/locations",
        method="scrape",
        band=(5, 10),
    ),
    Brand(
        slug="qatra",
        display_name="Qatra Coffee",
        locator_url="https://qatracoffee.com/locations",
        method="scrape",
        band=(2, 6),
        notes="qatracoffee.com is the Yemeni brand — NOT qatracafe.com (see exclusions).",
    ),
    Brand(
        slug="heyma",
        display_name="Heyma",
        locator_url="https://heymacoffeeca.com",
        method="scrape",
        band=(1, 4),
    ),
    Brand(
        slug="caffeena",
        display_name="Caffeena Coffee House",
        locator_url="https://caffeena.com/locations",
        method="scrape",
        band=(1, 8),
    ),
    Brand(
        slug="mokafe",
        display_name="MOKAFÉ",
        locator_url="https://mymokafe.com",
        method="scrape",
        band=(1, 12),
        notes=(
            "Prior research disagreed on which storefronts are actually "
            "MOKAFÉ; verify by hand before publishing, and tighten the band "
            "once the scraper settles. Distinct company from Moka & Co."
        ),
    ),
    Brand(
        slug="mohka_house",
        display_name="Mohka House",
        locator_url="",
        method="manual",
        band=(0, 5),
        hq="Oakland, CA",
        notes="No website; hand-maintained CSV.",
    ),
    Brand(
        slug="sanaa_cafe",
        display_name="Sana'a Cafe",
        locator_url="https://thesanaacafe.com",
        method="manual",
        band=(0, 15),
        alt_domains=("sanaahousecafe.com",),
        notes=(
            "Locator provably incomplete — it omits stores the press confirms "
            "are trading — and its 'coming soon' labels are unreliable, since "
            "the label sits in the order-button slot. Hand-maintained CSV; "
            "treat the total as a floor, not a count."
        ),
    ),
)

EXCLUSIONS: tuple[Exclusion, ...] = (
    Exclusion(
        domain="qatracafe.com",
        reason="Afghan chai cafe, single location, Pleasanton CA. No Yemen connection. Unrelated to Qatra Coffee (qatracoffee.com).",
        related_brand="qatra",
    ),
    Exclusion(
        domain="mymokafe.com",
        reason="MOKAFÉ is a distinct company from Moka & Co (mokanco.com). Both stay in the registry — never merge them.",
        related_brand="moka_and_co",
    ),
    Exclusion(
        domain="sanaahousecafe.com",
        reason="Legacy secondary domain of Sana'a Cafe — alias, not a separate brand.",
        related_brand="sanaa_cafe",
    ),
)


def get_brand(slug: str) -> Brand:
    for brand in BRANDS:
        if brand.slug == slug:
            return brand
    raise KeyError(f"unknown brand slug: {slug}")


def scraped_brands() -> tuple[Brand, ...]:
    return tuple(b for b in BRANDS if b.method == "scrape")


def manual_brands() -> tuple[Brand, ...]:
    return tuple(b for b in BRANDS if b.method == "manual")
