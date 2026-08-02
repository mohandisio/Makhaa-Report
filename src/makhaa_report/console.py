"""Terminal rendering. All human-facing output goes through here."""

import logging

from rich.console import Console, Group
from rich.live import Live
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.spinner import Spinner
from rich.table import Table

from . import geo
from .models import BrandResult, RunStats
from .registry import get_brand

console = Console()

_OUTCOME_STYLE = {
    "ok": ("done", "green"),
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


class ScrapeProgress:
    """The run summary, drawn from the start and filled in as brands finish.

    Every brand appears immediately as pending, so the shape of the run is
    visible before it is over; the last frame is the finished summary, so
    there is only one table rather than a progress display plus a report.
    """

    def __init__(self) -> None:
        self._order: list[str] = []
        self._results: dict[str, BrandResult] = {}
        self._active: str | None = None
        self._requests: dict[str, int] = {}
        self._live: Live | None = None
        self._run_id: int | None = None

    # --- events the pipeline emits -------------------------------------

    def start(self, run_id: int, slugs: list[str]) -> None:
        self._run_id = run_id
        self._order = list(slugs)
        self._refresh()

    def start_brand(self, slug: str) -> None:
        self._active = slug
        self._requests[slug] = 0
        self._refresh()

    def note_request(self, slug: str) -> None:
        self._requests[slug] = self._requests.get(slug, 0) + 1
        self._refresh()

    def finish_brand(self, result: BrandResult) -> None:
        self._results[result.slug] = result
        if self._active == result.slug:
            self._active = None
        self._refresh()

    # --- rendering ------------------------------------------------------

    def __enter__(self) -> "ScrapeProgress":
        self._live = Live(self.table(), console=console, refresh_per_second=12)
        self._live.start()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._live is not None:
            self._live.update(self.table())
            self._live.stop()
            self._live = None
            if not console.is_terminal:
                # Piped output ends the final frame mid-line; without this
                # the run tally is glued to the table's bottom border.
                console.line()

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.table())

    def _status(self, slug: str):
        result = self._results.get(slug)
        if result is not None:
            label, style = _OUTCOME_STYLE[result.outcome]
            return f"[{style}]{label}[/{style}]"
        if slug == self._active:
            count = self._requests.get(slug, 0)
            suffix = f" {count} requests" if count > 1 else ""
            return Spinner("dots", text=f"scraping{suffix}")  # inherits the row's blue
        return "[dim]pending[/dim]"

    def table(self) -> Table:
        title = f"Run {self._run_id}" if self._run_id else "Scrape"
        table = Table(title=title, title_justify="left", header_style="bold")
        table.add_column("Brand")
        table.add_column("Rows", justify="right")
        table.add_column("Status")
        table.add_column("Note", style="dim")

        for slug in self._order:
            brand = get_brand(slug)
            result = self._results.get(slug)
            if result is None:
                rows = "[dim]-[/dim]"
            elif result.outcome == "no_scraper":
                rows = "-"
            else:
                rows = str(result.rows)
            table.add_row(
                brand.display_name,
                rows,
                self._status(slug),
                result.note if result else "",
                style="blue" if slug == self._active else None,
            )
        return table


_VERDICT_STYLE = {
    "adopted": "green",
    "unchanged": "dim",
    "inexact": "yellow",
    "unmatched": "red",
}


