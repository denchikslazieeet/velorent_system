{% load static %}
const CACHE_NAME = "velorent-pwa-v30";
const OFFLINE_URL = "{% url 'offline' %}";
const STATIC_PREFIX = new URL("{% static '' %}", self.location.origin).pathname;
const STYLE_URL = new URL("{% static 'css/style.css' %}", self.location.origin).pathname;
const STATIC_ASSETS = [
  OFFLINE_URL,
  "{% static 'css/style.css' %}?v=20260522-1",
  "{% static 'img/velorent-icon.svg' %}",
  "{% static 'img/velorent-logo.svg' %}",
  "{% static 'img/page-bike-bg.svg' %}",
  "{% static 'img/pwa-icon-192.png' %}",
  "{% static 'img/pwa-icon-512.png' %}"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const url = new URL(event.request.url);
  const isVideo = event.request.destination === "video" || url.pathname.endsWith(".mp4");

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  if (isVideo) {
    return;
  }

  if (url.origin === self.location.origin && url.pathname === STYLE_URL) {
    event.respondWith(
      fetch(event.request, { cache: "no-cache" }).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  if (url.origin === self.location.origin && url.pathname.startsWith(STATIC_PREFIX)) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) {
          return cached;
        }
        return fetch(event.request).then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        });
      })
    );
  }
});
