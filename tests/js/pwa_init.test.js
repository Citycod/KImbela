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

function createLocalStorage(initialValues = {}) {
  const values = new Map(Object.entries(initialValues));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
    snapshot() {
      return Object.fromEntries(values);
    },
  };
}

function elementMatches(element, selector) {
  if (selector.startsWith('#')) return element.id === selector.slice(1);
  if (selector.startsWith('.')) {
    return element.className.split(/\s+/).includes(selector.slice(1));
  }

  const dataAction = selector.match(/^\[data-action="([^"]+)"\]$/);
  if (dataAction) return element.dataset.action === dataAction[1];

  return element.tagName.toLowerCase() === selector.toLowerCase();
}

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.style = {};
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.className = '';
    this.id = '';
    this.disabled = false;
    this.focused = false;
    this._textContent = '';
  }

  set textContent(value) {
    this._textContent = String(value);
    this.children = [];
  }

  get textContent() {
    return this._textContent + this.children.map(child => child.textContent).join('');
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] || null;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }

  addEventListener(type, handler) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(handler);
  }

  querySelector(selector) {
    for (const child of this.children) {
      if (elementMatches(child, selector)) return child;
      const descendant = child.querySelector(selector);
      if (descendant) return descendant;
    }
    return null;
  }

  async click() {
    const results = (this.listeners.click || []).map(handler => handler({ target: this }));
    await Promise.all(results.filter(result => result && typeof result.then === 'function'));
  }

  focus() {
    this.focused = true;
  }
}

function createDocument(readyState = 'loading') {
  const head = new FakeElement('head');
  const body = new FakeElement('body');
  return {
    readyState,
    head,
    body,
    createElement(tagName) {
      return new FakeElement(tagName);
    },
    getElementById(id) {
      return head.querySelector(`#${id}`) || body.querySelector(`#${id}`);
    },
    querySelector(selector) {
      if (selector === 'meta[name="csrf-token"]') {
        return { getAttribute: () => 'csrf-token' };
      }
      return head.querySelector(selector) || body.querySelector(selector);
    },
  };
}

function loadInitializer({
  registrations = [],
  canonical,
  fetchImpl,
  userAgent = 'test browser',
  platform = 'Linux',
  maxTouchPoints = 0,
  standalone = false,
  displayModeStandalone = false,
  matchMediaAvailable = true,
  storageValues = {},
  documentReadyState = 'loading',
} = {}) {
  const listeners = {};
  const serviceWorkerListeners = {};
  const registerCalls = [];
  const fetchCalls = [];
  const mediaQueryListeners = [];
  const localStorage = createLocalStorage(storageValues);
  const document = createDocument(documentReadyState);
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
    userAgent,
    platform,
    maxTouchPoints,
    standalone,
  };
  const standaloneMediaQuery = {
    matches: displayModeStandalone,
    addEventListener(type, handler) {
      if (type === 'change') mediaQueryListeners.push(handler);
    },
  };
  const window = {
    navigator,
    location: { origin: 'https://kimbela.test' },
    localStorage,
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    addEventListener(type, handler) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(handler);
    },
  };
  if (matchMediaAvailable) window.matchMedia = () => standaloneMediaQuery;
  let notificationPermissionRequests = 0;
  const notification = {
    permission: 'granted',
    async requestPermission() {
      notificationPermissionRequests += 1;
      return 'granted';
    },
  };
  window.Notification = notification;
  window.PushManager = function PushManager() {};
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
    localStorage,
    navigator,
    window,
  };

  vm.runInNewContext(initSource, context, { filename: 'static/pwa_init.js' });

  return {
    canonicalRegistration,
    fetchCalls,
    listeners,
    localStorage,
    registerCalls,
    window,
    document,
    getNotificationPermissionRequests: () => notificationPermissionRequests,
    getInstallPrompt: () => document.getElementById('kimbela-install-prompt'),
    async triggerWindowEvent(type, event = {}) {
      const results = (listeners[type] || []).map(listener => listener(event));
      await Promise.all(results.filter(result => result && typeof result.then === 'function'));
      await new Promise(resolve => setImmediate(resolve));
    },
    async triggerDOMContentLoaded() {
      document.readyState = 'interactive';
      await this.triggerWindowEvent('DOMContentLoaded');
    },
    async triggerStandaloneChange(matches) {
      standaloneMediaQuery.matches = matches;
      const results = mediaQueryListeners.map(listener => listener({ matches }));
      await Promise.all(results.filter(result => result && typeof result.then === 'function'));
    },
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

function createBeforeInstallPromptEvent(outcome = 'accepted') {
  let preventDefaultCount = 0;
  let promptCount = 0;
  return {
    preventDefault() {
      preventDefaultCount += 1;
    },
    async prompt() {
      promptCount += 1;
    },
    userChoice: Promise.resolve({ outcome }),
    getPreventDefaultCount: () => preventDefaultCount,
    getPromptCount: () => promptCount,
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

test('beforeinstallprompt is captured and shown after the DOM is ready', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent();

  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  assert.equal(installEvent.getPreventDefaultCount(), 1);
  assert.equal(runtime.getInstallPrompt(), null);

  await runtime.triggerDOMContentLoaded();

  const prompt = runtime.getInstallPrompt();
  assert.ok(prompt);
  assert.match(prompt.textContent, /Install Kimbela/);
  assert.ok(prompt.querySelector('[data-action="install"]'));
});

test('Install invokes the native prompt and an accepted install hides the UI', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent('accepted');
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="install"]').click();

  assert.equal(installEvent.getPromptCount(), 1);
  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('dismissed native prompt is hidden and snoozed locally', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent('dismissed');
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="install"]').click();

  assert.equal(installEvent.getPromptCount(), 1);
  assert.equal(runtime.getInstallPrompt(), null);
  assert.ok(Number(runtime.localStorage.getItem('kimbelaInstallDismissedAt')) > 0);
});

