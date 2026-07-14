#!/usr/bin/env python3
"""Extract named forest-road rows from Nagano's R7-R11 official plan.

The plan can contain ``ほか`` after a named road. Only the explicitly named
road is retained; unnamed roads covered by ``ほか`` are never inferred.
"""

from __future__ import annotations

import argparse
import csv
import re
import urllib.request
from collections import OrderedDict
from pathlib import Path

import pdfplumber


SOURCE_URL = "https://www.pref.nagano.lg.jp/ringyo/documents/sinkeikaku2025.pdf"
DEFAULT_PDF = Path("tmp/pdfs/nagano_r7_r11.pdf")
DEFAULT_OUTPUT = Path("data/processed/nagano_current_plan.csv")
SOURCE_LABEL = "長野県『農山漁村地域整備計画（R7-R11）』"


def clean(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def normalize_road_name(value: str | None) -> tuple[str, bool]:
    text = clean(value)
    if not text.startswith("林道"):
        return "", False
    text = text.removeprefix("林道")
    has_others = text.endswith("ほか")
    if has_others:
        text = text[: -len("ほか")]
    return text, has_others


def download_if_needed(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "JapaneseRindoDB/0.2"})
    with urllib.request.urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())


def extract_rows(pdf_path: Path) -> list[dict[str, str]]:
    grouped: OrderedDict[tuple[str, str], dict[str, object]] = OrderedDict()
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages[1:], start=2):
            for table in page.extract_tables():
                for row in table[2:]:
                    if len(row) < 10:
                        continue
                    road_name, has_others = normalize_road_name(row[2])
                    municipality = clean(row[4] or row[3])
                    if not road_name or not municipality:
                        continue
                    key = (road_name, municipality)
                    entry = grouped.setdefault(
                        key,
                        {
                            "road_name": road_name,
                            "municipality": municipality,
                            "business_types": [],
                            "contents": [],
                            "terms": [],
                            "costs": [],
                            "pages": [],
                            "has_others": False,
                        },
                    )
                    entry["business_types"].append(clean(row[1]))
                    entry["contents"].append(clean(row[5]))
                    entry["terms"].append(clean(row[6]))
                    entry["costs"].append(clean(row[7]).replace(",", ""))
                    entry["pages"].append(str(page_number))
                    entry["has_others"] = bool(entry["has_others"] or has_others)

    output = []
    for entry in grouped.values():
        output.append(
            {
                "林道名": str(entry["road_name"]),
                "関係市町村": str(entry["municipality"]),
                "事業型": " | ".join(dict.fromkeys(entry["business_types"])),
                "事業内容": " | ".join(dict.fromkeys(entry["contents"])),
                "工期": " | ".join(dict.fromkeys(entry["terms"])),
                "総事業費千円": " | ".join(dict.fromkeys(entry["costs"])),
                "ほか表記": "あり" if entry["has_others"] else "なし",
                "資料ページ": " | ".join(dict.fromkeys(entry["pages"])),
                "行政出典": f"{SOURCE_LABEL} {SOURCE_URL}",
                "確認日": "2026-07-10",
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    download_if_needed(args.pdf)
    rows = extract_rows(args.pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "林道名",
        "関係市町村",
        "事業型",
        "事業内容",
        "工期",
        "総事業費千円",
        "ほか表記",
        "資料ページ",
        "行政出典",
        "確認日",
    ]
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Extracted {len(rows)} unique named roads to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
