const CACHE_NAME = 'quintillizas-ai-v2'; // Si haces cambios grandes, cambia el v2 por v3, v4, etc.

self.addEventListener('install', event => {
  // Fuerza al nuevo Service Worker a activarse inmediatamente
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  // Elimina las cachés viejas
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // Intenta buscar en la red primero, si falla, usa la caché
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