test('Not now snoozes install discovery without opening the native prompt', async () => {
  const runtime = loadInitializer();
  const firstEvent = createBeforeInstallPromptEvent();
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent('beforeinstallprompt', firstEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="dismiss"]').click();
  const reloadedRuntime = loadInitializer({
    storageValues: runtime.localStorage.snapshot(),
  });
  await reloadedRuntime.triggerDOMContentLoaded();
  await reloadedRuntime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );

  assert.equal(firstEvent.getPromptCount(), 0);
  assert.equal(runtime.getInstallPrompt(), null);
  assert.ok(Number(runtime.localStorage.getItem('kimbelaInstallDismissedAt')) > 0);
  assert.equal(reloadedRuntime.getInstallPrompt(), null);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('expired local dismissal permits install discovery again', async () => {
  const expired = Date.now() - (15 * 24 * 60 * 60 * 1000);
  const runtime = loadInitializer({
    storageValues: { kimbelaInstallDismissedAt: String(expired) },
  });
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );

  assert.ok(runtime.getInstallPrompt());
  assert.equal(runtime.localStorage.getItem('kimbelaInstallDismissedAt'), null);
});

test('legacy permanent iOS dismissal is migrated to the temporary snooze', async () => {
  const runtime = loadInitializer({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
    storageValues: { iosInstallPromptDismissed: 'true' },
  });

  await runtime.triggerDOMContentLoaded();

  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.localStorage.getItem('iosInstallPromptDismissed'), null);
  assert.ok(Number(runtime.localStorage.getItem('kimbelaInstallDismissedAt')) > 0);
});

test('appinstalled hides install UI and clears a prior dismissal', async () => {
  const runtime = loadInitializer();
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );
  assert.ok(runtime.getInstallPrompt());
  runtime.localStorage.setItem('kimbelaInstallDismissedAt', String(Date.now()));

  await runtime.triggerWindowEvent('appinstalled');
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );

  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.localStorage.getItem('kimbelaInstallDismissedAt'), null);
});

test('standalone display mode never shows native install UI', async () => {
  const runtime = loadInitializer({ displayModeStandalone: true });
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );

  assert.equal(runtime.getInstallPrompt(), null);
});

test('switching to standalone display mode hides visible install UI', async () => {
  const runtime = loadInitializer();
  await runtime.triggerDOMContentLoaded();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );
  assert.ok(runtime.getInstallPrompt());

  await runtime.triggerStandaloneChange(true);

  assert.equal(runtime.getInstallPrompt(), null);
});

test('iOS shows Home Screen instructions only outside standalone mode', async () => {
  const runtime = loadInitializer({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
  });

  await runtime.triggerDOMContentLoaded();

  const prompt = runtime.getInstallPrompt();
  assert.ok(prompt);
  assert.match(prompt.textContent, /Tap the Share button/);
  assert.match(prompt.textContent, /Choose “Add to Home Screen”/);
  assert.match(prompt.textContent, /Tap Add/);
  assert.ok(prompt.querySelector('[data-action="ios-help"]'));
  assert.equal(prompt.querySelector('[data-action="install"]'), null);

  const standaloneRuntime = loadInitializer({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
    standalone: true,
  });
  await standaloneRuntime.triggerDOMContentLoaded();
  assert.equal(standaloneRuntime.getInstallPrompt(), null);
});

test('iPadOS desktop user agent receives iOS installation instructions', async () => {
  const runtime = loadInitializer({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)',
    platform: 'MacIntel',
    maxTouchPoints: 5,
  });

  await runtime.triggerDOMContentLoaded();

  assert.ok(runtime.getInstallPrompt());
  assert.ok(runtime.getInstallPrompt().querySelector('[data-action="ios-help"]'));
});

test('unsupported browsers show no install controls or permission prompt', async () => {
  const runtime = loadInitializer({ matchMediaAvailable: false });

  await runtime.triggerDOMContentLoaded();

  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});
