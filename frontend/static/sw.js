const CACHE = "clubedecinema-v19";
const STATIC = [
  "/",
  "/watch",
  "/static/css/styles.css",
  "/static/css/editorial.css",
  "/static/js/shared/editorial.js",
  "/static/js/shared/movie-details.js",
  "/static/css/components/movie-details.css",
  "/static/css/base.css",
  "/static/css/components/letterboxd.css",
  "/static/css/components/watched.css",
  "/static/css/components/reactions.css",
  "/static/css/components/chat.css",
  "/static/css/pages/profile.css",
  "/static/css/components/username.css",
  "/static/css/responsive.css",
  "/static/css/pages/cinema.css",
  "/static/css/pages/watch.css",
  "/static/css/themes/italian.css",
  "/static/css/themes/netflix.css",
  "/static/css/utilities.css",
  "/static/js/pages/app.js",
  "/static/js/pages/watch.js",
  "/static/js/pages/archive.js",
  "/static/manifest.json",
  "/static/icons/favicon.ico",
  "/static/icons/favicon-32x32.png",
  "/static/icons/android-chrome-192x192.png",
  "/static/icons/android-chrome-512x512.png",
  "/static/images/netflix-n.png",
  "/static/images/netflix-wordmark.png",
  "/static/icons/apple-touch-icon.png",
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
  if (url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/movies/") ||
      url.pathname.startsWith("/weeks") ||
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
                  url.pathname === "/leaderboard" ||
                  url.pathname === "/admin" ||
                  url.pathname === "/preview" ||
                  url.pathname.startsWith("/profile/");

  if (isAsset) {
    e.respondWith(
      fetch(e.request, { cache: "no-cache" })
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
