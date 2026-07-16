#!/usr/bin/env python3
"""Validate a Lv0 master CSV.

Rules:
- Required columns include: ID, 林道名, 取得元
- IDs must be AAA-000000 format
- No duplicate IDs
- Legacy three-column files cannot contain duplicate road names
- OSM-first extended files use a unique candidate key for same-name roads
- No empty required values
- Coordinates must be a valid pair when present
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
    candidate_keys: set[str] = set()
    count = 0

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing_columns = [column for column in REQUIRED if column not in fieldnames]
        if missing_columns:
            errors.append(f"Missing required columns: {missing_columns}; got {fieldnames}")
        extended = "候補キー" in fieldnames
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

            if not extended and name in names:
                errors.append(f"Line {line_no}: duplicate road name {name}")
            names.add(name)

            if extended:
                candidate_key = (row.get("候補キー") or "").strip()
                if not candidate_key:
                    errors.append(f"Line {line_no}: empty 候補キー")
                elif candidate_key in candidate_keys:
                    errors.append(f"Line {line_no}: duplicate 候補キー {candidate_key}")
                candidate_keys.add(candidate_key)

                lat_text = (row.get("代表緯度") or "").strip()
                lon_text = (row.get("代表経度") or "").strip()
                if bool(lat_text) != bool(lon_text):
                    errors.append(f"Line {line_no}: representative coordinate pair is incomplete")
                if lat_text and lon_text:
                    try:
                        lat = float(lat_text)
                        lon = float(lon_text)
                    except ValueError:
                        errors.append(f"Line {line_no}: invalid representative coordinates")
                    else:
                        if not 20 <= lat <= 50 or not 120 <= lon <= 155:
                            errors.append(f"Line {line_no}: representative coordinates are outside Japan")

                osm_ids = (row.get("OSM_ID") or "").strip()
                if osm_ids and not re.fullmatch(r"\d+(?:/\d+)*", osm_ids):
                    errors.append(f"Line {line_no}: invalid OSM_ID {osm_ids!r}")
                if osm_ids and (not lat_text or not lon_text):
                    errors.append(f"Line {line_no}: OSM candidate is missing representative coordinates")

    if errors:
        return fail(errors)

    print(f"OK: {path} ({count} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
