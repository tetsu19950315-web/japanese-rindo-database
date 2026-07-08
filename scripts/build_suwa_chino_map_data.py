#!/usr/bin/env python3
"""Build MVP map data for the Suwa/Chino candidate set.

Inputs:
- data/processed/suwa_chino_candidates.csv
- data/processed/overpass_suwa_chino_bbox.json (optional cache)

Outputs:
- data/processed/suwa_chino_locations.csv
- data/processed/routes.geojson
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CANDIDATES_CSV = Path("data/processed/suwa_chino_candidates.csv")
BBOX_CACHE = Path("data/processed/overpass_suwa_chino_bbox.json")
LOCATIONS_CSV = Path("data/processed/suwa_chino_locations.csv")
ROUTES_GEOJSON = Path("data/processed/routes.geojson")
USER_AGENT = "JapaneseRindoMVP/0.1"
BBOX = (35.8, 138.0, 36.35, 138.55)
TODAY = date.today().isoformat()


@dataclass
class MatchResult:
    match_type: str
    matched_name: str
    source: str
    display_lat: float
    display_lon: float
    entry_lat: float
    entry_lon: float
    exit_lat: float | None
    exit_lon: float | None
    geometry: dict


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("林道", "")
    text = text.replace("線", "")
    text = text.replace("支", "")
    text = text.replace("ヶ", "ケ")
    text = text.replace("ガ", "カ")
    text = re.sub(r"\d+号$", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def municipality_from_source(source: str) -> str:
    for municipality in ("茅野市", "諏訪市", "原村", "富士見町", "岡谷市", "下諏訪町"):
        if municipality in source:
            return municipality
    return "長野県"


def candidate_variants(name: str) -> list[str]:
    variants = {name}
    base = name
    if base.endswith("線"):
        base = base[:-1]
        variants.add(base)
        variants.add(f"林道{name}")
    else:
        variants.add(f"{name}線")
        variants.add(f"林道{name}")
        variants.add(f"林道{name}線")

    if base.endswith("支"):
        stem = base[:-1]
        variants.add(stem)
        variants.add(f"林道{stem}")
        variants.add(f"林道{stem}線")

    if "２号" in name:
        variants.add(name.replace("２号", "2号"))
        variants.add(name.replace("２号", "二号"))

    return [v for v in variants if v]


def midpoint(coords: list[list[float]]) -> list[float]:
    return coords[len(coords) // 2]


def way_to_match(candidate_name: str, way: dict) -> MatchResult:
    coords = [[pt["lon"], pt["lat"]] for pt in way["geometry"]]
    first = coords[0]
    last = coords[-1]
    middle = midpoint(coords)
    matched_name = way.get("tags", {}).get("name", candidate_name)
    return MatchResult(
        match_type="osm_way_name_match",
        matched_name=matched_name,
        source=f"OpenStreetMap way name match: {matched_name} (way {way['id']})",
        display_lat=middle[1],
        display_lon=middle[0],
        entry_lat=first[1],
        entry_lon=first[0],
        exit_lat=last[1],
        exit_lon=last[0],
        geometry={"type": "LineString", "coordinates": coords},
    )


def nominatim_to_match(result: dict) -> MatchResult:
    lat = float(result["lat"])
    lon = float(result["lon"])
    return MatchResult(
        match_type="osm_nominatim_name_match",
        matched_name=result.get("name") or result.get("display_name", ""),
        source=f"OpenStreetMap Nominatim: {result.get('display_name', '')}",
        display_lat=lat,
        display_lon=lon,
        entry_lat=lat,
        entry_lon=lon,
        exit_lat=None,
        exit_lon=None,
        geometry={"type": "Point", "coordinates": [lon, lat]},
    )


def load_bbox_ways() -> list[dict]:
    if not BBOX_CACHE.exists():
        return []
    payload = json.loads(BBOX_CACHE.read_text(encoding="utf-8"))
    return [element for element in payload.get("elements", []) if element.get("type") == "way" and element.get("tags", {}).get("name")]


def score_way(candidate_name: str, way_name: str) -> tuple[int, int]:
    target = normalize_name(candidate_name)
    way_norm = normalize_name(way_name)
    if not target or not way_norm:
        return (-1, 0)
    if way_norm == target:
        return (100, len(way_name))
    if target in way_norm:
        return (80, len(way_name))
    if way_norm in target:
        return (60, len(way_name))
    return (-1, 0)


def find_way_match(candidate_name: str, ways: list[dict]) -> MatchResult | None:
    scored: list[tuple[tuple[int, int], dict]] = []
    for way in ways:
        score = score_way(candidate_name, way.get("tags", {}).get("name", ""))
        if score[0] >= 0:
            scored.append((score, way))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return way_to_match(candidate_name, scored[0][1])


def score_nominatim_result(candidate_name: str, result: dict) -> tuple[int, float]:
    target = normalize_name(candidate_name)
    haystack = normalize_name(
        " ".join(
            [
                result.get("name", ""),
                result.get("display_name", ""),
                result.get("category", ""),
                result.get("type", ""),
            ]
        )
    )
    score = 0
    if target and target in haystack:
        score += 50
    category = result.get("category", "")
    if category in {"highway", "natural", "place", "tourism"}:
        score += 20
    if "林道" in (result.get("name", "") + result.get("display_name", "")):
        score += 15
    return (score, float(result.get("importance", 0.0)))


def nominatim_search(candidate_name: str, municipality: str) -> MatchResult | None:
    queries: list[str] = []
    for variant in candidate_variants(candidate_name):
        queries.append(f"{variant} {municipality} 長野県 日本")
    queries.append(f"{candidate_name} 長野県 日本")

    seen: set[str] = set()
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
                "viewbox": f"{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}",
                "q": query,
            }
        )
        request = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            results = json.loads(response.read().decode("utf-8"))
        time.sleep(1.1)
        if not results:
            continue
        ranked = sorted(results, key=lambda item: score_nominatim_result(candidate_name, item), reverse=True)
        best = ranked[0]
        if score_nominatim_result(candidate_name, best)[0] >= 20:
            return nominatim_to_match(best)
    return None


def pick_match(candidate: dict, ways: list[dict]) -> MatchResult | None:
    candidate_name = candidate["林道名"]

    match = find_way_match(candidate_name, ways)
    if match:
        return match

    for variant in candidate_variants(candidate_name):
        match = find_way_match(variant, ways)
        if match:
            return match

    return nominatim_search(candidate_name, municipality_from_source(candidate["取得元"]))


def main() -> int:
    candidates = list(csv.DictReader(CANDIDATES_CSV.open("r", encoding="utf-8-sig", newline="")))
    ways = load_bbox_ways()

    location_rows: list[dict] = []
    features: list[dict] = []

    for candidate in candidates:
        match = pick_match(candidate, ways)
        if not match:
            print(f"UNMATCHED {candidate['ID']} {candidate['林道名']}")
            continue

        print(f"MATCHED {candidate['ID']} {candidate['林道名']} -> {match.matched_name} [{match.match_type}]")

        location_rows.append(
            {
                "ID": candidate["ID"],
                "表示緯度": f"{match.display_lat:.7f}",
                "表示経度": f"{match.display_lon:.7f}",
                "入口緯度": f"{match.entry_lat:.7f}",
                "入口経度": f"{match.entry_lon:.7f}",
                "出口緯度": f"{match.exit_lat:.7f}" if match.exit_lat is not None else "",
                "出口経度": f"{match.exit_lon:.7f}" if match.exit_lon is not None else "",
                "位置取得元": match.source,
                "位置確認日": TODAY,
            }
        )

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": candidate["ID"],
                    "name": candidate["林道名"],
                    "matchedName": match.matched_name,
                    "matchType": match.match_type,
                    "source": match.source,
                },
                "geometry": match.geometry,
            }
        )

    LOCATIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LOCATIONS_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ID", "表示緯度", "表示経度", "入口緯度", "入口経度", "出口緯度", "出口経度", "位置取得元", "位置確認日"],
        )
        writer.writeheader()
        writer.writerows(location_rows)

    ROUTES_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Built {len(location_rows)} location rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
