#!/usr/bin/env python3
"""Collect auditable evidence for Nagano Lv0 road candidates.

The collector is intentionally conservative:

* OSM is recorded as the discovery/position source, never as independent proof.
* Official documents are matched by exact normalized names.
* Duplicate short names require municipality or plan-area disambiguation.
* Search-result snippets are retained as index evidence, but are not treated as
  direct documents.

Run the official phase first, then run the web phase in resumable chunks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
TMP = ROOT / "tmp" / "research"
EVIDENCE_OUTPUT = PROCESSED / "nagano_level_evidence.json"
MUNICIPAL_PLAN_INDEX = TMP / "municipal_plans" / "index.json"
WEB_CACHE_DIR = TMP / "web_search"
PYTHON_RESEARCH = ROOT / "tmp" / "python-research"
CHECKED_ON = "2026-07-16"
USER_AGENT = "JapaneseRindoDB/0.5 (+https://github.com/tetsu19950315-web/japanese-rindo-database)"

if PYTHON_RESEARCH.exists():
    sys.path.insert(0, str(PYTHON_RESEARCH))

try:
    import pdfplumber
    from pypdf import PdfReader
except ImportError as error:  # pragma: no cover - actionable local setup error
    raise SystemExit(
        "pdfplumber and pypdf are required. Install them with: "
        "python -m pip install --target tmp/python-research pdfplumber==0.11.8 pypdf==6.4.0"
    ) from error

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


NATIONAL_PLANS = {
    "lower": {
        "title": "千曲川下流国有林の地域別の森林計画書（第七次）",
        "url": "https://www.rinya.maff.go.jp/chubu/policy/business/sinrinkeikaku/attach/pdf/sinrinkeikaku21-298.pdf",
        "path": TMP / "plans" / "lower.pdf",
        "pages": [8],
        "municipalities": {
            "長野市", "須坂市", "千曲市", "坂城町", "小布施町", "高山村", "信濃町",
            "飯綱町", "小川村", "中野市", "飯山市", "山ノ内町", "木島平村",
            "野沢温泉村", "栄村",
        },
    },
    "upper": {
        "title": "千曲川上流国有林の地域別の森林計画書（第六次）",
        "url": "https://www.rinya.maff.go.jp/chubu/policy/business/sinrinkeikaku/attach/pdf/sinrinkeikaku21-183.pdf",
        "path": TMP / "plans" / "upper.pdf",
        "pages": [9],
        "municipalities": {
            "佐久市", "小諸市", "上田市", "東御市", "軽井沢町", "御代田町", "立科町",
            "青木村", "長和町", "小海町", "佐久穂町", "川上村", "南牧村",
            "南相木村", "北相木村",
        },
    },
    "ina": {
        "title": "伊那谷国有林の地域別の森林計画書（第六次）",
        "url": "https://www.rinya.maff.go.jp/chubu/policy/business/sinrinkeikaku/attach/pdf/sinrinkeikaku21-69.pdf",
        "path": TMP / "plans" / "ina.pdf",
        "pages": [8],
        "municipalities": {
            "岡谷市", "諏訪市", "茅野市", "下諏訪町", "富士見町", "原村", "伊那市",
            "駒ヶ根市", "辰野町", "箕輪町", "飯島町", "南箕輪村", "中川村", "宮田村",
            "飯田市", "松川町", "高森町", "阿南町", "阿智村", "平谷村", "根羽村",
            "下條村", "売木村", "天龍村", "泰阜村", "喬木村", "豊丘村", "大鹿村",
        },
    },
    "kiso": {
        "title": "木曽谷国有林の地域別の森林計画書（第六次）",
        "url": "https://www.rinya.maff.go.jp/chubu/policy/business/sinrinkeikaku/attach/pdf/sinrinkeikaku21-1.pdf",
        "path": TMP / "plans" / "kiso.pdf",
        "pages": [11, 12, 13],
        "municipalities": {"上松町", "南木曽町", "木祖村", "王滝村", "大桑村", "木曽町"},
    },
}

EXCLUDED_HOSTS = {
    "www.openstreetmap.org",
    "openstreetmap.org",
    "mapcarta.com",
    "ja.mapy.cz",
    "www.google.com",
    "google.com",
    "search.yahoo.co.jp",
    "www.bing.com",
    "bing.com",
}

ATTRIBUTE_PATTERNS = {
    "路面": re.compile(r"未舗装|舗装|ダート|砂利|グラベル|コンクリート"),
    "通行情報": re.compile(r"通行止|通行禁止|冬季閉鎖|ゲート|車両通行|通行可能|通行可"),
    "延長": re.compile(r"(?:延長|全長|距離).{0,20}\d+(?:[.,]\d+)?\s*(?:km|㎞|m|ｍ)", re.I),
    "路線特性": re.compile(r"完抜け|ピストン|行き止まり|支線|接続"),
}

MANUAL_MUNICIPAL_PLAN_SEEDS = {
    "生坂村": {
        "url": "https://www.village.ikusaka.nagano.jp/gyousei/sinkouka/pdf/sinrin16.pdf",
        "title": "生坂村森林整備計画",
    },
    "白馬村": {
        "url": "https://www.vill.hakuba.lg.jp/gyosei/soshikikarasagasu/noseika/norinkakari/1/1466.html",
        "title": "白馬村森林整備計画",
    },
    "筑北村": {
        "url": "https://www.vill.chikuhoku.lg.jp/fs/1/2/9/8/_/sinrinseibikeikaku.pdf",
        "title": "筑北村森林整備計画",
    },
    "箕輪町": {
        "url": "https://www.town.minowa.lg.jp/material/files/group/13/seibikeikaku.pdf",
        "title": "箕輪町森林整備計画",
    },
    "茅野市": {
        "url": "https://www.city.chino.lg.jp/uploaded/attachment/28188.pdf",
        "title": "茅野市森林整備計画書",
    },
    "諏訪市": {
        "url": "https://www.city.suwa.lg.jp/uploaded/life/74090_150401_misc.pdf",
        "title": "諏訪市森林整備計画書",
    },
    "豊丘村": {
        "url": "https://www.vill.nagano-toyooka.lg.jp/10sangyou/03ringyou/",
        "title": "豊丘村森林整備計画",
    },
    "長野市": {
        "url": "https://www.city.nagano.nagano.jp/documents/19569/naganoshishinrinseibikeikakusyo.pdf",
        "title": "長野市森林整備計画書",
    },
    "阿智村": {
        "url": "https://www.vill.achi.lg.jp/soshiki/33/20230401sinrinseibikeikaku.html",
        "title": "阿智村森林整備計画",
    },
    "須坂市": {
        "url": "https://www.city.suzaka.nagano.jp/material/files/group/16/shinrinseibikeikaku_pdf.pdf",
        "title": "須坂市森林整備計画",
    },
    "飯田市": {
        "url": "https://www.city.iida.lg.jp/uploaded/life/102942_294482_misc.pdf",
        "title": "飯田市森林整備計画",
    },
    "駒ヶ根市": {
        "url": "https://www.city.komagane.nagano.jp/material/files/group/11/R7sinrinseibikeikaku.pdf",
        "title": "駒ヶ根市森林整備計画",
    },
    "高山村": {
        "url": "https://www.vill.takayama.nagano.jp/fs/4/3/3/4/2/8/_/__7___________.pdf",
        "title": "高山村森林整備計画",
    },
}

PUBLIC_CATALOGS = [
    "https://rindo-ktansaku.sakura.ne.jp/nagano-top/nagano-list-1.htm",
    "https://rindo-ktansaku.sakura.ne.jp/nagano-top/nagano-list-2.htm",
]

PUBLIC_DETAIL_SEEDS = [
    {
        "name": "王城枝垂栗線",
        "municipalities": ["辰野町", "岡谷市"],
        "url": "https://rindoufan.hatenablog.com/entry/2020/01/31/231413",
        "title": "長野県・林道 王城枝垂栗線",
        "attributes": ["路面", "路線特性", "難易度", "実走記録"],
    },
]


def lv0_path() -> Path:
    return next(RAW_DIR.glob("NGN_Lv0_Master_*.csv"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = (
        text.replace("林道", "")
        .replace("澤", "沢")
        .replace("ヶ", "ケ")
        .replace("ヵ", "カ")
        .replace("（", "(")
        .replace("）", ")")
    )
    text = re.sub(r"[\s・･·]", "", text)
    return text.removesuffix("線")


def compact_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(value or ""))
    text = text.replace("澤", "沢").replace("ヶ", "ケ").replace("ヵ", "カ")
    return re.sub(r"\s+", "", text)


def municipality_values(value: str) -> set[str]:
    return {
        part
        for part in re.split(r"[・／/,、\s]+", value or "")
        if part and part not in {"長野県"}
    }


def urls_in(value: str) -> list[str]:
    return re.findall(r"https?://[^\s|]+", value or "")


def host_for(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().split(":", 1)[0]


def is_official_url(url: str) -> bool:
    host = host_for(url)
    return (
        host.endswith(".go.jp")
        or host.endswith(".lg.jp")
        or ".pref." in host
        or host.startswith(("www.city.", "city.", "www.town.", "town.", "www.vill.", "vill."))
    )


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch_bytes(url: str, max_bytes: int = 25_000_000, timeout: int = 45) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ja,en;q=0.5",
            "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"response exceeds {max_bytes} bytes")
        return data, content_type


def fetch_with_retry(url: str, attempts: int = 2) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetch_bytes(url)
        except (OSError, urllib.error.URLError, ValueError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt)
    assert last_error is not None
    raise last_error


def decode_html(data: bytes, content_type: str) -> str:
    charset_match = re.search(r"charset=([\w-]+)", content_type)
    encodings = [charset_match.group(1)] if charset_match else []
    encodings.extend(["utf-8", "shift_jis", "cp932"])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def yahoo_search(query: str) -> list[dict[str, str]]:
    url = "https://search.yahoo.co.jp/search?p=" + urllib.parse.quote(query)
    data, content_type = fetch_with_retry(url)
    source = decode_html(data, content_type)
    results: list[dict[str, str]] = []
    for block in re.findall(r"(?is)<li(?:\s[^>]*)?>(.*?)</li>", source):
        links = re.findall(
            r"""(?is)<a\b[^>]*href=(["'])(.*?)\1[^>]*>(.*?)</a>""",
            block,
        )
        for _, href, label in links:
            href = html.unescape(href)
            if not href.startswith(("http://", "https://")):
                continue
            host = host_for(href)
            if host.endswith("yahoo.co.jp") or host.endswith("yahoo.net.jp"):
                continue
            text = strip_tags(block)
            title = strip_tags(label)
            results.append({"url": href, "title": title, "text": text})
            break
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        canonical = result["url"].split("#", 1)[0]
        if canonical in seen:
            continue
        seen.add(canonical)
        unique.append(result)
    return unique


def load_evidence() -> list[dict[str, object]]:
    if not EVIDENCE_OUTPUT.exists():
        return []
    return json.loads(EVIDENCE_OUTPUT.read_text(encoding="utf-8"))


def save_evidence(entries: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    for entry in entries:
        key = (str(entry["id"]), str(entry["url"]), str(entry["sourceType"]))
        by_key[key] = entry
    output = sorted(by_key.values(), key=lambda row: (str(row["id"]), str(row["sourceType"]), str(row["url"])))
    EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def evidence(
    row: dict[str, str],
    *,
    source_type: str,
    source_class: str,
    title: str,
    url: str,
    method: str,
    confidence: str,
    direct: bool,
    attributes: Iterable[str] = (),
    excerpt: str = "",
) -> dict[str, object]:
    return {
        "id": row["ID"],
        "name": row["林道名"],
        "municipality": row.get("関係市町村", ""),
        "sourceType": source_type,
        "sourceClass": source_class,
        "title": title,
        "url": url,
        "method": method,
        "confidence": confidence,
        "direct": direct,
        "attributes": list(dict.fromkeys(attributes)),
        "excerpt": re.sub(r"\s+", " ", excerpt).strip()[:500],
        "checkedOn": CHECKED_ON,
    }


def baseline_evidence(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        osm_url = row.get("OSM_URL", "")
        if osm_url:
            attributes = ["代表位置", "路線形状"]
            if row.get("OSM道路種別"):
                attributes.append("道路種別")
            if row.get("OSM路面"):
                attributes.append("路面")
            if row.get("OSM_tracktype"):
                attributes.append("tracktype")
            if row.get("OSM_access"):
                attributes.append("access")
            output.append(
                evidence(
                    row,
                    source_type="osm",
                    source_class="osm",
                    title="OpenStreetMap",
                    url=osm_url.split("|", 1)[0],
                    method="OSM名称付き道路候補と線形",
                    confidence="discovery",
                    direct=True,
                    attributes=attributes,
                )
            )

        source = row.get("取得元", "")
        non_osm_urls = [url for url in urls_in(source) if host_for(url) not in EXCLUDED_HOSTS]
        if not non_osm_urls and row.get("発見種別") != "既存資料":
            continue
        for source_url in non_osm_urls:
            output.append(
                evidence(
                    row,
                    source_type="existing-official" if is_official_url(source_url) else "existing-public",
                    source_class="official" if is_official_url(source_url) else "public-web",
                    title=source.split("http", 1)[0].strip(" |") or host_for(source_url),
                    url=source_url,
                    method="既存Lv0資料から継承",
                    confidence="exact-municipality",
                    direct=True,
                    attributes=["行政計画", "関係市町村"] if is_official_url(source_url) else ["関係市町村"],
                )
            )
    return output


def add_processed_plan_evidence(
    rows: list[dict[str, str]],
    output: list[dict[str, object]],
) -> None:
    by_name_municipality: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for municipality in municipality_values(row.get("関係市町村", "")):
            by_name_municipality[(normalize_name(row["林道名"]), municipality)].append(row)

    plan_specs = [
        (
            PROCESSED / "nagano_current_plan.csv",
            "長野県『農山漁村地域整備計画（R7-R11）』",
            "current-prefectural-plan",
        ),
        (
            PROCESSED / "nagano_plan_history.csv",
            "長野県『農山漁村地域整備計画』過年度資料",
            "historical-prefectural-plan",
        ),
    ]
    for path, fallback_title, source_type in plan_specs:
        if not path.exists():
            continue
        for plan_row in read_csv(path):
            road_name = plan_row.get("林道名", "")
            municipality = plan_row.get("関係市町村", "")
            candidates = by_name_municipality.get((normalize_name(road_name), municipality), [])
            if len(candidates) != 1:
                continue
            candidate = candidates[0]
            source_text = plan_row.get("行政出典") or plan_row.get("取得元") or ""
            source_urls = urls_in(source_text)
            if not source_urls:
                continue
            attributes = ["行政計画", "関係市町村"]
            if plan_row.get("事業型"):
                attributes.append("整備種別")
            if plan_row.get("事業内容"):
                attributes.append("整備内容")
            if plan_row.get("工期"):
                attributes.append("工期")
            output.append(
                evidence(
                    candidate,
                    source_type=source_type,
                    source_class="official",
                    title=source_text.split("http", 1)[0].strip() or fallback_title,
                    url=source_urls[0],
                    method="林道名・市町村の完全一致",
                    confidence="exact-municipality",
                    direct=True,
                    attributes=attributes,
                    excerpt=" | ".join(
                        value
                        for value in [
                            plan_row.get("事業型", ""),
                            plan_row.get("事業内容", ""),
                            plan_row.get("工期", ""),
                        ]
                        if value
                    ),
                )
            )


def national_plan_names(spec: dict[str, object]) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    with pdfplumber.open(Path(spec["path"])) as pdf:
        for page_index in spec["pages"]:
            page = pdf.pages[int(page_index)]
            for table in page.extract_tables():
                for table_row in table[1:]:
                    if len(table_row) < 3 or not table_row[2]:
                        continue
                    for line in str(table_row[2]).splitlines():
                        line = re.sub(r"\s+", "", line)
                        if not line or line.startswith("計") or "箇所" in line:
                            continue
                        split_lines = [line]
                        if "・" in line:
                            parts = [part for part in line.split("・") if part]
                            if len(parts) > 1 and all(part.endswith("線") for part in parts):
                                split_lines = parts
                        for route_name in split_lines:
                            names.append((route_name, f"資料ページ {int(page_index) + 1}"))
    return names


def add_national_plan_evidence(
    rows: list[dict[str, str]],
    output: list[dict[str, object]],
) -> None:
    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_name[normalize_name(row["林道名"])].append(row)

    for spec in NATIONAL_PLANS.values():
        allowed = set(spec["municipalities"])
        for route_name, excerpt in national_plan_names(spec):
            aliases = [route_name]
            base = re.sub(r"[（(].*?[）)]", "", route_name)
            if base and base != route_name:
                aliases.append(base)
            candidates: list[dict[str, str]] = []
            for alias in aliases:
                candidates.extend(by_name.get(normalize_name(alias), []))
            candidates = list({candidate["ID"]: candidate for candidate in candidates}.values())
            regional = [
                candidate
                for candidate in candidates
                if municipality_values(candidate.get("関係市町村", "")) & allowed
            ]
            selected = regional
            confidence = "exact-plan-area"
            method = "国有林計画の路線名完全一致・計画区域で一意"
            if not selected:
                blank_municipality = [
                    candidate
                    for candidate in candidates
                    if not municipality_values(candidate.get("関係市町村", ""))
                    and len(normalize_name(route_name)) >= 4
                ]
                if len(candidates) == 1 and len(blank_municipality) == 1:
                    selected = blank_municipality
                    confidence = "exact-name-positioned"
                    method = "国有林計画の長い路線名完全一致・OSM位置あり・同名候補一意"
            if len(selected) != 1:
                continue
            candidate = selected[0]
            output.append(
                evidence(
                    candidate,
                    source_type="national-forest-plan",
                    source_class="official",
                    title=str(spec["title"]),
                    url=str(spec["url"]),
                    method=method,
                    confidence=confidence,
                    direct=True,
                    attributes=["行政計画", "整備種別", "整備延長"],
                    excerpt=f"{route_name} / {excerpt}",
                )
            )


def official_pdf_links(page_url: str, page_html: str) -> list[str]:
    links: list[str] = []
    for _, href, label in re.findall(
        r"""(?is)<a\b[^>]*href=(["'])(.*?)\1[^>]*>(.*?)</a>""",
        page_html,
    ):
        target = urllib.parse.urljoin(page_url, html.unescape(href))
        text = strip_tags(label)
        if not target.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        if re.search(r"森林整備計画|森林計画|計画書|林道", text + target, re.I):
            links.append(target)
    return list(dict.fromkeys(links))


def cached_document_text(url: str) -> tuple[str, str]:
    cache_dir = TMP / "municipal_plans" / "documents"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".pdf" if urllib.parse.urlparse(url).path.lower().endswith(".pdf") else ".html"
    cache_path = cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}{suffix}"
    if not cache_path.exists():
        data, content_type = fetch_with_retry(url)
        if "pdf" in content_type or data.startswith(b"%PDF"):
            cache_path = cache_path.with_suffix(".pdf")
        cache_path.write_bytes(data)
    data = cache_path.read_bytes()
    if cache_path.suffix == ".pdf" or data.startswith(b"%PDF"):
        text_cache = cache_path.with_suffix(".txt")
        if text_cache.exists():
            return text_cache.read_text(encoding="utf-8"), "pdf"
        try:
            reader = PdfReader(cache_path)
            if len(reader.pages) > 250:
                return "", "pdf-too-many-pages"
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            text_cache.write_text(text, encoding="utf-8")
            return text, "pdf"
        except Exception:
            return "", "pdf-unreadable"
    text_cache = cache_path.with_suffix(".txt")
    if text_cache.exists():
        return text_cache.read_text(encoding="utf-8"), "html"
    text = strip_tags(decode_html(data, "text/html"))
    text_cache.write_text(text, encoding="utf-8")
    return text, "html"


def candidate_occurs_in_plan(name: str, document_text: str) -> tuple[bool, str]:
    needle = normalize_name(name)
    if not needle:
        return False, ""
    compact = compact_text(document_text)
    raw_name = compact_text(name).replace("林道", "")
    if len(needle) < 4 and raw_name not in compact:
        return False, ""
    normalized_document = normalize_name(compact)
    position = normalized_document.find(needle)
    if position < 0:
        return False, ""
    raw_position = compact.find(needle)
    if raw_position < 0:
        raw_position = max(0, position)
    excerpt = compact[max(0, raw_position - 120): raw_position + len(needle) + 160]
    context_keywords = re.search(r"林道|路線名|開設|改良|拡張|舗装|延長|利用区域", excerpt)
    if len(needle) < 4 and not context_keywords:
        return False, excerpt
    return bool(context_keywords or len(needle) >= 4), excerpt


def discover_municipal_plan_urls(municipality: str) -> list[dict[str, str]]:
    query = f'"{municipality}" 森林整備計画 林道 PDF'
    results = yahoo_search(query)
    selected: list[dict[str, str]] = []
    for result in results:
        if not is_official_url(result["url"]):
            continue
        if not re.search(r"森林整備計画|森林計画|林道", result["text"]):
            continue
        selected.append(result)
        if len(selected) >= 1:
            break
    return selected


def load_municipal_plan_index() -> dict[str, object]:
    if not MUNICIPAL_PLAN_INDEX.exists():
        return {}
    return json.loads(MUNICIPAL_PLAN_INDEX.read_text(encoding="utf-8"))


def save_municipal_plan_index(index: dict[str, object]) -> None:
    MUNICIPAL_PLAN_INDEX.parent.mkdir(parents=True, exist_ok=True)
    MUNICIPAL_PLAN_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def add_municipal_plan_evidence(
    rows: list[dict[str, str]],
    output: list[dict[str, object]],
    *,
    delay: float,
    municipality_limit: int | None,
    municipality_start_index: int,
    municipality_count: int | None,
) -> None:
    by_municipality: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for municipality in municipality_values(row.get("関係市町村", "")):
            by_municipality[municipality].append(row)

    index = load_municipal_plan_index()
    municipalities = sorted(by_municipality)
    municipalities = municipalities[municipality_start_index:]
    if municipality_count is not None:
        municipalities = municipalities[:municipality_count]
    processed_new = 0
    for municipality_number, municipality in enumerate(municipalities, start=1):
        if municipality_limit is not None and processed_new >= municipality_limit:
            break
        cached = index.get(municipality)
        manual_seed = MANUAL_MUNICIPAL_PLAN_SEEDS.get(municipality)
        if manual_seed and (cached is None or cached.get("error")):
            cached = {
                "searchedOn": CHECKED_ON,
                "results": [
                    {
                        "url": manual_seed["url"],
                        "title": manual_seed["title"],
                        "text": manual_seed["title"],
                    }
                ],
                "documents": [],
                "seeded": True,
            }
            index[municipality] = cached
            save_municipal_plan_index(index)
        if cached is None:
            try:
                search_results = discover_municipal_plan_urls(municipality)
                cached = {"searchedOn": CHECKED_ON, "results": search_results, "documents": []}
                index[municipality] = cached
                save_municipal_plan_index(index)
                processed_new += 1
                time.sleep(delay)
            except Exception as error:
                index[municipality] = {
                    "searchedOn": CHECKED_ON,
                    "results": [],
                    "documents": [],
                    "error": f"{type(error).__name__}: {error}",
                }
                save_municipal_plan_index(index)
                processed_new += 1
                continue

        documents: list[dict[str, str]] = list(cached.get("documents", []))
        if not documents:
            document_urls: list[tuple[str, str]] = []
            for result in cached.get("results", []):
                result_url = result["url"]
                if result_url.lower().split("?", 1)[0].endswith(".pdf"):
                    document_urls.append((result_url, result.get("title", "")))
                    continue
                try:
                    data, content_type = fetch_with_retry(result_url)
                    page_html = decode_html(data, content_type)
                    for pdf_url in official_pdf_links(result_url, page_html):
                        document_urls.append((pdf_url, result.get("title", "")))
                except Exception:
                    continue
            for document_url, title in list(dict.fromkeys(document_urls))[:1]:
                try:
                    text, kind = cached_document_text(document_url)
                    documents.append(
                        {
                            "url": document_url,
                            "title": title or f"{municipality}森林整備計画",
                            "kind": kind,
                            "textLength": str(len(text)),
                        }
                    )
                except Exception as error:
                    documents.append(
                        {
                            "url": document_url,
                            "title": title or f"{municipality}森林整備計画",
                            "kind": "error",
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
            cached["documents"] = documents
            save_municipal_plan_index(index)

        for document in documents[:1]:
            if document.get("kind") in {"error", "pdf-unreadable", "pdf-too-many-pages"}:
                continue
            document_title = compact_text(document.get("title", ""))
            if municipality not in document_title:
                continue
            try:
                document_text, _ = cached_document_text(document["url"])
            except Exception:
                continue
            matches: dict[str, list[dict[str, str]]] = defaultdict(list)
            excerpts: dict[str, str] = {}
            for candidate in by_municipality[municipality]:
                matched, excerpt = candidate_occurs_in_plan(candidate["林道名"], document_text)
                if matched:
                    key = normalize_name(candidate["林道名"])
                    matches[key].append(candidate)
                    excerpts[candidate["ID"]] = excerpt
            for same_name in matches.values():
                confidence = "exact-municipality" if len(same_name) == 1 else "ambiguous-same-name"
                for candidate in same_name:
                    output.append(
                        evidence(
                            candidate,
                            source_type="municipal-forest-plan",
                            source_class="official",
                            title=document.get("title") or f"{municipality}森林整備計画",
                            url=document["url"],
                            method="市町村森林整備計画内の路線名一致",
                            confidence=confidence,
                            direct=confidence == "exact-municipality",
                            attributes=["行政計画", "関係市町村"],
                            excerpt=excerpts.get(candidate["ID"], ""),
                        )
                    )
        print(
            f"Municipal plans: {municipality_number}/{len(municipalities)} "
            f"{municipality}; documents={len(documents)}"
        )


def add_public_catalog_evidence(
    rows: list[dict[str, str]],
    output: list[dict[str, object]],
) -> None:
    by_name_municipality: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for municipality in municipality_values(row.get("関係市町村", "")):
            by_name_municipality[(normalize_name(row["林道名"]), municipality)].append(row)

    for catalog_url in PUBLIC_CATALOGS:
        try:
            data, content_type = fetch_with_retry(catalog_url)
            source = decode_html(data, content_type)
        except Exception:
            continue
        sections = re.findall(
            r"(?is)<b>\s*([^<]*?(?:市|町|村))\s*/[^<]*</b>(.*?)(?=<b>\s*[^<]*?(?:市|町|村)\s*/|$)",
            source,
        )
        for municipality, section in sections:
            municipality = re.sub(r"\s+", "", strip_tags(municipality))
            for row_block in re.findall(r"(?is)<tr\b.*?</tr>", section):
                anchor = re.search(
                    r"""(?is)<a\b[^>]*href=(["'])(.*?)\1[^>]*>(.*?)</a>""",
                    row_block,
                )
                if not anchor:
                    continue
                road_name = strip_tags(anchor.group(3))
                if "林道" not in road_name:
                    continue
                candidates = by_name_municipality.get((normalize_name(road_name), municipality), [])
                if len(candidates) != 1:
                    continue
                candidate = candidates[0]
                row_text = strip_tags(row_block)
                attributes = ["実走記録"]
                if "○" in row_text or re.search(r"ダート|未舗装|舗装", row_text):
                    attributes.append("路面")
                if re.search(r"完抜|ピストン|行き止まり", row_text):
                    attributes.append("路線特性")
                if re.search(r"封鎖|通行|ゲート|崩落", row_text):
                    attributes.append("通行情報")
                detail_url = urllib.parse.urljoin(catalog_url, html.unescape(anchor.group(2)))
                output.append(
                    evidence(
                        candidate,
                        source_type="public-catalog",
                        source_class="public-web",
                        title=f"林道探索の書「{road_name}」",
                        url=detail_url,
                        method="掲載林道一覧の林道名・市町村完全一致",
                        confidence="exact-municipality",
                        direct=True,
                        attributes=attributes,
                        excerpt=row_text,
                    )
                )

    by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_name[normalize_name(row["林道名"])].append(row)
    for seed in PUBLIC_DETAIL_SEEDS:
        allowed_municipalities = set(seed.get("municipalities", []))
        candidates = [
            row
            for row in by_name.get(normalize_name(str(seed["name"])), [])
            if allowed_municipalities & municipality_values(row.get("関係市町村", ""))
        ]
        if len(candidates) != 1:
            continue
        output.append(
            evidence(
                candidates[0],
                source_type="public-detail",
                source_class="public-web",
                title=str(seed["title"]),
                url=str(seed["url"]),
                method="実走記事の林道名・所在地完全一致",
                confidence="exact-direct",
                direct=True,
                attributes=list(seed["attributes"]),
            )
        )


def result_matches_candidate(
    row: dict[str, str],
    result: dict[str, str],
    duplicate_count: int,
) -> bool:
    host = host_for(result["url"])
    if host in EXCLUDED_HOSTS:
        return False
    needle = normalize_name(row["林道名"])
    haystack = normalize_name(result["text"])
    if not needle or needle not in haystack:
        return False
    compact = compact_text(result["text"])
    municipalities = municipality_values(row.get("関係市町村", ""))
    needs_location = len(needle) < 4 or duplicate_count > 1
    if needs_location and municipalities and not any(value in compact for value in municipalities):
        return False
    if len(needle) < 4 and "林道" not in compact:
        return False
    return True


def direct_page_evidence(
    row: dict[str, str],
    result: dict[str, str],
    duplicate_count: int,
) -> tuple[bool, list[str], str]:
    url = result["url"]
    host = host_for(url)
    if host.endswith(("youtube.com", "youtu.be", "instagram.com", "facebook.com", "x.com", "twitter.com")):
        return False, [], result["text"]
    try:
        text, kind = cached_document_text(url)
    except Exception:
        return False, [], result["text"]
    needle = normalize_name(row["林道名"])
    normalized = normalize_name(text)
    if not needle or needle not in normalized:
        return False, [], result["text"]
    compact = compact_text(text)
    municipalities = municipality_values(row.get("関係市町村", ""))
    needs_location = len(needle) < 4 or duplicate_count > 1
    if needs_location and municipalities and not any(value in compact for value in municipalities):
        return False, [], result["text"]
    attributes = [
        attribute
        for attribute, pattern in ATTRIBUTE_PATTERNS.items()
        if pattern.search(text)
    ]
    position = normalized.find(needle)
    excerpt = compact[max(0, position - 120): position + len(needle) + 240]
    return True, attributes, excerpt or result["text"]


def web_search_row(
    row: dict[str, str],
    duplicate_count: int,
    max_results: int,
) -> list[dict[str, object]]:
    municipality = row.get("関係市町村", "") or "長野県"
    name = row["林道名"]
    query = f'"{name}" 林道 "{municipality}" 長野県'
    results = yahoo_search(query)
    output: list[dict[str, object]] = []
    accepted_hosts: set[str] = set()
    for result in results:
        if not result_matches_candidate(row, result, duplicate_count):
            continue
        host = host_for(result["url"])
        if host in accepted_hosts:
            continue
        accepted_hosts.add(host)
        direct, attributes, excerpt = direct_page_evidence(row, result, duplicate_count)
        source_class = "official" if is_official_url(result["url"]) else "public-web"
        output.append(
            evidence(
                row,
                source_type="web-direct" if direct else "web-index",
                source_class=source_class,
                title=result["title"] or host,
                url=result["url"],
                method="公開Web検索の完全一致後に本文確認" if direct else "公開Web検索の見出し・要約一致",
                confidence="exact-direct" if direct else "exact-index",
                direct=direct,
                attributes=attributes,
                excerpt=excerpt,
            )
        )
        if len(output) >= max_results:
            break
    return output


def add_web_evidence(
    rows: list[dict[str, str]],
    entries: list[dict[str, object]],
    *,
    start_index: int,
    limit: int | None,
    delay: float,
    max_results: int,
    only_without_independent: bool,
) -> list[dict[str, object]]:
    independent_by_id: Counter[str] = Counter()
    for entry in entries:
        if entry.get("sourceClass") not in {"osm"} and entry.get("confidence") != "ambiguous-same-name":
            independent_by_id[str(entry["id"])] += 1
    name_counts = Counter(normalize_name(row["林道名"]) for row in rows)
    targets = [
        row
        for row in rows
        if not only_without_independent or independent_by_id[row["ID"]] == 0
    ]
    targets = targets[start_index:]
    if limit is not None:
        targets = targets[:limit]

    WEB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for number, row in enumerate(targets, start=1):
        cache_path = WEB_CACHE_DIR / f"{row['ID']}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            row_entries = cached.get("evidence", [])
        else:
            try:
                row_entries = web_search_row(row, name_counts[normalize_name(row["林道名"])], max_results)
                cache_path.write_text(
                    json.dumps(
                        {
                            "id": row["ID"],
                            "queryName": row["林道名"],
                            "searchedOn": CHECKED_ON,
                            "evidence": row_entries,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception as error:
                cache_path.write_text(
                    json.dumps(
                        {
                            "id": row["ID"],
                            "queryName": row["林道名"],
                            "searchedOn": CHECKED_ON,
                            "error": f"{type(error).__name__}: {error}",
                            "evidence": [],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                row_entries = []
            time.sleep(delay)
        entries.extend(row_entries)
        if number % 25 == 0 or number == len(targets):
            entries = save_evidence(entries)
            print(f"Web evidence: {number}/{len(targets)} rows processed; total evidence={len(entries)}")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["official", "web", "all"], default="official")
    parser.add_argument("--delay", type=float, default=0.65)
    parser.add_argument("--municipality-limit", type=int)
    parser.add_argument("--municipality-start-index", type=int, default=0)
    parser.add_argument("--municipality-count", type=int)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument(
        "--all-web",
        action="store_true",
        help="Search rows that already have independent evidence too.",
    )
    args = parser.parse_args()

    rows = read_csv(lv0_path())
    entries = load_evidence()
    if args.phase in {"official", "all"}:
        entries = [
            entry
            for entry in entries
            if entry.get("sourceType") not in {
                "osm",
                "existing-official",
                "existing-public",
                "current-prefectural-plan",
                "historical-prefectural-plan",
                "national-forest-plan",
                "municipal-forest-plan",
                "public-catalog",
                "public-detail",
            }
        ]
        entries.extend(baseline_evidence(rows))
        add_processed_plan_evidence(rows, entries)
        add_national_plan_evidence(rows, entries)
        add_municipal_plan_evidence(
            rows,
            entries,
            delay=args.delay,
            municipality_limit=args.municipality_limit,
            municipality_start_index=args.municipality_start_index,
            municipality_count=args.municipality_count,
        )
        add_public_catalog_evidence(rows, entries)
        entries = save_evidence(entries)
        print(f"Official phase complete: {len(rows)} candidates, {len(entries)} evidence rows")

    if args.phase in {"web", "all"}:
        entries = add_web_evidence(
            rows,
            entries,
            start_index=args.start_index,
            limit=args.limit,
            delay=args.delay,
            max_results=args.max_results,
            only_without_independent=not args.all_web,
        )
        entries = save_evidence(entries)
        print(f"Web phase complete: {len(entries)} evidence rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
