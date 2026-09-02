const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const partialSource = fs.readFileSync(
  path.resolve(
    __dirname,
    '../../templates/partials/user_dashboard_body_scripts.html',
  ),
  'utf8',
);
const scriptStart = partialSource.indexOf('<script>') + '<script>'.length;
const scriptEnd = partialSource.indexOf('</script>', scriptStart);
const birthdaySource = partialSource.slice(scriptStart, scriptEnd);

class FakeClassList {
  constructor(initial = []) {
    this.values = new Set(initial);
  }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
  toggle(value) {
    if (this.values.has(value)) {
      this.values.delete(value);
      return false;
    }
    this.values.add(value);
    return true;
  }
}

class FakeElement {
  constructor(initialClasses = []) {
    this.attributes = new Map();
    this.classList = new FakeClassList(initialClasses);
    this.innerHTML = '';
    this.style = {};
    this.textContent = '';
  }
  contains() { return false; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) || null; }
}

function birthday(id, name = `Friend ${id}`) {
  return {
    id,
    name,
    avatar: `/avatar-${id}.png`,
    age: 30,
  };
}

function createRuntime(todayBirthdays, { online = true, coordinated = false } = {}) {
  const requests = [];
  const intervals = [];
  const clearedIntervals = [];
  let leader = true;
  let leadershipCallback = null;
  const elements = {
    birthdayCount: new FakeElement(['hidden']),
    birthdayNotificationBadge: new FakeElement(),
    birthdayNotificationList: new FakeElement(),
    birthdayNotificationPopup: new FakeElement(['hidden', 'scale-95', 'opacity-0']),
    birthdayShortcut: new FakeElement(),
  };
  elements.birthdayCount.style.display = 'none';
  const document = {
    body: { style: {} },
    hidden: false,
    visibilityState: 'visible',
    addEventListener() {},
    getElementById(id) { return elements[id] || null; },
  };
  const window = {
    KimbelaNetwork: {
      isOnline() { return online; },
      requestJson(key, url) {
        requests.push(url);
        return Promise.resolve({
          success: true,
          birthdays: todayBirthdays,
          count: todayBirthdays.length,
        });
      },
    },
  };
  if (coordinated) {
    window.KimbelaPassivePolling = {
      isLeader() { return leader; },
      onLeadershipChange(callback) {
        leadershipCallback = callback;
        callback(leader);
        return () => {};
      },
      publish() {},
      subscribe() { return () => {}; },
    };
  }
  const context = {
    alert() {},
    clearInterval(timer) { clearedIntervals.push(timer); },
    clearTimeout() {},
    document,
    fetch: async () => { throw new Error('Unexpected duplicate fetch'); },
    setInterval(callback) {
      const timer = { callback };
      intervals.push(timer);
      return timer;
    },
    setTimeout(callback) { callback(); return 1; },
    window,
  };

  vm.runInNewContext(
    `${birthdaySource}\nglobalThis.BirthdayCelebrationForTest = BirthdayCelebration;`,
    context,
    { filename: 'templates/partials/user_dashboard_body_scripts.html' },
  );

  return {
    elements,
    clearedIntervals,
    intervals,
    requests,
    system: new context.BirthdayCelebrationForTest(),
    async setLeader(value) {
      leader = value;
      leadershipCallback(value);
      await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('zero birthdays keeps shortcut available and hides only its count', async () => {
  const runtime = createRuntime([]);

  await runtime.system.checkBirthdays();

  assert.equal(runtime.elements.birthdayCount.style.display, 'none');
  assert.equal(runtime.elements.birthdayCount.classList.contains('hidden'), true);
  assert.match(runtime.elements.birthdayNotificationList.innerHTML, /No birthdays today/);
  assert.equal(
    runtime.elements.birthdayShortcut.getAttribute('aria-label'),
    'Birthdays, none today',
  );
});

test('one birthday displays an exact badge count', async () => {
  const runtime = createRuntime([birthday(1)]);

  await runtime.system.checkBirthdays();

  assert.equal(runtime.elements.birthdayCount.textContent, 1);
  assert.equal(runtime.elements.birthdayCount.style.display, 'flex');
  assert.equal(runtime.elements.birthdayCount.classList.contains('hidden'), false);
  assert.equal(
    runtime.elements.birthdayShortcut.getAttribute('aria-label'),
    'Birthdays, 1 today',
  );
});

test('multiple birthday badge counts are exact through nine and compact after', async () => {
  const four = createRuntime([birthday(1), birthday(2), birthday(3), birthday(4)]);
  await four.system.checkBirthdays();
  assert.equal(four.elements.birthdayCount.textContent, 4);

  const ten = createRuntime(Array.from({ length: 10 }, (_, index) => birthday(index + 1)));
  await ten.system.checkBirthdays();
  assert.equal(ten.elements.birthdayCount.textContent, '9+');
  assert.equal(
    ten.elements.birthdayShortcut.getAttribute('aria-label'),
    'Birthdays, 10 today',
  );
});

test('shortcut opens the existing birthday popup without another request', async () => {
  const runtime = createRuntime([]);
  await runtime.system.checkBirthdays();
  const requestCount = runtime.requests.length;

  runtime.system.showBirthdayNotifications();
  await runtime.system.updateBirthdayBadge();

  assert.equal(
    runtime.elements.birthdayNotificationPopup.classList.contains('hidden'),
    false,
  );
  assert.equal(runtime.requests.length, requestCount);
});

test('friend selection reuses already-fetched birthday data', async () => {
  const friend = birthday(7, 'Cached Friend');
  const runtime = createRuntime([friend]);
  let selected = null;
  runtime.system.showBirthdayModal = value => { selected = value; };
  await runtime.system.checkBirthdays();

  runtime.system.openBirthdayForFriend(friend.id);

  assert.equal(selected.name, 'Cached Friend');
  assert.deepEqual(runtime.requests, ['/api/birthdays/today']);
});

test('concurrent birthday startup checks share one request', async () => {
  const runtime = createRuntime([birthday(1)]);

  await Promise.all([
    runtime.system.checkBirthdays(),
    runtime.system.checkBirthdays(),
  ]);

  assert.deepEqual(runtime.requests, ['/api/birthdays/today']);
});

test('offline friend selection does not fetch or recursively retry', async () => {
  const runtime = createRuntime([], { online: false });

  runtime.system.openBirthdayForFriend(1);
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(runtime.requests, []);
});

test('birthday polling follows visible leader handoff without catch-up requests', async () => {
  const runtime = createRuntime([birthday(1)], { coordinated: true });
  runtime.system.init();
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(runtime.requests, ['/api/birthdays/today']);
  assert.equal(runtime.intervals.length, 1);

  await runtime.setLeader(false);
  assert.equal(runtime.clearedIntervals.length, 1);
  assert.deepEqual(runtime.requests, ['/api/birthdays/today']);

  await runtime.setLeader(true);
  assert.deepEqual(runtime.requests, [
    '/api/birthdays/today',
    '/api/birthdays/today',
  ]);
  assert.equal(runtime.intervals.length, 2);
});
