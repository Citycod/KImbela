const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const workerSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/sw.js'),
  'utf8',
);
const messengerSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/messenger.js'),
  'utf8',
);

function createResponse(body, options = {}) {
  return {
    body,
    status: options.status || 200,
    type: options.type || 'basic',
    headers: options.headers || {},
    clone() {
      return createResponse(body, options);
    },
  };
}

function loadWorker(overrides = {}) {
  const handlers = {};
  const deletedCaches = [];
  const cachePuts = [];
  const addAllCalls = [];
  const notifications = [];
  const openedWindows = [];
  const subscriptionCalls = [];
  let claimCount = 0;

  const runtimeCache = {
    addAll: async (urls) => {
      addAllCalls.push([...urls]);
      if (overrides.addAllError) throw overrides.addAllError;
    },
    put: async (request, response) => {
      cachePuts.push({ request, response });
    },
  };

  const caches = {
    open: async () => runtimeCache,
    keys: async () => overrides.cacheNames || [],
    delete: async (name) => {
      deletedCaches.push(name);
      return true;
    },
    match: async (request) => {
      if (overrides.cacheMatch) return overrides.cacheMatch(request);
      return undefined;
    },
  };

  const self = {
    location: { origin: 'https://kimbela.test' },
    clients: {
      claim: async () => {
        claimCount += 1;
      },
      matchAll: async () => overrides.windowClients || [],
      openWindow: async (url) => {
        openedWindows.push(url);
        return undefined;
      },
    },
    registration: {
      pushManager: {
        subscribe: async (options) => {
          subscriptionCalls.push(options);
          return overrides.replacementSubscription;
        },
      },
      showNotification: async (title, options) => {
        notifications.push({ title, options });
      },
    },
    addEventListener(type, handler) {
      handlers[type] = handler;
    },
  };

  const context = {
    URL,
    Set,
    Promise,
    Response: class Response {
      constructor(body, options) {
        Object.assign(this, createResponse(body, options));
      }
    },
    caches,
    console: { error() {} },
    fetch: overrides.fetch || (async () => createResponse('network')),
    self,
    clients: self.clients,
  };
  vm.runInNewContext(workerSource, context, { filename: 'static/sw.js' });

  return {
    addAllCalls,
    cachePuts,
    deletedCaches,
    handlers,
    notifications,
    openedWindows,
    subscriptionCalls,
    getClaimCount: () => claimCount,
  };
}

function createFetchEvent(request) {
  let responsePromise;
  return {
    request,
    respondWith(promise) {
      responsePromise = Promise.resolve(promise);
    },
    getResponse: () => responsePromise,
  };
}

test('install successfully precaches every essential offline resource', async () => {
  const worker = loadWorker();
  let installPromise;

  worker.handlers.install({ waitUntil: (promise) => { installPromise = promise; } });
  await installPromise;

  assert.deepEqual(worker.addAllCalls, [[
    '/offline',
    '/static/manifest.json',
    '/static/img/icons/icon-192x192.png',
    '/static/img/icons/icon-512x512.png',
    '/static/img/icons/icon-maskable-192x192.png',
    '/static/img/icons/icon-maskable-512x512.png',
  ]]);
});

test('precache excludes dashboard, authenticated API, and large content', async () => {
  const worker = loadWorker();
  let installPromise;

  worker.handlers.install({ waitUntil: (promise) => { installPromise = promise; } });
  await installPromise;

  const precachedUrls = worker.addAllCalls.flat();
  assert.equal(precachedUrls.some(url => url.includes('user_dashboard')), false);
  assert.equal(precachedUrls.some(url => url.startsWith('/api/')), false);
  assert.equal(precachedUrls.some(url => /\.(?:css|js|mp4|webp|jpe?g)$/.test(url)), false);
});

test('install rejects when an essential precache resource is missing', async () => {
  const worker = loadWorker({ addAllError: new Error('missing asset') });
  let installPromise;

  worker.handlers.install({ waitUntil: (promise) => { installPromise = promise; } });

  await assert.rejects(installPromise, /missing asset/);
});

test('activation deletes only old Kimbela-owned caches', async () => {
  const worker = loadWorker({
    cacheNames: [
      'kimbela-cache-v3',
      'kimbela-precache-v3',
      'kimbela-precache-v4',
      'kimbela-static-v4',
      'unrelated-app-cache',
    ],
  });
  let activationPromise;

  worker.handlers.activate({ waitUntil: (promise) => { activationPromise = promise; } });
  await activationPromise;

  assert.deepEqual(worker.deletedCaches.sort(), [
    'kimbela-cache-v3',
    'kimbela-precache-v3',
    'kimbela-precache-v4',
    'kimbela-static-v4',
  ]);
  assert.equal(worker.getClaimCount(), 1);
});

