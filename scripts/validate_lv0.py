#!/usr/bin/env python3
"""Validate a Lv0 master CSV.

Rules:
- Required columns: ID, 林道名, 取得元
- IDs must be AAA-000000 format
- No duplicate IDs
- No duplicate road names within the same file
- No empty required values
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REQUIRED = ["ID", "林道名", "取得元"]
ID_RE = re.compile(r"^[A-Z]{3}-\d{6}$")


def fail(messages: list[str]) -> int:
    for message in messages:
        print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_lv0.py <csv_path>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        return fail([f"File not found: {path}"])

    errors: list[str] = []
    ids: set[str] = set()
    names: set[str] = set()
    count = 0

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED:
            errors.append(f"Columns must be exactly {REQUIRED}, got {reader.fieldnames}")
        for line_no, row in enumerate(reader, start=2):
            count += 1
            for column in REQUIRED:
                if not (row.get(column) or "").strip():
                    errors.append(f"Line {line_no}: empty {column}")

            road_id = (row.get("ID") or "").strip()
            name = (row.get("林道名") or "").strip()

            if road_id and not ID_RE.fullmatch(road_id):
                errors.append(f"Line {line_no}: invalid ID {road_id!r}")
            if road_id in ids:
                errors.append(f"Line {line_no}: duplicate ID {road_id}")
            ids.add(road_id)

            if name in names:
                errors.append(f"Line {line_no}: duplicate road name {name}")
            names.add(name)

    if errors:
        return fail(errors)

    print(f"OK: {path} ({count} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
