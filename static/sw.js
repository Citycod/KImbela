const CACHE_NAME = 'kimbela-cache-v2';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/manifest.json',
  '/static/img/icons/icon-192x192.png',
  '/static/img/icons/icon-512x512.png',
  // offline fallback page would go here if implemented, e.g. '/offline.html'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache).catch(err => {
            console.error("Failed to cache some items, continuing anyway", err);
        });
      })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME)
          .map(name => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // Simple cache-first strategy for static assets
  if (event.request.url.includes('/static/')) {
    event.respondWith(
      caches.match(event.request)
        .then(response => {
          return response || fetch(event.request);
        })
    );
  } else {
    // Network-first for other requests
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match(event.request);
      })
    );
  }
});

self.addEventListener('push', event => {
  if (event.data) {
    try {
      const data = event.data.json();
      const title = data.title || 'Kimbela Notification';
      const options = {
        body: data.body || 'You have a new notification.',
        icon: '/static/img/icons/icon-192x192.png',
        badge: '/static/img/icons/icon-192x192.png',
        data: {
          url: data.url || '/'
        }
      };
      event.waitUntil(self.registration.showNotification(title, options));
    } catch (e) {
      console.error('Error parsing push data', e);
    }
  }
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const urlToOpen = event.notification.data.url;
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      // Check if there is already a window/tab open with the target URL
      for (let i = 0; i < windowClients.length; i++) {
        const client = windowClients[i];
        if (client.url.includes(urlToOpen) && 'focus' in client) {
          return client.focus();
        }
      }
      // If not, open a new window/tab
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
