const CACHE_VERSION = "rindo-v9-20260716";
const APP_CACHE = `${CACHE_VERSION}-app`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const fromRoot = (path) => new URL(path, self.location.href).toString();

const APP_SHELL = [
  fromRoot("./"),
  fromRoot("./index.html"),
  fromRoot("./app/"),
  fromRoot("./app/index.html"),
  fromRoot("./app/main.js?v=20260716-1"),
  fromRoot("./app/styles.css?v=20260716-1"),
  fromRoot("./app/vendor/leaflet/leaflet.js"),
  fromRoot("./app/vendor/leaflet/leaflet.css"),
  fromRoot("./app/vendor/maplibre/maplibre-gl.js"),
  fromRoot("./app/vendor/maplibre/maplibre-gl.css"),
  fromRoot("./app/vendor/maplibre/leaflet-maplibre-gl.js"),
  fromRoot("./manifest.webmanifest"),
  fromRoot("./icons/rindo-192.png"),
  fromRoot("./icons/rindo-512.png"),
  fromRoot("./data/processed/nagano_map_data.json"),
  fromRoot("./data/processed/karte.json"),
  fromRoot("./data/processed/nagano_shortlist.json"),
  fromRoot("./data/processed/nagano_routes.geojson"),
];

const EXTERNAL_ASSETS = [
  "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const appCache = await caches.open(APP_CACHE);
      await appCache.addAll(APP_SHELL);
      const runtimeCache = await caches.open(RUNTIME_CACHE);
      await Promise.allSettled(EXTERNAL_ASSETS.map((url) => runtimeCache.add(url)));
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => ![APP_CACHE, RUNTIME_CACHE].includes(name)).map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

async function cacheFirst(request) {
  const cached = await caches.match(request, { ignoreSearch: false });
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok || response.type === "opaque") {
    const cache = await caches.open(RUNTIME_CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(APP_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (request.mode === "navigate") {
    event.respondWith(
      networkFirst(request).catch(() => caches.match(fromRoot("./app/index.html"), { ignoreSearch: true })),
    );
    return;
  }

  if (url.origin === self.location.origin && url.pathname.includes("/data/processed/")) {
    event.respondWith(networkFirst(request));
    return;
  }

  event.respondWith(cacheFirst(request));
});
