from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "tmp" / "pages-dist"

FILES_TO_COPY = [
    (ROOT / "index.html", OUTPUT_DIR / "index.html"),
    (ROOT / "app" / "index.html", OUTPUT_DIR / "app" / "index.html"),
    (ROOT / "app" / "main.js", OUTPUT_DIR / "app" / "main.js"),
    (ROOT / "app" / "styles.css", OUTPUT_DIR / "app" / "styles.css"),
    (ROOT / "app" / "vendor" / "leaflet" / "leaflet.js", OUTPUT_DIR / "app" / "vendor" / "leaflet" / "leaflet.js"),
    (ROOT / "app" / "vendor" / "leaflet" / "leaflet.css", OUTPUT_DIR / "app" / "vendor" / "leaflet" / "leaflet.css"),
    (ROOT / "app" / "vendor" / "leaflet" / "LICENSE", OUTPUT_DIR / "app" / "vendor" / "leaflet" / "LICENSE"),
    (
        ROOT / "app" / "vendor" / "maplibre" / "maplibre-gl.js",
        OUTPUT_DIR / "app" / "vendor" / "maplibre" / "maplibre-gl.js",
    ),
    (
        ROOT / "app" / "vendor" / "maplibre" / "maplibre-gl.css",
        OUTPUT_DIR / "app" / "vendor" / "maplibre" / "maplibre-gl.css",
    ),
    (
        ROOT / "app" / "vendor" / "maplibre" / "leaflet-maplibre-gl.js",
        OUTPUT_DIR / "app" / "vendor" / "maplibre" / "leaflet-maplibre-gl.js",
    ),
    (
        ROOT / "app" / "vendor" / "maplibre" / "LICENSE-maplibre-gl.txt",
        OUTPUT_DIR / "app" / "vendor" / "maplibre" / "LICENSE-maplibre-gl.txt",
    ),
    (
        ROOT / "app" / "vendor" / "maplibre" / "LICENSE-leaflet-plugin.txt",
        OUTPUT_DIR / "app" / "vendor" / "maplibre" / "LICENSE-leaflet-plugin.txt",
    ),
    (ROOT / "manifest.webmanifest", OUTPUT_DIR / "manifest.webmanifest"),
    (ROOT / "sw.js", OUTPUT_DIR / "sw.js"),
    (ROOT / "icons" / "rindo-192.png", OUTPUT_DIR / "icons" / "rindo-192.png"),
    (ROOT / "icons" / "rindo-512.png", OUTPUT_DIR / "icons" / "rindo-512.png"),
    (ROOT / "data" / "processed" / "nagano_map_data.json", OUTPUT_DIR / "data" / "processed" / "nagano_map_data.json"),
    (ROOT / "data" / "processed" / "karte.json", OUTPUT_DIR / "data" / "processed" / "karte.json"),
    (ROOT / "data" / "processed" / "nagano_routes.geojson", OUTPUT_DIR / "data" / "processed" / "nagano_routes.geojson"),
    (
        ROOT / "data" / "processed" / "nagano_shortlist.json",
        OUTPUT_DIR / "data" / "processed" / "nagano_shortlist.json",
    ),
    (
        ROOT / "data" / "processed" / "nagano_candidate_master.csv",
        OUTPUT_DIR / "data" / "processed" / "nagano_candidate_master.csv",
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
