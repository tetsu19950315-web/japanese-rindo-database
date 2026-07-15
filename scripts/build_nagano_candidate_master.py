#!/usr/bin/env python3
"""Build the statewide Nagano candidate master without inventing road facts."""

from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
CURRENT_PLAN = PROCESSED / "nagano_current_plan.csv"
PLAN_HISTORY = PROCESSED / "nagano_plan_history.csv"
OSM_MATCHES = PROCESSED / "osm_nagano_candidate_matches.json"
MUNICIPALITY_BOUNDS = PROCESSED / "nagano_municipality_bounds.json"
EXISTING_MAP = PROCESSED / "mvp_map_data.json"
MASTER_CSV = PROCESSED / "nagano_candidate_master.csv"
MAP_JSON = PROCESSED / "nagano_map_data.json"
SHORTLIST_JSON = PROCESSED / "nagano_shortlist.json"
ENTRANCE_DATA = ROOT / "data" / "reference" / "nagano_entrances.json"

CURRENT_PLAN_URL = "https://www.pref.nagano.lg.jp/ringyo/documents/sinkeikaku2025.pdf"
CHINO_PLAN_URL = "https://www.city.chino.lg.jp/uploaded/attachment/28188.pdf"
SUWA_PLAN_URL = "https://www.city.suwa.lg.jp/uploaded/life/74090_150401_misc.pdf"
CHECKED_ON = "2026-07-10"


FIRST17 = {
    "NGN-000001": ("茅野市", "開設（新設）", "5,000m", "104", "位置未特定"),
    "NGN-000002": ("茅野市", "開設（新設）", "5,000m", "497", "位置未特定"),
    "NGN-000003": ("茅野市", "開設（新設）", "3,300m", "243", "位置未特定"),
    "NGN-000004": ("茅野市", "開設（新設）", "600m", "10", "位置未特定"),
    "NGN-000005": ("茅野市", "開設（改築）", "2,000m", "247", "位置未特定"),
    "NGN-000006": ("茅野市", "拡張（舗装）", "1,800m", "217", "代表点あり"),
    "NGN-000007": ("茅野市", "拡張（改良）・法面保全", "600m・10箇所", "130", "位置未特定"),
    "NGN-000008": ("茅野市", "拡張（改良）・局部改良", "1,000m・5箇所", "168", "位置未特定"),
    "NGN-000009": ("茅野市", "拡張（改良）・局部改良", "150m・3箇所", "59", "代表点あり"),
    "NGN-000010": ("茅野市", "拡張（改良）・局部改良", "50m・1箇所", "67", "線形あり"),
    "NGN-000011": ("諏訪市", "開設", "3,300m", "106", "代表点あり"),
    "NGN-000012": ("諏訪市", "拡張（改良）・法面保全", "1,000m・10箇所", "197", "代表点あり"),
    "NGN-000013": ("諏訪市", "拡張（改良・舗装）", "改良200m・2箇所／舗装1,000m", "125", "代表点あり"),
    "NGN-000014": ("諏訪市", "拡張（改良）・局部改良", "60m・2箇所", "68", "代表点あり"),
    "NGN-000015": ("諏訪市", "拡張（舗装）", "2,500m", "103", "代表点あり"),
    "NGN-000016": ("諏訪市", "拡張（舗装）", "2,000m", "315", "代表点あり"),
    "NGN-000017": ("諏訪市", "拡張（舗装）", "1,500m", "34", "代表点あり"),
}

EAST = {"佐久市", "小諸市", "上田市", "東御市", "軽井沢町", "御代田町", "立科町", "青木村", "長和町", "小海町", "佐久穂町", "川上村", "南牧村", "南相木村", "北相木村"}
NORTH = {"長野市", "須坂市", "千曲市", "坂城町", "小布施町", "高山村", "信濃町", "飯綱町", "小川村", "中野市", "飯山市", "山ノ内町", "木島平村", "野沢温泉村", "栄村"}
CENTRAL = {"松本市", "塩尻市", "安曇野市", "麻績村", "生坂村", "山形村", "朝日村", "筑北村", "大町市", "池田町", "松川村", "白馬村", "小谷村", "上松町", "南木曽町", "木祖村", "王滝村", "大桑村", "木曽町"}


