const CACHE = "clubedecinema-v8";
const STATIC = [
  "/",
  "/watch",
  "/static/styles.css",
  "/static/app.js",
  "/static/watch.js",
  "/static/archive.js",
  "/static/manifest.json",
  "/static/favicon.ico",
  "/static/favicon-32x32.png",
  "/static/android-chrome-192x192.png",
  "/static/android-chrome-512x512.png",
  "/static/netflix-n.png",
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
      url.pathname.startsWith("/chat") ||
      url.pathname.startsWith("/search") ||
      url.pathname.startsWith("/admin/")) {
    return;
  }

  // HTML, JS and CSS — always network first, fallback to cache
  const isAsset = url.pathname.endsWith(".js") || 
                  url.pathname.endsWith(".css") ||
                  url.pathname.endsWith(".html") ||
                  url.pathname === "/" ||
                  url.pathname === "/watch" ||
                  url.pathname === "/archive" ||
                  url.pathname === "/admin" ||
                  url.pathname === "/preview" ||
                  url.pathname.startsWith("/profile/");

  if (isAsset) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Everything else (images, fonts) — cache first
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
