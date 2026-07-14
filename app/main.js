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
const RECORD_DB_NAME = "japanese-rindo-field-records";
const RECORD_STORE_NAME = "roadRecords";
const BASE_MAP_STORAGE_KEY = "japanese-rindo-base-map";
const MAX_PHOTOS = 3;

const state = {
  allRoads: [],
  candidateCount: 0,
  map: null,
  baseMap: "osm",
  tileLayers: {},
  markers: new Map(),
  routeLayers: new Map(),
  routeFeatures: [],
  selectedId: null,
  sheetState: "collapsed",
  view: "trip",
  region: "all",
  userLocation: null,
  userMarker: null,
  accuracyCircle: null,
  googleMap: null,
  googleMarkers: new Map(),
  googleRouteLayers: new Map(),
  googleUserMarker: null,
  googleAccuracyCircle: null,
  googleApiPromise: null,
  records: new Map(),
  recordStorageReady: false,
  recordDraftLocation: null,
  recordDraftPhotos: [],
  deferredInstallPrompt: null,
};

const ui = {
  summaryText: document.getElementById("summaryText"),
  detailSheet: document.getElementById("detailSheet"),
  detailEmpty: document.getElementById("detailEmpty"),
  detailCard: document.getElementById("detailCard"),
  sheetToggle: document.getElementById("sheetToggle"),
  sheetToggleTitle: document.getElementById("sheetToggleTitle"),
  sheetToggleHint: document.getElementById("sheetToggleHint"),
  roadId: document.getElementById("roadId"),
  roadName: document.getElementById("roadName"),
  sourceBadge: document.getElementById("sourceBadge"),
  rideBadge: document.getElementById("rideBadge"),
  recordBadge: document.getElementById("recordBadge"),
  roadSummary: document.getElementById("roadSummary"),
  roadMunicipality: document.getElementById("roadMunicipality"),
  roadSurface: document.getElementById("roadSurface"),
  roadAccess: document.getElementById("roadAccess"),
  roadChecked: document.getElementById("roadChecked"),
  roadConfidence: document.getElementById("roadConfidence"),
  roadRouteStatus: document.getElementById("roadRouteStatus"),
  roadEntry: document.getElementById("roadEntry"),
  entryCoordinates: document.getElementById("entryCoordinates"),
  roadExit: document.getElementById("roadExit"),
  roadRideNote: document.getElementById("roadRideNote"),
  positionSource: document.getElementById("positionSource"),
  candidateSource: document.getElementById("candidateSource"),
  sourceLinksBlock: document.getElementById("sourceLinksBlock"),
  sourceLinks: document.getElementById("sourceLinks"),
  cautions: document.getElementById("cautions"),
  navButton: document.getElementById("navButton"),
  shareButton: document.getElementById("shareButton"),
  openRecordButton: document.getElementById("openRecordButton"),
  copyCoordinatesButton: document.getElementById("copyCoordinatesButton"),
  distanceBanner: document.getElementById("distanceBanner"),
  entryDistance: document.getElementById("entryDistance"),
  locationButton: document.getElementById("locationButton"),
  installButton: document.getElementById("installButton"),
  exportButton: document.getElementById("exportButton"),
  connectionBadge: document.getElementById("connectionBadge"),
  regionFilter: document.getElementById("regionFilter"),
  baseMapSelect: document.getElementById("baseMapSelect"),
  mapProviderMessage: document.getElementById("mapProviderMessage"),
  leafletMap: document.getElementById("map"),
  googleMap: document.getElementById("googleMap"),
  fieldRecord: document.getElementById("fieldRecord"),
  recordForm: document.getElementById("recordForm"),
  recordSummaryStatus: document.getElementById("recordSummaryStatus"),
  recordObservedAt: document.getElementById("recordObservedAt"),
  recordAccess: document.getElementById("recordAccess"),
  recordSurface: document.getElementById("recordSurface"),
  recordGate: document.getElementById("recordGate"),
  recordLocationText: document.getElementById("recordLocationText"),
  recordLocationButton: document.getElementById("recordLocationButton"),
  recordNote: document.getElementById("recordNote"),
  recordPhotos: document.getElementById("recordPhotos"),
  photoPreview: document.getElementById("photoPreview"),
  recordMessage: document.getElementById("recordMessage"),
  deleteRecordButton: document.getElementById("deleteRecordButton"),
  filterButtons: Array.from(document.querySelectorAll(".filter-chip")),
};

function parseInitialState() {
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view");
  let savedBaseMap = "osm";
  try {
    savedBaseMap = window.localStorage.getItem(BASE_MAP_STORAGE_KEY) || "osm";
  } catch (error) {
    console.warn("背景地図の設定を読み込めませんでした", error);
  }
  const requestedBaseMap = params.get("map") || savedBaseMap;
  return {
    view: ["all", "selected", "trip"].includes(requestedView) ? requestedView : "trip",
    region: ["all", "東信", "南信", "中信", "北信"].includes(params.get("region")) ? params.get("region") : "all",
    baseMap: ["osm", "gsi", "google"].includes(requestedBaseMap) ? requestedBaseMap : "osm",
    roadId: params.get("road"),
  };
}

function isDesktopLayout() {
  return window.matchMedia("(min-width: 900px)").matches;
}

