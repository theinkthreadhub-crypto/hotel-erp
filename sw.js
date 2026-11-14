// Setu - Restaurant & Hotel POS - Service Worker
const CACHE_NAME = 'setu-pos-v103';
// Smart Food Visuals pictures never change under the same name: kept across app updates
const FOOD_CACHE = 'setu-food-v1';
const ASSETS = [
  './',
  './hotel_erp.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './favicon.ico',
  './horeca-icon-dark.png',
  './horeca-logo-full.png',
  './horeca-icon-trans.png',
  './horeca-logo-dark.png',
  './food/food-match.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS).catch(err => {
        console.warn('Cache prefill warning:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME && key !== FOOD_CACHE).map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  // Live database calls must always reach the main counter, never a cache
  const url = new URL(event.request.url);
  // Dish pictures (library files and the hotel's own photos, named by their hash): cache on first view, then offline
  if (/\/food\/(lib|thumb)\/[a-z0-9-]+\.webp$/.test(url.pathname) || /^\/api\/media\/m_[0-9a-f]{32}(\.t)?$/.test(url.pathname)) {
    event.respondWith(caches.open(FOOD_CACHE).then(cache => cache.match(event.request).then(hit => hit || fetch(event.request).then(res => {
      if (res && res.status === 200) cache.put(event.request, res.clone());
      return res;
    }))));
    return;
  }
  if (url.pathname.startsWith('/api/')) return;
  // The app page itself: always try the network first so an updated Setu shows at once;
  // the cached copy is only used when offline
  if (event.request.mode === 'navigate' || url.pathname.endsWith('.html')) {
    event.respondWith(
      fetch(event.request).then(networkResponse => {
        if (networkResponse && networkResponse.status === 200) {
          const copy = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
        }
        return networkResponse;
      }).catch(() => caches.match(event.request).then(r => r || caches.match('./hotel_erp.html')))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then(cachedResponse => {
      if (cachedResponse) {
        fetch(event.request).then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, networkResponse));
          }
        }).catch(() => {});
        return cachedResponse;
      }
      return fetch(event.request).catch(() => {
        if (event.request.mode === 'navigate') {
          return caches.match('./hotel_erp.html');
        }
      });
    })
  );
});
