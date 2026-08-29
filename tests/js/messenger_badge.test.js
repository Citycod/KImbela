const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

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
  constructor({ hidden = false } = {}) {
    this.attributes = new Map();
    this.children = [];
    this.classList = new FakeClassList(hidden ? ['hidden'] : []);
    this.dataset = {};
    this.innerHTML = '';
    this.style = {};
    this.textContent = '';
  }
  addEventListener() {}
  appendChild(child) { this.children.push(child); return child; }
  focus() {}
  querySelector(selector) {
    if (selector === '#unreadMessagesBadge') {
      return this.children.find(child => child.id === 'unreadMessagesBadge') || null;
    }
    return null;
  }
  querySelectorAll() { return []; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) || null; }
}

function createRuntime({ initialUnread = 0, online = true } = {}) {
  let unreadCount = initialUnread;
  const requests = [];
  const socketHandlers = new Map();
  const navbarButton = new FakeElement();
  const navbarBadge = new FakeElement({ hidden: true });
  navbarBadge.id = 'unreadMessagesBadge';
  navbarButton.appendChild(navbarBadge);
  const sidebarButton = new FakeElement();
  const sidebarBadge = new FakeElement({ hidden: true });
  sidebarBadge.id = 'sidebarMsgBadge';
  sidebarBadge.style.display = 'none';
  const notificationBadge = new FakeElement({ hidden: true });
  notificationBadge.id = 'notificationBadge';
  notificationBadge.textContent = 'bell-sentinel';

  const elements = {
    friendsContainer: new FakeElement(),
    notificationBadge,
    openMessaging: navbarButton,
    openMessagingSidebar: sidebarButton,
    sidebarMsgBadge: sidebarBadge,
    unreadMessagesBadge: navbarBadge,
  };
  const document = {
    body: new FakeElement(),
    cookie: '',
    addEventListener() {},
    createElement() { return new FakeElement(); },
    getElementById(id) { return elements[id] || null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const socket = {
    connected: false,
    connect() {},
    disconnect() { this.connected = false; },
    emit() {},
    on(type, callback) { socketHandlers.set(type, callback); },
    trigger(type, payload) {
      if (type === 'connect') this.connected = true;
      const callback = socketHandlers.get(type);
      if (callback) callback(payload);
    },
  };
  const network = {
    isOnline() { return online; },
    onOffline() { return () => {}; },
    onOnline() { return () => {}; },
    requestJson(key, url) {
      requests.push(url);
      if (url === '/api/messaging/friends') {
        return Promise.resolve({ success: true, friends: [] });
      }
      if (url === '/api/messaging/unread-count') {
        return Promise.resolve({ unread_count: unreadCount });
      }
      if (url.startsWith('/api/messaging/mark-conversation-read/')) {
        unreadCount = 0;
        return Promise.resolve({ success: true, marked: 1 });
      }
      throw new Error(`Unexpected request: ${url}`);
    },
  };
  const window = {
    KimbelaNetwork: network,
    currentUserId: 1,
    defaultAvatar: '/static/default-avatar.png',
    location: { origin: 'https://kimbela.test', search: '' },
  };
  const context = {
    URLSearchParams,
    clearTimeout,
    console: { error() {}, log() {} },
    document,
    fetch: async () => { throw new Error('Unexpected direct fetch'); },
    io() { return socket; },
    setTimeout(callback) { callback(); return 1; },
    window,
  };

  vm.runInNewContext(messengerSource, context, {
    filename: 'static/assets/js/messenger.js',
  });

  async function flush() {
    await new Promise(resolve => setImmediate(resolve));
    await new Promise(resolve => setImmediate(resolve));
  }

  return {
    elements,
    Messenger: window.Messenger,
    requests,
    setUnread(value) { unreadCount = value; },
    socket,
    flush,
  };
}

test('zero unread hides both message badges without touching notification bell', () => {
  const runtime = createRuntime();

  runtime.Messenger.renderUnreadBadges(0);

  assert.equal(runtime.elements.unreadMessagesBadge.style.display, 'none');
  assert.equal(runtime.elements.sidebarMsgBadge.style.display, 'none');
  assert.equal(runtime.elements.notificationBadge.textContent, 'bell-sentinel');
  assert.equal(
    runtime.elements.openMessaging.getAttribute('aria-label'),
    'Messages, no unread messages',
  );
});

test('one and multiple unread counts render in desktop and mobile badges', () => {
  const runtime = createRuntime();

  runtime.Messenger.renderUnreadBadges(1);
  assert.equal(runtime.elements.unreadMessagesBadge.textContent, '1');
  assert.equal(runtime.elements.sidebarMsgBadge.textContent, '1');
  assert.equal(runtime.elements.unreadMessagesBadge.style.display, 'flex');
  assert.equal(runtime.elements.sidebarMsgBadge.style.display, 'inline-flex');

  runtime.Messenger.renderUnreadBadges(7);
  assert.equal(runtime.elements.unreadMessagesBadge.textContent, '7');
  assert.equal(runtime.elements.sidebarMsgBadge.textContent, '7');
});

test('ten or more unread messages use compact formatting', () => {
  const runtime = createRuntime();

  runtime.Messenger.renderUnreadBadges(10);
  assert.equal(runtime.elements.unreadMessagesBadge.textContent, '9+');
  assert.equal(runtime.elements.sidebarMsgBadge.textContent, '9+');
  assert.equal(runtime.elements.unreadMessagesBadge.dataset.unreadCount, '10');
});

test('initial unread refresh uses the existing unread endpoint', async () => {
  const runtime = createRuntime({ initialUnread: 4 });

  await runtime.Messenger.updateUnreadBadge();

  assert.equal(runtime.elements.unreadMessagesBadge.textContent, '4');
  assert.equal(runtime.elements.sidebarMsgBadge.textContent, '4');
  assert.deepEqual(runtime.requests, ['/api/messaging/unread-count']);
});

test('incoming message updates the visible badge and refreshes authoritatively', async () => {
  const runtime = createRuntime({ initialUnread: 0 });
  runtime.Messenger.init();
  await runtime.flush();
  runtime.setUnread(1);

  runtime.socket.trigger('new_message', {
    id: 20,
    sender_id: 2,
    receiver_id: 1,
    status: 'sent',
  });
  await runtime.flush();

  assert.equal(runtime.elements.unreadMessagesBadge.textContent, '1');
  assert.equal(runtime.elements.sidebarMsgBadge.textContent, '1');
  assert.equal(
    runtime.requests.filter(url => url === '/api/messaging/unread-count').length,
    2,
  );
});

test('conversation read completes before unread refresh and clears both badges', async () => {
  const runtime = createRuntime({ initialUnread: 3 });
  await runtime.Messenger.updateUnreadBadge();
  runtime.requests.length = 0;

  await runtime.Messenger.markConversationAsRead(2);

  assert.deepEqual(runtime.requests, [
    '/api/messaging/mark-conversation-read/2',
    '/api/messaging/unread-count',
  ]);
  assert.equal(runtime.elements.unreadMessagesBadge.style.display, 'none');
  assert.equal(runtime.elements.sidebarMsgBadge.style.display, 'none');
});
