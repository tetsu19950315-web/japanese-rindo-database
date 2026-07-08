#!/usr/bin/env python3
"""Create a candidate CSV by matching keywords in road names and sources.

This is only a first-pass helper. Geographic membership must still be verified
from reliable sources before a road is treated as an area candidate.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("keywords", nargs="+")
    args = parser.parse_args()

    needles = [k.casefold() for k in args.keywords]

    with args.input_csv.open("r", encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src)
        rows = []
        for row in reader:
            haystack = f'{row.get("林道名", "")} {row.get("取得元", "")}'.casefold()
            if any(k in haystack for k in needles):
                rows.append(row)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=["ID", "林道名", "取得元"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} candidates to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
