#!/usr/bin/env python3
"""Extract auditable forest-road records from Nagano prefectural plans."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pdfplumber


OUTPUT = Path("data/processed/nagano_plan_history.csv")
PLAN_SOURCES = [
    (
        Path("tmp/pdfs/nagano_h22_h26.pdf"),
        "H22-H26",
        "https://www.pref.nagano.lg.jp/ringyo/documents/kyukeikaku.pdf",
    ),
    (
        Path("tmp/pdfs/nagano_h27_h31.pdf"),
        "H27-H31",
        "https://www.pref.nagano.lg.jp/ringyo/documents/keikaku01.pdf",
    ),
    (
        Path("tmp/pdfs/nagano_h27_h31_change2.pdf"),
        "H27-H31第2回変更",
        "https://www.pref.nagano.lg.jp/ringyo/documents/henkou2.pdf",
    ),
    (
        Path("tmp/pdfs/nagano_r2_r6.pdf"),
        "R2-R6",
        "https://www.pref.nagano.lg.jp/ringyo/documents/nousangyosonchikiseibikeikakur2~r6.pdf",
    ),
    (
        Path("tmp/pdfs/nagano_r2_r6_change2.pdf"),
        "R2-R6第2回変更",
        "https://www.pref.nagano.lg.jp/ringyo/documents/2022_01keikaku.pdf",
    ),
    (
        Path("tmp/pdfs/nagano_r7_r11.pdf"),
        "R7-R11",
        "https://www.pref.nagano.lg.jp/ringyo/documents/sinkeikaku2025.pdf",
    ),
]


def clean(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def extract_road_name(value: str | None) -> tuple[str, bool]:
    text = clean(value)
    match = re.search(r"[（(]林道(.+?)[）)]", text)
    if match:
        name = match.group(1)
    elif text.startswith("林道"):
        name = text.removeprefix("林道")
    else:
        return "", False
    if "事業" in name or name.startswith("点検診断"):
        return "", False
    has_others = name.endswith("ほか")
    if has_others:
        name = name[: -len("ほか")]
    return name, has_others


def extract_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for pdf_path, period, url in PLAN_SOURCES:
        if not pdf_path.exists():
            raise FileNotFoundError(f"Missing source PDF: {pdf_path}")
        with pdfplumber.open(pdf_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables():
                    for row in table:
                        if len(row) < 7:
                            continue
                        road_index = next(
                            (index for index, cell in enumerate(row) if extract_road_name(cell)[0]),
                            None,
                        )
                        if road_index is None or road_index + 5 >= len(row):
                            continue
                        road_name, has_others = extract_road_name(row[road_index])
                        municipality = clean(row[road_index + 2])
                        if not road_name or not municipality or municipality == "関係市町村":
                            continue
                        record = {
                            "林道名": road_name,
                            "関係市町村": municipality,
                            "計画期間": period,
                            "事業型": clean(row[road_index - 1] if road_index > 0 else ""),
                            "事業内容": clean(row[road_index + 3]),
                            "工期": clean(row[road_index + 4]),
                            "総事業費千円": clean(row[road_index + 5]).replace(",", ""),
                            "ほか表記": "あり" if has_others else "なし",
                            "資料ページ": str(page_number),
                            "行政出典URL": url,
                            "確認日": "2026-07-10",
                        }
                        key = tuple(record.values())
                        if key not in seen:
                            seen.add(key)
                            records.append(record)
    return records


def main() -> int:
    records = extract_records()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "林道名",
        "関係市町村",
        "計画期間",
        "事業型",
        "事業内容",
        "工期",
        "総事業費千円",
        "ほか表記",
        "資料ページ",
        "行政出典URL",
        "確認日",
    ]
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"Extracted {len(records)} plan records to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
