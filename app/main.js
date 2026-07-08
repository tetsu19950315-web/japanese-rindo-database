const SOURCE_META = {
  "official-map": { label: "公式図", color: "#9a4d2f" },
  "osm-road": { label: "OSM道路", color: "#356f58" },
  "osm-area": { label: "OSM地名", color: "#7a6d2f" },
};

const CONFIDENCE_LABEL = {
  high: "高",
  medium: "中",
  "medium-low": "中-低",
  low: "低",
};

const VIEW_LABEL = {
  all: "全部",
  selected: "本命",
  trip: "本命+予備",
};

const APP_CONFIG = window.RINDO_APP_CONFIG || {};
const DATA_BASE_PATH = APP_CONFIG.dataBasePath || "../data/processed";

const state = {
  allRoads: [],
  candidateCount: 0,
  map: null,
  markers: new Map(),
  selectedId: null,
  view: "trip",
};

const ui = {
  summaryText: document.getElementById("summaryText"),
  detailEmpty: document.getElementById("detailEmpty"),
  detailCard: document.getElementById("detailCard"),
  roadId: document.getElementById("roadId"),
  roadName: document.getElementById("roadName"),
  sourceBadge: document.getElementById("sourceBadge"),
  rideBadge: document.getElementById("rideBadge"),
  roadSummary: document.getElementById("roadSummary"),
  roadMunicipality: document.getElementById("roadMunicipality"),
  roadSurface: document.getElementById("roadSurface"),
  roadAccess: document.getElementById("roadAccess"),
  roadChecked: document.getElementById("roadChecked"),
  roadConfidence: document.getElementById("roadConfidence"),
  roadEntry: document.getElementById("roadEntry"),
  roadExit: document.getElementById("roadExit"),
  roadRideNote: document.getElementById("roadRideNote"),
  positionSource: document.getElementById("positionSource"),
  candidateSource: document.getElementById("candidateSource"),
  cautions: document.getElementById("cautions"),
  navButton: document.getElementById("navButton"),
  shareButton: document.getElementById("shareButton"),
  filterButtons: Array.from(document.querySelectorAll(".filter-chip")),
};

function parseInitialState() {
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view");
  const requestedRoad = params.get("road");

  return {
    view: ["all", "selected", "trip"].includes(requestedView) ? requestedView : "trip",
    roadId: requestedRoad,
  };
}

