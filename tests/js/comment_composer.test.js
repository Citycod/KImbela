const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/comment_composer.js'),
  'utf8',
);
const dashboardTemplate = fs.readFileSync(
  path.resolve(__dirname, '../../templates/user_dashboard.html'),
  'utf8',
);
const partialTemplate = fs.readFileSync(
  path.resolve(__dirname, '../../templates/_posts_partial.html'),
  'utf8',
);
const groupTemplate = fs.readFileSync(
  path.resolve(__dirname, '../../templates/group_detail.html'),
  'utf8',
);

function makeRuntime({ online = true, addComment } = {}) {
  const feedback = [];
  const listeners = {};
  const document = {
    addEventListener(type, callback) { listeners[type] = callback; },
    createElement() { return {}; },
    querySelectorAll() { return []; },
  };
  const context = {
    Event: class Event {
      constructor(type) { this.type = type; }
    },
    document,
    navigator: { onLine: online },
    window: {
      addComment: addComment || (async () => true),
      addEventListener() {},
      KimbelaNetwork: { isOnline: () => online },
      Toast: { show(message, type) { feedback.push({ message, type }); } },
    },
  };
  vm.runInNewContext(source, context);
  return { api: context.window.CommentComposer, feedback, listeners };
}

function makeComposer(value = '') {
  const attributes = {};
  const input = {
    disabled: false,
    value,
    selectionStart: value.length,
    selectionEnd: value.length,
    closest() { return composer; },
    dispatchEvent() {},
    focus() { this.focused = true; },
    matches(selector) { return selector === '.comment-composer-input'; },
    setSelectionRange(start, end) {
      this.selectionStart = start;
      this.selectionEnd = end;
    },
  };
  const send = {
    disabled: true,
    innerHTML: '',
    setAttribute(name, value) { attributes[name] = value; },
  };
  const emoji = { disabled: false };
  const composer = {
    dataset: { postId: '42', submitting: 'false' },
    querySelector(selector) {
      if (selector === '.comment-composer-input') return input;
      if (selector === '.comment-composer-send') return send;
      if (selector === '.comment-composer-emoji') return emoji;
      return null;
    },
  };
  return { attributes, composer, emoji, input, send };
}

test('feed and group composers render emoji and accessible send controls', () => {
  for (const template of [dashboardTemplate, partialTemplate, groupTemplate]) {
    assert.match(template, /comment-composer-emoji/);
    assert.match(template, /aria-label="Add emoji"/);
    assert.match(template, /comment-composer-send/);
    assert.match(template, /aria-label="Send comment"/);
  }
});

test('emoji insertion preserves text and uses the current cursor position', () => {
  const { api } = makeRuntime();
  const { input } = makeComposer('Hello world');
  input.selectionStart = 6;
  input.selectionEnd = 6;

  api.insertEmoji(input, '😊');

  assert.equal(input.value, 'Hello 😊world');
  assert.equal(input.selectionStart, 8);
  assert.equal(input.selectionEnd, 8);
  assert.equal(input.focused, true);
});

test('send is disabled for empty and whitespace-only comments', () => {
  const { api } = makeRuntime();
  const empty = makeComposer('');
  const whitespace = makeComposer('   ');
  const populated = makeComposer('Ready');

  api.sync(empty.composer);
  api.sync(whitespace.composer);
  api.sync(populated.composer);

  assert.equal(empty.send.disabled, true);
  assert.equal(whitespace.send.disabled, true);
  assert.equal(populated.send.disabled, false);
});

test('successful submission uses the post id and clears the input', async () => {
  const calls = [];
  const { api } = makeRuntime({
    addComment: async (postId, content) => {
      calls.push({ postId, content });
      return true;
    },
  });
  const state = makeComposer(' A comment ');

  assert.equal(await api.submit(state.composer), true);
  assert.deepEqual(calls, [{ postId: '42', content: 'A comment' }]);
  assert.equal(state.input.value, '');
  assert.equal(state.composer.dataset.submitting, 'false');
});

test('duplicate submission is prevented while the first request is active', async () => {
  let resolveRequest;
  let callCount = 0;
  const pending = new Promise(resolve => { resolveRequest = resolve; });
  const { api } = makeRuntime({
    addComment: async () => {
      callCount += 1;
      return pending;
    },
  });
  const state = makeComposer('Only once');

  const first = api.submit(state.composer);
  const second = api.submit(state.composer);
  assert.equal(await second, false);
  assert.equal(callCount, 1);

  resolveRequest(true);
  assert.equal(await first, true);
});

test('offline submission is blocked and preserves the typed comment', async () => {
  let called = false;
  const { api, feedback } = makeRuntime({
    online: false,
    addComment: async () => { called = true; },
  });
  const state = makeComposer('Keep this');

  assert.equal(await api.submit(state.composer), false);
  assert.equal(called, false);
  assert.equal(state.input.value, 'Keep this');
  assert.deepEqual(feedback, [{
    message: "You're offline. Reconnect to post your comment.",
    type: 'warning',
  }]);
});

test('failed submission preserves text and restores controls for retry', async () => {
  const { api } = makeRuntime({ addComment: async () => false });
  const state = makeComposer('Retry me');

  assert.equal(await api.submit(state.composer), false);
  assert.equal(state.input.value, 'Retry me');
  assert.equal(state.input.disabled, false);
  assert.equal(state.emoji.disabled, false);
  assert.equal(state.send.disabled, false);
  assert.equal(state.composer.dataset.submitting, 'false');
});

test('comment picker is created only after the emoji control is activated', () => {
  assert.match(
    source,
    /DOMContentLoaded', \(\) => \{\s*document\.querySelectorAll\('\.comment-composer'\)\.forEach\(sync\);\s*\}\)/,
  );
  assert.match(source, /function toggleEmojiPicker\(button\)/);
  assert.match(source, /document\.createElement\('div'\)/);
  assert.match(source, /document\.body\.appendChild\(picker\)/);
  assert.match(source, /picker\.style\.position = 'fixed'/);
  assert.doesNotMatch(source, /composer\.appendChild\(picker\)/);
});

test('emoji controls include the Tailwind 2 transform utility for centering', () => {
  for (const template of [dashboardTemplate, partialTemplate, groupTemplate]) {
    assert.match(
      template,
      /comment-composer-emoji[^>]*top-1\/2 transform -translate-y-1\/2/,
    );
  }
});

test('feed and group submission paths use the existing resilience layer', () => {
  const dashboardSource = fs.readFileSync(
    path.resolve(__dirname, '../../static/assets/js/dashboard.js'),
    'utf8',
  );
  assert.match(dashboardSource, /`comment-submit-\$\{postId\}`/);
  assert.match(groupTemplate, /`comment-submit-\$\{postId\}`/);
  assert.match(groupTemplate, /KimbelaNetwork\.requestJson/);
});