class GeocodeProgress:
    """The address-resolution summary, filled in as brands are worked through.

    Same shape as ScrapeProgress: every brand is listed from the start, so
    the size of the job is visible before it finishes, and the last frame
    is the summary rather than a separate report.
    """

    def __init__(self) -> None:
        self._order: list[str] = []
        self._counts: dict[str, dict[str, int]] = {}
        self._coords: dict[str, int] = {}
        self._done: set[str] = set()
        self._live: Live | None = None
        self._caption: str = ""
        # Nominatim is capped at one request a second, so this is the one
        # stage with a wait worth showing — and a rate limit makes the
        # estimate honest rather than decorative.
        self._bar = Progress(
            TextColumn("[dim]OpenStreetMap[/dim]"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeRemainingColumn(),
            TextColumn("[dim]{task.fields[address]}[/dim]"),
            auto_refresh=False,
        )
        self._task: int | None = None

    # --- events ---------------------------------------------------------

    def start(self, slugs: list[str]) -> None:
        self._order = list(slugs)
        self._counts = {slug: {} for slug in slugs}
        self._refresh()

    def lookup_started(self, fresh: int, cached: int) -> None:
        if fresh:
            self._caption = f"asking Census about {fresh} addresses ({cached} cached)"
        else:
            self._caption = f"all {cached} addresses answered from cache"
        self._refresh()

    def lookup_finished(self) -> None:
        self._caption = ""
        self._refresh()

    def record(self, slug: str, verdict: str) -> None:
        counts = self._counts.setdefault(slug, {})
        counts[verdict] = counts.get(verdict, 0) + 1
        self._refresh()

    def coords(self, slug: str) -> None:
        self._coords[slug] = self._coords.get(slug, 0) + 1
        self._refresh()

    def fallback_started(self, total: int) -> None:
        self._task = self._bar.add_task("osm", total=total, address="")
        self._refresh()

    def fallback_step(self, address: str) -> None:
        if self._task is not None:
            self._bar.update(self._task, advance=1, address=address)
            self._refresh()

    def fallback_finished(self) -> None:
        if self._task is not None:
            self._bar.remove_task(self._task)
            self._task = None
        self._refresh()

    def finish_brand(self, slug: str) -> None:
        self._done.add(slug)
        self._refresh()

    # --- rendering ------------------------------------------------------

    def __enter__(self) -> "GeocodeProgress":
        self._live = Live(self._render(), console=console, refresh_per_second=12)
        self._live.start()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._live is not None:
            self._live.update(self._render())
            self._live.stop()
            self._live = None
            if not console.is_terminal:
                console.line()

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def _render(self):
        if self._task is None:
            return self.table()
        return Group(self.table(), self._bar)

    def table(self) -> Table:
        table = Table(title="Address resolution", title_justify="left",
                      header_style="bold", caption=self._caption or None,
                      caption_justify="left")
        table.add_column("Brand")
        table.add_column("Rows", justify="right")
        for verdict in geo.VERDICTS:
            table.add_column(verdict.capitalize(), justify="right",
                             style=_VERDICT_STYLE[verdict])
        table.add_column("+Coords", justify="right", style="cyan")
        table.add_column("Status")

        for slug in self._order:
            counts = self._counts.get(slug, {})
            total = sum(counts.values())
            if slug in self._done:
                status = "[green]done[/green]"
            elif total:
                status = Spinner("dots", text="resolving")
            else:
                status = "[dim]pending[/dim]"
            filled = self._coords.get(slug, 0)
            table.add_row(
                get_brand(slug).display_name,
                str(total) if total else "[dim]-[/dim]",
                *(str(counts.get(v, 0)) if counts.get(v) else "[dim]-[/dim]"
                  for v in geo.VERDICTS),
                f"+{filled}" if filled else "[dim]-[/dim]",
                status,
            )
        return table


def render_address_changes(stats, limit: int = 60) -> None:
    """Print what resolution did, in the order a reviewer wants to read it."""
    substantive = stats.substantive
    if substantive:
        table = Table(title="Addresses rewritten (beyond letter case)",
                      title_justify="left", header_style="bold")
        table.add_column("Brand", style="dim")
        table.add_column("Before")
        table.add_column("After", style="green")
        for change in substantive[:limit]:
            table.add_row(change.slug, change.before(), change.after())
        console.print(table)
        if len(substantive) > limit:
            console.print(f"[dim]... and {len(substantive) - limit} more[/dim]")

    if stats.cosmetic:
        console.print(
            f"[dim]{stats.cosmetic} further rows changed in letter case or "
            f"punctuation only.[/dim]"
        )

    unverified = set(stats.unverified)
    unresolved = stats.unresolved
    if unresolved:
        table = Table(
            title="Census could not confirm these", title_justify="left",
            header_style="bold",
            caption="OSM = OpenStreetMap knows the address; "
                    "no = neither source does",
            caption_justify="left",
        )
        table.add_column("Brand", style="dim")
        table.add_column("Census")
        table.add_column("OSM")
        table.add_column("Address")
        for change in unresolved[:limit]:
            address = change.before()
            found = address not in unverified
            table.add_row(
                change.slug,
                f"[{_VERDICT_STYLE[change.verdict]}]{change.verdict}[/]",
                "[green]yes[/green]" if found else "[red]no[/red]",
                address,
            )
        console.print(table)
        if len(unresolved) > limit:
            console.print(f"[dim]... and {len(unresolved) - limit} more[/dim]")


def render_geocode_summary(stats) -> None:
    counts = stats.counts
    parts = [f"{counts.get(v, 0)} {v}" for v in geo.VERDICTS]
    console.print(f"{stats.total} addresses: " + ", ".join(parts))
    if stats.collisions:
        console.print(
            f"[yellow]{len(stats.collisions)} rows resolved onto an address "
            f"another row already held and were folded into it[/]"
        )
    if stats.verified:
        verified = ", ".join(f"{n} by {src}" for src, n in sorted(stats.verified.items()))
        console.print(f"[green]addresses confirmed: {verified}[/]")
    if stats.unverified:
        console.print(
            f"[red]{len(stats.unverified)} addresses no source recognises[/]"
        )
    if stats.recorded:
        console.print(
            f"[dim]{len(stats.recorded)} corrections recorded in overrides.csv "
            f"so the next scrape keeps them[/dim]"
        )
    if stats.filled:
        filled = ", ".join(f"{n} from {src}" for src, n in sorted(stats.filled.items()))
        console.print(f"[cyan]coordinates added this run: {filled}[/]")
    if stats.still_dark:
        console.print(
            f"[red]{stats.still_dark} rows have no coordinates from any "
            f"source[/] [dim](flagged; patch them in overrides.csv)[/dim]"
        )
    if stats.flagged:
        console.print(f"[yellow]{len(stats.flagged)} rows flagged for review[/]")


_KIND_STYLE = {"unconfirmed": "yellow", "coordinate": "red"}


def render_sanitize_queue(findings) -> None:
    """The rows waiting on a person, worst first."""
    if not findings:
        console.print("[green]nothing to review — every row is confirmed[/]")
        return
    table = Table(title="Rows needing a human", title_justify="left",
                  header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Brand", style="dim")
    table.add_column("Why")
    table.add_column("Address")
    for i, f in enumerate(findings, 1):
        table.add_row(str(i), f.brand,
                      f"[{_KIND_STYLE[f.kind]}]{f.why}[/]", f.address)
    console.print(table)
    kinds = {}
    for f in findings:
        kinds[f.kind] = kinds.get(f.kind, 0) + 1
    console.print(
        f"{len(findings)} to review: "
        + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
    )


def render_scrape_summary(stats: RunStats, table: bool = True) -> None:
    """Print the run outcome. Skip the table when a live one already showed it."""
    if table:
        progress = ScrapeProgress()
        progress.start(stats.run_id, [r.slug for r in stats.results])
        for result in stats.results:
            progress.finish_brand(result)
        console.print(progress.table())

    failed = stats.brands_failed
    summary = f"{stats.total_rows} locations from {len(stats.brands_succeeded)} brands"
    if failed:
        console.print(f"[bold red]{summary}; {len(failed)} failed:[/] {', '.join(failed)}")
    else:
        console.print(f"[green]{summary}[/]")
