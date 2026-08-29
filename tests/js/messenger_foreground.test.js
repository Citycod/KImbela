const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const messengerSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/messenger.js'),
  'utf8',
);
const foregroundSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/foreground_push.js'),
  'utf8',
);

class FakeClassList {
  constructor(values = []) { this.values = new Set(values); }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
}

class FakeElement {
  constructor({ hidden = false } = {}) {
    this.children = [];
    this.classList = new FakeClassList(hidden ? ['hidden'] : []);
    this.className = '';
    this.style = {};
    this.textContent = '';
  }
  addEventListener() {}
  appendChild(child) { this.children.push(child); child.parent = this; return child; }
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
  }
  setAttribute() {}
}

function createRuntime() {
  const body = new FakeElement();
  const elements = {
    chatArea: new FakeElement({ hidden: true }),
    chatAvatar: new FakeElement(),
    chatInput: new FakeElement(),
    chatMessages: new FakeElement(),
    chatName: new FakeElement(),
    friendList: new FakeElement(),
    messengerPopup: new FakeElement({ hidden: true }),
  };
  const document = {
    body,
    cookie: '',
    visibilityState: 'visible',
    addEventListener() {},
    createElement() { return new FakeElement(); },
    getElementById(id) { return elements[id] || null; },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === '.foreground-push-toast') {
        return body.children.filter(child => child.className.includes('foreground-push-toast'));
      }
      return [];
    },
  };
  const serviceWorkerHandlers = new Map();
  const navigator = {
    onLine: true,
    serviceWorker: {
      addEventListener(type, callback) { serviceWorkerHandlers.set(type, callback); },
    },
  };
  const window = {
    currentUserId: 1,
    defaultAvatar: '/static/default-avatar.png',
    location: { origin: 'https://kimbela.test', search: '' },
  };
  const context = {
    URL,
    URLSearchParams,
    clearTimeout() {},
    console: { error() {}, log() {} },
    document,
    fetch: async url => {
      if (url.startsWith('/api/messaging/messages/')) {
        return { ok: true, json: async () => ({ messages: [], has_more: false }) };
      }
      throw new Error(`Unexpected request: ${url}`);
    },
    navigator,
    setTimeout() { return 1; },
    window,
  };

  vm.runInNewContext(foregroundSource, context, {
    filename: 'static/assets/js/foreground_push.js',
  });
  vm.runInNewContext(messengerSource, context, {
    filename: 'static/assets/js/messenger.js',
  });

  return { body, document, elements, serviceWorkerHandlers, window };
}

test('visible app shows lightweight feedback for message, social, or birthday push', () => {
  const runtime = createRuntime();

  assert.equal(runtime.window.KimbelaForegroundPush.show({
    title: 'New comment',
    body: 'Someone commented on your post.',
    url: '/post/example#comment-2',
  }), true);

  assert.equal(runtime.body.children.length, 1);
  assert.equal(runtime.body.children[0].children[0].textContent, 'New comment');
  assert.equal(
    runtime.body.children[0].children[1].textContent,
    'Someone commented on your post.',
  );
});

test('backgrounded document does not show extra foreground feedback', () => {
  const runtime = createRuntime();
  runtime.document.visibilityState = 'hidden';

  assert.equal(runtime.window.KimbelaForegroundPush.show({
    title: 'New message',
    body: 'Hello',
    url: '/user_dashboard?chat=13',
  }), false);
  assert.equal(runtime.body.children.length, 0);
});

test('exact open conversation suppresses only the extra toast', async () => {
  const runtime = createRuntime();
  runtime.elements.messengerPopup.classList.remove('hidden');
  runtime.window.Messenger.openChat(13, 'Sender', '/avatar.png');

  assert.equal(runtime.window.Messenger.isExactActiveConversation(
    '/user_dashboard?chat=13',
  ), true);
  assert.equal(runtime.window.KimbelaForegroundPush.show({
    title: 'New message',
    body: 'Already visible',
    url: '/user_dashboard?chat=13',
  }), false);
  assert.equal(runtime.body.children.length, 0);
});

test('different conversation still shows foreground feedback', () => {
  const runtime = createRuntime();
  runtime.elements.messengerPopup.classList.remove('hidden');
  runtime.window.Messenger.openChat(13, 'Current friend', '/avatar.png');

  assert.equal(runtime.window.KimbelaForegroundPush.show({
    title: 'New message',
    body: 'From someone else',
    url: '/user_dashboard?chat=14',
  }), true);
  assert.equal(runtime.body.children.length, 1);
});

test('service-worker foreground message handler is registered without changing push', () => {
  assert.match(
    foregroundSource,
    /serviceWorker\.addEventListener\('message'/,
  );
  assert.doesNotMatch(
    foregroundSource,
    /registration\.showNotification|pushManager\.subscribe/,
  );
  assert.match(messengerSource, /KimbelaForegroundPush\.setSuppressor/);
});
