const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const initSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/pwa_init.js'),
  'utf8',
);

function createSubscription(endpoint) {
  let unsubscribeCount = 0;
  return {
    endpoint,
    keys: { p256dh: 'p256dh', auth: 'auth' },
    async unsubscribe() {
      unsubscribeCount += 1;
      return true;
    },
    getUnsubscribeCount: () => unsubscribeCount,
    toJSON() {
      return { endpoint: this.endpoint, keys: this.keys };
    },
  };
}

function createRegistration(scriptPath, subscription = null) {
  let unregisterCount = 0;
  let subscribeCount = 0;
  let currentSubscription = subscription;
  const registration = {
    scope: scriptPath === '/sw.js'
      ? 'https://kimbela.test/'
      : 'https://kimbela.test/static/',
    active: {
      scriptURL: `https://kimbela.test${scriptPath}`,
      state: 'activated',
    },
    pushManager: {
      async getSubscription() {
        return currentSubscription;
      },
      async subscribe() {
        subscribeCount += 1;
        currentSubscription = createSubscription('https://push.example/canonical');
        return currentSubscription;
      },
    },
    async unregister() {
      unregisterCount += 1;
      return true;
    },
    getUnregisterCount: () => unregisterCount,
    getSubscribeCount: () => subscribeCount,
    getSubscription: () => currentSubscription,
  };
  return registration;
}

function jsonResponse({ ok = true, status = 200, redirected = false } = {}) {
  return {
    ok,
    status,
    redirected,
    headers: { get: () => 'application/json' },
  };
}

