const KIMBELA_CACHE_PREFIX = 'kimbela-';
const PRECACHE_NAME = 'kimbela-precache-v5';
const STATIC_CACHE_NAME = 'kimbela-static-v5';
const OFFLINE_URL = '/offline';
const ESSENTIAL_PRECACHE_URLS = [
  OFFLINE_URL,
  '/static/manifest.json',
  '/static/img/icons/icon-192x192.png',
  '/static/img/icons/icon-512x512.png',
  '/static/img/icons/icon-maskable-192x192.png',
  '/static/img/icons/icon-maskable-512x512.png',
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
        icon: data.icon || '/static/img/icons/icon-192x192.png',
        badge: data.badge || '/static/img/icons/icon-192x192.png',
        timestamp: Number.isFinite(data.timestamp) ? data.timestamp : Date.now(),
        vibrate: [100, 50, 100],
        data: {
          url: data.url || '/'
        }
      };
      if (typeof data.tag === 'string' && data.tag) {
        options.tag = data.tag;
        options.renotify = data.renotify === true;
      }
      const systemNotification = self.registration.showNotification(title, options);
      const foregroundFeedback = self.clients
        .matchAll({ type: 'window', includeUncontrolled: true })
        .then(windowClients => {
          const visibleClients = windowClients.filter(
            client => client.visibilityState === 'visible'
          );
          const targetClient = visibleClients.find(client => client.focused)
            || visibleClients[0];
          if (targetClient && 'postMessage' in targetClient) {
            targetClient.postMessage({
              type: 'PUSH_FOREGROUND_NOTIFICATION',
              notification: {
                title,
                body: options.body,
                url: options.data.url,
                tag: options.tag || '',
                avatar: data.avatar || '',
                timestamp: options.timestamp,
                eventType: data.event_type || 'notification',
              },
            });
          }
        });
      event.waitUntil(Promise.all([systemNotification, foregroundFeedback]));
    } catch (e) {
      console.error('Error parsing push data', e);
    }
  }
});

self.addEventListener('pushsubscriptionchange', event => {
  const replacementPromise = event.newSubscription
    ? Promise.resolve(event.newSubscription)
    : (
      event.oldSubscription && event.oldSubscription.options
        ? self.registration.pushManager.subscribe(event.oldSubscription.options)
        : Promise.reject(new Error('Push subscription replacement options unavailable'))
    );

  event.waitUntil(
    replacementPromise.then(subscription => (
      self.clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(windowClients => {
          const subscriptionData = subscription.toJSON
            ? subscription.toJSON()
            : subscription;
          windowClients.forEach(client => client.postMessage({
            type: 'PUSH_SUBSCRIPTION_CHANGED',
            subscription: subscriptionData,
          }));
        })
    )).catch(error => {
      console.error('Failed to refresh push subscription', error);
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const urlToOpen = event.notification.data?.url || '/';
  const targetUrl = new URL(urlToOpen, self.location.origin);
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (let i = 0; i < windowClients.length; i++) {
        const client = windowClients[i];
        const clientUrl = new URL(client.url);
        const sameDestination = clientUrl.origin === targetUrl.origin
          && clientUrl.pathname === targetUrl.pathname
          && clientUrl.search === targetUrl.search;
        if (sameDestination && 'focus' in client) {
          if ('navigate' in client && client.url !== targetUrl.href) {
            return client.navigate(targetUrl.href).then(navigatedClient => (
              navigatedClient && 'focus' in navigatedClient
                ? navigatedClient.focus()
                : client.focus()
            ));
          }
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
