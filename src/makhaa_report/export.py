"""Mirror the database to flat CSVs after every run.

Column and row order come from db.dump_table so weekly git diffs stay
readable.
"""

import csv
import sqlite3
from pathlib import Path

from . import config, db

_TABLES = ("locations", "brands", "runs", "exclusions")


def export_all(conn: sqlite3.Connection, out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or config.EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in _TABLES:
        columns, rows = db.dump_table(conn, name)
        path = out_dir / f"{name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(tuple(r) for r in rows)
        written.append(path)
    return written
