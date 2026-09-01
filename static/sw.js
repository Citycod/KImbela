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
      .then(() => self.skipWaiting())
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

const DEFAULT_NOTIFICATION_TITLE = 'Kimbela Notification';
const DEFAULT_NOTIFICATION_BODY = 'You have a new notification.';
const DEFAULT_NOTIFICATION_ICON = '/static/img/icons/icon-192x192.png';

function readPushPayload(event) {
  if (!event.data) return {};

  try {
    const parsed = event.data.json();
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed;
    }
    if (parsed !== undefined && parsed !== null) {
      return { body: String(parsed) };
    }
  } catch (error) {
    try {
      const textPayload = event.data.text();
      return textPayload ? { body: textPayload } : {};
    } catch (textError) {
      console.error('Unable to read push payload', textError);
    }
  }

  return {};
}

function safeNotificationAsset(value) {
  if (typeof value !== 'string' || !value.trim()) return DEFAULT_NOTIFICATION_ICON;

  try {
    const assetUrl = new URL(value, self.location.origin);
    if (assetUrl.protocol === 'https:' || assetUrl.protocol === 'http:') return value;
  } catch (error) {
    // Use the known local icon when a payload contains an invalid asset URL.
  }
  return DEFAULT_NOTIFICATION_ICON;
}

function safeNotificationDestination(value) {
  if (typeof value !== 'string' || !value.trim()) return '/';

  try {
    const destination = new URL(value, self.location.origin);
    return destination.origin === self.location.origin ? value : '/';
  } catch (error) {
    return '/';
  }
}

function showPushNotification(data) {
  const title = typeof data.title === 'string' && data.title.trim()
    ? data.title
    : DEFAULT_NOTIFICATION_TITLE;
  const body = typeof data.body === 'string' && data.body.trim()
    ? data.body
    : DEFAULT_NOTIFICATION_BODY;
  const options = {
    body,
    icon: safeNotificationAsset(data.icon),
    badge: safeNotificationAsset(data.badge),
    timestamp: Number.isFinite(data.timestamp) ? data.timestamp : Date.now(),
    vibrate: [100, 50, 100],
    data: {
      url: safeNotificationDestination(data.url),
    },
  };
  if (typeof data.tag === 'string' && data.tag) {
    options.tag = data.tag;
    options.renotify = data.renotify === true;
  }

  const systemNotification = Promise.resolve()
    .then(() => self.registration.showNotification(title, options))
    .catch(error => {
      console.error('Notification options rejected; retrying with safe defaults', error);
      return self.registration.showNotification(DEFAULT_NOTIFICATION_TITLE, {
        body,
        data: { url: options.data.url },
      });
    });

  const foregroundFeedback = Promise.resolve()
    .then(() => self.clients.matchAll({ type: 'window', includeUncontrolled: true }))
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
            body,
            url: options.data.url,
            tag: options.tag || '',
            avatar: typeof data.avatar === 'string' ? data.avatar : '',
            timestamp: options.timestamp,
            eventType: typeof data.event_type === 'string'
              ? data.event_type
              : 'notification',
          },
        });
      }
    })
    .catch(error => {
      // Foreground feedback is best-effort and must never block OS delivery.
      console.error('Unable to deliver foreground push feedback', error);
    });

  return Promise.all([systemNotification, foregroundFeedback]);
}

self.addEventListener('push', event => {
  event.waitUntil(
    Promise.resolve().then(() => showPushNotification(readPushPayload(event)))
  );
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