test('offline navigation returns the precached offline page', async () => {
  const offlineResponse = createResponse('offline page');
  const worker = loadWorker({
    fetch: async () => { throw new Error('offline'); },
    cacheMatch: async (request) => request === '/offline' ? offlineResponse : undefined,
  });
  const event = createFetchEvent({
    method: 'GET',
    mode: 'navigate',
    url: 'https://kimbela.test/user_dashboard',
    headers: { has: () => false },
  });

  worker.handlers.fetch(event);

  assert.equal(await event.getResponse(), offlineResponse);
});

test('same-origin public static assets are cached after a network miss', async () => {
  const networkResponse = createResponse('asset');
  const worker = loadWorker({ fetch: async () => networkResponse });
  const request = {
    method: 'GET',
    mode: 'cors',
    url: 'https://kimbela.test/static/app.js',
    headers: { has: () => false },
  };
  const event = createFetchEvent(request);

  worker.handlers.fetch(event);
  assert.equal(await event.getResponse(), networkResponse);
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(worker.cachePuts.length, 1);
  assert.equal(worker.cachePuts[0].request, request);
});

test('authenticated API requests are not intercepted or cached', () => {
  const worker = loadWorker();
  const event = createFetchEvent({
    method: 'GET',
    mode: 'cors',
    url: 'https://kimbela.test/api/messaging/friends',
    headers: { has: () => false },
  });

  worker.handlers.fetch(event);

  assert.equal(event.getResponse(), undefined);
  assert.equal(worker.cachePuts.length, 0);
});

test('push and notification-click handlers remain registered', async () => {
  const worker = loadWorker();
  let pushPromise;

  assert.equal(typeof worker.handlers.push, 'function');
  assert.equal(typeof worker.handlers.notificationclick, 'function');

  worker.handlers.push({
    data: {
      json: () => ({
        title: 'New message',
        body: 'Hello',
        url: '/user_dashboard?chat=13',
        icon: '/static/img/icons/icon-192x192.png',
        badge: '/static/img/icons/icon-192x192.png',
        tag: 'message-13',
        renotify: true,
        timestamp: 1700000000125,
      }),
    },
    waitUntil: (promise) => { pushPromise = promise; },
  });
  await pushPromise;

  assert.equal(worker.notifications.length, 1);
  assert.equal(worker.notifications[0].title, 'New message');
  assert.equal(
    worker.notifications[0].options.data.url,
    '/user_dashboard?chat=13',
  );
  assert.equal(
    worker.notifications[0].options.icon,
    '/static/img/icons/icon-192x192.png',
  );
  assert.equal(
    worker.notifications[0].options.badge,
    '/static/img/icons/icon-192x192.png',
  );
  assert.equal(worker.notifications[0].options.tag, 'message-13');
  assert.equal(worker.notifications[0].options.renotify, true);
  assert.equal(worker.notifications[0].options.timestamp, 1700000000125);
  assert.deepEqual(Array.from(worker.notifications[0].options.vibrate), [100, 50, 100]);
  assert.equal('requireInteraction' in worker.notifications[0].options, false);
  assert.equal('silent' in worker.notifications[0].options, false);
});

test('same tagged thread still shows every repeated message push', async () => {
  const worker = loadWorker();

  for (const body of ['One', 'Two', 'Three']) {
    let pushPromise;
    worker.handlers.push({
      data: {
        json: () => ({
          title: 'New message',
          body,
          url: '/user_dashboard?chat=13',
          tag: 'message-13',
          renotify: true,
        }),
      },
      waitUntil: promise => { pushPromise = promise; },
    });
    await pushPromise;
  }

  assert.equal(worker.notifications.length, 3);
  assert.deepEqual(
    worker.notifications.map(item => item.options.tag),
    ['message-13', 'message-13', 'message-13'],
  );
  assert.equal(worker.notifications.every(item => item.options.renotify), true);
});

test('closed app still receives the OS-level system notification', async () => {
  const worker = loadWorker({ windowClients: [] });
  let pushPromise;

  worker.handlers.push({
    data: { json: () => ({ title: 'Closed', body: 'Background push', url: '/user_dashboard' }) },
    waitUntil: promise => { pushPromise = promise; },
  });
  await pushPromise;

  assert.equal(worker.notifications.length, 1);
  assert.equal(worker.notifications[0].title, 'Closed');
});

test('backgrounded app receives system push without foreground feedback', async () => {
  const foregroundMessages = [];
  const worker = loadWorker({
    windowClients: [{
      visibilityState: 'hidden',
      focused: false,
      postMessage: message => foregroundMessages.push(message),
    }],
  });
  let pushPromise;

  worker.handlers.push({
    data: { json: () => ({ title: 'Background', body: 'Still delivered', url: '/user_dashboard' }) },
    waitUntil: promise => { pushPromise = promise; },
  });
  await pushPromise;

  assert.equal(worker.notifications.length, 1);
  assert.deepEqual(foregroundMessages, []);
});

