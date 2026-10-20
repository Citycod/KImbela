const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/share_utils.js'),
  'utf8',
);
const dashboardSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/dashboard.js'),
  'utf8',
);
const groupSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/group_detail.html'),
  'utf8',
);
const modularPostsSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/modules/posts/index.js'),
  'utf8',
);

function runtime(clipboard) {
  const calls = [];
  let clickHandler = null;
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
    getElementById() { return null; },
    addEventListener(name, handler) {
      if (name === 'click') clickHandler = handler;
    },
    execCommand(command) {
      calls.push(command);
      return true;
    },
  };
  const window = {
    isSecureContext: true,
    location: { origin: 'https://www.kimbela.com' },
    setTimeout(callback) { callback(); },
  };
  const navigator = clipboard ? { clipboard } : {};
  function CustomEvent(name, options) {
    this.type = name;
    this.detail = options.detail;
  }
  vm.runInNewContext(source, { CustomEvent, document, navigator, URL, window });
  return { calls, clickHandler, share: window.KimbelaShare };
}

test('builds one stable versioned URL for feed and group share actions', () => {
  const { share } = runtime(null);

  assert.equal(
    share.postUrl('post-uuid'),
    'https://www.kimbela.com/post/post-uuid?share_v=2',
  );
  assert.equal(
    share.postUrl('post-uuid', '/post/post-uuid'),
    'https://www.kimbela.com/post/post-uuid?share_v=2',
  );
  assert.equal(share.POST_SHARE_REVISION, '2');
});

test('replaces an old revision without adding duplicate or random parameters', () => {
  const { share } = runtime(null);
  assert.equal(
    share.postUrl(
      'post-uuid',
      'https://www.kimbela.com/post/post-uuid?share_v=1',
    ),
    'https://www.kimbela.com/post/post-uuid?share_v=2',
  );
});

test('feed and every group share path use the shared versioned URL helper', () => {
  assert.match(dashboardSource, /KimbelaShare\.postUrl\(postId, shareUrl, getPublicBaseUrl\(\)\)/);
  assert.match(groupSource, /KimbelaShare\.postUrl\(postId, shareUrl, getPublicBaseUrl\(\)\)/);
  assert.match(modularPostsSource, /KimbelaShare\.postUrl\(/);
});

test('copy, native share, and WhatsApp all consume the same versioned payload URL', () => {
  for (const consumerSource of [dashboardSource, groupSource]) {
    assert.match(consumerSource, /KimbelaShare\.copyText\(url\)/);
    assert.match(consumerSource, /navigator\.share\(\{ title: 'Kimbela Post', text, url \}\)/);
    assert.match(consumerSource, /wa\.me\/\?text=\$\{encodedText\}%20\$\{encodedUrl\}/);
  }
});

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

test('desktop copy trigger reports success only after clipboard resolves', async () => {
  let resolveClipboard;
  const result = runtime({
    writeText() {
      return new Promise(resolve => { resolveClipboard = resolve; });
    },
  });
  const label = { textContent: 'Copy link' };
  const events = [];
  const trigger = {
    dataset: {
      postId: 'profile-post-uuid',
      url: '/post/profile-post-uuid',
    },
    disabled: false,
    querySelector() { return label; },
    dispatchEvent(event) { events.push(event); },
  };

  const pending = result.share.copyFromTrigger(trigger);
  assert.equal(label.textContent, 'Copy link');
  assert.equal(events.length, 0);
  resolveClipboard();
  assert.equal(await pending, true);
  assert.equal(events[0].type, 'kimbela:copy-success');
  assert.equal(
    events[0].detail.url,
    'https://www.kimbela.com/post/profile-post-uuid?share_v=2',
  );
});

test('desktop copy trigger uses fallback before showing success', async () => {
  const result = runtime({
    async writeText() { throw new Error('NotAllowedError'); },
  });
  const label = { textContent: 'Copy link' };
  const events = [];
  const trigger = {
    dataset: { postId: 'fallback-uuid', url: '/post/fallback-uuid' },
    disabled: false,
    querySelector() { return label; },
    dispatchEvent(event) { events.push(event); },
  };

  assert.equal(await result.share.copyFromTrigger(trigger), true);
  assert.ok(result.calls.includes('copy'));
  assert.equal(events[0].type, 'kimbela:copy-success');
});
