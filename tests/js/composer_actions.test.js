const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const dashboardSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/dashboard.js'),
  'utf8',
);
const dashboardTemplate = fs.readFileSync(
  path.resolve(__dirname, '../../templates/user_dashboard.html'),
  'utf8',
);
const dashboardBodyScripts = fs.readFileSync(
  path.resolve(__dirname, '../../templates/partials/user_dashboard_body_scripts.html'),
  'utf8',
);

function loadComposerActions() {
  const start = dashboardSource.indexOf('function openPostComposer()');
  const end = dashboardSource.indexOf('function syncComposerMediaInput(');
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);

  const listeners = {};
  const classNames = new Set(['hidden']);
  const textarea = { focusCount: 0, focus() { this.focusCount += 1; } };
  const modal = {
    classList: { remove() {} },
    querySelector(selector) {
      return selector === 'textarea[name="post_content"]' ? textarea : null;
    },
    style: {},
  };
  const mediaInput = {
    accept: '',
    clickCount: 0,
    click() { this.clickCount += 1; },
  };
  const notice = {
    classList: {
      toggle(name, force) {
        if (force) classNames.add(name);
        else classNames.delete(name);
      },
    },
    textContent: '',
  };
  const elements = { composerActionNotice: notice, mediaInput, postModal: modal };
  const window = {
    openModalCalls: [],
    openModal(id) { this.openModalCalls.push(id); },
    openEmojiPickerCalls: 0,
    openEmojiPicker() { this.openEmojiPickerCalls += 1; },
  };
  const context = {
    document: {
      addEventListener(type, callback) { listeners[type] = callback; },
      body: { style: {} },
      getElementById(id) { return elements[id] || null; },
    },
    setTimeout(callback) { callback(); },
    window,
  };

  vm.runInNewContext(
    `${dashboardSource.slice(start, end)}\nglobalThis.api = { openPostComposerAction, setPostComposerActionNotice };`,
    context,
  );

  return { api: context.api, classNames, listeners, mediaInput, notice, textarea, window };
}

function loadPostEmojiPicker() {
  const start = dashboardBodyScripts.indexOf('let currentTextarea = null;');
  const end = dashboardBodyScripts.indexOf('// GIF PICKER FUNCTIONS');
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);

  let emojiListener = null;
  let initialized = false;
  const modalClasses = new Set(['hidden']);
  const textarea = {
    value: 'Feeling ',
    selectionStart: 8,
    selectionEnd: 8,
    dispatchEvent() {},
    focus() {},
  };
  const emojiModal = {
    classList: {
      add(name) { modalClasses.add(name); },
      remove(name) { modalClasses.delete(name); },
    },
  };
  const picker = {
    addEventListener(type, callback) {
      assert.equal(type, 'emoji-click');
      emojiListener = callback;
    },
    hasAttribute(name) {
      return name === 'data-initialized' && initialized;
    },
    setAttribute(name) {
      if (name === 'data-initialized') initialized = true;
    },
  };
  const context = {
    Event: class Event {},
    document: {
      addEventListener() {},
      body: { style: {} },
      createElement() { return {}; },
      getElementById(id) {
        return { emojiModal, emojiPicker: picker }[id] || null;
      },
      head: { appendChild() {} },
      querySelector(selector) {
        if (selector === '#postModal textarea[name="post_content"]') return textarea;
        if (selector.startsWith('script[')) return {};
        return null;
      },
    },
  };
  vm.runInNewContext(
    `${dashboardBodyScripts.slice(start, end)}\nglobalThis.openPicker = openEmojiPicker;`,
    context,
  );

  return {
    choose(emoji) { emojiListener({ detail: { emoji: { unicode: emoji } } }); },
    modalClasses,
    open: context.openPicker,
    textarea,
  };
}

test('composer controls are non-submit buttons wired to one delegated action path', () => {
  for (const action of ['photo', 'video', 'poll', 'feeling']) {
    assert.match(
      dashboardTemplate,
      new RegExp(`<button type="button" class="kb-composer-btn ${action}" data-composer-action="${action}"`),
    );
  }
  assert.match(
    dashboardTemplate,
    /<button type="button" class="kb-post-btn" data-composer-action="post"/,
  );

  const runtime = loadComposerActions();
  let prevented = false;
  runtime.listeners.click({
    preventDefault() { prevented = true; },
    target: {
      closest(selector) {
        assert.equal(selector, '[data-composer-action]');
        return { dataset: { composerAction: 'post' } };
      },
    },
  });
  assert.equal(prevented, true);
  assert.deepEqual(runtime.window.openModalCalls, ['postModal']);
});

test('Photo opens the real image input without submitting the post form', () => {
  const runtime = loadComposerActions();

  assert.equal(runtime.api.openPostComposerAction('photo'), true);
  assert.equal(runtime.mediaInput.accept, 'image/*');
  assert.equal(runtime.mediaInput.clickCount, 1);
  assert.deepEqual(runtime.window.openModalCalls, ['postModal']);
});

test('Feeling opens the existing emoji selector for the post textarea', () => {
  const runtime = loadComposerActions();

  assert.equal(runtime.api.openPostComposerAction('feeling'), true);
  assert.equal(runtime.window.openEmojiPickerCalls, 1);
  assert.deepEqual(runtime.window.openModalCalls, ['postModal']);
  assert.equal((dashboardBodyScripts.match(/function openEmojiPicker\(\)/g) || []).length, 1);
  assert.equal((dashboardBodyScripts.match(/picker\.addEventListener\('emoji-click'/g) || []).length, 1);
  assert.match(
    dashboardTemplate,
    /id="emojiModal" class="modal fixed inset-0 z-\[10050\]/,
  );
  assert.match(
    dashboardBodyScripts,
    /event\.detail\?\.emoji\?\.unicode \|\| event\.detail\?\.unicode/,
  );

  const picker = loadPostEmojiPicker();
  picker.open();
  picker.choose('😊');
  assert.equal(picker.textarea.value, 'Feeling 😊');
  assert.equal(picker.modalClasses.has('hidden'), true);
});

test('unsupported Video and Poll actions explain the existing backend restriction', () => {
  const video = loadComposerActions();
  assert.equal(video.api.openPostComposerAction('video'), true);
  assert.match(video.notice.textContent, /Video uploads are not currently supported/);
  assert.equal(video.classNames.has('hidden'), false);
  assert.equal(video.mediaInput.clickCount, 0);

  const poll = loadComposerActions();
  assert.equal(poll.api.openPostComposerAction('poll'), true);
  assert.match(poll.notice.textContent, /Poll posts are not currently supported/);
  assert.equal(poll.classNames.has('hidden'), false);
  assert.equal(poll.mediaInput.clickCount, 0);
});

test('ordinary Post opens and focuses the existing text composer', () => {
  const runtime = loadComposerActions();

  assert.equal(runtime.api.openPostComposerAction('post'), true);
  assert.equal(runtime.textarea.focusCount, 1);
  assert.equal(runtime.classNames.has('hidden'), true);
});
