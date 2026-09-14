"""Command-line interface.

Exit codes: 0 ok; 1 any brand failed; 2 usage error (argparse).
"""

import argparse
import sys

from . import db
from .console import ScrapeProgress, console, render_scrape_summary, setup_logging


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(
        prog="makhaa-report",
        description="Census of US Yemeni coffee chain locations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="scrape all brands into SQLite (idempotent)")
    p_scrape.add_argument("--brand", action="append", dest="brands", metavar="SLUG",
                          help="limit to one brand (repeatable)")

    p_manual = sub.add_parser(
        "manual-entry",
        help="add a store by hand for a brand with no scrapable locator",
    )
    p_manual.add_argument(
        "fields",
        nargs="+",
        metavar="FIELD",
        help='key=value pairs or one JSON object, e.g. brand=mohka_house '
             'street="123 Grand Ave" city=Oakland state=CA',
    )

    p_geocode = sub.add_parser(
        "geocode", help="resolve addresses against the Census geocoder"
    )
    p_geocode.add_argument("--dry-run", action="store_true",
                           help="show what would change, write nothing")

    p_sanitize = sub.add_parser(
        "sanitize", help="review the rows a geocoder could not settle"
    )
    p_sanitize.add_argument("--list", action="store_true", dest="list_only",
                            help="print the queue and exit")
    p_sanitize.add_argument("--adopt-coordinates", action="store_true",
                            help="replace locator coordinates that disagree "
                                 "with an exact census match")
    p_sanitize.add_argument("--dry-run", action="store_true",
                            help="show what would change, write nothing")

    p_export = sub.add_parser("export", help="mirror database to CSVs")
    p_export.add_argument("--out", default=None, metavar="DIR")

    p_report = sub.add_parser("report", help="generate the self-contained HTML report")
    p_report.add_argument("--out", default=None, metavar="FILE")

    p_diff = sub.add_parser("diff", help="compare two runs")
    p_diff.add_argument("run_a", type=int)
    p_diff.add_argument("run_b", type=int)

    args = parser.parse_args(argv)

    if args.command == "scrape":
        from . import config
        from .confirm import AddressConfirmer
        from .pipeline import run_scrape

        with ScrapeProgress() as progress:
            stats = run_scrape(
                db.connect(),
                brands=args.brands,
                progress=progress,
                confirmer=AddressConfirmer(config.GEO_DIR),
            )
        # The live table's last frame is the summary; only the tally is left.
        render_scrape_summary(stats, table=False)
        return 1 if stats.brands_failed else 0

    if args.command == "manual-entry":
        from . import config
        from .confirm import AddressConfirmer
        from .manual import ManualEntryError, append_entry, parse_entry
        from .pipeline import run_scrape

        try:
            record = parse_entry(args.fields)
            path = append_entry(record)
        except ManualEntryError as exc:
            console.print(f"[bold red]manual entry rejected:[/] {exc}")
            return 2
        console.print(f"[dim]wrote[/] {path}")
        # Load the brand straight back through the normal path, so the
        # row is normalized, snapshotted and exported like any other.
        stats = run_scrape(
            db.connect(),
            brands=[record["brand"]],
            confirmer=AddressConfirmer(config.GEO_DIR),
        )
        render_scrape_summary(stats)
        return 1 if stats.brands_failed else 0

    if args.command == "geocode":
        from .console import (
            GeocodeProgress, render_address_changes, render_geocode_summary,
        )
        from .geocode import run_geocode

        with GeocodeProgress() as progress:
            stats = run_geocode(db.connect(), dry_run=args.dry_run, progress=progress)
        render_address_changes(stats)
        render_geocode_summary(stats)
        if args.dry_run:
            console.print("[yellow]dry run — nothing written[/]")
        return 0

    if args.command == "sanitize":
        from .console import render_sanitize_queue
        from .sanitize import find_problems

        from .sanitize import adopt_coordinates

        conn = db.connect()
        findings = find_problems(conn)
        render_sanitize_queue(findings)
        if args.list_only:
            return 0
        if args.adopt_coordinates:
            adopted = adopt_coordinates(conn, findings, dry_run=args.dry_run)
            for f in adopted:
                console.print(
                    f"[green]{f.brand}[/] {f.address} "
                    f"[dim]{f.lat:.4f},{f.lon:.4f} -> "
                    f"{f.census.lat:.4f},{f.census.lon:.4f} ({f.drift:.0f} km)[/dim]"
                )
            console.print(f"{len(adopted)} coordinates adopted from census")
            if args.dry_run:
                console.print("[yellow]dry run — nothing written[/]")
            return 0
        console.print(
            "[dim]addresses are corrected one at a time; "
            "use --adopt-coordinates for the mechanical fixes[/dim]"
        )
        return 0

    if args.command == "export":
        from pathlib import Path

        from .export import export_all

        for path in export_all(db.connect(), Path(args.out) if args.out else None):
            console.print(f"[dim]wrote[/] {path}")
        return 0

    if args.command == "report":
        from pathlib import Path

        from .report import write_report

        path = write_report(db.connect(), Path(args.out) if args.out else None)
        console.print(f"[dim]wrote[/] {path}")
        return 0

    not_implemented = {
        "diff": "compare two runs",
    }
    console.print(
        f"[yellow]{args.command}[/] ({not_implemented[args.command]}) is not implemented yet"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
