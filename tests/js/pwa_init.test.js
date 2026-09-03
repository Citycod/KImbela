const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const initSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/pwa_init.js'),
  'utf8',
);
const dashboardSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/user_dashboard.html'),
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

function createLocalStorage(initialValues = {}, shouldThrow = false) {
  const values = new Map(Object.entries(initialValues));
  return {
    getItem(key) {
      if (shouldThrow) throw new Error('localStorage unavailable');
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      if (shouldThrow) throw new Error('localStorage unavailable');
      values.set(key, String(value));
    },
    removeItem(key) {
      if (shouldThrow) throw new Error('localStorage unavailable');
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
    this.hidden = false;
    this.selected = false;
    this.value = '';
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

  select() {
    this.selected = true;
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

function addInstallPageMarkup(document) {
  const root = document.createElement('main');
  root.id = 'kimbela-install-page';
  document.body.appendChild(root);

  ['checking', 'native', 'ios', 'installed', 'installing', 'fallback'].forEach(state => {
    const section = document.createElement('section');
    section.id = `install-page-${state}`;
    section.hidden = state !== 'checking';
    root.appendChild(section);
  });

  const fallbackMessage = document.createElement('p');
  fallbackMessage.id = 'install-page-fallback-message';
  document.getElementById('install-page-fallback').appendChild(fallbackMessage);

  const installButton = document.createElement('button');
  installButton.id = 'install-page-install-button';
  root.appendChild(installButton);

  const shareButton = document.createElement('button');
  shareButton.id = 'install-page-share-button';
  root.appendChild(shareButton);

  const linkField = document.createElement('input');
  linkField.id = 'install-page-link';
  linkField.value = 'https://kimbela.com/install';
  root.appendChild(linkField);

  const feedback = document.createElement('p');
  feedback.id = 'install-page-feedback';
  root.appendChild(feedback);
}

function addPushPromptMarkup(document) {
  const banner = document.createElement('div');
  banner.id = 'push-prompt-banner';
  banner.hidden = true;
  banner.style.display = 'none';
  banner.setAttribute('aria-hidden', 'true');
  document.body.appendChild(banner);
}

function loadInitializer({
  registrations = [],
  canonical,
  registerError = null,
  fetchImpl,
  userAgent = 'test browser',
  platform = 'Linux',
  maxTouchPoints = 0,
  standalone = false,
  displayModeStandalone = false,
  matchMediaAvailable = true,
  storageValues = {},
  storageThrows = false,
  documentReadyState = 'loading',
  installPage = false,
  pushPrompt = false,
  shareImpl,
  clipboardImpl,
  notificationPermission = 'granted',
  notificationRequestResult = 'granted',
  pushManagerSupported = true,
} = {}) {
  const listeners = {};
  const serviceWorkerListeners = {};
  const registerCalls = [];
  const fetchCalls = [];
  const mediaQueryListeners = [];
  const localStorage = createLocalStorage(storageValues, storageThrows);
  const timers = new Map();
  let nextTimerId = 1;
  const document = createDocument(documentReadyState);
  if (installPage) addInstallPageMarkup(document);
  if (pushPrompt) addPushPromptMarkup(document);
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
      if (registerError) throw registerError;
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
  if (shareImpl) navigator.share = shareImpl;
  if (clipboardImpl) navigator.clipboard = { writeText: clipboardImpl };
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
    setTimeout(handler, delay) {
      const timerId = nextTimerId;
      nextTimerId += 1;
      timers.set(timerId, { handler, delay });
      return timerId;
    },
    clearTimeout(timerId) {
      timers.delete(timerId);
    },
  };
  if (matchMediaAvailable) window.matchMedia = () => standaloneMediaQuery;
  let notificationPermissionRequests = 0;
  const notification = {
    permission: notificationPermission,
    async requestPermission() {
      notificationPermissionRequests += 1;
      this.permission = notificationRequestResult;
      return notificationRequestResult;
    },
  };
  window.Notification = notification;
  if (pushManagerSupported) window.PushManager = function PushManager() {};
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
    getPushPrompt: () => document.getElementById('push-prompt-banner'),
    getInstallPrompt: () => document.getElementById('kimbela-install-prompt'),
    getInstallPageState: () => {
      const root = document.getElementById('kimbela-install-page');
      return root ? root.dataset.installState : null;
    },
    getTimers: () => Array.from(timers.values()),
    async runTimers() {
      const pendingTimers = Array.from(timers.entries());
      timers.clear();
      for (const [, timer] of pendingTimers) timer.handler();
      await new Promise(resolve => setImmediate(resolve));
    },
    async triggerWindowEvent(type, event = {}) {
      const results = (listeners[type] || []).map(listener => listener(event));
      await Promise.all(results.filter(result => result && typeof result.then === 'function'));
      await new Promise(resolve => setImmediate(resolve));
    },
    async triggerDOMContentLoaded() {
      document.readyState = 'interactive';
      await this.triggerWindowEvent('DOMContentLoaded');
    },
    async triggerPageLoad() {
      await this.triggerDOMContentLoaded();
      await this.triggerLoad();
      await new Promise(resolve => setImmediate(resolve));
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
  const runtime = loadInitializer({
    registrations: [canonical],
    canonical,
    pushPrompt: true,
  });

  await runtime.triggerPageLoad();

  assert.equal(runtime.fetchCalls.length, 1);
  assert.equal(runtime.fetchCalls[0].url, '/api/pwa/subscribe');
  assert.equal(JSON.parse(runtime.fetchCalls[0].options.body).endpoint, existing.endpoint);
  assert.equal(runtime.getPushPrompt().hidden, true);
  assert.equal(runtime.getPushPrompt().style.display, 'none');
});

test('missing canonical subscription is recovered when permission is already granted', async () => {
  const canonical = createRegistration('/sw.js');
  const runtime = loadInitializer({ registrations: [canonical], canonical });

  await runtime.triggerLoad();

  assert.equal(canonical.getSubscribeCount(), 1);
  assert.equal(runtime.fetchCalls.length, 1);
  assert.equal(runtime.fetchCalls[0].url, '/api/pwa/subscribe');
  assert.equal(
    JSON.parse(runtime.fetchCalls[0].options.body).endpoint,
    'https://push.example/canonical',
  );
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('denied push permission does not subscribe, save, or request permission', async () => {
  const canonical = createRegistration('/sw.js');
  const runtime = loadInitializer({
    registrations: [canonical],
    canonical,
    notificationPermission: 'denied',
    pushPrompt: true,
  });

  await runtime.triggerPageLoad();
  await runtime.window.enablePushNotifications();
  await runtime.window.enablePushNotifications();

  assert.equal(canonical.getSubscribeCount(), 0);
  assert.equal(runtime.fetchCalls.length, 0);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
  assert.equal(runtime.getPushPrompt().hidden, true);
  assert.equal(runtime.getPushPrompt().style.display, 'none');
});

test('default push permission shows the dashboard CTA despite an old dismissal key', async () => {
  const runtime = loadInitializer({
    notificationPermission: 'default',
    pushPrompt: true,
    storageValues: { pushPromptDismissed: 'true' },
  });

  assert.equal(runtime.getPushPrompt().hidden, true);
  await runtime.triggerDOMContentLoaded();

  assert.equal(runtime.getPushPrompt().hidden, false);
  assert.equal(runtime.getPushPrompt().style.display, '');
  assert.equal(runtime.getPushPrompt().getAttribute('aria-hidden'), 'false');
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('unsupported push environment keeps the dashboard CTA hidden', async () => {
  const runtime = loadInitializer({
    notificationPermission: 'default',
    pushManagerSupported: false,
    pushPrompt: true,
  });

  await runtime.triggerDOMContentLoaded();

  assert.equal(runtime.getPushPrompt().hidden, true);
  assert.equal(runtime.getPushPrompt().style.display, 'none');
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('default permission prompts only on enable and successful subscription hides CTA', async () => {
  const canonical = createRegistration('/sw.js');
  const runtime = loadInitializer({
    registrations: [canonical],
    canonical,
    notificationPermission: 'default',
    notificationRequestResult: 'granted',
    pushPrompt: true,
  });

  await runtime.triggerPageLoad();
  assert.equal(runtime.getPushPrompt().hidden, false);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);

  const enabled = await runtime.window.enablePushNotifications();

  assert.equal(enabled, true);
  assert.equal(runtime.getNotificationPermissionRequests(), 1);
  assert.equal(canonical.getSubscribeCount(), 1);
  assert.deepEqual(runtime.fetchCalls.map(call => call.url), ['/api/pwa/subscribe']);
  assert.equal(runtime.getPushPrompt().hidden, true);
  assert.equal(runtime.getPushPrompt().style.display, 'none');
});

test('dashboard Turn On control calls the existing enable function and hides on success', async () => {
  const handlerStart = dashboardSource.indexOf('function handlePushEnableClick(btn)');
  const handlerEnd = dashboardSource.indexOf('</script>', handlerStart);
  assert.ok(handlerStart >= 0);
  assert.ok(handlerEnd > handlerStart);
  assert.match(
    dashboardSource,
    /onclick="handlePushEnableClick\(this\)">Turn On<\/button>/,
  );

  const banner = { style: { display: '' } };
  const button = { disabled: false, innerHTML: 'Turn On' };
  let enableCalls = 0;
  const context = {
    alert() {},
    document: {
      getElementById(id) {
        return id === 'push-prompt-banner' ? banner : null;
      },
    },
    enablePushNotifications() {
      enableCalls += 1;
      return Promise.resolve(true);
    },
  };
  vm.runInNewContext(
    dashboardSource.slice(handlerStart, handlerEnd),
    context,
    { filename: 'templates/user_dashboard.html' },
  );

  context.handlePushEnableClick(button);
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(enableCalls, 1);
  assert.equal(banner.style.display, 'none');
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

test('beforeinstallprompt waits for DOM and canonical worker readiness', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent();

  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  assert.equal(installEvent.getPreventDefaultCount(), 1);
  assert.equal(runtime.getInstallPrompt(), null);

  await runtime.triggerDOMContentLoaded();
  assert.equal(runtime.getInstallPrompt(), null);

  await runtime.triggerLoad();
  await new Promise(resolve => setImmediate(resolve));

  const prompt = runtime.getInstallPrompt();
  assert.ok(prompt);
  assert.match(prompt.textContent, /Install Kimbela/);
  assert.ok(prompt.querySelector('[data-action="install"]'));
});

test('failed canonical worker readiness does not expose install UI', async () => {
  const runtime = loadInitializer({
    registerError: new Error('essential precache failed'),
  });
  const installEvent = createBeforeInstallPromptEvent();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);
  await runtime.triggerDOMContentLoaded();

  await assert.rejects(runtime.triggerLoad(), /essential precache failed/);
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(installEvent.getPreventDefaultCount(), 1);
  assert.equal(runtime.getInstallPrompt(), null);
});

test('accepted native install shows a non-blocking installing state', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent('accepted');
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="install"]').click();

  assert.equal(installEvent.getPromptCount(), 1);
  assert.ok(runtime.getInstallPrompt());
  assert.equal(runtime.getInstallPrompt().getAttribute('role'), 'status');
  assert.match(runtime.getInstallPrompt().textContent, /Installing Kimbela…/);
  assert.match(runtime.getInstallPrompt().textContent, /continue using Kimbela/);
  assert.equal(runtime.getInstallPrompt().querySelector('[data-action="install"]'), null);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('delayed appinstalled never blocks the page or leaves permanent feedback', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent('accepted');
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="install"]').click();

  const feedback = runtime.getInstallPrompt();
  assert.equal(feedback.getAttribute('role'), 'status');
  assert.equal(feedback.querySelector('button'), null);
  assert.deepEqual(runtime.getTimers().map(timer => timer.delay), [20000]);

  await runtime.runTimers();
  assert.equal(runtime.getInstallPrompt(), null);
});

test('dismissed native prompt is hidden and snoozed locally', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent('dismissed');
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="install"]').click();

  assert.equal(installEvent.getPromptCount(), 1);
  assert.equal(runtime.getInstallPrompt(), null);
  assert.ok(Number(runtime.localStorage.getItem('kimbelaInstallDismissedAt')) > 0);
});

test('Not now snoozes install discovery without opening the native prompt', async () => {
  const runtime = loadInitializer();
  const firstEvent = createBeforeInstallPromptEvent();
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent('beforeinstallprompt', firstEvent);

  await runtime.getInstallPrompt().querySelector('[data-action="dismiss"]').click();
  const reloadedRuntime = loadInitializer({
    storageValues: runtime.localStorage.snapshot(),
  });
  await reloadedRuntime.triggerPageLoad();
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
  await runtime.triggerPageLoad();
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

  await runtime.triggerPageLoad();

  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.localStorage.getItem('iosInstallPromptDismissed'), null);
  assert.ok(Number(runtime.localStorage.getItem('kimbelaInstallDismissedAt')) > 0);
});

test('appinstalled shows success briefly and clears a prior dismissal', async () => {
  const runtime = loadInitializer();
  await runtime.triggerPageLoad();
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

  assert.ok(runtime.getInstallPrompt());
  assert.match(runtime.getInstallPrompt().textContent, /Kimbela installed successfully/);
  assert.equal(runtime.localStorage.getItem('kimbelaInstallDismissedAt'), null);
  await runtime.runTimers();
  assert.equal(runtime.getInstallPrompt(), null);
});

test('standalone display mode never shows native install UI', async () => {
  const runtime = loadInitializer({ displayModeStandalone: true });
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );

  assert.equal(runtime.getInstallPrompt(), null);
});

test('switching to standalone display mode hides visible install UI', async () => {
  const runtime = loadInitializer();
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );
  assert.ok(runtime.getInstallPrompt());

  await runtime.triggerStandaloneChange(true);

  assert.equal(runtime.getInstallPrompt(), null);
});

test('switching to standalone mode hides an in-progress install state', async () => {
  const runtime = loadInitializer();
  const installEvent = createBeforeInstallPromptEvent('accepted');
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);
  await runtime.getInstallPrompt().querySelector('[data-action="install"]').click();
  assert.match(runtime.getInstallPrompt().textContent, /Installing Kimbela/);

  await runtime.triggerStandaloneChange(true);

  assert.equal(runtime.getInstallPrompt(), null);
  assert.deepEqual(runtime.getTimers(), []);
});

