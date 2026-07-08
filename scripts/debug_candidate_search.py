#!/usr/bin/env python3
"""Inspect Nominatim search results for a candidate in suwa_chino_candidates.csv."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_suwa_chino_map_data import USER_AGENT, candidate_variants, municipality_from_source


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_id")
    args = parser.parse_args()

    rows = list(csv.DictReader(Path("data/processed/suwa_chino_candidates.csv").open("r", encoding="utf-8-sig", newline="")))
    row = next((item for item in rows if item["ID"] == args.candidate_id), None)
    if row is None:
        raise SystemExit(f"Candidate not found: {args.candidate_id}")

    municipality = municipality_from_source(row["取得元"])
    queries = [f"{variant} {municipality} 長野県 日本" for variant in candidate_variants(row["林道名"])]
    queries.append(f"{row['林道名']} 長野県 日本")

    inspected = []
    seen = set()
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        params = urllib.parse.urlencode(
            {
                "format": "jsonv2",
                "limit": 10,
                "countrycodes": "jp",
                "bounded": 1,
                "viewbox": "138.0,35.8,138.55,36.35",
                "q": query,
            }
        )
        request = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        inspected.append({"query": query, "results": payload})

    print(json.dumps({"candidate": row, "queries": inspected}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
