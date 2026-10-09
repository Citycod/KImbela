const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/share_utils.js'),
  'utf8',
);

function runtime(clipboard) {
  const calls = [];
  const textarea = {
    style: {},
    value: '',
    focus() { calls.push('focus'); },
    remove() { calls.push('remove'); },
    select() { calls.push('select'); },
    setAttribute() {},
    setSelectionRange() { calls.push('range'); },
  };
  const document = {
    body: { appendChild() { calls.push('append'); } },
    createElement() { return textarea; },
    execCommand(command) {
      calls.push(command);
      return true;
    },
  };
  const window = { isSecureContext: true };
  const navigator = clipboard ? { clipboard } : {};
  vm.runInNewContext(source, { document, navigator, window });
  return { calls, share: window.KimbelaShare };
}

test('uses the modern Clipboard API when Android exposes a working implementation', async () => {
  const values = [];
  const result = runtime({
    async writeText(value) { values.push(value); },
  });

  await result.share.copyText('https://kimbela.com/post/example');
  assert.deepEqual(values, ['https://kimbela.com/post/example']);
  assert.deepEqual(result.calls, []);
});

test('falls back when an Android webview rejects or omits the Clipboard API', async () => {
  const rejected = runtime({
    async writeText() { throw new Error('NotAllowedError'); },
  });
  await rejected.share.copyText('https://kimbela.com/post/rejected');
  assert.ok(rejected.calls.includes('copy'));

  const missing = runtime(null);
  await missing.share.copyText('https://kimbela.com/post/missing');
  assert.ok(missing.calls.includes('copy'));
});