test('iOS shows Home Screen instructions only outside standalone mode', async () => {
  const runtime = loadInitializer({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
  });

  await runtime.triggerPageLoad();

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
  await standaloneRuntime.triggerPageLoad();
  assert.equal(standaloneRuntime.getInstallPrompt(), null);
});

test('iPadOS desktop user agent receives iOS installation instructions', async () => {
  const runtime = loadInitializer({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)',
    platform: 'MacIntel',
    maxTouchPoints: 5,
  });

  await runtime.triggerPageLoad();

  assert.ok(runtime.getInstallPrompt());
  assert.ok(runtime.getInstallPrompt().querySelector('[data-action="ios-help"]'));
});

test('unsupported browsers show no install controls or permission prompt', async () => {
  const runtime = loadInitializer({ matchMediaAvailable: false });

  await runtime.triggerPageLoad();

  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('blocked localStorage does not break install discovery or dismissal', async () => {
  const runtime = loadInitializer({ storageThrows: true });
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent(
    'beforeinstallprompt',
    createBeforeInstallPromptEvent(),
  );

  assert.ok(runtime.getInstallPrompt());
  await runtime.getInstallPrompt().querySelector('[data-action="dismiss"]').click();
  assert.equal(runtime.getInstallPrompt(), null);
  assert.equal(runtime.getNotificationPermissionRequests(), 0);
});

test('dedicated install page uses the shared Chromium prompt controller', async () => {
  const runtime = loadInitializer({ installPage: true });
  const installEvent = createBeforeInstallPromptEvent('accepted');
  await runtime.triggerPageLoad();

  assert.equal(runtime.getInstallPageState(), 'fallback');
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);
  assert.equal(runtime.getInstallPageState(), 'native');

  await runtime.document.getElementById('install-page-install-button').click();
  assert.equal(installEvent.getPromptCount(), 1);
  assert.equal(runtime.getInstallPageState(), 'installing');
  assert.equal(runtime.getNotificationPermissionRequests(), 0);

  await runtime.triggerWindowEvent('appinstalled');
  assert.equal(runtime.getInstallPageState(), 'installed');
});

test('dedicated public install page does not make a subscription API request', async () => {
  const existing = createSubscription('https://push.example/install-page');
  const canonical = createRegistration('/sw.js', existing);
  const runtime = loadInitializer({ installPage: true, registrations: [canonical], canonical });

  await runtime.triggerPageLoad();

  assert.deepEqual(runtime.fetchCalls, []);
});

test('dedicated install page handles a dismissed native prompt', async () => {
  const runtime = loadInitializer({ installPage: true });
  const installEvent = createBeforeInstallPromptEvent('dismissed');
  await runtime.triggerPageLoad();
  await runtime.triggerWindowEvent('beforeinstallprompt', installEvent);

  await runtime.document.getElementById('install-page-install-button').click();

  assert.equal(runtime.getInstallPageState(), 'fallback');
  assert.ok(Number(runtime.localStorage.getItem('kimbelaInstallDismissedAt')) > 0);
});

test('dedicated install page shows iPhone and iPadOS instructions without a fake CTA', async () => {
  const iphone = loadInitializer({
    installPage: true,
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
  });
  await iphone.triggerPageLoad();

  const ipad = loadInitializer({
    installPage: true,
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)',
    platform: 'MacIntel',
    maxTouchPoints: 5,
  });
  await ipad.triggerPageLoad();

  assert.equal(iphone.getInstallPageState(), 'ios');
  assert.equal(ipad.getInstallPageState(), 'ios');
  assert.equal(
    iphone.document.getElementById('install-page-native').hidden,
    true,
  );
});

