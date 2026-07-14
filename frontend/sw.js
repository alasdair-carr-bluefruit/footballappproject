// Service Worker — network-first with cache fallback
const CACHE = "squad-rotation-v6";
// app.js is a thin entry point that side-effect-imports the modules below, so
// they must all be pre-cached for the app to work offline (app.js alone is not
// enough). Keep this list in sync with frontend/*.js (see index.html).
const SHELL = [
  "/",
  "/app.js",
  "/state.js",
  "/pitch.js",
  "/setup-form.js",
  "/season.js",
  "/tournament.js",
  "/screens.js",
  "/api.js",
  "/style.css",
  "/manifest.json",
];

self.addEventListener("install", e => {
  // Cache each asset individually — a single failure won't abort the whole install
  e.waitUntil(
    caches.open(CACHE).then(c =>
      Promise.allSettled(SHELL.map(url => c.add(url)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  // API requests: always network, no caching
  if (e.request.url.includes("/api/")) {
    e.respondWith(fetch(e.request));
    return;
  }
  // App shell: network-first, fall back to cache
  e.respondWith(
    fetch(e.request).then(res => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match(e.request))
  );
});
