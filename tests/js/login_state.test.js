const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/login.js'),
  'utf8',
);

function runtime({ valid = true } = {}) {
  const formListeners = {};
  const windowListeners = {};
  const buttonAttributes = new Map();
  const form = {
    dataset: {},
    addEventListener(type, callback) { formListeners[type] = callback; },
    checkValidity() { return valid; },
  };
  const button = {
    dataset: { idleLabel: 'Sign In', loadingLabel: 'Signing in...' },
    disabled: false,
    textContent: 'Sign In',
    setAttribute(name, value) { buttonAttributes.set(name, value); },
    removeAttribute(name) { buttonAttributes.delete(name); },
  };
  const document = {
    readyState: 'complete',
    getElementById(id) {
      return { loginForm: form, loginSubmitButton: button }[id] || null;
    },
  };
  const window = {
    addEventListener(type, callback) { windowListeners[type] = callback; },
    setTimeout(callback) { callback(); },
  };
  vm.runInNewContext(source, { document, window });

  function submit() {
    const event = {
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
    };
    formListeners.submit(event);
    return event;
  }

  return { button, buttonAttributes, submit, windowListeners };
}

test('valid login enters an accessible loading state and blocks duplicate submit', () => {
  const page = runtime();
  const first = page.submit();
  assert.equal(first.defaultPrevented, false);
  assert.equal(page.button.textContent, 'Signing in...');
  assert.equal(page.button.disabled, true);
  assert.equal(page.buttonAttributes.get('aria-disabled'), 'true');
  assert.equal(page.buttonAttributes.get('aria-busy'), 'true');

  const duplicate = page.submit();
  assert.equal(duplicate.defaultPrevented, true);
  assert.equal(page.button.textContent, 'Signing in...');
});

test('invalid or failed/back-navigation login restores the idle state', () => {
  const invalid = runtime({ valid: false });
  invalid.submit();
  assert.equal(invalid.button.textContent, 'Sign In');
  assert.equal(invalid.button.disabled, false);

  const failed = runtime();
  failed.submit();
  failed.windowListeners.pageshow();
  assert.equal(failed.button.textContent, 'Sign In');
  assert.equal(failed.button.disabled, false);
  assert.equal(failed.buttonAttributes.get('aria-disabled'), 'false');
  assert.equal(failed.buttonAttributes.has('aria-busy'), false);
});
