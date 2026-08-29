const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const networkSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/network_resilience.js'),
  'utf8',
);
const messengerSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/messenger.js'),
  'utf8',
);

class FakeClassList {
  constructor(initial = []) {
    this.values = new Set(initial);
  }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
}

class FakeElement {
  constructor() {
    this.classList = new FakeClassList();
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.innerHTML = '';
    this.textContent = '';
  }
  addEventListener() {}
  appendChild(child) { this.children.push(child); return child; }
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  setAttribute() {}
}

function createRuntime({ online = true } = {}) {
  const windowHandlers = new Map();
  const fetchCalls = [];
  const navigator = { onLine: online };
  const elements = {
    friendsContainer: new FakeElement(),
    openMessaging: new FakeElement(),
  };
  const document = {
    readyState: 'complete',
    body: new FakeElement(),
    cookie: '',
    addEventListener() {},
    createElement() { return new FakeElement(); },
    getElementById(id) { return elements[id] || null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const socketHandlers = new Map();
  const socket = {
    connected: false,
    connectCalls: 0,
    disconnectCalls: 0,
    emit() {},
    on(type, callback) { socketHandlers.set(type, callback); },
    connect() { this.connectCalls += 1; },
    disconnect() { this.connected = false; this.disconnectCalls += 1; },
    trigger(type, payload) {
      if (type === 'connect') this.connected = true;
      const callback = socketHandlers.get(type);
      if (callback) callback(payload);
    },
  };
  const ioOptions = [];
  const window = {
    currentUserId: 1,
    defaultAvatar: '/static/default-avatar.png',
    location: { origin: 'https://kimbela.test', search: '' },
    addEventListener(type, callback) {
      if (!windowHandlers.has(type)) windowHandlers.set(type, []);
      windowHandlers.get(type).push(callback);
    },
  };
  const context = {
    URLSearchParams,
    clearTimeout,
    console: { error() {}, log() {} },
    document,
    fetch: async (url) => {
      fetchCalls.push(url);
      if (url === '/api/messaging/friends') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ success: true, friends: [] }),
        };
      }
      if (url === '/api/messaging/unread-count') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ unread_count: 0 }),
        };
      }
      throw new Error(`Unexpected request: ${url}`);
    },
    io(options) { ioOptions.push(options); return socket; },
    navigator,
    setTimeout(callback) { callback(); return 1; },
    window,
  };

  vm.runInNewContext(networkSource, context);
  vm.runInNewContext(messengerSource, context);

  async function flush() {
    await new Promise(resolve => setImmediate(resolve));
    await new Promise(resolve => setImmediate(resolve));
  }
  function dispatch(type) {
    (windowHandlers.get(type) || []).forEach(callback => callback());
  }

  return {
    dispatch,
    fetchCalls,
    ioOptions,
    navigator,
    socket,
    flush,
    Messenger: window.Messenger,
  };
}

test('offline initialization makes no friends or unread requests', async () => {
  const runtime = createRuntime({ online: false });

  runtime.Messenger.init();
  await runtime.flush();

  assert.deepEqual(runtime.fetchCalls, []);
  assert.equal(runtime.ioOptions.length, 0);
});

test('failed Socket.IO connections do not repeat messaging bootstrap', async () => {
  const runtime = createRuntime();

  runtime.Messenger.init();
  await runtime.flush();
  runtime.socket.trigger('connect_error', new Error('offline'));
  runtime.socket.trigger('connect_error', new Error('offline'));
  await runtime.flush();

  assert.equal(
    runtime.fetchCalls.filter(url => url === '/api/messaging/friends').length,
    1,
  );
  assert.equal(
    runtime.fetchCalls.filter(url => url === '/api/messaging/unread-count').length,
    1,
  );
  assert.equal(runtime.ioOptions[0].reconnectionDelayMax, 10000);
});

test('first successful connection after failures refreshes bootstrap once', async () => {
  const runtime = createRuntime();
  runtime.Messenger.init();
  await runtime.flush();
  runtime.fetchCalls.length = 0;

  runtime.socket.trigger('connect_error', new Error('unstable network'));
  runtime.socket.trigger('connect_error', new Error('unstable network'));
  runtime.socket.trigger('connect');
  runtime.socket.trigger('connect');
  await runtime.flush();

  assert.equal(
    runtime.fetchCalls.filter(url => url === '/api/messaging/friends').length,
    1,
  );
  assert.equal(
    runtime.fetchCalls.filter(url => url === '/api/messaging/unread-count').length,
    1,
  );
});

test('successful recovery refreshes friends and unread state once', async () => {
  const runtime = createRuntime();
  runtime.Messenger.init();
  await runtime.flush();
  runtime.socket.trigger('connect');
  await runtime.flush();
  runtime.fetchCalls.length = 0;

  runtime.navigator.onLine = false;
  runtime.dispatch('offline');
  runtime.navigator.onLine = true;
  runtime.dispatch('online');
  runtime.socket.trigger('connect');
  runtime.socket.trigger('connect');
  await runtime.flush();

  assert.equal(
    runtime.fetchCalls.filter(url => url === '/api/messaging/friends').length,
    1,
  );
  assert.equal(
    runtime.fetchCalls.filter(url => url === '/api/messaging/unread-count').length,
    1,
  );
});
