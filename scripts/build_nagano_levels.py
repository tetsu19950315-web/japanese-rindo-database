#!/usr/bin/env python3
"""Build Lv0/Lv1/Lv2 classifications from collected source evidence."""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
EVIDENCE_JSON = PROCESSED / "nagano_level_evidence.json"
EVIDENCE_CSV = PROCESSED / "nagano_level_evidence.csv"
LEVEL_MASTER = PROCESSED / "nagano_level_master.csv"
LEVEL_REPORT = PROCESSED / "nagano_level_report.json"
ENRICHED_MASTER = PROCESSED / "nagano_candidate_master.csv"
MAP_DATA = PROCESSED / "nagano_map_data.json"
MUNICIPAL_PLAN_INDEX = ROOT / "tmp" / "research" / "municipal_plans" / "index.json"
WEB_CACHE_DIR = ROOT / "tmp" / "research" / "web_search"
CHECKED_ON = "2026-07-16"

AUDIT_FIELDS = [
    "照合状態",
    "資料照合件数",
    "行政資料件数",
    "公開Web資料件数",
    "独立ドメイン数",
    "詳細属性",
    "判定理由",
    "主出典",
    "根拠URL",
    "照合日",
]


def lv0_path() -> Path:
    return next(RAW_DIR.glob("NGN_Lv0_Master_*.csv"))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def optional_float(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def map_region(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "未分類"
    if lat >= 36.65:
        return "北信"
    if lon >= 138.0 and lat >= 36.1:
        return "東信"
    if lat <= 36.15:
        return "南信"
    return "中信"


def source_links_for_map(
    existing_links: list[dict[str, str]],
    row: dict[str, object],
) -> list[dict[str, str]]:
    links = [dict(item) for item in existing_links if isinstance(item, dict) and item.get("url")]
    known_urls = {item["url"] for item in links}

    osm_url = str(row.get("OSM_URL") or "").strip()
    if osm_url and osm_url not in known_urls:
        links.append(
            {
                "title": "OpenStreetMap",
                "url": osm_url,
                "note": "Lv0候補の位置・路線情報",
            }
        )
        known_urls.add(osm_url)

    evidence_urls = [
        value.strip()
        for value in str(row.get("根拠URL") or "").split(" | ")
        if value.strip()
    ]
    primary_source = str(row.get("主出典") or "").strip()
    for index, url in enumerate(evidence_urls):
        if url in known_urls:
            continue
        links.append(
            {
                "title": primary_source if index == 0 and primary_source else "照合資料",
                "url": url,
                "note": f"{row.get('Lv', 'Lv0')}昇格・照合根拠",
            }
        )
        known_urls.add(url)
    return links


def build_public_map_data(level_rows: list[dict[str, object]]) -> None:
    existing_rows: list[dict[str, object]] = []
    if MAP_DATA.exists():
        existing_rows = json.loads(MAP_DATA.read_text(encoding="utf-8"))
    existing_by_id = {str(row["id"]): row for row in existing_rows}

    map_rows: list[dict[str, object]] = []
    for row in level_rows:
        road_id = str(row["ID"])
        level = str(row.get("Lv") or "Lv0")
        existing = dict(existing_by_id.get(road_id, {}))
        lat = optional_float(row.get("代表緯度"))
        lon = optional_float(row.get("代表経度"))
        display_lat = existing.get("displayLat")
        display_lon = existing.get("displayLon")
        if not isinstance(display_lat, (int, float)) and lat is not None:
            display_lat = lat
        if not isinstance(display_lon, (int, float)) and lon is not None:
            display_lon = lon

        osm_ids = [
            int(value)
            for value in str(row.get("OSM_ID") or "").split("/")
            if value.isdigit()
        ]
        surface_bits = []
        for key, label in (
            ("OSM道路種別", "highway"),
            ("OSM路面", "surface"),
            ("OSM_tracktype", "tracktype"),
        ):
            value = str(row.get(key) or "").strip()
            if value:
                surface_bits.append(f"{label}={value}")

        cautions = list(existing.get("cautions") or [])
        for caution in (
            "入口未特定の候補はOSM代表点を表示しています",
            "通行可否・ゲート・路面は現地で最新状況を確認してください",
        ):
            if caution not in cautions:
                cautions.append(caution)
        osm_access = str(row.get("OSM_access") or "").strip()
        if osm_access in {"no", "private"}:
            access_caution = f"OSMにaccess={osm_access}の記載あり"
            if access_caution not in cautions:
                cautions.append(access_caution)

        municipality = str(row.get("関係市町村") or existing.get("municipality") or "")
        decision_reason = str(row.get("判定理由") or "").strip()
        primary_source = str(row.get("主出典") or "").strip()
        source = str(row.get("取得元") or "").strip()
        existing.update(
            {
                "id": road_id,
                "name": str(row.get("林道名") or existing.get("name") or ""),
                "municipality": municipality,
                "region": existing.get("region") or map_region(lat, lon),
                "priority": existing.get("priority") or {"Lv2": "B", "Lv1": "C"}.get(level, "D"),
                "displayLat": display_lat,
                "displayLon": display_lon,
                "entryLat": existing.get("entryLat"),
                "entryLon": existing.get("entryLon"),
                "exitLat": existing.get("exitLat"),
                "exitLon": existing.get("exitLon"),
                "positionStatus": existing.get("positionStatus")
                or ("OSM代表点" if lat is not None and lon is not None else "位置未特定"),
                "entranceClassification": existing.get("entranceClassification") or "unknown",
                "entranceClassificationNote": existing.get("entranceClassificationNote")
                or (
                    "入口未特定。OSM路線上の代表点として表示しています。"
                    if lat is not None and lon is not None
                    else "入口・代表点とも未特定です。候補資料のみ確認できます。"
                ),
                "entrances": existing.get("entrances") or [],
                "sourceType": existing.get("sourceType")
                or ("osm-road" if osm_ids else "official-map"),
                "positionSource": existing.get("positionSource")
                or (str(row.get("OSM_URL") or "") if osm_ids else "位置情報源未特定"),
                "candidateSource": primary_source or existing.get("candidateSource") or source,
                "summary": existing.get("summary")
                or decision_reason
                or "OSMから抽出した長野県内の林道候補です。",
                "surfaceSummary": existing.get("surfaceSummary")
                if existing.get("surfaceSummary") not in {None, "", "未確認"}
                else ("OSM: " + ", ".join(surface_bits) if surface_bits else "未確認"),
                "accessStatus": existing.get("accessStatus")
                if existing.get("accessStatus") not in {None, ""}
                else (f"OSM access={osm_access}・要現地確認" if osm_access else "要確認"),
                "cautions": cautions,
                "lastChecked": str(row.get("照合日") or row.get("取得日") or CHECKED_ON),
                "confidence": {"Lv2": "high", "Lv1": "medium"}.get(level, "low"),
                "osmWayIds": osm_ids,
                "primaryOsmWayId": osm_ids[0] if osm_ids else existing.get("primaryOsmWayId"),
                "sourceLinks": source_links_for_map(
                    list(existing.get("sourceLinks") or []),
                    row,
                ),
                "level": level,
                "levelStatus": str(row.get("照合状態") or ""),
                "levelReason": decision_reason,
                "evidenceCount": int(str(row.get("資料照合件数") or "0")),
                "detailAttributes": [
                    value.strip()
                    for value in str(row.get("詳細属性") or "").split(" | ")
                    if value.strip()
                ],
            }
        )
        map_rows.append(existing)

    MAP_DATA.write_text(
        json.dumps(map_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def host_for(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().split(":", 1)[0]


def is_usable_independent(entry: dict[str, object]) -> bool:
    return (
        entry.get("sourceClass") != "osm"
        and entry.get("confidence") != "ambiguous-same-name"
        and bool(entry.get("url"))
    )


def detail_attributes(
    row: dict[str, str],
    candidate_detail: dict[str, str],
    entries: list[dict[str, object]],
) -> list[str]:
    attributes: list[str] = []
    if row.get("OSM_ID"):
        attributes.append("路線形状")
    if row.get("OSM道路種別"):
        attributes.append("道路種別")
    if row.get("OSM路面"):
        attributes.append("路面")
    if row.get("OSM_tracktype"):
        attributes.append("tracktype")
    if row.get("OSM_access"):
        attributes.append("access")

    candidate_columns = {
        "行政計画": "行政計画",
        "事業型": "整備種別",
        "事業内容": "整備内容",
        "整備延長等": "整備延長",
        "利用区域ha": "利用区域",
        "通行可否": "通行情報",
        "未舗装手掛かり": "路面",
    }
    for column, attribute in candidate_columns.items():
        value = candidate_detail.get(column, "")
        if value and value not in {"未確認", "要確認", "なし"}:
            attributes.append(attribute)

    for entry in entries:
        if not is_usable_independent(entry):
            continue
        for attribute in entry.get("attributes", []):
            if attribute not in {"代表位置", "関係市町村"}:
                attributes.append(str(attribute))
    return list(dict.fromkeys(attributes))


def classify(
    row: dict[str, str],
    candidate_detail: dict[str, str],
    entries: list[dict[str, object]],
) -> dict[str, object]:
    independent = [entry for entry in entries if is_usable_independent(entry)]
    direct = [entry for entry in independent if entry.get("direct")]
    official = [entry for entry in direct if entry.get("sourceClass") == "official"]
    public = [entry for entry in independent if entry.get("sourceClass") == "public-web"]
    direct_domains = {host_for(str(entry["url"])) for entry in direct if host_for(str(entry["url"]))}
    attributes = detail_attributes(row, candidate_detail, entries)
    has_osm_position = bool(row.get("OSM_ID") and row.get("代表緯度") and row.get("代表経度"))
    has_basic = bool(
        row.get("関係市町村")
        or has_osm_position
        or official
        or candidate_detail.get("行政計画")
    )

    level = "Lv0"
    status = "照合済み・独立資料未確認"
    reason = "行政資料・公開資料との一意な一致を確認できず、OSM発見候補として継続。"
    if independent and has_basic:
        level = "Lv1"
        status = "基本情報確認"
        if official:
            reason = "行政資料で同名路線と市町村または計画区域を確認。"
        else:
            reason = "OSMとは独立した公開資料で同名路線と地域情報を確認。"

    official_osm_match = has_osm_position and bool(official)
    multi_public_match = has_osm_position and len(direct_domains) >= 2
    if level == "Lv1" and len(attributes) >= 2 and (official_osm_match or multi_public_match):
        level = "Lv2"
        status = "根拠付きカルテ"
        if official_osm_match:
            reason = (
                "位置付きOSMと行政資料を名称・地域で一意照合し、"
                f"{'・'.join(attributes[:5])}を確認。"
            )
        else:
            reason = (
                "位置付きOSMと独立した公開資料2系統以上を照合し、"
                f"{'・'.join(attributes[:5])}を確認。"
            )

    preferred = sorted(
        independent,
        key=lambda entry: (
            entry.get("sourceClass") != "official",
            not bool(entry.get("direct")),
            str(entry.get("url")),
        ),
    )
    urls = list(dict.fromkeys(str(entry["url"]) for entry in independent if entry.get("url")))
    primary = preferred[0] if preferred else None
    return {
        "level": level,
        "status": status,
        "evidenceCount": len(independent),
        "officialCount": len(official),
        "publicCount": len(public),
        "domainCount": len({host_for(url) for url in urls if host_for(url)}),
        "attributes": attributes,
        "reason": reason,
        "primarySource": str(primary["title"]) if primary else "",
        "urls": urls,
    }


def evidence_csv_rows(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for entry in entries:
        output.append(
            {
                "ID": entry.get("id", ""),
                "林道名": entry.get("name", ""),
                "関係市町村": entry.get("municipality", ""),
                "証拠種別": entry.get("sourceType", ""),
                "証拠区分": entry.get("sourceClass", ""),
                "資料名": entry.get("title", ""),
                "URL": entry.get("url", ""),
                "照合方法": entry.get("method", ""),
                "照合信頼度": entry.get("confidence", ""),
                "本文直接確認": "はい" if entry.get("direct") else "いいえ",
                "確認属性": " | ".join(str(value) for value in entry.get("attributes", [])),
                "抜粋": entry.get("excerpt", ""),
                "確認日": entry.get("checkedOn", ""),
            }
        )
    return output


def main() -> int:
    raw_fields, raw_rows = read_csv(lv0_path())
    entries: list[dict[str, object]] = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    by_id: dict[str, list[dict[str, object]]] = defaultdict(list)
    for entry in entries:
        by_id[str(entry["id"])].append(entry)

    candidate_details: dict[str, dict[str, str]] = {}
    if ENRICHED_MASTER.exists():
        _, detail_rows = read_csv(ENRICHED_MASTER)
        candidate_details = {row["ID"]: row for row in detail_rows}

    level_rows: list[dict[str, object]] = []
    levels: Counter[str] = Counter()
    source_types = Counter(str(entry.get("sourceType")) for entry in entries)
    rows_with_official = 0
    rows_with_public = 0
    rows_with_osm = 0
    no_municipality = 0
    unresolved_without_municipality = 0
    lv1_official = 0
    lv1_public_only = 0
    lv2_official = 0
    public_supplemented_official = 0
    original_144_levels: Counter[str] = Counter()
    new_919_levels: Counter[str] = Counter()
    for row in raw_rows:
        decision = classify(row, candidate_details.get(row["ID"], {}), by_id.get(row["ID"], []))
        row["Lv"] = str(decision["level"])
        row["照合状態"] = str(decision["status"])
        row["資料照合件数"] = str(decision["evidenceCount"])
        row["行政資料件数"] = str(decision["officialCount"])
        row["公開Web資料件数"] = str(decision["publicCount"])
        row["独立ドメイン数"] = str(decision["domainCount"])
        row["詳細属性"] = " | ".join(decision["attributes"])
        row["判定理由"] = str(decision["reason"])
        row["主出典"] = str(decision["primarySource"])
        row["根拠URL"] = " | ".join(decision["urls"])
        row["照合日"] = CHECKED_ON
        level_rows.append(dict(row))
        levels[row["Lv"]] += 1
        rows_with_official += int(int(row["行政資料件数"]) > 0)
        rows_with_public += int(int(row["公開Web資料件数"]) > 0)
        rows_with_osm += int(bool(row.get("OSM_ID")))
        no_municipality += int(not row.get("関係市町村") or row.get("関係市町村") == "長野県")
        unresolved_without_municipality += int(
            row["Lv"] == "Lv0"
            and (not row.get("関係市町村") or row.get("関係市町村") == "長野県")
        )
        lv1_official += int(row["Lv"] == "Lv1" and int(row["行政資料件数"]) > 0)
        lv1_public_only += int(
            row["Lv"] == "Lv1"
            and int(row["行政資料件数"]) == 0
            and int(row["公開Web資料件数"]) > 0
        )
        lv2_official += int(row["Lv"] == "Lv2" and int(row["行政資料件数"]) > 0)
        public_supplemented_official += int(
            int(row["行政資料件数"]) > 0 and int(row["公開Web資料件数"]) > 0
        )
        numeric_id = int(row["ID"].split("-")[1])
        if numeric_id <= 144:
            original_144_levels[row["Lv"]] += 1
        else:
            new_919_levels[row["Lv"]] += 1

    output_fields = list(dict.fromkeys(raw_fields + AUDIT_FIELDS))
    write_csv(LEVEL_MASTER, output_fields, level_rows)
    write_csv(lv0_path(), output_fields, level_rows)
    build_public_map_data(level_rows)

    evidence_fields = [
        "ID",
        "林道名",
        "関係市町村",
        "証拠種別",
        "証拠区分",
        "資料名",
        "URL",
        "照合方法",
        "照合信頼度",
        "本文直接確認",
        "確認属性",
        "抜粋",
        "確認日",
    ]
    write_csv(EVIDENCE_CSV, evidence_fields, evidence_csv_rows(entries))

    municipal_index = {}
    if MUNICIPAL_PLAN_INDEX.exists():
        municipal_index = json.loads(MUNICIPAL_PLAN_INDEX.read_text(encoding="utf-8"))
    municipal_with_documents = sorted(
        municipality
        for municipality, item in municipal_index.items()
        if item.get("documents")
    )
    municipal_without_documents = sorted(
        municipality
        for municipality, item in municipal_index.items()
        if not item.get("documents")
    )
    web_cache_count = len(list(WEB_CACHE_DIR.glob("*.json"))) if WEB_CACHE_DIR.exists() else 0
    web_cache_errors = 0
    if WEB_CACHE_DIR.exists():
        for path in WEB_CACHE_DIR.glob("*.json"):
            try:
                web_cache_errors += int("error" in json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                web_cache_errors += 1

    report = {
        "generatedOn": CHECKED_ON,
        "protocol": "docs/LEVELING_PROTOCOL.md",
        "mode": "行政資料優先の完全照合 + 公開林道カタログ補完",
        "totalCandidates": len(level_rows),
        "auditedCandidates": len(level_rows),
        "levelCounts": dict(sorted(levels.items())),
        "promotedCandidates": levels["Lv1"] + levels["Lv2"],
        "cohortLevelCounts": {
            "original144": dict(sorted(original_144_levels.items())),
            "newOsm919": dict(sorted(new_919_levels.items())),
        },
        "promotionBasis": {
            "Lv2OfficialAndOsm": lv2_official,
            "Lv1OfficialBasicOnly": lv1_official,
            "Lv1PublicOnly": lv1_public_only,
            "officialRowsAlsoSupplementedByPublicWeb": public_supplemented_official,
        },
        "sourceCoverage": {
            "withOsm": rows_with_osm,
            "withOfficialEvidence": rows_with_official,
            "withPublicWebEvidence": rows_with_public,
            "withoutMunicipality": no_municipality,
        },
        "unresolved": {
            "total": levels["Lv0"],
            "withoutMunicipality": unresolved_without_municipality,
            "reason": "独立資料との一意一致なし。OSM候補として保持し、個別調査対象へ送る。",
        },
        "evidenceRows": len(entries),
        "evidenceBySourceType": dict(sorted(source_types.items())),
        "municipalPlanResearch": {
            "municipalitiesIndexed": len(municipal_index),
            "withDocuments": len(municipal_with_documents),
            "withoutDocuments": municipal_without_documents,
        },
        "individualWebSearch": {
            "cachedRows": web_cache_count,
            "errorRows": web_cache_errors,
            "note": "検索サービスのHTTP 429後は連続検索を停止。公開カタログと公式資料で補完。",
        },
        "rules": {
            "Lv0": "独立資料との一意一致なし",
            "Lv1": "独立公開資料 + 基本情報",
            "Lv2": "位置付きOSM + 行政資料、または独立直接資料2ドメイン以上 + 詳細属性2項目以上",
        },
    }
    LEVEL_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Built {len(level_rows)} level rows: "
        + ", ".join(f"{level}={levels[level]}" for level in ["Lv0", "Lv1", "Lv2"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
