from __future__ import annotations

import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "tmp" / "pages-dist"


class IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"] or "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app_html = (BUILD / "app" / "index.html").read_text(encoding="utf-8")
    app_js = (BUILD / "app" / "main.js").read_text(encoding="utf-8")
    service_worker = (BUILD / "sw.js").read_text(encoding="utf-8")

    parser = IdParser()
    parser.feed(app_html)
    id_counts = Counter(parser.ids)
    duplicates = sorted(item for item, count in id_counts.items() if count > 1)
    require(not duplicates, f"Duplicate HTML ids: {duplicates}")

    referenced_ids = set(re.findall(r'getElementById\("([^"]+)"\)', app_js))
    missing_ids = sorted(referenced_ids - set(parser.ids))
    require(not missing_ids, f"JavaScript references missing HTML ids: {missing_ids}")
    require("./vendor/leaflet/leaflet.js" in app_html, "Leaflet JavaScript must be served locally")
    require("./vendor/leaflet/leaflet.css" in app_html, "Leaflet CSS must be served locally")
    require("unpkg.com/leaflet" not in app_html, "App must not depend on the Leaflet CDN")
    require((BUILD / "app" / "vendor" / "leaflet" / "LICENSE").is_file(), "Leaflet license is missing")
    require("baseMapSelect" in parser.ids, "Base-map selector is missing")
    require("googleMap" in parser.ids, "Google map container is missing")
    require("googleMapsApiKey" in app_html, "Google Maps API key setting is missing")
    require(
        "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png" in app_js,
        "Official GSI standard map tile is missing",
    )
    require(
        "https://maps.googleapis.com/maps/api/js" in app_js,
        "Official Google Maps JavaScript API loader is missing",
    )
    require("google.com/vt" not in app_js, "Unofficial Google raster tiles must not be used")

    manifest = json.loads((BUILD / "manifest.webmanifest").read_text(encoding="utf-8"))
    require(manifest.get("display") == "standalone", "PWA display must be standalone")
    require(manifest.get("start_url", "").startswith("./app/"), "PWA start_url must open the app")
    for icon in manifest.get("icons", []):
        icon_path = BUILD / icon["src"].removeprefix("./")
        require(icon_path.is_file(), f"Manifest icon is missing: {icon_path}")

    shell_paths = re.findall(r'fromRoot\("(\./[^"?]*)"\)', service_worker)
    for shell_path in shell_paths:
        target = BUILD / shell_path.removeprefix("./")
        require(target.exists(), f"Offline shell target is missing: {target}")

    roads = json.loads((BUILD / "data" / "processed" / "nagano_map_data.json").read_text(encoding="utf-8"))
    road_ids = {road["id"] for road in roads}
    routes = json.loads((BUILD / "data" / "processed" / "nagano_routes.geojson").read_text(encoding="utf-8"))
    features = routes.get("features", [])
    require(features, "Route GeoJSON has no features")
    require(all(feature.get("geometry", {}).get("type") == "LineString" for feature in features), "Routes must be LineStrings")
    require(all(feature.get("properties", {}).get("id") in road_ids for feature in features), "Route id is not in MVP data")
    relations = Counter(feature["properties"].get("relation") for feature in features)
    require(relations["name-match"] >= 8, "At least eight statewide name-matched routes are required")

    print(
        f"OK: {len(parser.ids)} UI ids, {len(features)} route lines "
        f"({relations['name-match']} name match), "
        f"{len(manifest.get('icons', []))} PWA icons"
    )


if __name__ == "__main__":
    main()
