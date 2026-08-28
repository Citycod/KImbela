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

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
  }

  contains(value) {
    return this.values.has(value);
  }
}

class FakeElement {
  constructor({ hidden = false } = {}) {
    this.classList = new FakeClassList(hidden ? ['hidden'] : []);
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.innerHTML = '';
    this.textContent = '';
    this.src = '';
    this.scrollHeight = 0;
    this.scrollTop = 0;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener() {}
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

function loadMessenger({ search, friends }) {
  const fetchCalls = [];
  const elements = {
    messengerPopup: new FakeElement({ hidden: true }),
    friendsContainer: new FakeElement(),
    friendList: new FakeElement(),
    chatArea: new FakeElement({ hidden: true }),
    chatName: new FakeElement(),
    chatAvatar: new FakeElement(),
    chatMessages: new FakeElement(),
    chatMessagesWrapper: new FakeElement(),
    chatInput: new FakeElement(),
  };
  const document = {
    body: new FakeElement(),
    cookie: '',
    addEventListener() {},
    createElement() {
      return new FakeElement();
    },
    getElementById(id) {
      return elements[id] || null;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const window = {
    currentUserId: 1,
    defaultAvatar: '/static/default-avatar.png',
    location: { origin: 'https://kimbela.test', search },
  };
  const context = {
    URLSearchParams,
    console: { error() {}, log() {} },
    document,
    fetch: async url => {
      fetchCalls.push(url);
      if (url === '/api/messaging/friends') {
        return { json: async () => ({ success: true, friends }) };
      }
      if (url.startsWith('/api/messaging/messages/')) {
        return { json: async () => ({ messages: [], has_more: false }) };
      }
      throw new Error(`Unexpected request: ${url}`);
    },
    setTimeout(callback) {
      callback();
      return 1;
    },
    clearTimeout() {},
    window,
  };

  vm.runInNewContext(messengerSource, context, {
    filename: 'static/assets/js/messenger.js',
  });

  return { elements, fetchCalls, window };
}

test('profile chat query opens the requested authorized friend', async () => {
  const friend = {
    id: 13,
    name: 'Profile Recipient',
    avatar: '/avatar-13.png',
    unread_count: 0,
  };
  const runtime = loadMessenger({ search: '?chat=13', friends: [friend] });

  await runtime.window.Messenger.loadFriendsList();

  assert.equal(runtime.elements.messengerPopup.classList.contains('hidden'), false);
  assert.equal(runtime.elements.friendList.classList.contains('hidden'), true);
  assert.equal(runtime.elements.chatArea.classList.contains('hidden'), false);
  assert.equal(runtime.elements.chatName.textContent, friend.name);
  assert.equal(runtime.elements.chatAvatar.src, friend.avatar);
  assert.deepEqual(runtime.fetchCalls, [
    '/api/messaging/friends',
    '/api/messaging/messages/13?limit=50',
  ]);
});

test('non-friend or blocked chat target is ignored safely', async () => {
  const runtime = loadMessenger({
    search: '?chat=13',
    friends: [{ id: 14, name: 'Allowed Friend', avatar: '/avatar-14.png' }],
  });

  await runtime.window.Messenger.loadFriendsList();

  assert.equal(runtime.elements.messengerPopup.classList.contains('hidden'), true);
  assert.deepEqual(runtime.fetchCalls, ['/api/messaging/friends']);
});

test('invalid chat target is ignored safely', async () => {
  const runtime = loadMessenger({ search: '?chat=not-a-user', friends: [] });

  await runtime.window.Messenger.loadFriendsList();

  assert.equal(runtime.elements.messengerPopup.classList.contains('hidden'), true);
  assert.deepEqual(runtime.fetchCalls, ['/api/messaging/friends']);
});

test('generic profile Message control opens the authorized friend list', async () => {
  const runtime = loadMessenger({ search: '?messenger=1', friends: [] });

  await runtime.window.Messenger.loadFriendsList();

  assert.equal(runtime.elements.messengerPopup.classList.contains('hidden'), false);
  assert.equal(runtime.elements.friendList.classList.contains('hidden'), false);
  assert.equal(runtime.elements.chatArea.classList.contains('hidden'), true);
  assert.deepEqual(runtime.fetchCalls, ['/api/messaging/friends']);
});