function getSelectedRoad() {
  return state.allRoads.find((item) => item.id === state.selectedId) || null;
}

function toLocalInputValue(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function formatDistance(meters) {
  if (!Number.isFinite(meters)) return "—";
  if (meters < 1000) return `${Math.max(1, Math.round(meters / 10) * 10)} m`;
  return `${(meters / 1000).toFixed(meters < 10_000 ? 1 : 0)} km`;
}

function distanceMeters(lat1, lon1, lat2, lon2) {
  const radius = 6_371_000;
  const toRadians = (degrees) => (degrees * Math.PI) / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
  return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function selectedRoadDistance() {
  const road = getSelectedRoad();
  if (!road || !state.userLocation || !Number.isFinite(road.entryLat) || !Number.isFinite(road.entryLon)) {
    return null;
  }
  return distanceMeters(
    state.userLocation.latitude,
    state.userLocation.longitude,
    road.entryLat,
    road.entryLon,
  );
}

function updateSheetToggle() {
  const selectedRoad = getSelectedRoad();
  const hasSelection = Boolean(selectedRoad);
  const isExpanded = state.sheetState === "expanded";
  const distance = selectedRoadDistance();

  ui.sheetToggleTitle.textContent = hasSelection ? selectedRoad.name : "候補をタップ";
  ui.sheetToggleHint.textContent = hasSelection
    ? distance !== null
      ? `入口まで ${formatDistance(distance)}`
      : isExpanded
        ? "地図を広く見る"
        : "カルテを開く"
    : "地図を見ながら候補を探す";
  ui.sheetToggle.setAttribute("aria-expanded", String(isExpanded));
}

function setSheetState(nextState) {
  state.sheetState = isDesktopLayout() ? "expanded" : nextState;
  ui.detailSheet.dataset.sheetState = state.sheetState;
  updateSheetToggle();
  if (state.map) {
    window.setTimeout(() => state.map.invalidateSize(), 180);
  }
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
    stroke: "#59685c",
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

function routeStyle(road, feature, isSelected) {
  const tierMeta = getTierMeta(road);
  const exact = feature.properties.relation === "name-match";
  return {
    color: tierMeta.stroke,
    weight: isSelected ? 6 : exact ? 4 : 3,
    opacity: isSelected ? 0.96 : exact ? 0.84 : 0.58,
    dashArray: exact ? null : "7 7",
    lineCap: "round",
    lineJoin: "round",
  };
}

function isVisibleInCurrentView(road) {
  const regionMatches = state.region === "all" || road.region === state.region;
  if (!regionMatches) return false;
  if (state.view === "all") return true;
  if (state.view === "selected") return road.rideTier === "selected";
  return road.rideTier === "selected" || road.rideTier === "reserve";
}

function getVisibleRoads() {
  return state.allRoads.filter(isVisibleInCurrentView);
}

function updateSummary() {
  const visibleCount = getVisibleRoads().length;
  const recordCount = state.records.size;
  ui.summaryText.textContent = `${VIEW_LABEL[state.view]} ${visibleCount}件 / 候補${state.candidateCount}件${recordCount ? ` / 現地記録${recordCount}件` : ""}`;
}

function updateUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("view", state.view);
  if (state.region === "all") url.searchParams.delete("region");
  else url.searchParams.set("region", state.region);
  if (state.baseMap === "osm") url.searchParams.delete("map");
  else url.searchParams.set("map", state.baseMap);
  if (state.selectedId) url.searchParams.set("road", state.selectedId);
  else url.searchParams.delete("road");
  window.history.replaceState({}, "", url);
}

function setBadge(road) {
  const meta = SOURCE_META[road.sourceType] || SOURCE_META["official-map"];
  ui.sourceBadge.textContent = meta.label;
  ui.sourceBadge.style.color = meta.color;

  const tierMeta = getTierMeta(road);
  ui.rideBadge.textContent = tierMeta.label;
  ui.rideBadge.dataset.tier = tierMeta.tier;

  const hasRecord = state.records.has(road.id);
  ui.recordBadge.hidden = !hasRecord;
}

function updateSelectionStyles() {
  state.markers.forEach((marker, roadId) => {
    const road = state.allRoads.find((item) => item.id === roadId);
    if (road) marker.setStyle(markerStyle(road, roadId === state.selectedId));
  });

  state.routeLayers.forEach((layers, roadId) => {
    const road = state.allRoads.find((item) => item.id === roadId);
    if (!road) return;
    layers.forEach(({ layer, feature }) => {
      layer.setStyle(routeStyle(road, feature, roadId === state.selectedId));
      if (roadId === state.selectedId && state.map.hasLayer(layer)) layer.bringToFront();
    });
  });
  updateGoogleSelectionStyles();
}

function renderMapLayers({ fit = true } = {}) {
  const bounds = [];

  state.allRoads.forEach((road) => {
    const marker = state.markers.get(road.id);
    if (!marker) return;
    const visible = isVisibleInCurrentView(road);

    if (visible) {
      if (!state.map.hasLayer(marker)) marker.addTo(state.map);
      bounds.push([road.displayLat, road.displayLon]);
    } else if (state.map.hasLayer(marker)) {
      marker.removeFrom(state.map);
    }

    (state.routeLayers.get(road.id) || []).forEach(({ layer }) => {
      if (visible) {
        if (!state.map.hasLayer(layer)) layer.addTo(state.map);
      } else if (state.map.hasLayer(layer)) {
        layer.removeFrom(state.map);
      }
    });
  });

  updateSelectionStyles();
  updateSummary();
  if (state.baseMap === "google") syncGoogleMapLayers({ fit });
  else if (fit && bounds.length > 0) state.map.fitBounds(bounds, { padding: [48, 48] });
}

function ensureVisibleSelection() {
  if (!state.selectedId) return;
  const selectedRoad = state.allRoads.find((item) => item.id === state.selectedId);
  if (selectedRoad && !isVisibleInCurrentView(selectedRoad)) {
    state.selectedId = getVisibleRoads()[0]?.id || null;
  }
}

function updateDistanceDisplay() {
  const distance = selectedRoadDistance();
  ui.distanceBanner.hidden = distance === null;
  ui.entryDistance.textContent = distance === null ? "—" : formatDistance(distance);
  updateSheetToggle();
}

function renderSourceLinks(road) {
  ui.sourceLinks.innerHTML = "";
  (road.karteSources || []).forEach((source) => {
    if (!source.url) return;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = source.title || source.url;
    item.appendChild(link);
    ui.sourceLinks.appendChild(item);
  });
  ui.sourceLinksBlock.hidden = ui.sourceLinks.children.length === 0;
}

function renderCautions(road) {
  ui.cautions.innerHTML = "";
  const cautions = road.cautions?.length ? road.cautions : ["現地で最新状況を確認"];
  cautions.forEach((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    ui.cautions.appendChild(item);
  });
}

function routeStatusLabel(road) {
  if (road.routeRelations.includes("name-match")) return "OSMで路線名一致（実線）";
  if (road.routeRelations.includes("nearby-track")) return "周辺OSM track（破線・参考）";
  return "線形未確認（入口 / 代表点のみ）";
}

function selectRoad(id, options = {}) {
  const road = state.allRoads.find((item) => item.id === id);
  if (!road) return;

  if (!isVisibleInCurrentView(road)) {
    state.view = "all";
    state.region = "all";
    ui.regionFilter.value = "all";
    syncFilterButtons();
    renderMapLayers();
  }

  state.selectedId = road.id;
  setSheetState(options.expandSheet === false ? "collapsed" : "expanded");
  ui.detailEmpty.classList.add("hidden");
  ui.detailCard.classList.remove("hidden");

  ui.roadId.textContent = road.id;
  ui.roadName.textContent = road.name;
  ui.roadSummary.textContent = road.summary;
  ui.roadMunicipality.textContent = road.municipality;
  ui.roadSurface.textContent = road.surfaceSummary;
  ui.roadAccess.textContent = road.accessStatus;
  ui.roadChecked.textContent = road.lastChecked || "未確認";
  ui.roadConfidence.textContent = CONFIDENCE_LABEL[road.confidence] || road.confidence || "未設定";
  ui.roadRouteStatus.textContent = routeStatusLabel(road);
  ui.roadEntry.textContent = road.entryText || "入口情報未作成";
  ui.entryCoordinates.textContent = `${road.entryLat.toFixed(6)}, ${road.entryLon.toFixed(6)}`;
  ui.roadExit.textContent = road.exitText || "未作成";
  ui.roadRideNote.textContent = road.rideNote || "カルテ化済み候補";
  ui.positionSource.textContent = road.positionSource;
  ui.candidateSource.textContent = road.candidateSource;
  ui.navButton.href = buildGoogleMapsUrl(road);

  setBadge(road);
  renderCautions(road);
  renderSourceLinks(road);
  loadRecordForm(road);
  updateDistanceDisplay();
  updateSelectionStyles();
  updateUrl();

  if (!options.skipFly && state.baseMap === "google" && state.googleMap) {
    state.googleMap.setCenter({ lat: road.displayLat, lng: road.displayLon });
    state.googleMap.setZoom(Math.max(state.googleMap.getZoom() || 0, 12));
  } else if (!options.skipFly) {
    state.map.flyTo([road.displayLat, road.displayLon], Math.max(state.map.getZoom(), 12), {
      animate: true,
      duration: 0.5,
    });
  }
}

function syncFilterButtons() {
  ui.filterButtons.forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function setView(view) {
  state.view = view;
  syncFilterButtons();
  ensureVisibleSelection();
  renderMapLayers();

  if (state.selectedId) selectRoad(state.selectedId, { skipFly: true });
  else if (isDesktopLayout()) {
    const fallback = getVisibleRoads()[0];
    if (fallback) selectRoad(fallback.id, { skipFly: true });
  }
  updateUrl();
}

function setRegion(region) {
  state.region = region;
  ensureVisibleSelection();
  renderMapLayers();

  if (state.selectedId) selectRoad(state.selectedId, { skipFly: true });
  else if (isDesktopLayout()) {
    const fallback = getVisibleRoads()[0];
    if (fallback) selectRoad(fallback.id, { skipFly: true });
  }
  updateUrl();
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  } else {
    window.prompt("コピーしてください", text);
  }
}

async function shareCurrentRoad() {
  const road = getSelectedRoad();
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
      if (error?.name === "AbortError") return;
    }
  }

  await copyText(payload.url);
  ui.shareButton.textContent = "共有URLをコピー済み";
  window.setTimeout(() => (ui.shareButton.textContent = "候補を共有"), 1600);
}