function loadInitializer({ registrations = [], canonical, fetchImpl } = {}) {
  const listeners = {};
  const serviceWorkerListeners = {};
  const registerCalls = [];
  const fetchCalls = [];
  const canonicalRegistration = canonical || createRegistration('/sw.js');
  const serviceWorker = {
    addEventListener(type, handler) {
      serviceWorkerListeners[type] = serviceWorkerListeners[type] || [];
      serviceWorkerListeners[type].push(handler);
    },
    async getRegistrations() {
      return registrations;
    },
    async register(pathname, options) {
      registerCalls.push({ pathname, options });
      return canonicalRegistration;
    },
    ready: Promise.resolve(canonicalRegistration),
  };
  const navigator = {
    serviceWorker,
    userAgent: 'test browser',
    standalone: false,
  };
  const window = {
    navigator,
    location: { origin: 'https://kimbela.test' },
    matchMedia: () => ({ matches: false }),
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    addEventListener(type, handler) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(handler);
    },
  };
  const notification = {
    permission: 'granted',
    requestPermission: async () => 'granted',
  };
  window.Notification = notification;
  window.PushManager = function PushManager() {};
  const document = {
    querySelector: () => ({ getAttribute: () => 'csrf-token' }),
    createElement: () => ({
      style: {},
      querySelector: () => ({ addEventListener() {} }),
    }),
    head: { appendChild() {} },
    body: { appendChild() {} },
  };
  const context = {
    Buffer,
    Error,
    JSON,
    Notification: notification,
    Promise,
    Uint8Array,
    URL,
    alert() {},
    console: { error() {}, log() {} },
    document,
    fetch: async (url, options) => {
      fetchCalls.push({ url, options });
      return fetchImpl ? fetchImpl(url, options) : jsonResponse();
    },
    localStorage: { getItem: () => null, setItem() {} },
    navigator,
    window,
  };

  vm.runInNewContext(initSource, context, { filename: 'static/pwa_init.js' });

  return {
    canonicalRegistration,
    fetchCalls,
    listeners,
    registerCalls,
    window,
    async triggerLoad() {
      for (const listener of listeners.load || []) listener();
      return window._swRegistrationPromise;
    },
    async triggerServiceWorkerMessage(data) {
      for (const listener of serviceWorkerListeners.message || []) listener({ data });
      await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('clean install registers one canonical root-scoped worker', async () => {
  const runtime = loadInitializer();

  const registration = await runtime.triggerLoad();

  assert.equal(registration, runtime.canonicalRegistration);
  assert.equal(runtime.registerCalls.length, 1);
  assert.equal(runtime.registerCalls[0].pathname, '/sw.js');
  assert.equal(runtime.registerCalls[0].options.scope, '/');
});

test('legacy registration without push is removed before canonical registration', async () => {
  const legacy = createRegistration('/static/sw.js');
  const runtime = loadInitializer({ registrations: [legacy] });

  await runtime.triggerLoad();

  assert.equal(legacy.getUnregisterCount(), 1);
  assert.equal(runtime.registerCalls.length, 1);
  assert.equal(runtime.registerCalls[0].pathname, '/sw.js');
});

test('legacy push is replaced only after canonical subscription is stored', async () => {
  const legacySubscription = createSubscription('https://push.example/legacy');
  const legacy = createRegistration('/static/sw.js', legacySubscription);
  const canonical = createRegistration('/sw.js');
  const runtime = loadInitializer({ registrations: [legacy], canonical });

  await runtime.triggerLoad();

  assert.equal(canonical.getSubscribeCount(), 1);
  assert.deepEqual(runtime.fetchCalls.map(call => call.url), [
    '/api/pwa/subscribe',
    '/api/pwa/unsubscribe',
  ]);
  assert.equal(legacySubscription.getUnsubscribeCount(), 1);
  assert.equal(legacy.getUnregisterCount(), 1);
  assert.equal(canonical.getUnregisterCount(), 0);
});

test('failed canonical subscription storage retains the legacy registration', async () => {
  const legacySubscription = createSubscription('https://push.example/legacy');
  const legacy = createRegistration('/static/sw.js', legacySubscription);
  const canonical = createRegistration('/sw.js');
  const runtime = loadInitializer({
    registrations: [legacy],
    canonical,
    fetchImpl: async url => url === '/api/pwa/subscribe'
      ? jsonResponse({ ok: false, status: 500 })
      : jsonResponse(),
  });

  await assert.rejects(runtime.triggerLoad(), /could not be stored/);

  assert.equal(canonical.getSubscription().getUnsubscribeCount(), 1);
  assert.equal(canonical.getUnregisterCount(), 1);
  assert.equal(legacySubscription.getUnsubscribeCount(), 0);
  assert.equal(legacy.getUnregisterCount(), 0);
});

test('normal push enablement reuses an existing canonical subscription', async () => {
  const existing = createSubscription('https://push.example/existing');
  const canonical = createRegistration('/sw.js', existing);
  const runtime = loadInitializer({ registrations: [canonical], canonical });

  await runtime.triggerLoad();
  const enabled = await runtime.window.enablePushNotifications();

  assert.equal(enabled, true);
  assert.equal(canonical.getSubscribeCount(), 0);
  assert.equal(existing.getUnsubscribeCount(), 0);
  assert.deepEqual(runtime.fetchCalls.map(call => call.url), [
    '/api/pwa/subscribe',
    '/api/pwa/subscribe',
  ]);
});

test('existing canonical subscription is resynchronized on page load', async () => {
  const existing = createSubscription('https://push.example/resynchronize');
  const canonical = createRegistration('/sw.js', existing);
  const runtime = loadInitializer({ registrations: [canonical], canonical });

  await runtime.triggerLoad();

  assert.equal(runtime.fetchCalls.length, 1);
  assert.equal(runtime.fetchCalls[0].url, '/api/pwa/subscribe');
  assert.equal(JSON.parse(runtime.fetchCalls[0].options.body).endpoint, existing.endpoint);
});

test('subscription-change message resynchronizes replacement subscription', async () => {
  const runtime = loadInitializer();
  const replacement = createSubscription('https://push.example/replacement').toJSON();

  await runtime.triggerServiceWorkerMessage({
    type: 'PUSH_SUBSCRIPTION_CHANGED',
    subscription: replacement,
  });

  assert.equal(runtime.fetchCalls.length, 1);
  assert.equal(runtime.fetchCalls[0].url, '/api/pwa/subscribe');
  assert.equal(JSON.parse(runtime.fetchCalls[0].options.body).endpoint, replacement.endpoint);
});
