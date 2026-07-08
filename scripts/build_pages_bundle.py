from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "tmp" / "pages-dist"

FILES_TO_COPY = [
    (ROOT / "index.html", OUTPUT_DIR / "index.html"),
    (ROOT / "app" / "main.js", OUTPUT_DIR / "app" / "main.js"),
    (ROOT / "app" / "styles.css", OUTPUT_DIR / "app" / "styles.css"),
    (ROOT / "data" / "processed" / "mvp_map_data.json", OUTPUT_DIR / "data" / "processed" / "mvp_map_data.json"),
    (ROOT / "data" / "processed" / "karte.json", OUTPUT_DIR / "data" / "processed" / "karte.json"),
    (
        ROOT / "data" / "processed" / "ride_shortlist_2026-07-08.json",
        OUTPUT_DIR / "data" / "processed" / "ride_shortlist_2026-07-08.json",
    ),
    (
        ROOT / "data" / "processed" / "suwa_chino_candidates.csv",
        OUTPUT_DIR / "data" / "processed" / "suwa_chino_candidates.csv",
    ),
]


def build_bundle() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    for source, target in FILES_TO_COPY:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":
    build_bundle()
