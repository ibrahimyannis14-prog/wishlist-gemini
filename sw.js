// Service Worker — Ma liste de vêtements Partagée
// Stratégie : "App Shell" en cache-first pour le HTML/manifest/icônes,
// tout le reste (Firebase, images, scraping backend) passe directement par le réseau
// car ce sont des données dynamiques/temps réel qui ne doivent pas être mises en cache.

const CACHE_NAME = 'wishlist-shell-v1';
const APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-192.png',
  './icons/icon-maskable-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // On ne gère que les requêtes GET.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Ne jamais intercepter Firebase, Google Fonts, ou le backend de scraping :
  // ces données doivent toujours venir du réseau (temps réel / dynamique).
  const isExternalDynamic =
    url.hostname.includes('firebaseio.com') ||
    url.hostname.includes('googleapis.com') ||
    url.hostname.includes('gstatic.com') ||
    url.hostname.includes('firebasestorage.app') ||
    url.hostname.includes('onrender.com');

  if (isExternalDynamic) {
    return; // laisse passer directement au réseau, pas de fetch() custom
  }

  // Pour l'app shell : cache-first, puis mise à jour en arrière-plan (stale-while-revalidate).
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      const networkFetch = fetch(req)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return networkResponse;
        })
        .catch(() => cachedResponse); // hors-ligne : on retombe sur le cache

      return cachedResponse || networkFetch;
    })
  );
});
