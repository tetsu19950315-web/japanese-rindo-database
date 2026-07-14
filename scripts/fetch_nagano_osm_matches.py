#!/usr/bin/env python3
"""Fetch exact-name OSM way matches for Nagano forest-road candidates."""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path


OUTPUT = Path("data/processed/osm_nagano_candidate_matches.json")
CURRENT_PLAN = Path("data/processed/nagano_current_plan.csv")
BBOX = (35.15, 137.25, 37.10, 138.90)
ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
USER_AGENT = "JapaneseRindoDB/0.2 (research cache)"


def lv0_path() -> Path:
    return next(Path("data/raw").glob("NGN_Lv0_Master_*.csv"))


def load_candidate_names() -> list[str]:
    names: list[str] = []
    with lv0_path().open("r", encoding="utf-8-sig", newline="") as handle:
        names.extend(row["林道名"] for row in list(csv.DictReader(handle))[:17])
    with CURRENT_PLAN.open("r", encoding="utf-8-sig", newline="") as handle:
        names.extend(row["林道名"] for row in csv.DictReader(handle))
    return list(dict.fromkeys(name for name in names if name))


def name_variants(name: str) -> list[str]:
    variants = {name, f"林道{name}"}
    if name.endswith("線"):
        base = name[:-1]
        variants.update({base, f"林道{base}", f"林道{base}線"})
    else:
        variants.update({f"{name}線", f"林道{name}線"})
    return sorted(variants)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("林道", "").replace(" ", "")
    text = text.replace("澤", "沢").replace("ヶ", "ケ").replace("ガ", "カ")
    return text.removesuffix("線")


def fetch_chunk(variants: list[str]) -> dict:
    pattern = "^(" + "|".join(re.escape(value) for value in variants) + ")$"
    south, west, north, east = BBOX
    query = (
        "[out:json][timeout:120];"
        f'(way["highway"]["name"~"{pattern}"]({south},{west},{north},{east}););'
        "out tags center;"
    )
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(4):
        endpoint = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            request = urllib.request.Request(
                endpoint,
                data=body,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(request, timeout=150) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - endpoint fallback is intentional
            last_error = error
            time.sleep(3 + attempt * 2)
    raise RuntimeError(f"Overpass query failed: {last_error}")


def main() -> int:
    candidate_names = load_candidate_names()
    normalized_targets: dict[str, list[str]] = {}
    for name in candidate_names:
        normalized_targets.setdefault(normalize_name(name), []).append(name)

    variants = sorted({variant for name in candidate_names for variant in name_variants(name)})
    elements_by_id: dict[int, dict] = {}
    chunk_size = len(variants)
    for start in range(0, len(variants), chunk_size):
        chunk = variants[start : start + chunk_size]
        payload = fetch_chunk(chunk)
        for element in payload.get("elements", []):
            osm_name = element.get("tags", {}).get("name", "")
            targets = normalized_targets.get(normalize_name(osm_name), [])
            if not targets:
                continue
            element["candidateNames"] = targets
            elements_by_id[element["id"]] = element
        print(
            f"Fetched variants {start + 1}-{min(start + chunk_size, len(variants))}: {len(elements_by_id)} ways",
            flush=True,
        )
        time.sleep(1.2)

    output = {
        "generatedOn": "2026-07-10",
        "bbox": BBOX,
        "candidateNameCount": len(candidate_names),
        "matchedWayCount": len(elements_by_id),
        "elements": list(elements_by_id.values()),
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(elements_by_id)} matched ways to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
