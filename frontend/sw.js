const CACHE = "clubedecinema-v1";
const STATIC = [
  "/",
  "/static/styles.css",
  "/static/app.js",
  "/static/manifest.json",
  "/static/favicon.ico",
  "/static/favicon-32x32.png",
  "/static/android-chrome-192x192.png",
  "/static/android-chrome-512x512.png",
  "/static/apple-touch-icon.png",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // API calls — always network, never cache
  if (url.pathname.startsWith("/weeks") ||
      url.pathname.startsWith("/auth") ||
      url.pathname.startsWith("/films") ||
      url.pathname.startsWith("/letterboxd") ||
      url.pathname.startsWith("/users") ||
      url.pathname.startsWith("/chat")) {
    return;
  }

  // Static assets — cache first, fallback to network
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
