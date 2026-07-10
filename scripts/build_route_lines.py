from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "overpass_suwa_chino_bbox.json"
OUTPUT = ROOT / "data" / "processed" / "routes.geojson"


# 路線名がOSMと一致するものだけを name-match とする。
# 公式図の代表点付近にあるだけの線形は nearby-track とし、林道本線と確定しない。
WAY_TARGETS = {
    146988886: {
        "id": "NGN-000010",
        "name": "猿ヶ入",
        "relation": "name-match",
        "evidence": "OSM name=林道猿ヶ入線",
    },
    1318012782: {
        "id": "NGN-000011",
        "name": "棚嵐線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
    141284509: {
        "id": "NGN-000011",
        "name": "棚嵐線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
    141284921: {
        "id": "NGN-000011",
        "name": "棚嵐線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
    140644025: {
        "id": "NGN-000012",
        "name": "赤ジッコ線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
    140643990: {
        "id": "NGN-000012",
        "name": "赤ジッコ線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
    140466054: {
        "id": "NGN-000013",
        "name": "扇平南峠線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
    140644021: {
        "id": "NGN-000014",
        "name": "付上線",
        "relation": "nearby-track",
        "evidence": "公式図代表点付近のOSM track",
    },
}


def build_route_lines() -> None:
    with SOURCE.open("r", encoding="utf-8") as source_file:
        source_data = json.load(source_file)

    ways = {
        element["id"]: element
        for element in source_data.get("elements", [])
        if element.get("type") == "way" and element.get("id") in WAY_TARGETS
    }

    missing = sorted(set(WAY_TARGETS) - set(ways))
    if missing:
        raise ValueError(f"Target OSM ways not found: {missing}")

    features = []
    for way_id, target in WAY_TARGETS.items():
        way = ways[way_id]
        geometry = way.get("geometry") or []
        if len(geometry) < 2:
            raise ValueError(f"OSM way {way_id} has no usable geometry")

        features.append(
            {
                "type": "Feature",
                "properties": {
                    **target,
                    "osmWayId": way_id,
                    "source": f"OpenStreetMap way {way_id}",
                    "sourceUrl": f"https://www.openstreetmap.org/way/{way_id}",
                    "highway": way.get("tags", {}).get("highway"),
                    "tracktype": way.get("tags", {}).get("tracktype"),
                    "surface": way.get("tags", {}).get("surface"),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[point["lon"], point["lat"]] for point in geometry],
                },
            }
        )

    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "generatedOn": "2026-07-10",
            "source": "OpenStreetMap Overpass extract collected 2026-07-08",
            "note": "name-match is a named route match; nearby-track is reference geometry only and is not a confirmed forest-road alignment.",
        },
        "features": features,
    }
    OUTPUT.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_route_lines()
