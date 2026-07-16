#!/usr/bin/env python3
"""Build the Nagano OSM-first Lv0 master while preserving existing IDs."""

from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from fetch_nagano_osm_lv0 import is_strict_candidate


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OSM_CACHE = PROCESSED / "osm_nagano_lv0_candidates.json"
OSM_GEOMETRY_CACHE = PROCESSED / "osm_nagano_lv0_geometry.json"
PREFECTURE_BOUNDARY_CACHE = PROCESSED / "osm_nagano_prefecture_boundary.json"
ENRICHED_MASTER = PROCESSED / "nagano_candidate_master.csv"
ROUTES_OUTPUT = PROCESSED / "nagano_osm_lv0_routes_v0.1.geojson"
REPORT_OUTPUT = PROCESSED / "nagano_osm_lv0_report.json"
CHECKED_ON = "2026-07-15"
MERGE_ENDPOINT_DISTANCE_METERS = 5_000
EXISTING_POSITION_MATCH_METERS = 20_000

FIELDS = [
    "ID",
    "林道名",
    "取得元",
    "Lv",
    "候補状態",
    "発見種別",
    "候補キー",
    "OSM要素種別",
    "OSM_ID",
    "OSM_URL",
    "代表緯度",
    "代表経度",
    "関係市町村",
    "位置状態",
    "OSM道路種別",
    "OSM路面",
    "OSM_tracktype",
    "OSM_access",
    "抽出理由",
    "取得日",
]


