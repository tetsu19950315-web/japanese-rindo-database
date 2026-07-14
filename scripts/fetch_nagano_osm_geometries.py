#!/usr/bin/env python3
"""Fetch one representative OSM geometry for each statewide shortlisted road."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUT = PROCESSED / "nagano_routes.geojson"
ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def main() -> int:
    shortlist = json.loads((PROCESSED / "nagano_shortlist.json").read_text(encoding="utf-8"))
    selected_ids = {row["id"] for row in shortlist["selected"]}
    roads = json.loads((PROCESSED / "nagano_map_data.json").read_text(encoding="utf-8"))
    selected = [row for row in roads if row["id"] in selected_ids and row.get("primaryOsmWayId")]
    by_way = {int(row["primaryOsmWayId"]): row for row in selected}
    ids = ",".join(str(value) for value in by_way)
    query = f"[out:json][timeout:90];way(id:{ids});out tags geom;"
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")

    last_error = None
    payload = None
    for endpoint in ENDPOINTS:
        try:
            request = urllib.request.Request(
                endpoint,
                data=body,
                headers={"User-Agent": "JapaneseRindoDB/0.2 (research cache)", "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception as error:  # noqa: BLE001 - endpoint fallback is intentional
            last_error = error
    if payload is None:
        raise RuntimeError(f"Overpass geometry query failed: {last_error}")

    features = []
    for element in payload.get("elements", []):
        road = by_way.get(int(element["id"]))
        geometry = element.get("geometry") or []
        coordinates = [[point["lon"], point["lat"]] for point in geometry]
        if not road or len(coordinates) < 2:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "id": road["id"],
                "name": road["name"],
                "municipality": road["municipality"],
                "region": road["region"],
                "relation": "name-match",
                "osmWayId": element["id"],
                "osmName": element.get("tags", {}).get("name", ""),
                "highway": element.get("tags", {}).get("highway", ""),
                "surface": element.get("tags", {}).get("surface", ""),
                "tracktype": element.get("tags", {}).get("tracktype", ""),
                "checkedOn": "2026-07-10",
            },
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })

    collection = {
        "type": "FeatureCollection",
        "name": "Nagano statewide shortlisted forest-road reference lines",
        "source": "OpenStreetMap contributors via Overpass API",
        "generatedOn": "2026-07-10",
        "features": features,
    }
    OUTPUT.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(features)} route features to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
