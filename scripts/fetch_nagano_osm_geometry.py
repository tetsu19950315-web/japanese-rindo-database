#!/usr/bin/env python3
"""Fetch geometry for the strict Nagano OSM Lv0 way set in resumable chunks."""

from __future__ import annotations

import json
import time
from pathlib import Path

from build_nagano_osm_lv0 import point_in_prefecture, prefecture_rings
from fetch_nagano_osm_lv0 import CHECKED_ON, fetch, is_strict_candidate


SOURCE_CACHE = Path("data/processed/osm_nagano_lv0_candidates.json")
OUTPUT = Path("data/processed/osm_nagano_lv0_geometry.json")
CHUNK_SIZE = 150


def geometry_query(osm_ids: list[int]) -> str:
    joined = ",".join(str(osm_id) for osm_id in osm_ids)
    return f"[out:json][timeout:120];way(id:{joined});out geom qt;"


def write_cache(elements: dict[int, dict], target_count: int) -> None:
    payload = {
        "generatedOn": CHECKED_ON,
        "source": "OpenStreetMap contributors via Overpass API",
        "license": "ODbL 1.0",
        "targetWayCount": target_count,
        "geometryWayCount": len(elements),
        "elements": [elements[osm_id] for osm_id in sorted(elements)],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    payload = json.loads(SOURCE_CACHE.read_text(encoding="utf-8"))
    rings = prefecture_rings()
    target_ids = []
    for element in payload.get("elements", []):
        center = element.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
        if not is_strict_candidate(element):
            continue
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and point_in_prefecture(lat, lon, rings):
            target_ids.append(int(element["id"]))

    geometries: dict[int, dict] = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        target_id_set = set(target_ids)
        geometries = {
            int(element["id"]): element
            for element in existing.get("elements", [])
            if element.get("geometry") and int(element["id"]) in target_id_set
        }

    missing = [osm_id for osm_id in sorted(target_ids) if osm_id not in geometries]
    total_chunks = (len(missing) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for chunk_number, offset in enumerate(range(0, len(missing), CHUNK_SIZE), start=1):
        osm_ids = missing[offset : offset + CHUNK_SIZE]
        response = fetch(geometry_query(osm_ids))
        received = 0
        for element in response.get("elements", []):
            geometry = element.get("geometry")
            if element.get("type") == "way" and isinstance(geometry, list) and len(geometry) >= 2:
                geometries[int(element["id"])] = {"id": int(element["id"]), "geometry": geometry}
                received += 1
        write_cache(geometries, len(target_ids))
        print(
            f"Geometry chunk {chunk_number}/{total_chunks}: {received}/{len(osm_ids)} "
            f"({len(geometries)}/{len(target_ids)} cached)",
            flush=True,
        )
        time.sleep(1)

    write_cache(geometries, len(target_ids))
    missing_count = len(target_ids) - len(geometries)
    print(f"Wrote {len(geometries)} geometries to {OUTPUT}; missing: {missing_count}")
    return 0 if missing_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
