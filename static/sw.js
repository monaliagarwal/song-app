const CACHE_NAME = 'moodtune-v1';
const urlsToCache = [
  '/',
  '/static/manifest.json',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  if (event.request.url.includes('/generate/') ||
      event.request.url.includes('/search/') ||
      event.request.url.includes('/detect-mood/')) {
    return fetch(event.request);
  }
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