test('dedicated install page detects standalone and unsupported states', async () => {
  const installed = loadInitializer({ installPage: true, displayModeStandalone: true });
  await installed.triggerPageLoad();

  const unsupported = loadInitializer({ installPage: true, matchMediaAvailable: false });
  await unsupported.triggerPageLoad();

  assert.equal(installed.getInstallPageState(), 'installed');
  assert.equal(installed.document.getElementById('install-page-native').hidden, true);
  assert.equal(unsupported.getInstallPageState(), 'fallback');
});

test('dedicated install page shares with Web Share API when available', async () => {
  const sharedPayloads = [];
  const runtime = loadInitializer({
    installPage: true,
    shareImpl: async payload => sharedPayloads.push(payload),
  });
  await runtime.triggerPageLoad();

  await runtime.document.getElementById('install-page-share-button').click();

  assert.equal(sharedPayloads.length, 1);
  assert.equal(sharedPayloads[0].url, 'https://kimbela.com/install');
  assert.match(
    runtime.document.getElementById('install-page-feedback').textContent,
    /Install link shared/,
  );
});

test('dedicated install page falls back to clipboard sharing', async () => {
  const copiedValues = [];
  const runtime = loadInitializer({
    installPage: true,
    clipboardImpl: async value => copiedValues.push(value),
  });
  await runtime.triggerPageLoad();

  await runtime.document.getElementById('install-page-share-button').click();

  assert.deepEqual(copiedValues, ['https://kimbela.com/install']);
  assert.match(
    runtime.document.getElementById('install-page-feedback').textContent,
    /Install link copied/,
  );
});
