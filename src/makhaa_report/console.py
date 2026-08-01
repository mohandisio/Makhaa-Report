"""Terminal rendering. All human-facing output goes through here."""

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .models import RunStats
from .registry import get_brand

console = Console()

_OUTCOME_STYLE = {
    "ok": ("ok", "green"),
    "drift": ("DRIFT", "bold red"),
    "error": ("failed", "bold red"),
    "no_scraper": ("no scraper", "dim"),
}


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


def render_scrape_summary(stats: RunStats) -> None:
    table = Table(title=f"Run {stats.run_id}", title_justify="left", header_style="bold")
    table.add_column("Brand")
    table.add_column("Rows", justify="right")
    table.add_column("Expected", justify="right", style="dim")
    table.add_column("Status")
    table.add_column("Note", style="dim")

    for result in stats.results:
        brand = get_brand(result.slug)
        label, style = _OUTCOME_STYLE[result.outcome]
        table.add_row(
            brand.display_name,
            "-" if result.outcome == "no_scraper" else str(result.rows),
            f"{brand.band[0]}-{brand.band[1]}" if brand.method == "scrape" else "-",
            f"[{style}]{label}[/{style}]",
            result.note,
        )

    console.print(table)

    failed = stats.brands_failed
    summary = f"{stats.total_rows} locations from {len(stats.brands_succeeded)} brands"
    if failed:
        console.print(f"[bold red]{summary}; {len(failed)} failed:[/] {', '.join(failed)}")
    else:
        console.print(f"[green]{summary}[/]")
