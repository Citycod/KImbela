const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/boost_checkout.js'),
  'utf8',
);

function classList(initial = []) {
  const values = new Set(initial);
  return {
    add(value) { values.add(value); },
    remove(value) { values.delete(value); },
    contains(value) { return values.has(value); },
  };
}

function runtime() {
  const modal = { classList: classList(['hidden']) };
  const body = { style: { overflow: '' } };
  const document = {
    body,
    getElementById(id) { return id === 'paymentModal' ? modal : null; },
  };
  const window = {
    document,
    setTimeout,
    clearTimeout,
  };
  vm.runInNewContext(source, { window });
  return { body, document, modal, checkout: window.KimbelaBoostCheckout };
}

function response(payload, ok = true, status = 200) {
  return {
    ok,
    status,
    async text() { return JSON.stringify(payload); },
  };
}

test('checkout opens and successful initialization restores the application page', async () => {
  const state = runtime();
  const button = { innerHTML: 'Pay $3.00 USD Now', disabled: false };
  const controller = state.checkout.createController({
    document: state.document,
    fetch: async () => response({ success: true, payment_url: 'https://checkout.example' }),
  });

  controller.begin(button);
  assert.equal(state.modal.classList.contains('hidden'), false);
  assert.equal(state.body.style.overflow, 'hidden');
  assert.equal(button.disabled, true);
  const payload = await controller.requestJson('/checkout');
  assert.equal(payload.success, true);
  controller.finish();
  assert.equal(state.modal.classList.contains('hidden'), true);
  assert.equal(state.body.style.overflow, '');
  assert.equal(button.disabled, false);
});

test('initialization error and cancellation recovery cannot leave black overlay', async () => {
  const state = runtime();
  const messages = [];
  const button = { innerHTML: 'Pay', disabled: false };
  const controller = state.checkout.createController({
    document: state.document,
    fetch: async () => response({ error: 'Unavailable' }, false, 503),
    notify: message => messages.push(message),
  });

  controller.begin(button);
  await assert.rejects(controller.requestJson('/checkout'), /Unavailable/);
  controller.fail('Unable to start payment.');
  assert.equal(state.modal.classList.contains('hidden'), true);
  assert.equal(state.body.style.overflow, '');
  assert.equal(button.disabled, false);
  assert.deepEqual(messages, ['Unable to start payment.']);

  controller.begin(button);
  controller.recover();
  assert.equal(state.modal.classList.contains('hidden'), true);
  assert.equal(state.body.style.overflow, '');
});

test('a stalled payment request times out and can be cleaned up', async () => {
  const state = runtime();
  const button = { innerHTML: 'Pay', disabled: false };
  const controller = state.checkout.createController({
    document: state.document,
    fetch: () => new Promise(() => {}),
    timeoutMs: 5,
  });

  controller.begin(button);
  await assert.rejects(controller.requestJson('/checkout'), /timed out/);
  controller.finish();
  assert.equal(state.modal.classList.contains('hidden'), true);
  assert.equal(button.disabled, false);
});

test('boost template handles hosted-checkout cancel, callback error, and bfcache return', () => {
  const template = fs.readFileSync(
    path.resolve(__dirname, '../../templates/requests.html'),
    'utf8',
  );
  assert.match(template, /status !== 'successful' && status !== 'completed'/);
  assert.match(template, /window\.addEventListener\('pageshow'/);
  assert.match(template, /checkout\.fail\(error\.message \|\| 'Error verifying payment'\)/);
  assert.match(template, /window\.location\.assign\(paymentData\.payment_url\)/);
});