function buildGoogleMapsUrl(road) {
  const destination = `${road.entryLat},${road.entryLon}`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}&travelmode=driving`;
}

function getTierMeta(road) {
  if (road.rideTier === "selected") {
    return {
      tier: "selected",
      label: road.rideOrder ? `本命 ${road.rideOrder}` : "本命",
      stroke: "#8f5320",
      fillOpacity: 0.98,
      weight: 3,
    };
  }

  if (road.rideTier === "reserve") {
    return {
      tier: "reserve",
      label: "予備",
      stroke: "#2d5b75",
      fillOpacity: 0.94,
      weight: 3,
    };
  }

  return {
    tier: "other",
    label: "候補",
    stroke: "rgba(31, 42, 34, 0.24)",
    fillOpacity: 0.9,
    weight: 2,
  };
}

function markerStyle(road, isSelected) {
  const sourceMeta = SOURCE_META[road.sourceType] || SOURCE_META["official-map"];
  const tierMeta = getTierMeta(road);
  return {
    radius: isSelected ? 11 : road.rideTier === "selected" ? 10 : road.rideTier === "reserve" ? 9 : 8,
    weight: isSelected ? tierMeta.weight + 1 : tierMeta.weight,
    color: tierMeta.stroke,
    fillColor: sourceMeta.color,
    fillOpacity: isSelected ? 1 : tierMeta.fillOpacity,
  };
}

function isVisibleInCurrentView(road) {
  if (state.view === "all") return true;
  if (state.view === "selected") return road.rideTier === "selected";
  return road.rideTier === "selected" || road.rideTier === "reserve";
}

function getVisibleRoads() {
  return state.allRoads.filter(isVisibleInCurrentView);
}

function updateSummary() {
  const visibleCount = getVisibleRoads().length;
  ui.summaryText.textContent = `${VIEW_LABEL[state.view]} ${visibleCount}件表示 / 候補${state.candidateCount}件`;
}

function updateUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("view", state.view);

  if (state.selectedId) {
    url.searchParams.set("road", state.selectedId);
  } else {
    url.searchParams.delete("road");
  }

  window.history.replaceState({}, "", url);
}

function setBadge(road) {
  const meta = SOURCE_META[road.sourceType] || SOURCE_META["official-map"];
  ui.sourceBadge.textContent = meta.label;
  ui.sourceBadge.style.color = meta.color;

  const tierMeta = getTierMeta(road);
  ui.rideBadge.textContent = tierMeta.label;
  ui.rideBadge.dataset.tier = tierMeta.tier;
}

function updateSelectionStyles() {
  state.markers.forEach((marker, roadId) => {
    const road = state.allRoads.find((item) => item.id === roadId);
    if (!road) return;
    marker.setStyle(markerStyle(road, roadId === state.selectedId));
  });
}

function renderMarkers() {
  const bounds = [];

  state.allRoads.forEach((road) => {
    const marker = state.markers.get(road.id);
    if (!marker) return;

    if (isVisibleInCurrentView(road)) {
      if (!state.map.hasLayer(marker)) {
        marker.addTo(state.map);
      }
      bounds.push([road.displayLat, road.displayLon]);
    } else if (state.map.hasLayer(marker)) {
      marker.removeFrom(state.map);
    }
  });

  updateSelectionStyles();
  updateSummary();

  if (bounds.length > 0) {
    state.map.fitBounds(bounds, { padding: [48, 48] });
  }
}

function ensureVisibleSelection() {
  if (!state.selectedId) return;

  const selectedRoad = state.allRoads.find((item) => item.id === state.selectedId);
  if (selectedRoad && !isVisibleInCurrentView(selectedRoad)) {
    const fallback = getVisibleRoads()[0];
    state.selectedId = fallback ? fallback.id : null;
  }
}

function selectRoad(id, options = {}) {
  const road = state.allRoads.find((item) => item.id === id);
  if (!road) return;

  if (!isVisibleInCurrentView(road)) {
    state.view = "all";
    syncFilterButtons();
    renderMarkers();
  }

  state.selectedId = road.id;
  ui.detailEmpty.classList.add("hidden");
  ui.detailCard.classList.remove("hidden");

  ui.roadId.textContent = road.id;
  ui.roadName.textContent = road.name;
  ui.roadSummary.textContent = road.summary;
  ui.roadMunicipality.textContent = road.municipality;
  ui.roadSurface.textContent = road.surfaceSummary;
  ui.roadAccess.textContent = road.accessStatus;
  ui.roadChecked.textContent = road.lastChecked;
  ui.roadConfidence.textContent = CONFIDENCE_LABEL[road.confidence] || road.confidence || "未設定";
  ui.roadEntry.textContent = road.entryText || "未作成";
  ui.roadExit.textContent = road.exitText || "未作成";
  ui.roadRideNote.textContent = road.rideNote || "カルテ化済み候補";
  ui.positionSource.textContent = road.positionSource;
  ui.candidateSource.textContent = road.candidateSource;
  ui.navButton.href = buildGoogleMapsUrl(road);
  setBadge(road);

  ui.cautions.innerHTML = "";
  (road.cautions || []).forEach((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    ui.cautions.appendChild(item);
  });

  updateSelectionStyles();
  updateUrl();

  if (!options.skipFly) {
    state.map.flyTo([road.displayLat, road.displayLon], Math.max(state.map.getZoom(), 12), {
      animate: true,
      duration: 0.5,
    });
  }
}

function syncFilterButtons() {
  ui.filterButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === state.view);
  });
}

function setView(view) {
  state.view = view;
  syncFilterButtons();
  ensureVisibleSelection();
  renderMarkers();

  if (state.selectedId) {
    selectRoad(state.selectedId, { skipFly: true });
  } else {
    const fallback = getVisibleRoads()[0];
    if (fallback) {
      selectRoad(fallback.id, { skipFly: true });
    }
  }

  updateUrl();
}

async function shareCurrentRoad() {
  const road = state.allRoads.find((item) => item.id === state.selectedId);
  if (!road) return;

  const shareUrl = new URL(window.location.href);
  shareUrl.searchParams.set("view", state.view);
  shareUrl.searchParams.set("road", road.id);

  const payload = {
    title: `日本林道データベース: ${road.name}`,
    text: `${road.name} (${road.id})`,
    url: shareUrl.toString(),
  };

  if (navigator.share) {
    try {
      await navigator.share(payload);
      return;
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
  }

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(payload.url);
  } else {
    window.prompt("共有URL", payload.url);
    return;
  }
  ui.shareButton.textContent = "共有URLをコピー済み";
  window.setTimeout(() => {
    ui.shareButton.textContent = "この候補を共有";
  }, 1600);
}

function createMap() {
  state.map = L.map("map", {
    zoomControl: false,
    attributionControl: true,
  }).setView([35.99, 138.12], 11);

  L.control.zoom({ position: "bottomright" }).addTo(state.map);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(state.map);
}

function addMarkers() {
  state.allRoads.forEach((road) => {
    const marker = L.circleMarker([road.displayLat, road.displayLon], markerStyle(road, false));
    const tierLabel = getTierMeta(road).label;
    marker.bindPopup(`<div class="marker-popup"><strong>${road.name}</strong><br>${road.id} / ${tierLabel}</div>`);
    marker.on("click", () => selectRoad(road.id));
    state.markers.set(road.id, marker);
  });

  renderMarkers();
}

function enrichRoads(roads, karteRows, shortlist) {
  const karteById = new Map(karteRows.map((item) => [item.id, item]));
  const selectedById = new Map(shortlist.selected.map((item) => [item.id, item]));
  const reserveById = new Map(shortlist.reserve.map((item) => [item.id, item]));

  return roads.map((road) => {
    const karte = karteById.get(road.id);
    const selected = selectedById.get(road.id);
    const reserve = reserveById.get(road.id);

    return {
      ...road,
      summary: karte ? karte.summary : road.summary,
      surfaceSummary: karte ? karte.surface_summary : road.surfaceSummary,
      accessStatus: karte ? karte.access_status : road.accessStatus,
      cautions: karte ? karte.cautions : road.cautions,
      lastChecked: karte ? karte.last_checked : road.lastChecked,
      confidence: karte ? karte.confidence : road.confidence,
      entryText: karte ? karte.entry : road.entryText,
      exitText: karte ? karte.exit_or_terminus : road.exitText,
      karteSources: karte ? karte.sources : [],
      rideTier: selected ? "selected" : reserve ? "reserve" : "other",
      rideOrder: selected ? selected.order : null,
      rideNote: selected ? selected.selectionReason : reserve ? reserve.selectionReason : null,
    };
  });
}

function buildDataUrl(fileName) {
  return new URL(`${DATA_BASE_PATH}/${fileName}`, window.location.href).toString();
}

async function loadRoads() {
  const [roadsResponse, candidatesResponse, karteResponse, shortlistResponse] = await Promise.all([
    fetch(buildDataUrl("mvp_map_data.json")),
    fetch(buildDataUrl("suwa_chino_candidates.csv")),
    fetch(buildDataUrl("karte.json")),
    fetch(buildDataUrl("ride_shortlist_2026-07-08.json")),
  ]);

  const roads = await roadsResponse.json();
  const candidateCsv = await candidatesResponse.text();
  const karteRows = await karteResponse.json();
  const shortlist = await shortlistResponse.json();
  const candidateRows = candidateCsv.trim().split("\n").slice(1);

  state.candidateCount = candidateRows.length;
  state.allRoads = enrichRoads(roads, karteRows, shortlist);
}

function bindUi() {
  ui.filterButtons.forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });

  ui.shareButton.addEventListener("click", () => {
    shareCurrentRoad().catch((error) => {
      console.error(error);
      ui.shareButton.textContent = "共有に失敗";
      window.setTimeout(() => {
        ui.shareButton.textContent = "この候補を共有";
      }, 1600);
    });
  });
}

async function bootstrap() {
  const initialState = parseInitialState();

  createMap();
  bindUi();
  await loadRoads();
  addMarkers();

  state.view = initialState.view;
  syncFilterButtons();
  ensureVisibleSelection();
  renderMarkers();

  const preferredRoad =
    state.allRoads.find((item) => item.id === initialState.roadId && isVisibleInCurrentView(item)) ||
    state.allRoads.find((item) => item.id === initialState.roadId) ||
    getVisibleRoads()[0];

  if (preferredRoad) {
    selectRoad(preferredRoad.id, { skipFly: true });
  }
}

bootstrap().catch((error) => {
  console.error(error);
  ui.summaryText.textContent = "データの読み込みに失敗しました";
});
