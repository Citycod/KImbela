const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/profile_post_actions.js'),
  'utf8',
);

function runtime(payload, ok = true) {
  const statusNodes = [];
  const document = {
    body: { appendChild(node) { statusNodes.push(node); } },
    addEventListener() {},
    getElementById() { return null; },
    querySelector() {
      return { getAttribute() { return 'csrf-token'; } };
    },
    createElement() {
      return {
        style: {},
        setAttribute() {},
        remove() {},
      };
    },
  };
  const requests = [];
  const window = {
    confirm: () => true,
    document,
    setTimeout(callback) { callback(); },
    async fetch(url, options) {
      requests.push({ url, options });
      return {
        ok,
        headers: { get: () => 'application/json' },
        async json() { return payload; },
      };
    },
  };
  vm.runInNewContext(source, { document, encodeURIComponent, Object, window });
  return { api: window.KimbelaProfilePostActions, requests, statusNodes };
}

function trigger() {
  const card = { removed: false, remove() { this.removed = true; } };
  return {
    card,
    element: {
      dataset: { postId: '42' },
      disabled: false,
      innerHTML: 'Delete',
      textContent: 'Delete',
      closest: () => card,
    },
  };
}

test('profile delete removes the card only after explicit JSON success', async () => {
  const state = runtime({ success: true, post_id: 42 });
  const target = trigger();

  assert.equal(await state.api.deletePost(target.element), true);
  assert.equal(target.card.removed, true);
  assert.equal(state.requests[0].url, '/delete_post/42');
  assert.equal(state.requests[0].options.method, 'POST');
});

test('profile delete keeps the card when the server does not confirm success', async () => {
  const state = runtime({ success: false, error: 'Commit failed' }, false);
  const target = trigger();

  assert.equal(await state.api.deletePost(target.element), false);
  assert.equal(target.card.removed, false);
  assert.equal(target.element.disabled, false);
  assert.equal(target.element.innerHTML, 'Delete');
});