function setMapProviderMessage(message = "") {
  ui.mapProviderMessage.textContent = message;
  ui.mapProviderMessage.hidden = !message;
}

function loadGoogleMapsApi() {
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  if (state.googleApiPromise) return state.googleApiPromise;

  const apiKey = String(APP_CONFIG.googleMapsApiKey || "").trim();
  if (!apiKey) {
    return Promise.reject(new Error("GoogleマップのAPIキーが未設定です"));
  }

  state.googleApiPromise = new Promise((resolve, reject) => {
    const callbackName = `initRindoGoogleMap${Date.now()}`;
    const script = document.createElement("script");
    window[callbackName] = () => {
      delete window[callbackName];
      resolve(window.google.maps);
    };
    window.gm_authFailure = () => {
      state.googleApiPromise = null;
      setMapProviderMessage("GoogleマップのAPIキーまたは参照元制限を確認してください");
    };
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&loading=async&callback=${callbackName}`;
    script.async = true;
    script.onerror = () => {
      delete window[callbackName];
      state.googleApiPromise = null;
      reject(new Error("Googleマップを読み込めませんでした"));
    };
    document.head.appendChild(script);
  });
  return state.googleApiPromise;
}

function googleMarkerIcon(road, isSelected = false) {
  const sourceMeta = SOURCE_META[road.sourceType] || SOURCE_META["official-map"];
  const tierMeta = getTierMeta(road);
  return {
    path: window.google.maps.SymbolPath.CIRCLE,
    scale: isSelected ? 10 : road.rideTier === "selected" ? 9 : road.rideTier === "reserve" ? 8 : 7,
    fillColor: sourceMeta.color,
    fillOpacity: 1,
    strokeColor: tierMeta.stroke,
    strokeOpacity: 1,
    strokeWeight: isSelected ? tierMeta.weight + 1 : tierMeta.weight,
  };
}

function addGoogleMapLayers() {
  if (!state.googleMap || state.googleMarkers.size > 0) return;

  state.allRoads.forEach((road) => {
    const marker = new window.google.maps.Marker({
      position: { lat: road.displayLat, lng: road.displayLon },
      title: `${road.name} / ${road.id}`,
      icon: googleMarkerIcon(road),
      optimized: true,
    });
    marker.addListener("click", () => selectRoad(road.id));
    state.googleMarkers.set(road.id, marker);
  });

  state.routeFeatures.forEach((feature) => {
    if (feature.geometry?.type !== "LineString") return;
    const road = state.allRoads.find((item) => item.id === feature.properties?.id);
    if (!road) return;
    const style = routeStyle(road, feature, false);
    const line = new window.google.maps.Polyline({
      path: feature.geometry.coordinates.map(([lng, lat]) => ({ lat, lng })),
      strokeColor: style.color,
      strokeOpacity: style.opacity,
      strokeWeight: style.weight,
      clickable: true,
    });
    line.addListener("click", () => selectRoad(road.id));
    const existing = state.googleRouteLayers.get(road.id) || [];
    existing.push({ layer: line, feature });
    state.googleRouteLayers.set(road.id, existing);
  });
}

function updateGoogleSelectionStyles() {
  if (!state.googleMap) return;
  state.googleMarkers.forEach((marker, roadId) => {
    const road = state.allRoads.find((item) => item.id === roadId);
    if (road) marker.setIcon(googleMarkerIcon(road, roadId === state.selectedId));
  });
  state.googleRouteLayers.forEach((layers, roadId) => {
    const road = state.allRoads.find((item) => item.id === roadId);
    if (!road) return;
    layers.forEach(({ layer, feature }) => {
      const style = routeStyle(road, feature, roadId === state.selectedId);
      layer.setOptions({
        strokeColor: style.color,
        strokeOpacity: style.opacity,
        strokeWeight: style.weight,
        zIndex: roadId === state.selectedId ? 20 : 10,
      });
    });
  });
}

function syncGoogleUserLocation() {
  if (!state.googleMap || !state.userLocation) return;
  const center = { lat: state.userLocation.latitude, lng: state.userLocation.longitude };
  if (!state.googleUserMarker) {
    state.googleUserMarker = new window.google.maps.Marker({
      map: state.googleMap,
      position: center,
      title: "現在地",
      zIndex: 30,
      icon: {
        path: window.google.maps.SymbolPath.CIRCLE,
        scale: 8,
        fillColor: "#176f9e",
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 3,
      },
    });
    state.googleAccuracyCircle = new window.google.maps.Circle({
      map: state.googleMap,
      center,
      radius: state.userLocation.accuracy || 0,
      strokeColor: "#245f86",
      strokeOpacity: 0.8,
      strokeWeight: 1,
      fillColor: "#4c9ac7",
      fillOpacity: 0.12,
      clickable: false,
    });
  } else {
    state.googleUserMarker.setMap(state.googleMap);
    state.googleUserMarker.setPosition(center);
    state.googleAccuracyCircle.setMap(state.googleMap);
    state.googleAccuracyCircle.setCenter(center);
    state.googleAccuracyCircle.setRadius(state.userLocation.accuracy || 0);
  }
}

function syncGoogleMapLayers({ fit = false } = {}) {
  if (!state.googleMap) return;
  const bounds = new window.google.maps.LatLngBounds();
  let visibleCount = 0;
  state.allRoads.forEach((road) => {
    const visible = isVisibleInCurrentView(road);
    state.googleMarkers.get(road.id)?.setMap(visible ? state.googleMap : null);
    if (visible) {
      bounds.extend({ lat: road.displayLat, lng: road.displayLon });
      visibleCount += 1;
    }
    (state.googleRouteLayers.get(road.id) || []).forEach(({ layer }) => layer.setMap(visible ? state.googleMap : null));
  });
  syncGoogleUserLocation();
  updateGoogleSelectionStyles();
  if (fit && visibleCount > 1) state.googleMap.fitBounds(bounds, 52);
  else if (fit && visibleCount === 1) {
    state.googleMap.setCenter(bounds.getCenter());
    state.googleMap.setZoom(13);
  }
}

async function ensureGoogleMap() {
  await loadGoogleMapsApi();
  if (state.googleMap) return;
  const center = state.map.getCenter();
  state.googleMap = new window.google.maps.Map(ui.googleMap, {
    center: { lat: center.lat, lng: center.lng },
    zoom: state.map.getZoom(),
    mapTypeId: "roadmap",
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: false,
    gestureHandling: "greedy",
  });
  addGoogleMapLayers();
}

function saveBaseMapPreference(provider) {
  try {
    window.localStorage.setItem(BASE_MAP_STORAGE_KEY, provider);
  } catch (error) {
    console.warn("背景地図の設定を保存できませんでした", error);
  }
}

async function setBaseMap(provider, { fit = false } = {}) {
  const nextProvider = ["osm", "gsi", "google"].includes(provider) ? provider : "osm";
  const previousProvider = state.baseMap;
  ui.baseMapSelect.disabled = true;

  if (nextProvider === "google") {
    setMapProviderMessage("Googleマップを読み込み中...");
    try {
      await ensureGoogleMap();
    } catch (error) {
      setMapProviderMessage(`${error.message}。アプリ設定にキーを追加すると利用できます`);
      ui.baseMapSelect.value = previousProvider;
      ui.baseMapSelect.disabled = false;
      return false;
    }
    const center = state.map.getCenter();
    state.googleMap.setCenter({ lat: center.lat, lng: center.lng });
    state.googleMap.setZoom(state.map.getZoom());
    state.baseMap = "google";
    ui.leafletMap.hidden = true;
    ui.googleMap.hidden = false;
    setMapProviderMessage("");
    syncGoogleMapLayers({ fit });
  } else {
    if (previousProvider === "google" && state.googleMap) {
      const center = state.googleMap.getCenter();
      state.map.setView([center.lat(), center.lng()], state.googleMap.getZoom(), { animate: false });
    }
    Object.values(state.tileLayers).forEach((layer) => {
      if (state.map.hasLayer(layer)) state.map.removeLayer(layer);
    });
    state.tileLayers[nextProvider].addTo(state.map);
    state.baseMap = nextProvider;
    ui.googleMap.hidden = true;
    ui.leafletMap.hidden = false;
    setMapProviderMessage("");
    window.setTimeout(() => state.map.invalidateSize(), 0);
    if (fit) renderMapLayers({ fit: true });
  }

  ui.baseMapSelect.value = state.baseMap;
  ui.baseMapSelect.disabled = false;
  saveBaseMapPreference(state.baseMap);
  updateUrl();
  return true;
}

function createMap() {
  state.map = L.map("map", {
    zoomControl: false,
    attributionControl: true,
  }).setView([35.99, 138.12], 11);

  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  state.tileLayers = {
    osm: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }),
    gsi: L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png", {
      attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">国土地理院</a>',
      maxNativeZoom: 18,
      maxZoom: 19,
    }),
  };
  state.tileLayers.osm.addTo(state.map);
}

function addMapLayers() {
  state.allRoads.forEach((road) => {
    const marker = L.circleMarker([road.displayLat, road.displayLon], markerStyle(road, false));
    const recordLabel = state.records.has(road.id) ? " / 記録済み" : "";
    marker.bindPopup(
      `<div class="marker-popup"><strong>${road.name}</strong><br>${road.id} / ${getTierMeta(road).label}${recordLabel}</div>`,
    );
    marker.on("click", () => selectRoad(road.id));
    state.markers.set(road.id, marker);
  });

  state.routeFeatures.forEach((feature) => {
    if (feature.geometry?.type !== "LineString") return;
    const road = state.allRoads.find((item) => item.id === feature.properties?.id);
    if (!road) return;
    const latLngs = feature.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    const layer = L.polyline(latLngs, routeStyle(road, feature, false));
    layer.bindTooltip(`${road.name} / ${feature.properties.relation === "name-match" ? "名前一致線形" : "周辺参考線"}`);
    layer.on("click", () => selectRoad(road.id));
    const existing = state.routeLayers.get(road.id) || [];
    existing.push({ layer, feature });
    state.routeLayers.set(road.id, existing);
  });

  renderMapLayers();
}

function enrichRoads(roads, karteRows, shortlist, routeFeatures) {
  const karteById = new Map(karteRows.map((item) => [item.id, item]));
  const selectedById = new Map(shortlist.selected.map((item) => [item.id, item]));
  const reserveById = new Map(shortlist.reserve.map((item) => [item.id, item]));

  return roads.map((road) => {
    const karte = karteById.get(road.id);
    const selected = selectedById.get(road.id);
    const reserve = reserveById.get(road.id);
    const routeRelations = routeFeatures
      .filter((feature) => feature.properties?.id === road.id)
      .map((feature) => feature.properties.relation);

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
      karteSources: karte ? karte.sources : road.sourceLinks || [],
      routeRelations,
      rideTier: selected ? "selected" : reserve ? "reserve" : "other",
      rideOrder: selected ? selected.order : null,
      rideNote: selected ? selected.selectionReason : reserve ? reserve.selectionReason : null,
    };
  });
}

function buildDataUrl(fileName) {
  return new URL(`${DATA_BASE_PATH}/${fileName}`, window.location.href).toString();
}

async function checkedFetch(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response;
}

async function loadRoads() {
  const [roadsResponse, karteResponse, shortlistResponse, routesResponse] = await Promise.all([
    checkedFetch(buildDataUrl("nagano_map_data.json")),
    checkedFetch(buildDataUrl("karte.json")),
    checkedFetch(buildDataUrl("nagano_shortlist.json")),
    checkedFetch(buildDataUrl("nagano_routes.geojson")),
  ]);

  const roads = await roadsResponse.json();
  const karteRows = await karteResponse.json();
  const shortlist = await shortlistResponse.json();
  const routeCollection = await routesResponse.json();
  state.routeFeatures = routeCollection.features || [];
  state.candidateCount = shortlist.counts?.master || roads.length;
  state.allRoads = enrichRoads(roads, karteRows, shortlist, state.routeFeatures);
}

function locationErrorMessage(error) {
  if (error?.code === 1) return "位置情報が許可されていません";
  if (error?.code === 2) return "現在地を取得できませんでした";
  if (error?.code === 3) return "現在地の取得がタイムアウトしました";
  return "現在地を取得できませんでした";
}

function applyUserLocation(position, { center = false } = {}) {
  const { latitude, longitude, accuracy } = position.coords;
  state.userLocation = { latitude, longitude, accuracy, capturedAt: new Date().toISOString() };

  if (!state.userMarker) {
    state.accuracyCircle = L.circle([latitude, longitude], {
      radius: accuracy,
      color: "#245f86",
      weight: 1,
      fillColor: "#4c9ac7",
      fillOpacity: 0.12,
      interactive: false,
    }).addTo(state.map);
    state.userMarker = L.circleMarker([latitude, longitude], {
      radius: 8,
      color: "#ffffff",
      weight: 3,
      fillColor: "#176f9e",
      fillOpacity: 1,
    }).addTo(state.map);
    state.userMarker.bindTooltip("現在地");
  } else {
    state.userMarker.setLatLng([latitude, longitude]);
    state.accuracyCircle.setLatLng([latitude, longitude]).setRadius(accuracy);
  }

  if (center) state.map.setView([latitude, longitude], Math.max(state.map.getZoom(), 13));
  syncGoogleUserLocation();
  if (center && state.baseMap === "google" && state.googleMap) {
    state.googleMap.setCenter({ lat: latitude, lng: longitude });
    state.googleMap.setZoom(Math.max(state.googleMap.getZoom() || 0, 13));
  }
  ui.locationButton.textContent = "現在地を更新";
  ui.locationButton.classList.add("is-active");
  updateDistanceDisplay();
}

function requestCurrentLocation({ center = false } = {}) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("この端末は位置情報に対応していません"));
      return;
    }
    ui.locationButton.disabled = true;
    ui.locationButton.textContent = "現在地を取得中...";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        applyUserLocation(position, { center });
        ui.locationButton.disabled = false;
        resolve(state.userLocation);
      },
      (error) => {
        ui.locationButton.disabled = false;
        ui.locationButton.textContent = state.userLocation ? "現在地を更新" : "現在地を表示";
        reject(new Error(locationErrorMessage(error)));
      },
      { enableHighAccuracy: true, timeout: 12_000, maximumAge: 15_000 },
    );
  });
}

function openRecordDb() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("端末内保存に対応していません"));
      return;
    }
    const request = indexedDB.open(RECORD_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(RECORD_STORE_NAME)) {
        db.createObjectStore(RECORD_STORE_NAME, { keyPath: "roadId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function recordDbRequest(mode, operation) {
  const db = await openRecordDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(RECORD_STORE_NAME, mode);
    const store = transaction.objectStore(RECORD_STORE_NAME);
    const request = operation(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => reject(transaction.error);
  });
}

function getAllRecords() {
  return recordDbRequest("readonly", (store) => store.getAll());
}

function saveRecord(record) {
  return recordDbRequest("readwrite", (store) => store.put(record));
}

function removeRecord(roadId) {
  return recordDbRequest("readwrite", (store) => store.delete(roadId));
}

async function initializeRecords() {
  try {
    const records = await getAllRecords();
    state.records = new Map(records.map((record) => [record.roadId, record]));
    state.recordStorageReady = true;
  } catch (error) {
    console.error(error);
    state.recordStorageReady = false;
  }
  updateRecordControls();
}

function updateRecordControls() {
  ui.exportButton.hidden = state.records.size === 0;
  updateSummary();
}

function renderRecordLocation() {
  const location = state.recordDraftLocation;
  ui.recordLocationText.textContent = location
    ? `${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}（精度 約${Math.round(location.accuracy || 0)}m）`
    : "位置未記録";
}

function renderPhotoPreview() {
  ui.photoPreview.innerHTML = "";
  state.recordDraftPhotos.forEach((photo, index) => {
    const figure = document.createElement("figure");
    const image = document.createElement("img");
    image.src = photo.dataUrl;
    image.alt = photo.name || `現地写真 ${index + 1}`;
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.textContent = "削除";
    removeButton.setAttribute("aria-label", `${image.alt}を削除`);
    removeButton.addEventListener("click", () => {
      state.recordDraftPhotos.splice(index, 1);
      renderPhotoPreview();
    });
    figure.append(image, removeButton);
    ui.photoPreview.appendChild(figure);
  });
}

function loadRecordForm(road) {
  const record = state.records.get(road.id);
  ui.recordObservedAt.value = record ? toLocalInputValue(record.observedAt) : toLocalInputValue();
  ui.recordAccess.value = record?.accessStatus || "未確認";
  ui.recordSurface.value = record?.surface || "未確認";
  ui.recordGate.value = record?.gate || "不明";
  ui.recordNote.value = record?.note || "";
  ui.recordMessage.textContent = "";
  ui.recordSummaryStatus.textContent = record ? `保存済み ${new Date(record.savedAt).toLocaleDateString("ja-JP")}` : "未記録";
  ui.deleteRecordButton.hidden = !record;
  state.recordDraftLocation = record?.location ? { ...record.location } : null;
  state.recordDraftPhotos = record?.photos ? record.photos.map((photo) => ({ ...photo })) : [];
  ui.recordPhotos.value = "";
  renderRecordLocation();
  renderPhotoPreview();
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("写真を読み込めませんでした"));
    };
    image.src = url;
  });
}

async function compressPhoto(file) {
  if (!file.type.startsWith("image/")) throw new Error("画像ファイルを選んでください");
  if (file.size > 15 * 1024 * 1024) throw new Error("15MB以下の写真を選んでください");
  const image = await loadImageFromFile(file);
  const maxSide = 1280;
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.78));
  if (!blob) throw new Error("写真を縮小できませんでした");
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name: file.name,
    type: blob.type,
    size: blob.size,
    dataUrl: await blobToDataUrl(blob),
  };
}

async function addSelectedPhotos(files) {
  const remaining = MAX_PHOTOS - state.recordDraftPhotos.length;
  if (remaining <= 0) throw new Error("写真は最大3枚です");
  const selected = Array.from(files).slice(0, remaining);
  ui.recordMessage.textContent = "写真を縮小中...";
  for (const file of selected) {
    state.recordDraftPhotos.push(await compressPhoto(file));
    renderPhotoPreview();
  }
  ui.recordMessage.textContent = selected.length < files.length ? "写真は最大3枚まで保存できます" : "写真を追加しました";
}

async function submitRecord(event) {
  event.preventDefault();
  const road = getSelectedRoad();
  if (!road) return;
  if (!state.recordStorageReady) {
    ui.recordMessage.textContent = "この端末では記録を保存できません";
    return;
  }

  const observedAt = ui.recordObservedAt.value ? new Date(ui.recordObservedAt.value).toISOString() : new Date().toISOString();
  const record = {
    schemaVersion: 1,
    roadId: road.id,
    roadName: road.name,
    municipality: road.municipality,
    observedAt,
    accessStatus: ui.recordAccess.value,
    surface: ui.recordSurface.value,
    gate: ui.recordGate.value,
    note: ui.recordNote.value.trim(),
    location: state.recordDraftLocation ? { ...state.recordDraftLocation } : null,
    photos: state.recordDraftPhotos.map((photo) => ({ ...photo })),
    savedAt: new Date().toISOString(),
  };

  try {
    await saveRecord(record);
    state.records.set(road.id, record);
    ui.recordMessage.textContent = "端末内に保存しました";
    ui.recordSummaryStatus.textContent = `保存済み ${new Date(record.savedAt).toLocaleDateString("ja-JP")}`;
    ui.deleteRecordButton.hidden = false;
    setBadge(road);
    updateRecordControls();
  } catch (error) {
    console.error(error);
    ui.recordMessage.textContent = "保存できませんでした。写真を減らして再度お試しください";
  }
}

async function deleteCurrentRecord() {
  const road = getSelectedRoad();
  if (!road || !state.records.has(road.id)) return;
  if (!window.confirm(`${road.name}の現地記録を削除しますか？`)) return;
  try {
    await removeRecord(road.id);
    state.records.delete(road.id);
    loadRecordForm(road);
    setBadge(road);
    updateRecordControls();
    ui.recordMessage.textContent = "記録を削除しました";
  } catch (error) {
    console.error(error);
    ui.recordMessage.textContent = "削除できませんでした";
  }
}

function exportRecords() {
  const payload = {
    schemaVersion: 1,
    exportedAt: new Date().toISOString(),
    app: "日本林道データベース",
    records: Array.from(state.records.values()).sort((a, b) => a.roadId.localeCompare(b.roadId)),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `rindo-field-records-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function updateConnectionStatus() {
  const online = navigator.onLine;
  ui.connectionBadge.textContent = online ? "オンライン" : "オフライン";
  ui.connectionBadge.classList.toggle("is-offline", !online);
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  try {
    await navigator.serviceWorker.register(APP_CONFIG.serviceWorkerPath || "../sw.js");
  } catch (error) {
    console.error("Service worker registration failed", error);
  }
}

function bindUi() {
  ui.filterButtons.forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  ui.regionFilter.addEventListener("change", () => setRegion(ui.regionFilter.value));
  ui.baseMapSelect.addEventListener("change", () => {
    setBaseMap(ui.baseMapSelect.value).catch((error) => {
      console.error(error);
      setMapProviderMessage("背景地図の切り替えに失敗しました");
      ui.baseMapSelect.value = state.baseMap;
      ui.baseMapSelect.disabled = false;
    });
  });

  ui.sheetToggle.addEventListener("click", () => {
    if (!state.selectedId && state.sheetState === "collapsed") return;
    setSheetState(state.sheetState === "expanded" ? "collapsed" : "expanded");
  });

  ui.locationButton.addEventListener("click", async () => {
    try {
      await requestCurrentLocation({ center: true });
    } catch (error) {
      ui.locationButton.textContent = error.message;
      window.setTimeout(() => {
        ui.locationButton.textContent = state.userLocation ? "現在地を更新" : "現在地を表示";
      }, 2200);
    }
  });

  ui.copyCoordinatesButton.addEventListener("click", async () => {
    const road = getSelectedRoad();
    if (!road) return;
    await copyText(`${road.entryLat},${road.entryLon}`);
    ui.copyCoordinatesButton.textContent = "コピー済み";
    window.setTimeout(() => (ui.copyCoordinatesButton.textContent = "座標をコピー"), 1400);
  });

  ui.shareButton.addEventListener("click", () => {
    shareCurrentRoad().catch((error) => {
      console.error(error);
      ui.shareButton.textContent = "共有に失敗";
      window.setTimeout(() => (ui.shareButton.textContent = "候補を共有"), 1600);
    });
  });

  ui.openRecordButton.addEventListener("click", () => {
    ui.fieldRecord.open = true;
    ui.fieldRecord.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  ui.recordForm.addEventListener("submit", submitRecord);
  ui.deleteRecordButton.addEventListener("click", deleteCurrentRecord);
  ui.exportButton.addEventListener("click", exportRecords);

  ui.recordLocationButton.addEventListener("click", async () => {
    try {
      const location = state.userLocation || (await requestCurrentLocation());
      state.recordDraftLocation = { ...location };
      renderRecordLocation();
      ui.recordMessage.textContent = "現在地を記録欄へ追加しました。保存ボタンで確定します";
    } catch (error) {
      ui.recordMessage.textContent = error.message;
    }
  });

  ui.recordPhotos.addEventListener("change", () => {
    addSelectedPhotos(ui.recordPhotos.files).catch((error) => {
      console.error(error);
      ui.recordMessage.textContent = error.message;
    });
  });

  window.addEventListener("online", updateConnectionStatus);
  window.addEventListener("offline", updateConnectionStatus);
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.deferredInstallPrompt = event;
    ui.installButton.hidden = false;
  });
  window.addEventListener("appinstalled", () => {
    state.deferredInstallPrompt = null;
    ui.installButton.hidden = true;
  });
  ui.installButton.addEventListener("click", async () => {
    if (!state.deferredInstallPrompt) return;
    state.deferredInstallPrompt.prompt();
    await state.deferredInstallPrompt.userChoice;
    state.deferredInstallPrompt = null;
    ui.installButton.hidden = true;
  });

  window.addEventListener("resize", () => {
    if (state.googleMap && window.google?.maps) window.google.maps.event.trigger(state.googleMap, "resize");
    if (isDesktopLayout()) setSheetState("expanded");
    else {
      ui.detailSheet.dataset.sheetState = state.sheetState;
      updateSheetToggle();
      if (state.map) window.setTimeout(() => state.map.invalidateSize(), 120);
    }
  });
}

async function bootstrap() {
  const initialState = parseInitialState();
  createMap();
  bindUi();
  updateConnectionStatus();
  setSheetState(initialState.roadId || isDesktopLayout() ? "expanded" : "collapsed");

  await Promise.all([loadRoads(), initializeRecords()]);
  addMapLayers();

  state.view = initialState.view;
  state.region = initialState.region;
  ui.regionFilter.value = state.region;
  syncFilterButtons();
  ensureVisibleSelection();
  await setBaseMap(initialState.baseMap, { fit: false });
  renderMapLayers();

  const preferredRoad =
    state.allRoads.find((item) => item.id === initialState.roadId && isVisibleInCurrentView(item)) ||
    state.allRoads.find((item) => item.id === initialState.roadId) ||
    (isDesktopLayout() ? getVisibleRoads()[0] : null);

  if (preferredRoad) {
    selectRoad(preferredRoad.id, {
      skipFly: true,
      expandSheet: Boolean(initialState.roadId) || isDesktopLayout(),
    });
  }

  updateSheetToggle();
  registerServiceWorker();
}

bootstrap().catch((error) => {
  console.error(error);
  ui.summaryText.textContent = typeof window.L === "undefined"
    ? "地図機能の読み込みに失敗しました"
    : "データの読み込みに失敗しました";
});
