"""Command-line interface.

Exit codes: 0 ok; 1 any brand failed or drifted; 2 usage error (argparse).
"""

import argparse
import logging
import sys

from . import db


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="makhaa-report",
        description="Census of US Yemeni coffee chain locations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="scrape all brands into SQLite (idempotent)")
    p_scrape.add_argument("--brand", action="append", dest="brands", metavar="SLUG",
                          help="limit to one brand (repeatable)")
    p_scrape.add_argument("--allow-drift", action="store_true",
                          help="write rows even when a brand's count is outside its band")

    sub.add_parser("geocode", help="fill missing coordinates via Census batch geocoder")

    p_export = sub.add_parser("export", help="mirror database to CSVs")
    p_export.add_argument("--out", default=None, metavar="DIR")

    p_report = sub.add_parser("report", help="generate the self-contained HTML report")
    p_report.add_argument("--out", default=None, metavar="FILE")

    p_diff = sub.add_parser("diff", help="compare two runs")
    p_diff.add_argument("run_a", type=int)
    p_diff.add_argument("run_b", type=int)

    args = parser.parse_args(argv)

    if args.command == "scrape":
        from .pipeline import run_scrape

        stats = run_scrape(db.connect(), brands=args.brands, allow_drift=args.allow_drift)
        print(
            f"run {stats.run_id}: {stats.total_rows} rows, "
            f"{len(stats.brands_succeeded)} brands ok, "
            f"{len(stats.brands_failed)} failed"
            + (f" ({', '.join(stats.brands_failed)})" if stats.brands_failed else "")
        )
        return 1 if stats.brands_failed else 0

    if args.command == "export":
        from pathlib import Path

        from .export import export_all

        for path in export_all(db.connect(), Path(args.out) if args.out else None):
            print(path)
        return 0

    if args.command == "geocode":
        print("geocode: not implemented yet", file=sys.stderr)
        return 1

    if args.command == "report":
        print("report: not implemented yet", file=sys.stderr)
        return 1

    # args.command == "diff" (argparse guarantees a valid subcommand)
    print("diff: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