test('visible app receives one foreground event without disabling system push', async () => {
  const foregroundMessages = [];
  const worker = loadWorker({
    windowClients: [
      {
        visibilityState: 'visible',
        focused: false,
        postMessage: message => foregroundMessages.push(message),
      },
      {
        visibilityState: 'visible',
        focused: true,
        postMessage: message => foregroundMessages.push(message),
      },
    ],
  });
  let pushPromise;

  worker.handlers.push({
    data: {
      json: () => ({
        title: 'New message',
        body: 'Foreground body',
        url: '/user_dashboard?chat=13',
        tag: 'message-13',
      }),
    },
    waitUntil: promise => { pushPromise = promise; },
  });
  await pushPromise;

  assert.equal(worker.notifications.length, 1);
  assert.equal(foregroundMessages.length, 1);
  assert.equal(foregroundMessages[0].type, 'PUSH_FOREGROUND_NOTIFICATION');
  assert.equal(
    foregroundMessages[0].notification.url,
    '/user_dashboard?chat=13',
  );
});

test('foreground socket handling does not create a second browser notification', () => {
  assert.match(messengerSource, /socket\.on\('new_message', handleNewMessage\)/);
  assert.doesNotMatch(messengerSource, /registration\.showNotification|new Notification\s*\(/);
});

test('notification click focuses an existing app at the destination', async () => {
  let focusCount = 0;
  const destination = '/user_dashboard?chat=13';
  const worker = loadWorker({
    windowClients: [{
      url: `https://kimbela.test${destination}`,
      async focus() {
        focusCount += 1;
      },
    }],
  });
  let clickPromise;
  let closeCount = 0;

  worker.handlers.notificationclick({
    notification: {
      data: { url: destination },
      close() {
        closeCount += 1;
      },
    },
    waitUntil: promise => { clickPromise = promise; },
  });
  await clickPromise;

  assert.equal(closeCount, 1);
  assert.equal(focusCount, 1);
  assert.deepEqual(worker.openedWindows, []);
});

test('notification click navigates an existing post client to the exact comment anchor', async () => {
  let navigatedTo = '';
  let focusCount = 0;
  const destination = '/post/public-post#comment-42';
  const client = {
    url: 'https://kimbela.test/post/public-post',
    async navigate(url) {
      navigatedTo = url;
      return this;
    },
    async focus() { focusCount += 1; },
  };
  const worker = loadWorker({ windowClients: [client] });
  let clickPromise;

  worker.handlers.notificationclick({
    notification: { data: { url: destination }, close() {} },
    waitUntil: promise => { clickPromise = promise; },
  });
  await clickPromise;

  assert.equal(navigatedTo, `https://kimbela.test${destination}`);
  assert.equal(focusCount, 1);
  assert.deepEqual(worker.openedWindows, []);
});

test('notification click opens the valid destination when the app is closed', async () => {
  const destination = '/user_dashboard?chat=13';
  const worker = loadWorker({ windowClients: [] });
  let clickPromise;

  worker.handlers.notificationclick({
    notification: { data: { url: destination }, close() {} },
    waitUntil: promise => { clickPromise = promise; },
  });
  await clickPromise;

  assert.deepEqual(worker.openedWindows, [destination]);
});

test('push subscription changes are replaced and sent to open clients', async () => {
  const postedMessages = [];
  const options = { userVisibleOnly: true, applicationServerKey: 'existing-key' };
  const replacement = {
    toJSON: () => ({
      endpoint: 'https://push.example/replacement',
      keys: { p256dh: 'replacement-p256dh', auth: 'replacement-auth' },
    }),
  };
  const worker = loadWorker({
    replacementSubscription: replacement,
    windowClients: [{ postMessage: message => postedMessages.push(message) }],
  });
  let changePromise;

  assert.equal(typeof worker.handlers.pushsubscriptionchange, 'function');
  worker.handlers.pushsubscriptionchange({
    oldSubscription: { options },
    newSubscription: null,
    waitUntil: promise => { changePromise = promise; },
  });
  await changePromise;

  assert.equal(worker.subscriptionCalls.length, 1);
  assert.equal(worker.subscriptionCalls[0], options);
  assert.equal(postedMessages.length, 1);
  assert.equal(postedMessages[0].type, 'PUSH_SUBSCRIPTION_CHANGED');
  assert.equal(
    postedMessages[0].subscription.endpoint,
    'https://push.example/replacement',
  );
});
