"""Self-contained HTML report generated from the census database.

Aggregation functions are pure reads: connection in, JSON-serializable
dicts and lists out. The HTML itself lives in templates/report.html.j2.
"""

import sqlite3

from .models import STATUSES

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
        """SELECT l.brand AS slug, b.display_name,
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
