"""Brand registry: the 14 known chains, count bands, and lookalike exclusions.

Source of truth is this file, verified 2026-07-31 from each brand's own
locator. Bands double as scrape drift-check baselines. Re-verify counts
before tightening any band.
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
        notes="16 per-state pages /pages/<state>-locations; summary page is stale, ignore it. 243 claimed coming soon.",
    ),
    Brand(
        slug="qamaria",
        display_name="Qamaria Yemeni Coffee",
        locator_url="https://qamariacoffee.com",
        method="scrape",
        band=(32, 45),
        franchises=True,
        notes="Squarespace ?format=json. 800+ franchise applications claimed.",
    ),
    Brand(
        slug="qahwah_house",
        display_name="Qahwah House",
        locator_url="https://qahwahhouse.com",
        method="scrape",
        band=(24, 35),
        notes="/locations/<slug> pages discovered via sitemap.xml.",
    ),
    Brand(
        slug="moka_and_co",
        display_name="Moka & Co",
        locator_url="https://mokanco.com/pages/locations",
        method="scrape",
        band=(23, 35),
        notes="Two parallel URL structures on one domain — scrape exactly one or double-count. ~15 coming soon.",
    ),
    Brand(
        slug="shibam",
        display_name="Shibam Coffee Co.",
        locator_url="https://shibamcoffee.com",
        method="scrape",
        band=(18, 26),
        notes="WP REST /wp-json/wp/v2/pages?slug=our-locations&_fields=content. ~10 coming soon.",
    ),
    Brand(
        slug="arwa",
        display_name="Arwa Yemeni Coffee",
        locator_url="https://arwacoffee.com/locations",
        method="scrape",
        band=(10, 18),
        notes="~30 announced coming soon.",
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
        notes="1 open, 6 announced.",
    ),
    Brand(
        slug="mokafe",
        display_name="MOKAFÉ",
        locator_url="https://mymokafe.com",
        method="scrape",
        band=(1, 12),
        notes="Open count unresolved (2 or 10). Hand-resolve before publishing any number; tighten band then. Distinct company from Moka & Co.",
    ),
    Brand(
        slug="mohka_house",
        display_name="Mohka House",
        locator_url="",
        method="manual",
        band=(0, 5),
        hq="Oakland, CA",
        notes="No website. One store in Oakland. Hand-maintained CSV.",
    ),
    Brand(
        slug="sanaa_cafe",
        display_name="Sana'a Cafe",
        locator_url="https://thesanaacafe.com",
        method="manual",
        band=(0, 15),
        alt_domains=("sanaahousecafe.com",),
        notes=(
            "Locator provably incomplete (omits SF stores press confirms, plus "
            "Hayward and announced Long Beach); 'coming soon' labels unreliable "
            "(order-button slot). Hand-maintained CSV; 3 is a floor, not a count."
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


def scraped_brands() -> tuple[Brand, ...]:
    return tuple(b for b in BRANDS if b.method == "scrape")


def manual_brands() -> tuple[Brand, ...]:
    return tuple(b for b in BRANDS if b.method == "manual")
