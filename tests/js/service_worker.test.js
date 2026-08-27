const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const workerSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/sw.js'),
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
      openWindow: async () => undefined,
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
  ]]);
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
      json: () => ({ title: 'New message', body: 'Hello', url: '/messages' }),
    },
    waitUntil: (promise) => { pushPromise = promise; },
  });
  await pushPromise;

  assert.equal(worker.notifications.length, 1);
  assert.equal(worker.notifications[0].title, 'New message');
  assert.equal(worker.notifications[0].options.data.url, '/messages');
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