def lv0_path() -> Path:
    return next((ROOT / "data" / "raw").glob("NGN_Lv0_Master_*.csv"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = text.replace("林道", "").replace("澤", "沢").replace("ヶ", "ケ").replace("ヵ", "カ")
    text = re.sub(r"[\s・･]", "", text)
    return text.removesuffix("線")


def municipality_region(value: str) -> str:
    names = set(re.split(r"[・／,、]", value or ""))
    if names & EAST:
        return "東信"
    if names & NORTH:
        return "北信"
    if names & CENTRAL:
        return "中信"
    return "南信" if value else "未分類"


def point_in_bounds(lat: float, lon: float, bounds: list[float], margin: float = 0.015) -> bool:
    south, north, west, east = bounds
    return south - margin <= lat <= north + margin and west - margin <= lon <= east + margin


def osm_signal(tags: dict) -> tuple[str, str]:
    highway = tags.get("highway", "")
    surface = tags.get("surface", "")
    tracktype = tags.get("tracktype", "")
    strong = surface in {"gravel", "ground", "dirt", "unpaved", "compacted", "fine_gravel"} or tracktype in {"grade2", "grade3", "grade4", "grade5"}
    detail = ", ".join(filter(None, [f"highway={highway}" if highway else "", f"surface={surface}" if surface else "", f"tracktype={tracktype}" if tracktype else ""]))
    return ("強" if strong else "中" if highway else "なし", detail)


def join_unique(values: list[str], separator: str = "・") -> str:
    return separator.join(dict.fromkeys(value for value in values if value))


def load_sources() -> tuple[list[dict], list[dict], list[dict], dict, list[dict], dict, dict]:
    current = read_csv(CURRENT_PLAN)
    history = read_csv(PLAN_HISTORY)
    osm = json.loads(OSM_MATCHES.read_text(encoding="utf-8"))["elements"]
    bounds = json.loads(MUNICIPALITY_BOUNDS.read_text(encoding="utf-8"))["municipalities"]
    existing_map = json.loads(EXISTING_MAP.read_text(encoding="utf-8"))
    map_by_id = {row["id"]: row for row in existing_map}
    entrance_data = json.loads(ENTRANCE_DATA.read_text(encoding="utf-8"))
    entrances_by_id = {row["roadId"]: row for row in entrance_data.get("roads", [])}
    return current, history, osm, bounds, existing_map, map_by_id, entrances_by_id


def append_current_plan_to_lv0(current: list[dict]) -> list[dict]:
    path = lv0_path()
    rows = read_csv(path)
    by_norm = {normalize_name(row["林道名"]): row for row in rows}
    max_id = max(int(row["ID"].split("-")[1]) for row in rows)
    additions = 0
    for plan in current:
        name = plan["林道名"].strip()
        key = normalize_name(name)
        if not name or key in by_norm:
            continue
        max_id += 1
        row = {
            "ID": f"NGN-{max_id:06d}",
            "林道名": name,
            "取得元": f"長野県『農山漁村地域整備計画（R7-R11）』 {CURRENT_PLAN_URL}",
        }
        rows.append(row)
        by_norm[key] = row
        additions += 1
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ID", "林道名", "取得元"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Lv0: {len(rows)} rows ({additions} appended)")
    return rows


def build() -> None:
    current, history, osm_elements, bounds, _existing_map, map_by_id, entrances_by_id = load_sources()
    lv0_rows = append_current_plan_to_lv0(current)

    current_by_norm: dict[str, list[dict]] = defaultdict(list)
    history_by_norm: dict[str, list[dict]] = defaultdict(list)
    for row in current:
        current_by_norm[normalize_name(row["林道名"])].append(row)
    for row in history:
        history_by_norm[normalize_name(row["林道名"])].append(row)

    osm_by_norm: dict[str, list[dict]] = defaultdict(list)
    for element in osm_elements:
        for candidate in element.get("candidateNames", []):
            osm_by_norm[normalize_name(candidate)].append(element)

    master: list[dict] = []
    map_rows: list[dict] = []
    for lv0 in lv0_rows:
        road_id = lv0["ID"]
        name = lv0["林道名"]
        key = normalize_name(name)
        current_rows = current_by_norm.get(key, [])
        history_rows = history_by_norm.get(key, [])

        if road_id in FIRST17:
            municipality, work_type, work_length, area_ha, position_status = FIRST17[road_id]
            plan_period = "茅野市森林整備計画" if municipality == "茅野市" else "諏訪市森林整備計画"
            plan_detail = f"{work_type} {work_length}"
        else:
            municipality = join_unique([row["関係市町村"] for row in current_rows]) or join_unique([row["関係市町村"] for row in history_rows])
            work_type = join_unique([row.get("事業型", "") for row in current_rows], "／")
            work_length = ""
            area_ha = ""
            position_status = "位置未特定"
            plan_period = "R7-R11" if current_rows else join_unique([row.get("計画期間", "") for row in history_rows], "／")
            plan_detail = join_unique([row.get("事業内容", "") for row in current_rows], "／")

        expected_municipalities = [value for value in re.split(r"[・／,、]", municipality) if value]
        verified_osm: list[dict] = []
        rejected_osm = 0
        for element in osm_by_norm.get(key, []):
            center = element.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue
            if not expected_municipalities:
                rejected_osm += 1
                continue
            matching_municipality = next(
                (
                    city for city in expected_municipalities
                    if city in bounds and point_in_bounds(lat, lon, bounds[city]["boundingbox"])
                ),
                None,
            )
            if matching_municipality:
                copied = dict(element)
                copied["matchedMunicipality"] = matching_municipality
                verified_osm.append(copied)
            else:
                rejected_osm += 1

        best_osm = None
        if verified_osm:
            best_osm = max(
                verified_osm,
                key=lambda item: (
                    osm_signal(item.get("tags", {}))[0] == "強",
                    item.get("tags", {}).get("highway") == "track",
                    item.get("tags", {}).get("surface") in {"gravel", "ground", "dirt", "unpaved", "compacted", "fine_gravel"},
                ),
            )

        existing = map_by_id.get(road_id)
        if existing:
            lat = existing.get("displayLat")
            lon = existing.get("displayLon")
            exit_lat = existing.get("exitLat")
            exit_lon = existing.get("exitLon")
            position_status = "線形あり" if exit_lat is not None else "代表点あり"
            position_source = existing.get("positionSource", "")
        elif best_osm:
            lat = best_osm["center"]["lat"]
            lon = best_osm["center"]["lon"]
            exit_lat = exit_lon = None
            position_status = "OSM名前一致代表点"
            position_source = f"OpenStreetMap way {best_osm['id']}（名前一致・市町村境界確認済み）"
        else:
            lat = lon = exit_lat = exit_lon = None
            position_source = ""

        osm_ids = [str(item["id"]) for item in verified_osm]
        osm_highways = [item.get("tags", {}).get("highway", "") for item in verified_osm]
        osm_surfaces = [item.get("tags", {}).get("surface", "") for item in verified_osm]
        osm_tracktypes = [item.get("tags", {}).get("tracktype", "") for item in verified_osm]
        signals = [osm_signal(item.get("tags", {}))[0] for item in verified_osm]
        unpaved_signal = "強" if "強" in signals else "中" if "中" in signals else "未確認"

        paving_plan = "舗装" in (plan_detail + work_type)
        current_plan = bool(current_rows)
        positioned = isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        restricted = any(item.get("tags", {}).get("access") in {"no", "private"} for item in verified_osm)

        score = 0
        score += 4 if current_plan else 1 if history_rows else 0
        score += 4 if verified_osm else 0
        score += 3 if unpaved_signal == "強" else 1 if unpaved_signal == "中" else 0
        score += 2 if positioned else 0
        score -= 4 if paving_plan else 0
        score -= 5 if restricted else 0
        if road_id in FIRST17:
            score += 2

        if restricted:
            priority = "保留"
            candidate_status = "通行制限タグ要確認"
        elif paving_plan:
            priority = "C"
            candidate_status = "舗装計画あり・優先度低"
        elif score >= 12:
            priority = "A"
            candidate_status = "全県有力候補"
        elif score >= 10:
            priority = "B"
            candidate_status = "次点候補"
        elif current_plan or road_id in FIRST17:
            priority = "C"
            candidate_status = "位置追加調査"
        else:
            priority = "D"
            candidate_status = "行政履歴確認済み"

        reasons = []
        if road_id in FIRST17:
            reasons.append("市森林整備計画で整備内容・延長・利用区域を確認")
        if current_plan:
            reasons.append("長野県R7-R11計画掲載")
        if verified_osm:
            reasons.append("OSM名前一致を市町村境界で確認")
        if unpaved_signal == "強":
            reasons.append("trackまたは未舗装系タグあり")
        if paving_plan:
            reasons.append("舗装計画記載のため未舗装候補としては低優先")
        if not positioned:
            reasons.append("入口・代表点未特定")

        cautions = ["通行可否・ゲート・路面は現地未確認"]
        if rejected_osm:
            cautions.append(f"同名OSM {rejected_osm}件は市町村不一致で除外")
        if len(expected_municipalities) > 1:
            cautions.append("同名路線が複数市町村に存在する可能性あり")
        if paving_plan:
            cautions.append("計画記載は施工完了や現況を保証しない")

        source = lv0["取得元"]
        source_url = CHINO_PLAN_URL if municipality == "茅野市" else SUWA_PLAN_URL if municipality == "諏訪市" else CURRENT_PLAN_URL if current_plan else source
        row = {
            "ID": road_id,
            "林道名": name,
            "関係市町村": municipality,
            "地域": municipality_region(municipality),
            "候補状態": candidate_status,
            "優先度": priority,
            "行政計画": plan_period,
            "事業型": work_type,
            "事業内容": plan_detail,
            "整備延長等": work_length,
            "利用区域ha": area_ha,
            "位置状態": position_status,
            "緯度": "" if lat is None else f"{lat:.7f}",
            "経度": "" if lon is None else f"{lon:.7f}",
            "OSM一致": "あり" if verified_osm else "なし",
            "OSM道路種別": join_unique(osm_highways, "/"),
            "OSM路面": join_unique(osm_surfaces, "/"),
            "OSM tracktype": join_unique(osm_tracktypes, "/"),
            "OSM way ID": join_unique(osm_ids, "/"),
            "未舗装手掛かり": unpaved_signal,
            "通行可否": "要確認" if not restricted else "OSM制限タグあり・要確認",
            "選定理由": "。".join(reasons) + ("。" if reasons else ""),
            "注意点": "。".join(cautions) + "。",
            "取得元": source,
            "位置情報源": position_source,
            "参照URL": source_url,
            "確認日": CHECKED_ON,
            "score": score,
            "primaryOsmWayId": best_osm["id"] if best_osm else None,
        }
        master.append(row)

        if positioned:
            entrance_record = entrances_by_id.get(road_id, {})
            entrances = entrance_record.get("entrances", [])
            primary_entrance = next((item for item in entrances if item.get("navEnabled")), None)
            summary = row["選定理由"] or "行政資料に掲載された長野県内の林道候補。"
            if plan_detail:
                summary += f" 計画記載: {plan_detail}。"
            map_rows.append({
                "id": road_id,
                "name": name,
                "municipality": municipality,
                "region": row["地域"],
                "priority": priority,
                "displayLat": lat,
                "displayLon": lon,
                "entryLat": primary_entrance.get("lat") if primary_entrance else None,
                "entryLon": primary_entrance.get("lon") if primary_entrance else None,
                "exitLat": exit_lat,
                "exitLon": exit_lon,
                "positionStatus": position_status,
                "entranceClassification": entrance_record.get("classification", "unknown"),
                "entranceClassificationNote": entrance_record.get("classificationNote", "入口未特定。代表点として表示する。"),
                "entrances": entrances,
                "sourceType": existing.get("sourceType", "osm-road") if existing else "osm-road",
                "positionSource": position_source,
                "candidateSource": source,
                "summary": summary,
                "surfaceSummary": "OSM: " + ", ".join(filter(None, [join_unique(osm_highways, "/"), join_unique(osm_surfaces, "/"), join_unique(osm_tracktypes, "/")])) if verified_osm else "未確認",
                "accessStatus": row["通行可否"],
                "cautions": cautions,
                "lastChecked": CHECKED_ON,
                "confidence": "high" if priority == "A" else "medium" if priority == "B" else "low",
                "osmWayIds": [int(value) for value in osm_ids],
                "primaryOsmWayId": best_osm["id"] if best_osm else None,
                "sourceLinks": list(filter(None, [
                    {"title": "行政計画", "url": source_url, "note": plan_detail},
                    {
                        "title": f"OpenStreetMap way {best_osm['id']}",
                        "url": f"https://www.openstreetmap.org/way/{best_osm['id']}",
                        "note": "名前一致・市町村境界確認済み",
                    } if best_osm else None,
                ])),
            })

    output_fields = [key for key in master[0] if key not in {"score", "primaryOsmWayId"}]
    with MASTER_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in output_fields} for row in master)
    MAP_JSON.write_text(json.dumps(map_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ranked = [row for row in master if row["優先度"] in {"A", "B"} and row["位置状態"] != "位置未特定"]
    ranked.sort(key=lambda row: (-row["score"], row["地域"], row["ID"]))
    selected = []
    per_region: dict[str, int] = defaultdict(int)
    for row in ranked:
        if len(selected) >= 16:
            break
        if per_region[row["地域"]] >= 6:
            continue
        per_region[row["地域"]] += 1
        selected.append(row)
    selected_ids = {row["ID"] for row in selected}
    shortlist = {
        "generatedOn": CHECKED_ON,
        "selectionMode": "長野県全域・行政資料と市町村確認済みOSMの高速選定",
        "selectionCriteria": [
            "行政資料に路線名が掲載されている",
            "位置は公式図またはOSM名前一致を市町村境界で確認できる",
            "track・gravel等の未舗装手掛かりを優先する",
            "舗装計画・通行制限タグ・位置不明は優先度を下げる",
            "通行可否は現地または管理者確認前提とする",
        ],
        "selected": [
            {
                "order": index,
                "id": row["ID"],
                "name": row["林道名"],
                "municipality": row["関係市町村"],
                "region": row["地域"],
                "priority": row["優先度"],
                "selectionReason": row["選定理由"],
                "positionStatus": row["位置状態"],
                "unpavedSignal": row["未舗装手掛かり"],
                "sources": list(dict.fromkeys(filter(None, [
                    row["参照URL"],
                    f"https://www.openstreetmap.org/way/{row['primaryOsmWayId']}" if row.get("primaryOsmWayId") else "",
                ]))),
            }
            for index, row in enumerate(selected, start=1)
        ],
        "reserve": [
            {
                "id": row["ID"],
                "name": row["林道名"],
                "municipality": row["関係市町村"],
                "region": row["地域"],
                "selectionReason": row["選定理由"],
            }
            for row in ranked if row["ID"] not in selected_ids
        ],
        "counts": {
            "master": len(master),
            "mapped": len(map_rows),
            "selected": len(selected),
            "priorityA": sum(row["優先度"] == "A" for row in master),
            "priorityB": sum(row["優先度"] == "B" for row in master),
        },
    }
    SHORTLIST_JSON.write_text(json.dumps(shortlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Master: {len(master)} / mapped: {len(map_rows)} / shortlist: {len(selected)}")
    print("Regions:", dict(per_region))
    print("Priorities:", {value: sum(row["優先度"] == value for row in master) for value in ["A", "B", "C", "D", "保留"]})


if __name__ == "__main__":
    build()
