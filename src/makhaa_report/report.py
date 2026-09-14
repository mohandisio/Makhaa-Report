"""Self-contained HTML report generated from the census database.

Aggregation functions are pure reads: connection in, JSON-serializable
dicts and lists out. The HTML itself lives in templates/report.html.j2.
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, PackageLoader

from . import config
from .geo import distance_km
from .models import STATUSES, utcnow_iso

# Okabe-Ito palette: colorblind-safe, distinct on a light map background.
PALETTE = ("#E69F00", "#56B4E9", "#009E73", "#F0E442",
           "#0072B2", "#D55E00", "#CC79A7", "#000000")
OTHER_COLOR = "#9aa0a6"
TOP_BRANDS = 8


def headline_stats(conn: sqlite3.Connection) -> dict:
    """Total, per-status counts (every status present), brand/state counts."""
    stats = {"total": 0, "brands": 0, "states": 0, **{s: 0 for s in STATUSES}}
    row = conn.execute(
        "SELECT COUNT(*) total, COUNT(DISTINCT brand) brands, "
        "COUNT(DISTINCT state) states FROM locations"
    ).fetchone()
    stats.update(total=row["total"], brands=row["brands"], states=row["states"])
    for r in conn.execute("SELECT status, COUNT(*) n FROM locations GROUP BY status"):
        stats[r["status"]] = r["n"]
    return stats


def shop_rows(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    """(mapped, unmapped) shop dicts; rows without coordinates are listed,
    never dropped."""
    rows = conn.execute(
        """SELECT l.uid, l.brand, b.display_name AS brand_name, l.street, l.city,
                  l.state, l.postal, l.lat, l.lon, l.status, l.phone, l.hours
           FROM locations l JOIN brands b ON b.slug = l.brand
           ORDER BY l.brand, l.state, l.city, l.street"""
    ).fetchall()
    mapped, unmapped = [], []
    for r in rows:
        d = dict(r)
        (mapped if d["lat"] is not None and d["lon"] is not None else unmapped).append(d)
    return mapped, unmapped


def brand_table(conn: sqlite3.Connection) -> list[dict]:
    """Per-brand league table, busiest first. The display-name tiebreak keeps
    the order — and therefore the color assignment — deterministic."""
    rows = conn.execute(
        """SELECT l.brand AS slug, b.display_name, b.franchises,
                  COUNT(*) AS total,
                  SUM(l.status = 'open') AS open,
                  SUM(l.status = 'coming_soon') AS coming_soon,
                  COUNT(DISTINCT l.state) AS states
           FROM locations l JOIN brands b ON b.slug = l.brand
           GROUP BY l.brand
           ORDER BY total DESC, b.display_name ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def brand_colors(brands: list[dict]) -> dict[str, str]:
    """First TOP_BRANDS slugs of the league table get palette colors,
    the long tail shares one gray."""
    colors = {b["slug"]: OTHER_COLOR for b in brands}
    for brand, color in zip(brands[:TOP_BRANDS], PALETTE):
        colors[brand["slug"]] = color
    return colors


def state_counts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT state, COUNT(*) AS total FROM locations "
        "GROUP BY state ORDER BY total DESC, state ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def status_counts(conn: sqlite3.Connection) -> list[dict]:
    """Counts in STATUSES vocabulary order; only statuses present in data."""
    by_status = {
        r["status"]: r["n"]
        for r in conn.execute("SELECT status, COUNT(*) n FROM locations GROUP BY status")
    }
    return [{"status": s, "total": by_status[s]} for s in STATUSES if s in by_status]


