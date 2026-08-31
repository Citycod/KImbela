const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/deep_link_focus.js'),
  'utf8',
);

function runtime(hash, hasTarget = true) {
  const calls = [];
  const classes = new Set();
  const target = {
    classList: {
      add(value) { classes.add(value); },
      remove(value) { classes.delete(value); },
    },
    focus(options) { calls.push(['focus', options]); },
    removeAttribute(name) { calls.push(['removeAttribute', name]); },
    scrollIntoView(options) { calls.push(['scrollIntoView', options]); },
    setAttribute(name, value) { calls.push(['setAttribute', name, value]); },
  };
  const handlers = new Map();
  const window = {
    location: { hash },
    addEventListener(type, handler) { handlers.set(type, handler); },
    setTimeout() { return 1; },
  };
  const document = {
    getElementById(id) {
      return hasTarget && id === hash.slice(1) ? target : null;
    },
  };

  vm.runInNewContext(source, { document, window }, { filename: 'deep_link_focus.js' });
  return { calls, classes, handlers, target, window };
}

test('exact comment deep link scrolls, focuses, and highlights the comment', () => {
  const result = runtime('#comment-42');

  assert.equal(result.window.KimbelaDeepLinkFocus.focus(), true);
  assert.equal(result.calls[0][0], 'setAttribute');
  assert.equal(result.calls[1][0], 'scrollIntoView');
  assert.equal(result.calls[2][0], 'focus');
  assert.equal(result.classes.has('kimbela-deep-link-target'), true);
});

test('missing or invalid target leaves the destination page usable', () => {
  assert.equal(runtime('#comment-404', false).window.KimbelaDeepLinkFocus.focus(), false);
  assert.equal(runtime('#unsafe-target', true).window.KimbelaDeepLinkFocus.focus(), false);
});
