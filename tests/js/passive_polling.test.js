const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/passive_polling.js'),
  'utf8',
);

class SharedStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

class FakeDocument {
  constructor() {
    this.hidden = false;
    this.visibilityState = 'visible';
    this.listeners = new Map();
  }
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(callback);
  }
  removeEventListener(type, callback) {
    this.listeners.get(type)?.delete(callback);
  }
  setHidden(hidden) {
    this.hidden = hidden;
    this.visibilityState = hidden ? 'hidden' : 'visible';
    this.listeners.get('visibilitychange')?.forEach(callback => callback());
  }
}

function createBroadcastFactory() {
  const channels = new Map();
  return class FakeBroadcastChannel {
    constructor(name) {
      this.name = name;
      this.listeners = new Set();
      if (!channels.has(name)) channels.set(name, new Set());
      channels.get(name).add(this);
    }
    addEventListener(type, callback) {
      if (type === 'message') this.listeners.add(callback);
    }
    postMessage(data) {
      channels.get(this.name)?.forEach(channel => {
        if (channel !== this) {
          channel.listeners.forEach(callback => callback({ data }));
        }
      });
    }
    close() { channels.get(this.name)?.delete(this); }
  };
}

function createTab(storage, BroadcastChannel, userId = 7) {
  const document = new FakeDocument();
  const windowListeners = new Map();
  const intervals = [];
  const clearedIntervals = [];
  const window = {
    BroadcastChannel,
    currentUserId: userId,
    localStorage: storage,
    addEventListener(type, callback) {
      if (!windowListeners.has(type)) windowListeners.set(type, new Set());
      windowListeners.get(type).add(callback);
    },
    removeEventListener(type, callback) {
      windowListeners.get(type)?.delete(callback);
    },
    setInterval(callback, delay) {
      const timer = { callback, delay };
      intervals.push(timer);
      return timer;
    },
    clearInterval(timer) { clearedIntervals.push(timer); },
  };
  const context = { document, window };
  vm.runInNewContext(source, context, { filename: 'passive_polling.js' });
  return {
    api: window.KimbelaPassivePolling,
    clearedIntervals,
    document,
    intervals,
  };
}

test('only one visible tab leads passive polling and coordination stays lightweight', () => {
  const storage = new SharedStorage();
  const BroadcastChannel = createBroadcastFactory();
  const first = createTab(storage, BroadcastChannel);
  const second = createTab(storage, BroadcastChannel);

  assert.equal(first.api.isLeader(), true);
  assert.equal(second.api.isLeader(), false);
  assert.equal(first.intervals.length, 1);
  assert.equal(second.intervals.length, 1);
  assert.equal(first.intervals[0].delay, 15000);
  assert.equal(second.intervals[0].delay, 15000);
});

test('leader release and hidden-tab transition hand polling to another tab', () => {
  const storage = new SharedStorage();
  const BroadcastChannel = createBroadcastFactory();
  const first = createTab(storage, BroadcastChannel);
  const second = createTab(storage, BroadcastChannel);

  assert.equal(first.api.isLeader(), true);
  assert.equal(second.api.isLeader(), false);
  first.document.setHidden(true);

  assert.equal(first.api.isLeader(), false);
  assert.equal(second.api.isLeader(), true);
  assert.equal(first.clearedIntervals.length, 1);

  second.api.destroy();
  first.document.setHidden(false);
  assert.equal(first.api.isLeader(), true);
});

test('leader state is shared without a second database poll', () => {
  const storage = new SharedStorage();
  const BroadcastChannel = createBroadcastFactory();
  const first = createTab(storage, BroadcastChannel);
  const second = createTab(storage, BroadcastChannel);
  let received = null;

  first.api.isLeader();
  second.api.subscribe('notification-count', payload => { received = payload; });
  first.api.publish('notification-count', { count: 4 });

  assert.deepEqual(JSON.parse(JSON.stringify(received)), { count: 4 });
});

test('cross-tab impression claim suppresses duplicates until its bounded TTL', () => {
  const storage = new SharedStorage();
  const BroadcastChannel = createBroadcastFactory();
  const first = createTab(storage, BroadcastChannel);
  const second = createTab(storage, BroadcastChannel);

  assert.equal(first.api.claimOnce('ad-impression:12', 1800000), true);
  assert.equal(second.api.claimOnce('ad-impression:12', 1800000), false);
  assert.equal(first.api.claimOnce('ad-impression:13', 1800000), true);
});
