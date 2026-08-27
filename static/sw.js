const KIMBELA_CACHE_PREFIX = 'kimbela-';
const PRECACHE_NAME = 'kimbela-precache-v4';
const STATIC_CACHE_NAME = 'kimbela-static-v4';
const OFFLINE_URL = '/offline';
const ESSENTIAL_PRECACHE_URLS = [
  OFFLINE_URL,
  '/static/manifest.json',
  '/static/img/icons/icon-192x192.png',
  '/static/img/icons/icon-512x512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(PRECACHE_NAME)
      .then(cache => cache.addAll(ESSENTIAL_PRECACHE_URLS))
  );
});

self.addEventListener('activate', event => {
  const currentCaches = new Set([PRECACHE_NAME, STATIC_CACHE_NAME]);
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => (
          name.startsWith(KIMBELA_CACHE_PREFIX) && !currentCaches.has(name)
        ))
          .map(name => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') {
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => (
        caches.match(OFFLINE_URL).then(response => (
          response || new Response('You are offline.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
          })
        ))
      ))
    );
    return;
  }

  const requestUrl = new URL(event.request.url);
  const isPublicStaticAsset = (
    requestUrl.origin === self.location.origin
    && requestUrl.pathname.startsWith('/static/')
    && !event.request.headers.has('range')
  );

  if (isPublicStaticAsset) {
    event.respondWith(
      caches.match(event.request).then(cachedResponse => {
        if (cachedResponse) {
          return cachedResponse;
        }

        return fetch(event.request).then(networkResponse => {
          if (networkResponse.status === 200 && networkResponse.type !== 'opaque') {
            const responseToCache = networkResponse.clone();
            caches.open(STATIC_CACHE_NAME)
              .then(cache => cache.put(event.request, responseToCache))
              .catch(error => console.error('Static asset cache write failed', error));
          }
          return networkResponse;
        });
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
