const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/network_resilience.js'),
  'utf8',
);

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(...values) {
    values.forEach(value => this.values.add(value));
  }

  remove(...values) {
    values.forEach(value => this.values.delete(value));
  }

  contains(value) {
    return this.values.has(value);
  }
}

function createRuntime({ online = true, fetchImpl = null } = {}) {
  const eventHandlers = new Map();
  const elements = new Map();
  const fetchCalls = [];
  const navigator = { onLine: online };
  const document = {
    readyState: 'complete',
    body: {
      appendChild(element) {
        elements.set(element.id, element);
      },
    },
    addEventListener() {},
    createElement() {
      return {
        id: '',
        className: '',
        classList: new FakeClassList(),
        style: {},
        setAttribute() {},
        textContent: '',
      };
    },
    getElementById(id) {
      return elements.get(id) || null;
    },
  };
  const window = {
    addEventListener(type, callback) {
      if (!eventHandlers.has(type)) eventHandlers.set(type, []);
      eventHandlers.get(type).push(callback);
    },
  };
  const context = {
    clearTimeout,
    console: { error() {} },
    document,
    fetch: fetchImpl || (async (url) => {
      fetchCalls.push(url);
      return {
        ok: true,
        status: 200,
        json: async () => ({ url }),
      };
    }),
    navigator,
    setTimeout,
    window,
  };

  vm.runInNewContext(source, context, {
    filename: 'static/assets/js/network_resilience.js',
  });

  function dispatch(type) {
    (eventHandlers.get(type) || []).forEach(callback => callback());
  }

  return { dispatch, fetchCalls, navigator, network: window.KimbelaNetwork };
}

test('concurrent requests with one key share a single fetch', async () => {
  const runtime = createRuntime();

  const [first, second] = await Promise.all([
    runtime.network.requestJson('friends', '/api/messaging/friends'),
    runtime.network.requestJson('friends', '/api/messaging/friends'),
  ]);

  assert.deepEqual(runtime.fetchCalls, ['/api/messaging/friends']);
  assert.equal(first.url, '/api/messaging/friends');
  assert.equal(second.url, '/api/messaging/friends');
});

test('offline state blocks requests and emits each state transition once', async () => {
  const runtime = createRuntime();
  let offlineEvents = 0;
  let onlineEvents = 0;
  runtime.network.onOffline(() => { offlineEvents += 1; });
  runtime.network.onOnline(() => { onlineEvents += 1; });

  runtime.navigator.onLine = false;
  runtime.dispatch('offline');
  runtime.dispatch('offline');

  await assert.rejects(
    runtime.network.requestJson('unread', '/api/messaging/unread-count'),
    error => error.kind === 'offline',
  );
  assert.deepEqual(runtime.fetchCalls, []);
  assert.equal(offlineEvents, 1);

  runtime.navigator.onLine = true;
  runtime.dispatch('online');
  runtime.dispatch('online');
  await runtime.network.requestJson('unread', '/api/messaging/unread-count');
  assert.deepEqual(runtime.fetchCalls, ['/api/messaging/unread-count']);
  assert.equal(onlineEvents, 1);
});

test('comment feedback distinguishes offline, network, and server failures', () => {
  const runtime = createRuntime();

  assert.equal(
    runtime.network.commentFeedback({ kind: 'offline' }),
    "You're offline. Reconnect to load comments.",
  );
  assert.equal(
    runtime.network.commentFeedback({ kind: 'network' }),
    'Connection lost. Reconnect and try loading comments again.',
  );
  assert.equal(
    runtime.network.commentFeedback({ kind: 'server' }),
    'Failed to load comments',
  );
});

test('transport failure and HTTP failure retain distinct comment behavior', async () => {
  const networkRuntime = createRuntime({
    fetchImpl: async () => { throw new TypeError('Failed to fetch'); },
  });
  await assert.rejects(
    networkRuntime.network.requestJson('comments', '/get_comments/1'),
    error => error.kind === 'network' &&
      networkRuntime.network.commentFeedback(error).includes('Reconnect'),
  );

  const serverRuntime = createRuntime({
    fetchImpl: async () => ({
      ok: false,
      status: 500,
      json: async () => ({}),
    }),
  });
  await assert.rejects(
    serverRuntime.network.requestJson('comments', '/get_comments/1'),
    error => error.kind === 'server' &&
      serverRuntime.network.commentFeedback(error) === 'Failed to load comments',
  );
});
