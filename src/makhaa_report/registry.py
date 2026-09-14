"""Brand registry: the known chains and the lookalikes to keep out.

Nothing here claims to know how many stores a brand has. The scrape is
the source of truth for that, and a count written by hand is stale the
moment it is written.

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
        notes=(
            "WP REST /wp-json/wp/v2/pages?slug=our-locations returns the "
            "page as rendered HTML. Card headings are regional labels "
            "rather than cities, so the address is the identity. Stores "
            "announce themselves in prose (\"Soft opening coming soon\") "
            "with no dedicated marker. No coordinates published."
        ),
    ),
    Brand(
        slug="arwa",
        display_name="Arwa Yemeni Coffee",
        locator_url="https://arwacoffee.com/locations/",
        method="scrape",
        notes=(
            "WordPress; one section per store with an embedded Google "
            "map the coordinates come from. Contact paragraphs run "
            "address, email, phone. No announced stores are published "
            "here."
        ),
    ),
    Brand(
        slug="matari",
        display_name="Matari Coffee",
        locator_url="https://mataricoffee.com/locations",
        method="scrape",
        notes=(
            "One card per store. The Mississauga store is Canadian and "
            "falls out of the US address parse without special-casing. "
            "Three announced markets are published as a bare city and "
            "state with no street, so Matari's announced presence in TX "
            "and GA is not captured. The Hicksville store publishes a "
            "region where the city belongs (\"Hicksville, Long Isand\"), "
            "so its city reads wrong until corrected in overrides.csv. "
            "No coordinates published."
        ),
    ),
    Brand(
        slug="delah",
        display_name="Delah Coffee",
        locator_url="https://delahcoffee.com/locations/",
        method="scrape",
        notes=(
            "Elementor; per-store blocks carry no usable classes and "
            "two render inside embedded Google widgets, so the icon "
            "list is read instead — one \"City: address\" entry per "
            "store among phone, email and social entries. Only the one "
            "store linked to a full Maps place URL has coordinates. No "
            "announced stores are published here."
        ),
    ),
    Brand(
        slug="qatra",
        display_name="Qatra Coffee",
        locator_url="https://qatracoffee.com/",
        method="scrape",
        notes=(
            "qatracoffee.com is the Yemeni brand — NOT qatracafe.com "
            "(see exclusions). There is no locations page; /locations "
            "404s, so addresses are read off the home page, where each "
            "appears several times and is deduplicated. Only the store "
            "in the schema block has coordinates. No announced stores."
        ),
    ),
    Brand(
        slug="heyma",
        display_name="Heyma",
        locator_url="https://www.heymacoffeeca.com/locations",
        method="scrape",
        notes=(
            "Each store is a Google directions link whose text is the "
            "address and whose href carries the coordinates. Headings "
            "are street names, so the city is used as the name. Both "
            "stores publish the same phone number. No announced stores."
        ),
    ),
    Brand(
        slug="caffeena",
        display_name="Caffeena Coffee House",
        locator_url="https://caffeena.com/locations",
        method="scrape",
        notes=(
            "The page is split into \"Now Open Locations\" and \"Coming "
            "Soon Locations\" sections, so status comes from walking "
            "back to the nearest section heading. Addresses sit in "
            "plain paragraphs; no coordinates or phone numbers are "
            "published."
        ),
    ),
    Brand(
        slug="mokafe",
        display_name="MOKAFÉ",
        locator_url="https://mymokafe.com/pages/locations",
        method="scrape",
        notes=(
            "Each store is one bold line combining name and address, "
            "split on the colon or, failing that, the bullet. The site "
            "claims ten storefronts, including several branded MOKAFÉ "
            "to Go; those count as stores, settling the earlier dispute "
            "over the total. Distinct company from Moka & Co. No "
            "coordinates published."
        ),
    ),
    Brand(
        slug="port",
        display_name="Port Coffee Co.",
        locator_url="https://portcoffeeco.com",
        method="scrape",
        hq="Louisiana",
        notes=(
            "Single-page app: the shell HTML is empty, but the store "
            "records live in the JS bundle it loads, with a status "
            "field and Maps place links carrying coordinates. Fragile "
            "by nature — a rebuild that changes how the data is "
            "written breaks the parse, and nothing but the fixture "
            "test will say so."
        ),
    ),
    Brand(
        slug="qishr",
        display_name="Qishr Coffee House",
        locator_url="https://qishrcoffeehouse.co",
        method="scrape",
        notes=(
            "Single-page app with no store list — the one cafe's "
            "address is inlined in the footer markup, so it arrives as "
            "two adjacent string literals in the JS bundle. Fragile by "
            "nature: a rebuild breaks the parse silently."
        ),
    ),
    Brand(
        slug="house_of_mokhah",
        display_name="House of Mokhah",
        locator_url="https://www.houseofmokhaycc.com/cafes",
        method="scrape",
        notes=(
            "Squarespace; the address sits in one element with the "
            "street and city line as separate text nodes. A further "
            "location is announced in prose with no address, so it is "
            "not captured."
        ),
    ),
    Brand(
        slug="biladi",
        display_name="Biladi Coffee House",
        locator_url="https://biladicoffeehouse.com",
        method="scrape",
        franchises=True,
        notes=(
            "Elementor; addresses carry a pipe-separated label prefix, "
            "stripped by the address parser."
        ),
    ),
    Brand(
        slug="original_mocha",
        display_name="Original Mocha",
        locator_url="https://originalmocha.com",
        method="scrape",
        franchises=True,
        notes=(
            "WordPress with a page per store. The sitemap omits them "
            "and the home page carries no address, so store pages are "
            "found by their city-then-state slug — new stores appear "
            "without anyone editing a list."
        ),
    ),
    Brand(
        slug="queen",
        display_name="Queen Yemeni Coffee",
        locator_url="https://queencoffeehouse.com",
        method="scrape",
        notes="Elementor; a middot separates street from city.",
    ),
    Brand(
        slug="socotra",
        display_name="Socotra Coffee House",
        locator_url="https://socotracoffeehouse.framer.website",
        method="scrape",
        notes="Framer, but server-rendered; the address sits whole in a map link.",
    ),
    Brand(
        slug="mochabox",
        display_name="MochaBox Coffee",
        locator_url="https://mochaboxcoffee.com",
        method="scrape",
        notes=(
            "Wix, with street and city in separate elements. Publishes "
            "a six-digit postcode, which is dropped rather than "
            "trimmed into a plausible wrong ZIP."
        ),
    ),
    Brand(
        slug="mohka_house",
        display_name="Mohka House",
        locator_url="",
        method="manual",
        hq="Oakland, CA",
        notes=(
            "No website of its own — only a Yelp listing, which is a "
            "third-party aggregator rather than the brand's own site, "
            "so its stores are added by manual entry into data/manual/mohka_house.csv."
        ),
    ),
    Brand(
        slug="sanaa_cafe",
        display_name="Sana'a Cafe",
        locator_url="https://thesanaacafe.com",
        method="scrape",
        alt_domains=("sanaahousecafe.com",),
        notes=(
            "Divi blurbs in runs of four: heading, address, phone, hours. "
            "Behind a WAF that always answers in Brotli, hence the brotli "
            "dependency. Treat the total as a floor, not a count: the "
            "locator omits stores the press confirms are trading, and it "
            "publishes Sacramento under the Oakland Broadway address, so "
            "that row is dropped and re-added from overrides.csv with "
            "the real address."
        ),
    ),
    Brand(
        slug="jabal",
        display_name="Jabal Coffee House",
        locator_url="https://jabalcoffeehouse.com/pages/locations",
        method="scrape",
        notes=(
            "Shopify map cards, each with a name and an address paragraph "
            "whose lines are joined by <br> rather than split into "
            "elements. City-only \"City, ST\" teasers with no street "
            "number are announcements, not broken addresses, and are "
            "skipped before parsing; a Canadian store (plus two more "
            "city-only Canadian teasers) falls out of the US address "
            "parse instead. \"Soft Opening\" wording means the store is "
            "already trading — only \"coming\" wording marks a row "
            "coming_soon."
        ),
    ),
    Brand(
        slug="mocha_point",
        display_name="Mocha Point Coffee",
        locator_url="https://mochapointcoffee.com/locations/",
        method="scrape",
        notes=(
            "Elementor page with no stable classes, so the address is "
            "read as plain text rather than through a selector. A "
            "second unit, \"Kansas\", is only a nav link to an Instagram "
            "profile with no published street address, so it never "
            "produces a row. No coming-soon marker, phone, hours or map "
            "embed is published."
        ),
    ),
    Brand(
        slug="bayt_almocha",
        display_name="Bayt Almocha",
        locator_url="https://baytalmocha.com/find-location",
        method="scrape",
        notes=(
            "Every store's address and coordinates sit in an inline "
            "Alpine.js `staticPoints` JSON array on the /find-location "
            "page rather than a separate API. Punctuation is "
            "inconsistent between records; one store publishes two ZIPs "
            "glued onto the same tail, and the one next to the state is "
            "kept. The page's \"Closed\"/\"Open until\" labels are live "
            "clocks, not a status field, so every row is recorded open."
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
    Exclusion(
        domain="motwcoffee.com",
        reason="MOTW Coffee & Pastries has 20+ locations selling Yemeni chai, but it is a pan-Muslim brand, not Yemeni-founded, so it is not part of the census.",
    ),
    Exclusion(
        domain="portofmokha.com",
        reason="Port of Mokha is a roaster and importer, not a cafe chain. Its name sits close to Port Coffee Co. (portcoffeeco.com).",
        related_brand="port",
    ),
)


def get_brand(slug: str) -> Brand:
    for brand in BRANDS:
        if brand.slug == slug:
            return brand
    raise KeyError(f"unknown brand slug: {slug}")


def scraped_brands(counts: dict[str, int] | None = None) -> tuple[Brand, ...]:
    """Brands with a scraper, biggest first.

    Ordered by how many stores each returned last time, so a sweep does
    the brands that matter most while someone is still watching. Brands
    never scraped fall back to registry order.
    """
    brands = [b for b in BRANDS if b.method == "scrape"]
    if not counts:
        return tuple(brands)
    order = {b.slug: i for i, b in enumerate(BRANDS)}
    return tuple(sorted(brands, key=lambda b: (-counts.get(b.slug, 0), order[b.slug])))


def manual_brands() -> tuple[Brand, ...]:
    return tuple(b for b in BRANDS if b.method == "manual")