def lv0_path() -> Path:
    return next(RAW_DIR.glob("NGN_Lv0_Master_*.csv"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = text.replace("林道", "").replace("澤", "沢").replace("ヶ", "ケ").replace("ヵ", "カ")
    text = re.sub(r"[\s・･]", "", text)
    return text.removesuffix("線")


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 6_371_000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def geometry_points(element: dict) -> list[tuple[float, float]]:
    points = [
        (point["lat"], point["lon"])
        for point in element.get("geometry", [])
        if isinstance(point.get("lat"), (int, float)) and isinstance(point.get("lon"), (int, float))
    ]
    if points:
        return points
    center = element.get("center") or {}
    if isinstance(center.get("lat"), (int, float)) and isinstance(center.get("lon"), (int, float)):
        return [(center["lat"], center["lon"])]
    return []


def endpoints(element: dict) -> list[tuple[float, float]]:
    points = geometry_points(element)
    return list(dict.fromkeys([points[0], points[-1]])) if points else []


def should_merge(a: dict, b: dict) -> bool:
    nodes_a = set(a.get("nodes", []))
    nodes_b = set(b.get("nodes", []))
    if nodes_a and nodes_b and nodes_a.intersection(nodes_b):
        return True
    return any(
        haversine(point_a, point_b) <= MERGE_ENDPOINT_DISTANCE_METERS
        for point_a in endpoints(a)
        for point_b in endpoints(b)
    )


def group_elements(elements: list[dict]) -> list[list[dict]]:
    grouped_by_name: dict[str, list[dict]] = defaultdict(list)
    for element in elements:
        grouped_by_name[element["normalizedName"]].append(element)

    components: list[list[dict]] = []
    for same_name in grouped_by_name.values():
        parents = list(range(len(same_name)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parents[root_right] = root_left

        for left in range(len(same_name)):
            for right in range(left + 1, len(same_name)):
                if should_merge(same_name[left], same_name[right]):
                    union(left, right)

        by_root: dict[int, list[dict]] = defaultdict(list)
        for index, element in enumerate(same_name):
            by_root[find(index)].append(element)
        components.extend(by_root.values())
    return components


def component_center(elements: list[dict]) -> tuple[float, float]:
    points = [point for element in elements for point in geometry_points(element)]
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def component_name(elements: list[dict]) -> str:
    names = [element["candidateName"] for element in elements]
    return Counter(names).most_common(1)[0][0]


def join_tags(elements: list[dict], key: str) -> str:
    return "/".join(dict.fromkeys(element.get("tags", {}).get(key, "") for element in elements if element.get("tags", {}).get(key)))


def stitch_boundary_rings(members: list[dict], role: str) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    for member in members:
        if member.get("type") != "way" or member.get("role") != role:
            continue
        points = [
            (float(point["lat"]), float(point["lon"]))
            for point in member.get("geometry", [])
            if isinstance(point.get("lat"), (int, float)) and isinstance(point.get("lon"), (int, float))
        ]
        if len(points) >= 2:
            segments.append(points)

    rings: list[list[tuple[float, float]]] = []
    while segments:
        ring = segments.pop()
        while ring[0] != ring[-1]:
            joined = False
            for index, segment in enumerate(segments):
                if ring[-1] == segment[0]:
                    ring.extend(segment[1:])
                elif ring[-1] == segment[-1]:
                    ring.extend(reversed(segment[:-1]))
                elif ring[0] == segment[-1]:
                    ring = segment[:-1] + ring
                elif ring[0] == segment[0]:
                    ring = list(reversed(segment[1:])) + ring
                else:
                    continue
                segments.pop(index)
                joined = True
                break
            if not joined:
                raise RuntimeError(f"Could not stitch an OSM prefecture {role} boundary ring")
        rings.append(ring)
    return rings


def point_in_ring(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    previous_lat, previous_lon = ring[-1]
    for current_lat, current_lon in ring:
        crosses = (current_lat > lat) != (previous_lat > lat)
        if crosses:
            longitude_at_lat = (
                (previous_lon - current_lon) * (lat - current_lat) / (previous_lat - current_lat) + current_lon
            )
            if lon < longitude_at_lat:
                inside = not inside
        previous_lat, previous_lon = current_lat, current_lon
    return inside


def prefecture_rings() -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    if not PREFECTURE_BOUNDARY_CACHE.exists():
        raise FileNotFoundError(
            f"Missing {PREFECTURE_BOUNDARY_CACHE}. Run fetch_nagano_osm_lv0.py --boundary-only first."
        )
    payload = json.loads(PREFECTURE_BOUNDARY_CACHE.read_text(encoding="utf-8"))
    relations = [element for element in payload.get("elements", []) if element.get("type") == "relation"]
    if len(relations) != 1:
        raise RuntimeError(f"Expected one cached Nagano prefecture relation, got {len(relations)}")
    members = relations[0].get("members", [])
    outer = stitch_boundary_rings(members, "outer")
    inner = stitch_boundary_rings(members, "inner")
    if not outer:
        raise RuntimeError("Nagano prefecture boundary contains no outer rings")
    return outer, inner


def point_in_prefecture(
    lat: float,
    lon: float,
    rings: tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]],
) -> bool:
    outer, inner = rings
    return any(point_in_ring(lat, lon, ring) for ring in outer) and not any(
        point_in_ring(lat, lon, ring) for ring in inner
    )


def municipality_bounds(
    payload: dict,
    rings: tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]],
) -> list[tuple[str, list[float]]]:
    result: list[tuple[str, list[float]]] = []
    for relation in payload.get("municipalities", []):
        tags = relation.get("tags", {})
        name = tags.get("name:ja") or tags.get("name")
        bounds = relation.get("bounds") or {}
        values = [bounds.get("minlat"), bounds.get("maxlat"), bounds.get("minlon"), bounds.get("maxlon")]
        center = relation.get("center") or {}
        center_lat = center.get("lat")
        center_lon = center.get("lon")
        if (
            name
            and all(isinstance(value, (int, float)) for value in values)
            and isinstance(center_lat, (int, float))
            and isinstance(center_lon, (int, float))
            and point_in_prefecture(center_lat, center_lon, rings)
        ):
            result.append((name, values))

    cached_path = PROCESSED / "nagano_municipality_bounds.json"
    if cached_path.exists():
        cached = json.loads(cached_path.read_text(encoding="utf-8"))
        known = {name for name, _bounds in result}
        for name, item in cached.get("municipalities", {}).items():
            bounds = item.get("boundingbox")
            if name not in known and isinstance(bounds, list) and len(bounds) == 4:
                result.append((name, bounds))
    return result


def infer_municipality(lat: float, lon: float, bounds: list[tuple[str, list[float]]]) -> str:
    matches = []
    for name, (south, north, west, east) in bounds:
        if south <= lat <= north and west <= lon <= east:
            matches.append(((north - south) * (east - west), name))
    return min(matches)[1] if matches else ""


def existing_context() -> dict[str, dict]:
    if not ENRICHED_MASTER.exists():
        return {}
    return {row["ID"]: row for row in read_csv(ENRICHED_MASTER)}


def float_value(value: str | None) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except ValueError:
        return None


def candidate_key(name: str, lat: float, lon: float) -> str:
    return f"osm:{normalize_name(name)}:{lat:.3f}:{lon:.3f}"


def build() -> int:
    payload = json.loads(OSM_CACHE.read_text(encoding="utf-8"))
    geometry_by_id: dict[int, list[dict]] = {}
    if OSM_GEOMETRY_CACHE.exists():
        geometry_payload = json.loads(OSM_GEOMETRY_CACHE.read_text(encoding="utf-8"))
        geometry_by_id = {
            int(element["id"]): element["geometry"]
            for element in geometry_payload.get("elements", [])
            if element.get("geometry")
        }
    context = existing_context()
    current_rows = read_csv(lv0_path())
    if context:
        baseline_ids = set(context)
        old_rows = [row for row in current_rows if row["ID"] in baseline_ids]
    else:
        old_rows = current_rows
    rings = prefecture_rings()
    bounds = municipality_bounds(payload, rings)
    bbox_elements = payload.get("elements", [])
    nagano_elements = []
    weak_or_nonforest_elements = 0
    for element in bbox_elements:
        if element["id"] in geometry_by_id:
            element = dict(element)
            element["geometry"] = geometry_by_id[element["id"]]
        center = element.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and point_in_prefecture(lat, lon, rings):
            if not is_strict_candidate(element):
                weak_or_nonforest_elements += 1
                continue
            nagano_elements.append(element)
    components = group_elements(nagano_elements)

    component_rows = []
    for elements in components:
        lat, lon = component_center(elements)
        name = component_name(elements)
        component_rows.append({
            "elements": elements,
            "name": name,
            "normalized": normalize_name(name),
            "lat": lat,
            "lon": lon,
            "municipality": infer_municipality(lat, lon, bounds),
            "osm_ids": sorted(element["id"] for element in elements),
        })

    old_by_norm: dict[str, list[dict]] = defaultdict(list)
    old_by_osm_id: dict[int, dict] = {}
    for row in old_rows:
        old_by_norm[normalize_name(row["林道名"])].append(row)
        for raw_id in re.findall(r"\d+", row.get("OSM_ID", "")):
            old_by_osm_id[int(raw_id)] = row
    component_count_by_norm = Counter(component["normalized"] for component in component_rows)

    assigned_existing: set[str] = set()
    component_assignments: dict[int, dict] = {}
    ambiguous_components = 0
    for index, component in enumerate(component_rows):
        overlap = next((old_by_osm_id[osm_id] for osm_id in component["osm_ids"] if osm_id in old_by_osm_id), None)
        if overlap and overlap["ID"] not in assigned_existing:
            component_assignments[index] = overlap
            assigned_existing.add(overlap["ID"])
            continue

        candidates = [row for row in old_by_norm.get(component["normalized"], []) if row["ID"] not in assigned_existing]
        if len(candidates) == 1 and len(old_by_norm.get(component["normalized"], [])) == 1:
            row = candidates[0]
            if component_count_by_norm[component["normalized"]] == 1:
                component_assignments[index] = row
                assigned_existing.add(row["ID"])
                continue
            details = context.get(row["ID"], {})
            expected = details.get("関係市町村", "")
            expected_names = [value for value in re.split(r"[・／,、]", expected) if value]
            known_lat = float_value(row.get("代表緯度")) or float_value(details.get("緯度"))
            known_lon = float_value(row.get("代表経度")) or float_value(details.get("経度"))
            position_matches = (
                known_lat is not None
                and known_lon is not None
                and haversine((known_lat, known_lon), (component["lat"], component["lon"])) <= EXISTING_POSITION_MATCH_METERS
            )
            municipality_matches = not expected_names or component["municipality"] in expected_names
            if position_matches or municipality_matches:
                component_assignments[index] = row
                assigned_existing.add(row["ID"])
                continue
        if candidates:
            ambiguous_components += 1

    max_id = max(int(row["ID"].split("-")[1]) for row in old_rows)
    new_components = [
        (index, component)
        for index, component in enumerate(component_rows)
        if index not in component_assignments
    ]
    new_components.sort(key=lambda item: (item[1]["normalized"], item[1]["lat"], item[1]["lon"], item[1]["osm_ids"]))
    for index, _component in new_components:
        max_id += 1
        component_assignments[index] = {"ID": f"NGN-{max_id:06d}", "林道名": "", "取得元": ""}

    component_by_id: dict[str, dict] = {}
    output_rows_by_id: dict[str, dict] = {}
    for index, component in enumerate(component_rows):
        old = component_assignments[index]
        road_id = old["ID"]
        details = context.get(road_id, {})
        is_existing = any(row["ID"] == road_id for row in old_rows)
        name = old.get("林道名") or component["name"]
        osm_ids = component["osm_ids"]
        osm_url = f"https://www.openstreetmap.org/way/{osm_ids[0]}"
        old_source = old.get("取得元", "").strip()
        source = (
            old_source
            if "OpenStreetMap contributors" in old_source
            else f"{old_source} | OpenStreetMap contributors {osm_url}"
            if old_source
            else f"OpenStreetMap contributors {osm_url}"
        )
        reasons = list(dict.fromkeys(
            reason
            for element in component["elements"]
            for reason in element.get("selectionReasons", [])
        ))
        municipality = details.get("関係市町村") if is_existing and details.get("関係市町村") else component["municipality"]
        output_rows_by_id[road_id] = {
            "ID": road_id,
            "林道名": name,
            "取得元": source,
            "Lv": "Lv0",
            "候補状態": "OSM・既存資料一致" if is_existing else "OSM候補・未照合",
            "発見種別": "OSM+既存資料" if is_existing else "OSM",
            "候補キー": candidate_key(component["name"], component["lat"], component["lon"]),
            "OSM要素種別": "way",
            "OSM_ID": "/".join(str(value) for value in osm_ids),
            "OSM_URL": osm_url,
            "代表緯度": f"{component['lat']:.7f}",
            "代表経度": f"{component['lon']:.7f}",
            "関係市町村": municipality or "",
            "位置状態": "OSM代表点",
            "OSM道路種別": join_tags(component["elements"], "highway"),
            "OSM路面": join_tags(component["elements"], "surface"),
            "OSM_tracktype": join_tags(component["elements"], "tracktype"),
            "OSM_access": join_tags(component["elements"], "access"),
            "抽出理由": "／".join(reasons),
            "取得日": CHECKED_ON,
        }
        component_by_id[road_id] = component

    for old in old_rows:
        if old["ID"] in output_rows_by_id:
            continue
        details = context.get(old["ID"], {})
        output_rows_by_id[old["ID"]] = {
            "ID": old["ID"],
            "林道名": old["林道名"],
            "取得元": old["取得元"],
            "Lv": old.get("Lv") or "Lv0",
            "候補状態": "既存資料のみ・OSM未照合",
            "発見種別": old.get("発見種別") or "既存資料",
            "候補キー": old.get("候補キー") or f"source:{old['ID']}",
            "OSM要素種別": "",
            "OSM_ID": "",
            "OSM_URL": "",
            "代表緯度": old.get("代表緯度", ""),
            "代表経度": old.get("代表経度", ""),
            "関係市町村": details.get("関係市町村", old.get("関係市町村", "")),
            "位置状態": old.get("位置状態") or "位置未特定",
            "OSM道路種別": "",
            "OSM路面": "",
            "OSM_tracktype": "",
            "OSM_access": "",
            "抽出理由": "既存Lv0から継承",
            "取得日": old.get("取得日", ""),
        }

    output_rows = sorted(output_rows_by_id.values(), key=lambda row: int(row["ID"].split("-")[1]))
    output_path = lv0_path()
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)

    features = []
    for road_id, component in component_by_id.items():
        for element in component["elements"]:
            points = geometry_points(element)
            if len(points) < 2:
                continue
            features.append({
                "type": "Feature",
                "properties": {
                    "id": road_id,
                    "name": output_rows_by_id[road_id]["林道名"],
                    "osmWayId": element["id"],
                    "source": "OpenStreetMap contributors",
                    "license": "ODbL 1.0",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lat, lon in points],
                },
            })
    ROUTES_OUTPUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    matched_existing = len(assigned_existing)
    report = {
        "generatedOn": CHECKED_ON,
        "mode": "OSM-first Lv0 / named-road high-speed extraction",
        "area": "長野県",
        "source": payload.get("source"),
        "license": payload.get("license"),
        "rawNamedWayCount": payload.get("rawNamedWayCount"),
        "bboxCandidateWayCount": payload.get("candidateWayCount"),
        "weakOrNonForestWayExcludedCount": weak_or_nonforest_elements,
        "naganoCandidateWayCount": len(nagano_elements),
        "geometryWayCount": sum(bool(element.get("geometry")) for element in nagano_elements),
        "mergedCandidateCount": len(component_rows),
        "existingInputCount": len(old_rows),
        "matchedExistingCount": matched_existing,
        "existingUnmatchedCount": len(old_rows) - matched_existing,
        "newIdCount": len(new_components),
        "finalLv0Count": len(output_rows),
        "firstNewId": new_components and output_rows_by_id[component_assignments[new_components[0][0]]["ID"]]["ID"],
        "lastId": output_rows[-1]["ID"],
        "ambiguousNameComponentCount": ambiguous_components,
        "municipalityInferredCount": sum(bool(row["関係市町村"]) for row in output_rows),
        "limitations": [
            "OSM上で名称のないtrackは対象外",
            "Lv0は林道の法的区分や通行可否を確定しない",
            "林道根拠が名称末尾の『線』だけの道路、および国道・街道・古道等の明確な非林道名は除外",
            "同名wayは共有ノードまたは端点5km以内を同一路線候補として統合",
            "長野県境判定はOSM way代表点を使用し、県境をまたぐwayは代表点側の県へ分類",
        ],
    }
    REPORT_OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Lv0: {len(output_rows)} rows / OSM groups: {len(component_rows)} / "
        f"matched existing: {matched_existing} / new IDs: {len(new_components)}"
    )
    print(f"Wrote {len(features)} OSM route features to {ROUTES_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
