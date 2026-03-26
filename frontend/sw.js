// Service Worker — offline-first app shell caching
const CACHE = "squad-rotation-v1";
const SHELL = ["/", "/app.js", "/api.js", "/style.css", "/manifest.json"];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
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
  // API requests: network-first, no offline fallback (data must be loaded while online)
  if (e.request.url.includes("/api/")) {
    e.respondWith(fetch(e.request));
    return;
  }
  // App shell: cache-first
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }))
  );
});
