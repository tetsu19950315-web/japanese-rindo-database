#!/usr/bin/env python3
"""Validate Nagano level classification outputs."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MASTER = PROCESSED / "nagano_level_master.csv"
EVIDENCE = PROCESSED / "nagano_level_evidence.csv"
REPORT = PROCESSED / "nagano_level_report.json"
ALLOWED_LEVELS = {"Lv0", "Lv1", "Lv2"}


def lv0_path() -> Path:
    return next(RAW_DIR.glob("NGN_Lv0_Master_*.csv"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    errors: list[str] = []
    raw_rows = read_csv(lv0_path())
    master_rows = read_csv(MASTER)
    evidence_rows = read_csv(EVIDENCE)
    report = json.loads(REPORT.read_text(encoding="utf-8"))

    if len(raw_rows) != 1063:
        errors.append(f"raw row count is {len(raw_rows)}, expected 1063")
    if len(master_rows) != 1063:
        errors.append(f"master row count is {len(master_rows)}, expected 1063")

    raw_ids = [row["ID"] for row in raw_rows]
    master_ids = [row["ID"] for row in master_rows]
    if raw_ids != master_ids:
        errors.append("raw/master ID order differs")
    expected_ids = [f"NGN-{number:06d}" for number in range(1, 1064)]
    if raw_ids != expected_ids:
        errors.append("IDs are not contiguous NGN-000001..NGN-001063")

    evidence_ids = {row["ID"] for row in evidence_rows}
    levels: Counter[str] = Counter()
    for row in master_rows:
        level = row.get("Lv", "")
        levels[level] += 1
        if level not in ALLOWED_LEVELS:
            errors.append(f"{row['ID']}: invalid level {level!r}")
        if not row.get("照合日"):
            errors.append(f"{row['ID']}: missing 照合日")
        if not row.get("判定理由"):
            errors.append(f"{row['ID']}: missing 判定理由")
        if level in {"Lv1", "Lv2"}:
            if row["ID"] not in evidence_ids:
                errors.append(f"{row['ID']}: promoted without evidence row")
            if not row.get("根拠URL"):
                errors.append(f"{row['ID']}: promoted without 根拠URL")
            if int(row.get("資料照合件数") or 0) < 1:
                errors.append(f"{row['ID']}: promoted with zero independent evidence")
        if level == "Lv2":
            if not row.get("OSM_ID"):
                errors.append(f"{row['ID']}: Lv2 without OSM_ID")
            if not row.get("代表緯度") or not row.get("代表経度"):
                errors.append(f"{row['ID']}: Lv2 without representative coordinates")
            detail_count = len([value for value in row.get("詳細属性", "").split(" | ") if value])
            if detail_count < 2:
                errors.append(f"{row['ID']}: Lv2 has fewer than two detail attributes")
            official_count = int(row.get("行政資料件数") or 0)
            domain_count = int(row.get("独立ドメイン数") or 0)
            if official_count < 1 and domain_count < 2:
                errors.append(f"{row['ID']}: Lv2 lacks official or two-domain support")

    for row in evidence_rows:
        if row["ID"] not in set(raw_ids):
            errors.append(f"evidence references unknown ID {row['ID']}")
        if not re.match(r"https?://", row.get("URL", "")):
            errors.append(f"{row['ID']}: invalid evidence URL {row.get('URL')!r}")

    report_counts = report.get("levelCounts", {})
    if any(int(report_counts.get(level, 0)) != levels[level] for level in ALLOWED_LEVELS):
        errors.append(f"report level counts differ: report={report_counts}, actual={dict(levels)}")
    if report.get("totalCandidates") != 1063 or report.get("auditedCandidates") != 1063:
        errors.append("report does not mark all 1063 candidates audited")

    if errors:
        for error in errors[:100]:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) > 100:
            print(f"ERROR: plus {len(errors) - 100} more errors", file=sys.stderr)
        return 1
    print(
        "OK: Nagano levels "
        + ", ".join(f"{level}={levels[level]}" for level in ["Lv0", "Lv1", "Lv2"])
        + f"; evidence={len(evidence_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
