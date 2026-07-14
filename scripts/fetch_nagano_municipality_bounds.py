#!/usr/bin/env python3
"""Cache OSM Nominatim bounds for municipalities used by matched candidates."""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


CURRENT_PLAN = Path("data/processed/nagano_current_plan.csv")
HISTORY = Path("data/processed/nagano_plan_history.csv")
OSM_MATCHES = Path("data/processed/osm_nagano_candidate_matches.json")
OUTPUT = Path("data/processed/nagano_municipality_bounds.json")
USER_AGENT = "JapaneseRindoDB/0.2 (municipality verification)"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def search(name: str) -> dict | None:
    params = urllib.parse.urlencode(
        {
            "q": f"{name}, 長野県, 日本",
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "jp",
            "addressdetails": 1,
        }
    )
    request = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        results = json.loads(response.read().decode("utf-8"))
    for result in results:
        address = result.get("address", {})
        if address.get("province") == "長野県" or address.get("state") == "長野県":
            return result
    return results[0] if results else None


def main() -> int:
    osm = json.loads(OSM_MATCHES.read_text(encoding="utf-8"))
    matched_names = {
        name
        for element in osm.get("elements", [])
        for name in element.get("candidateNames", [])
    }
    municipalities = {"茅野市", "諏訪市"}
    for row in rows(CURRENT_PLAN) + rows(HISTORY):
        if row.get("林道名") in matched_names:
            municipalities.add(row["関係市町村"])

    output: dict[str, dict] = {}
    for index, municipality in enumerate(sorted(municipalities), start=1):
        result = search(municipality)
        if result:
            output[municipality] = {
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "boundingbox": [float(value) for value in result["boundingbox"]],
                "displayName": result.get("display_name", ""),
                "osmType": result.get("osm_type"),
                "osmId": result.get("osm_id"),
            }
        print(f"{index}/{len(municipalities)} {municipality}: {'OK' if result else 'NOT FOUND'}", flush=True)
        time.sleep(1.1)

    payload = {
        "generatedOn": "2026-07-10",
        "source": "OpenStreetMap Nominatim municipality search",
        "municipalities": output,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} municipality bounds to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