def top_cities(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    rows = conn.execute(
        """SELECT city || ', ' || state AS label, COUNT(*) AS total,
                  COUNT(DISTINCT brand) AS brands
           FROM locations GROUP BY city, state
           ORDER BY total DESC, city ASC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def city_diversity(conn: sqlite3.Connection, limit: int = 15) -> list[dict]:
    """Cities ranked by distinct brands — the multi-brand hubs."""
    rows = conn.execute(
        """SELECT city || ', ' || state AS label,
                  COUNT(DISTINCT brand) AS brands, COUNT(*) AS total
           FROM locations GROUP BY city, state
           ORDER BY brands DESC, total DESC, city ASC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _metro_from_shops(name: str, shops: list[dict]) -> dict:
    total = len(shops)
    brand_counts: dict[str, dict] = {}
    for s in shops:
        b = brand_counts.setdefault(
            s["slug"], {"slug": s["slug"], "display_name": s["display_name"], "count": 0}
        )
        b["count"] += 1
    brands = sorted(brand_counts.values(), key=lambda b: (-b["count"], b["display_name"]))
    dates = [s["opened_date"] for s in shops if s["opened_date"]]
    return {
        "name": name,
        "center": {
            "lat": sum(s["lat"] for s in shops) / total,
            "lon": sum(s["lon"] for s in shops) / total,
        },
        "uids": [s["uid"] for s in shops],
        "total": total,
        "open": sum(1 for s in shops if s["status"] == "open"),
        "coming_soon": sum(1 for s in shops if s["status"] == "coming_soon"),
        "brands": brands,
        "top_share": round(brands[0]["count"] / total, 2) if brands else 0.0,
        "first_opening": min(dates) if dates else None,
        "dated": len(dates),
    }


def metro_areas(conn: sqlite3.Connection, *, radius_km: float = 40.0,
                limit: int = 8) -> list[dict]:
    """Metro clusters derived from the data, not a hand-curated list.

    Greedy by city size: the busiest not-yet-absorbed city claims every
    still-unassigned mapped shop within `radius_km` of its centroid, and
    is named after that city. Repeats until cities are exhausted.
    """
    rows = conn.execute(
        """SELECT l.uid, l.brand AS slug, b.display_name, l.city, l.state,
                  l.lat, l.lon, l.status, l.opened_date
           FROM locations l JOIN brands b ON b.slug = l.brand
           WHERE l.lat IS NOT NULL AND l.lon IS NOT NULL"""
    ).fetchall()
    shops = [dict(r) for r in rows]

    by_city: dict[tuple[str, str], list[dict]] = {}
    for s in shops:
        by_city.setdefault((s["city"], s["state"]), []).append(s)

    cities = [
        {
            "city": city, "state": state,
            "lat": sum(s["lat"] for s in members) / len(members),
            "lon": sum(s["lon"] for s in members) / len(members),
            "count": len(members),
        }
        for (city, state), members in by_city.items()
    ]
    cities.sort(key=lambda c: (-c["count"], c["city"], c["state"]))

    assigned: set[str] = set()
    metros = []
    for c in cities:
        city_uids = {s["uid"] for s in by_city[(c["city"], c["state"])]}
        if city_uids <= assigned:
            continue  # already absorbed by a bigger metro
        near = [
            s for s in shops
            if s["uid"] not in assigned
            and distance_km(c["lat"], c["lon"], s["lat"], s["lon"]) <= radius_km
        ]
        if not near:
            continue
        assigned.update(s["uid"] for s in near)
        metros.append(_metro_from_shops(f"{c['city']}, {c['state']}", near))

    metros.sort(key=lambda m: (-m["total"], m["name"]))
    return metros[:limit]


def coming_soon_by_state(conn: sqlite3.Connection) -> list[dict]:
    """Announced openings as (state, brand) rows; the page stacks them."""
    rows = conn.execute(
        """SELECT l.state, l.brand, b.display_name AS brand_name, COUNT(*) AS total
           FROM locations l JOIN brands b ON b.slug = l.brand
           WHERE l.status = 'coming_soon'
           GROUP BY l.state, l.brand ORDER BY l.state, l.brand"""
    ).fetchall()
    return [dict(r) for r in rows]


def market_concentration(conn: sqlite3.Connection, min_shops: int = 5) -> list[dict]:
    """Per state (with min_shops+), the leading brand and its share of the
    state's shops. A tie keeps the alphabetically-first brand."""
    rows = conn.execute(
        """WITH counts AS (
             SELECT state, brand, COUNT(*) AS n FROM locations GROUP BY state, brand
           ), totals AS (
             SELECT state, SUM(n) AS total FROM counts GROUP BY state
           )
           SELECT c.state, b.display_name AS leader, c.n AS leader_shops, t.total
           FROM counts c
           JOIN totals t ON t.state = c.state
           JOIN brands b ON b.slug = c.brand
           WHERE t.total >= ?
             AND c.n = (SELECT MAX(n) FROM counts c2 WHERE c2.state = c.state)
           ORDER BY CAST(c.n AS REAL) / t.total DESC, c.state, b.display_name""",
        (min_shops,),
    ).fetchall()
    seen: set[str] = set()
    out = []
    for r in rows:
        if r["state"] in seen:
            continue
        seen.add(r["state"])
        d = dict(r)
        d["share"] = round(d["leader_shops"] / d["total"], 3)
        out.append(d)
    return out


def openings_by_year(conn: sqlite3.Connection) -> dict:
    """Dated shop openings grouped by year, stacked by brand.

    Only brands with at least one dated opening appear in `series`; brands
    outside the league table's top TOP_BRANDS are folded into one "other"
    entry, matching the palette assignment in `brand_colors`.
    """
    brands = brand_table(conn)
    top_slugs = {b["slug"] for b in brands[:TOP_BRANDS]}
    top_names = {b["slug"]: b["display_name"] for b in brands[:TOP_BRANDS]}

    rows = conn.execute(
        """SELECT l.brand AS slug, substr(l.opened_date, 1, 4) AS year,
                  COUNT(*) AS n
           FROM locations l
           WHERE l.opened_date IS NOT NULL
           GROUP BY l.brand, year"""
    ).fetchall()

    years = sorted({r["year"] for r in rows})
    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        key = r["slug"] if r["slug"] in top_slugs else "other"
        buckets.setdefault(key, {})
        buckets[key][r["year"]] = buckets[key].get(r["year"], 0) + r["n"]

    order = [b["slug"] for b in brands[:TOP_BRANDS] if b["slug"] in buckets]
    if "other" in buckets:
        order.append("other")

    series = [
        {
            "slug": key,
            "display_name": top_names.get(key, "Other brands"),
            "counts": [buckets[key].get(y, 0) for y in years],
        }
        for key in order
    ]

    dated = sum(r["n"] for r in rows)
    total = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    confidence = {
        r["opened_confidence"]: r["n"]
        for r in conn.execute(
            """SELECT opened_confidence, COUNT(*) AS n FROM locations
               WHERE opened_date IS NOT NULL GROUP BY opened_confidence"""
        )
    }
    return {
        "years": years,
        "series": series,
        "dated": dated,
        "undated": total - dated,
        "confidence": confidence,
    }


def data_as_of(conn: sqlite3.Connection) -> str | None:
    """When the data itself last changed: the newest scrape run."""
    row = conn.execute(
        "SELECT MAX(COALESCE(finished_at, started_at)) FROM runs"
    ).fetchone()
    return row[0]


def faq(conn: sqlite3.Connection, today: str | None = None) -> list[dict]:
    """Plain-language Q&A computed straight from the database, never
    hand-written numbers. `today` (YYYY-MM-DD) defaults to the current UTC
    date and exists so tests are deterministic."""
    today_date = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
    entries = []

    brands = brand_table(conn)
    leader = brands[0]
    entries.append({
        "question": "Which brand has the most shops, and how many states is it in?",
        "answer": f"{leader['display_name']}: {leader['total']} shops "
                  f"across {leader['states']} states.",
        "note": "Counted from the brand's own locator on the last run.",
    })

    cutoff_month = f"{today_date.year - 1:04d}-{today_date.month:02d}"
    recent = conn.execute(
        """SELECT l.brand AS slug, b.display_name, COUNT(*) AS n
           FROM locations l JOIN brands b ON b.slug = l.brand
           WHERE l.opened_date IS NOT NULL AND l.opened_date >= ?
           GROUP BY l.brand ORDER BY n DESC, b.display_name ASC""",
        (cutoff_month,),
    ).fetchall()
    if recent:
        recent_leader = recent[0]
        answer2 = (f"{sum(r['n'] for r in recent)} shops; "
                   f"{recent_leader['display_name']} opened the most ({recent_leader['n']}).")
    else:
        answer2 = "No shops have a dated opening in the last 12 months."
    dated = conn.execute(
        "SELECT COUNT(*) FROM locations WHERE opened_date IS NOT NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    entries.append({
        "question": "How many shops opened in the last 12 months, "
                    "and which brand opened the most?",
        "answer": answer2,
        "note": f"{dated} of {total} shops have a dated opening; "
                "dates come from permit and licence records.",
    })

    coming = coming_soon_by_state(conn)
    by_state: dict[str, int] = {}
    for r in coming:
        by_state[r["state"]] = by_state.get(r["state"], 0) + r["total"]
    top_states = sorted(by_state.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    if top_states:
        where = ", ".join(f"{state} ({n})" for state, n in top_states)
        answer3 = f"{sum(by_state.values())} announced; most in {where}."
    else:
        answer3 = "No announced shops yet."
    entries.append({
        "question": "How many announced shops are not open yet, and where?",
        "answer": answer3,
        "note": "Only brands whose locator marks announced stores are counted.",
    })

    diverse = city_diversity(conn, limit=1)
    if diverse:
        top_city = diverse[0]
        city, state = top_city["label"].split(", ")
        names = [
            r[0] for r in conn.execute(
                """SELECT DISTINCT b.display_name FROM locations l
                   JOIN brands b ON b.slug = l.brand
                   WHERE l.city = ? AND l.state = ? ORDER BY b.display_name""",
                (city, state),
            )
        ]
        answer4 = f"{top_city['label']}: {top_city['brands']} brands ({', '.join(names)})."
    else:
        answer4 = "No cities yet."
    entries.append({
        "question": "Which city has the most competing brands?",
        "answer": answer4,
        "note": "Brands with at least one shop in that city.",
    })

    as_of = data_as_of(conn)
    cutoff_90 = (today_date - timedelta(days=90)).isoformat()
    runs_90 = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE finished_at IS NOT NULL "
        "AND substr(finished_at, 1, 10) >= ?",
        (cutoff_90,),
    ).fetchone()[0]
    entries.append({
        "question": "How current is this?",
        "answer": f"Last run {as_of[:10] if as_of else 'never'}; "
                  f"{runs_90} runs in the last 90 days.",
        "note": "Runs are weekly; a store not seen on a run keeps its last-seen "
                "date rather than being deleted.",
    })

    geo = {
        r["geocode_source"]: r["n"]
        for r in conn.execute(
            "SELECT geocode_source, COUNT(*) AS n FROM locations GROUP BY geocode_source"
        )
    }
    flagged = conn.execute(
        "SELECT COUNT(*) FROM locations WHERE geocode_flagged"
    ).fetchone()[0]
    entries.append({
        "question": "How verified are the addresses?",
        "answer": (f"{geo.get('census', 0)} placed by the Census geocoder, "
                   f"{geo.get('nominatim', 0)} by OpenStreetMap, "
                   f"{geo.get('locator', 0)} from the brand's own coordinates, "
                   f"{geo.get('manual', 0)} set by hand; {flagged} flagged for review."),
        "note": "Every address is checked against the Census geocoder before it "
                "is stored; OpenStreetMap is asked about the ones Census cannot confirm.",
    })

    return entries


def build_context(conn: sqlite3.Connection, generated_at: str | None = None) -> dict:
    """Everything the template needs. `payload` is the subset the page's
    JavaScript reads; the rest renders server-side."""
    mapped, unmapped = shop_rows(conn)
    brands = brand_table(conn)
    colors = brand_colors(brands)
    statuses = status_counts(conn)
    generated_at = generated_at or utcnow_iso()
    # The payload ships to the public page; keep it to what the pins and
    # popups display, nothing that reads like a raw dataset row.
    public = ("brand", "brand_name", "street", "city", "state",
              "lat", "lon", "status", "phone", "hours")
    payload_shops = [{k: s[k] for k in public} for s in mapped]
    shop_index_by_uid = {s["uid"]: i for i, s in enumerate(mapped)}
    payload_metros = []
    for metro in metro_areas(conn):
        m = {k: v for k, v in metro.items() if k != "uids"}
        m["shops"] = [shop_index_by_uid[uid] for uid in metro["uids"]
                      if uid in shop_index_by_uid]
        payload_metros.append(m)
    return {
        "generated_at": generated_at,
        "data_as_of": data_as_of(conn),
        "headline": headline_stats(conn),
        "brands": brands,
        "states": state_counts(conn),
        "unmapped": unmapped,
        "faq": faq(conn, generated_at[:10]),
        "payload": {
            "shops": payload_shops,
            "brands": brands,
            "brand_colors": colors,
            "states": state_counts(conn),
            "statuses": statuses,
            "top_cities": top_cities(conn),
            "city_diversity": city_diversity(conn),
            "coming_soon": coming_soon_by_state(conn),
            "concentration": market_concentration(conn),
            "openings_by_year": openings_by_year(conn),
            "metros": payload_metros,
        },
    }


def render_report(context: dict) -> str:
    env = Environment(loader=PackageLoader("makhaa_report"), autoescape=True)
    return env.get_template("report.html.j2").render(**context)


def write_report(conn: sqlite3.Connection, out: Path | None = None,
                 generated_at: str | None = None) -> Path:
    out = out or config.REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(build_context(conn, generated_at)), encoding="utf-8")
    return out
