#!/usr/bin/env python3
"""Fetch named OSM road candidates for the Nagano OSM-first Lv0 master."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path


OUTPUT = Path("data/processed/osm_nagano_lv0_candidates.json")
PREFECTURE_BOUNDARY_OUTPUT = Path("data/processed/osm_nagano_prefecture_boundary.json")
BBOX = (35.15, 137.25, 37.10, 138.90)
ENDPOINTS = [
    "https://dev.overpass-api.de/api_drolbr/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "JapaneseRindoDB/0.3 (OSM-first Lv0 research cache)"
CHECKED_ON = "2026-07-15"

ROAD_QUERY_TEMPLATE = """
[out:json][timeout:90];
(
  way["highway"="track"]["name"]({south},{west},{north},{east});
  way["highway"]["name"~"林道|森林管理道|作業道"]({south},{west},{north},{east});
  way["highway"="service"]["name"~"線$|支線$|作業道$|森林管理道$"]({south},{west},{north},{east});
  way["highway"="service"]["name"]["surface"~"^(unpaved|gravel|fine_gravel|compacted|ground|dirt|earth|mud|rock|sand)$"]({south},{west},{north},{east});
  way["highway"="service"]["name"]["tracktype"]({south},{west},{north},{east});
  way["highway"="unclassified"]["name"~"線$|支線$|作業道$|森林管理道$"]({south},{west},{north},{east});
  way["highway"="unclassified"]["name"]["surface"~"^(unpaved|gravel|fine_gravel|compacted|ground|dirt|earth|mud|rock|sand)$"]({south},{west},{north},{east});
  way["highway"="unclassified"]["name"]["tracktype"]({south},{west},{north},{east});
);
out body center qt;
""".strip()

MUNICIPALITY_QUERY = """
[out:json][timeout:120];
relation["boundary"="administrative"]["admin_level"="7"](35.15,137.25,37.10,138.90);
out tags center bb qt;
""".strip()

PREFECTURE_BOUNDARY_QUERY = """
[out:json][timeout:120];
relation["boundary"="administrative"]["ISO3166-2"="JP-20"];
out geom;
""".strip()

UNPAVED_SURFACES = {
    "compacted",
    "dirt",
    "earth",
    "fine_gravel",
    "gravel",
    "ground",
    "mud",
    "rock",
    "sand",
    "unpaved",
}
PEDESTRIAN_HINT = re.compile(r"登山道|遊歩道|歩道|トレイル|ハイキング|園路")
ROAD_NAME_HINT = re.compile(r"(?:林道|作業道|森林管理道|線|支線)$")
EXPLICIT_FOREST_HINT = re.compile(r"林道|森林管理道|作業道")
NON_FOREST_NAME_HINT = re.compile(
    r"国道|県道|市道|町道|村道|農道|街道|古道|登山道|遊歩道|歩道|トレイル|"
    r"サイクリング|ハイキング|スキー|ゲレンデ|高速|ETC|ＥＴＣ|復帰路線|退出路線|"
    r"パノラマルート|峠$|橋$|道$"
)


def lv0_path() -> Path:
    return next(Path("data/raw").glob("NGN_Lv0_Master_*.csv"))


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = text.replace("林道", "").replace("澤", "沢").replace("ヶ", "ケ").replace("ヵ", "カ")
    text = re.sub(r"[\s・･]", "", text)
    return text.removesuffix("線")


def existing_names() -> set[str]:
    with lv0_path().open("r", encoding="utf-8-sig", newline="") as handle:
        return {normalize_name(row["林道名"]) for row in csv.DictReader(handle) if row.get("林道名")}


def fetch(query: str) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(6):
        endpoint = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            request = urllib.request.Request(
                endpoint,
                data=body,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(request, timeout=165) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - endpoint fallback is intentional
            last_error = error
            print(f"Overpass attempt {attempt + 1} failed: {error}", flush=True)
            time.sleep(4 + attempt * 3)
    raise RuntimeError(f"Overpass query failed: {last_error}")


def road_tiles() -> list[tuple[str, str]]:
    south, west, north, east = BBOX
    middle_lat = (south + north) / 2
    middle_lon = (west + east) / 2
    boxes = [
        (south, west, middle_lat, middle_lon),
        (south, middle_lon, middle_lat, east),
        (middle_lat, west, north, middle_lon),
        (middle_lat, middle_lon, north, east),
    ]
    return [
        (
            f"tile-{index}",
            ROAD_QUERY_TEMPLATE.format(south=box[0], west=box[1], north=box[2], east=box[3]),
        )
        for index, box in enumerate(boxes, start=1)
    ]


def candidate_reasons(element: dict, known_names: set[str]) -> list[str]:
    tags = element.get("tags", {})
    name = tags.get("name:ja") or tags.get("name") or ""
    highway = tags.get("highway", "")
    surface = tags.get("surface", "")
    reasons: list[str] = []

    if "林道" in name or "森林管理道" in name or "作業道" in name:
        reasons.append("名称に林道系表記")
    if normalize_name(name) in known_names:
        reasons.append("既存Lv0名称一致")
    if highway == "track" and not PEDESTRIAN_HINT.search(name):
        reasons.append("名称付きhighway=track")
    if highway in {"service", "unclassified"} and surface in UNPAVED_SURFACES:
        reasons.append("未舗装系surfaceタグ")
    if highway in {"service", "unclassified"} and tags.get("tracktype"):
        reasons.append("tracktypeタグあり")
    if highway in {"service", "unclassified"} and ROAD_NAME_HINT.search(name):
        reasons.append("路線名形式のservice/unclassified")
    return reasons


def is_strict_candidate(element: dict) -> bool:
    """Return whether a fetched named way has an OSM clue specific enough for Lv0."""
    name = element.get("candidateName") or (element.get("tags", {}).get("name:ja") or element.get("tags", {}).get("name") or "")
    reasons = element.get("selectionReasons", [])
    if EXPLICIT_FOREST_HINT.search(name) or "既存Lv0名称一致" in reasons:
        return True
    if NON_FOREST_NAME_HINT.search(name):
        return False
    return any(
        reason in {"名称付きhighway=track", "未舗装系surfaceタグ", "tracktypeタグあり"}
        for reason in reasons
    )


def fetch_prefecture_boundary() -> int:
    payload = fetch(PREFECTURE_BOUNDARY_QUERY)
    relations = [element for element in payload.get("elements", []) if element.get("type") == "relation"]
    if len(relations) != 1:
        raise RuntimeError(f"Expected one Nagano prefecture relation, got {len(relations)}")
    output = {
        "generatedOn": CHECKED_ON,
        "source": "OpenStreetMap contributors via Overpass API",
        "license": "ODbL 1.0",
        "query": PREFECTURE_BOUNDARY_QUERY,
        "elements": relations,
    }
    PREFECTURE_BOUNDARY_OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote Nagano prefecture boundary to {PREFECTURE_BOUNDARY_OUTPUT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--boundary-only",
        action="store_true",
        help="Fetch only the Nagano prefecture boundary used for strict spatial filtering.",
    )
    args = parser.parse_args()
    if args.boundary_only:
        return fetch_prefecture_boundary()

    known_names = existing_names()
    road_elements: dict[int, dict] = {}
    query_counts: dict[str, int] = {}
    queries = road_tiles()
    for label, query in queries:
        road_payload = fetch(query)
        elements = road_payload.get("elements", [])
        query_counts[label] = len(elements)
        for element in elements:
            road_elements[element["id"]] = element
        print(f"Fetched {label}: {len(elements)} ways ({len(road_elements)} unique)", flush=True)
        time.sleep(2)
    time.sleep(2)
    try:
        municipality_payload = fetch(MUNICIPALITY_QUERY)
        print(f"Fetched {len(municipality_payload.get('elements', []))} municipality relations", flush=True)
    except RuntimeError as error:
        municipality_payload = {"elements": []}
        print(f"Municipality boundary refresh skipped: {error}", flush=True)

    candidates = []
    for element in road_elements.values():
        tags = element.get("tags", {})
        name = tags.get("name:ja") or tags.get("name") or ""
        center = element.get("center") or {}
        if not name or not isinstance(center.get("lat"), (int, float)) or not isinstance(center.get("lon"), (int, float)):
            continue
        reasons = candidate_reasons(element, known_names)
        if not reasons:
            continue
        copied = dict(element)
        copied["candidateName"] = name
        copied["normalizedName"] = normalize_name(name)
        copied["selectionReasons"] = reasons
        if is_strict_candidate(copied):
            candidates.append(copied)

    payload = {
        "generatedOn": CHECKED_ON,
        "source": "OpenStreetMap contributors via Overpass API",
        "license": "ODbL 1.0",
        "bbox": BBOX,
        "roadQueries": {label: query for label, query in queries},
        "roadQueryCounts": query_counts,
        "municipalityQuery": MUNICIPALITY_QUERY,
        "rawNamedWayCount": len(road_elements),
        "candidateWayCount": len(candidates),
        "elements": candidates,
        "municipalities": municipality_payload.get("elements", []),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(candidates)} candidate ways to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
