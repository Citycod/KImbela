const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const dashboardSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/dashboard.js'),
  'utf8',
);
const groupSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/group_detail.html'),
  'utf8',
);
const birthdaySource = fs.readFileSync(
  path.resolve(
    __dirname,
    '../../templates/partials/user_dashboard_body_scripts.html',
  ),
  'utf8',
);

function loadNotificationSystem() {
  const helpers = dashboardSource.slice(
    dashboardSource.indexOf('function isDashboardOnline()'),
    dashboardSource.indexOf('const MobileFeedAds ='),
  );
  const notificationCode = dashboardSource.slice(
    dashboardSource.indexOf('const NotificationSystem ='),
    dashboardSource.indexOf('// SEARCH SYSTEM'),
  );
  const requests = [];
  const intervals = [];
  const clearedIntervals = [];
  let online = false;
  let onlineHandler = null;
  let offlineHandler = null;
  const elements = {
    notificationBadge: {
      classList: { add() {}, remove() {} },
      textContent: '',
    },
    notificationsList: { innerHTML: '' },
    notificationDropdown: { addEventListener() {} },
  };
  const context = {
    appState: { notificationCheckInterval: null },
    bootstrap: {},
    clearInterval(id) { clearedIntervals.push(id); },
    document: {
      getElementById(id) { return elements[id] || null; },
    },
    navigator: { onLine: false },
    ProfileSystem: {},
    setInterval(callback) {
      const timer = { callback };
      intervals.push(timer);
      return timer;
    },
    TimeUtils: { formatNotificationTime() { return ''; } },
    Toast: {},
    window: {
      KimbelaNetwork: {
        isOnline() { return online; },
        requestJson(key, url) {
          requests.push(url);
          return Promise.resolve(url === '/notifications/count' ? { count: 0 } : []);
        },
        onOnline(callback) {
          onlineHandler = callback;
          return () => {};
        },
        onOffline(callback) {
          offlineHandler = callback;
          return () => {};
        },
      },
    },
  };

  vm.runInNewContext(
    `${helpers}\nconst appState = globalThis.appState;\n${notificationCode}\nglobalThis.system = NotificationSystem;`,
    context,
  );

  return {
    clearedIntervals,
    intervals,
    requests,
    system: context.system,
    async restoreOnline() {
      online = true;
      context.navigator.onLine = true;
      onlineHandler();
      await new Promise(resolve => setImmediate(resolve));
    },
    goOffline() {
      online = false;
      context.navigator.onLine = false;
      offlineHandler();
    },
  };
}

test('notification polling is gated, deduplicated, and has one recovery hook', () => {
  assert.match(dashboardSource, /if \(!isDashboardOnline\(\)\) return false;/);
  assert.match(dashboardSource, /if \(this\.badgeRequest\) return this\.badgeRequest;/);
  assert.match(dashboardSource, /'notification-count',\s*'\/notifications\/count'/);
  assert.match(dashboardSource, /if \(!this\.onlineUnsubscribe && window\.KimbelaNetwork\)/);
  assert.match(dashboardSource, /stopPolling\(\)/);
  assert.match(dashboardSource, /KimbelaNetwork\.onOffline/);
});

test('notification polling pauses offline and refreshes once after recovery', async () => {
  const runtime = loadNotificationSystem();

  runtime.system.init();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(runtime.requests, []);
  assert.equal(runtime.intervals.length, 0);

  await runtime.restoreOnline();
  assert.equal(
    runtime.requests.filter(url => url === '/notifications/count').length,
    1,
  );
  assert.equal(runtime.intervals.length, 1);

  runtime.goOffline();
  assert.equal(runtime.clearedIntervals.length, 1);

  await runtime.restoreOnline();
  runtime.system.init();
  assert.ok(runtime.clearedIntervals.length >= 2);
  assert.equal(runtime.intervals.length, 3);
});

test('dashboard comments use offline-aware requests and retry feedback', () => {
  assert.match(dashboardSource, /`post-comments-modal-\$\{postId\}`/);
  assert.match(dashboardSource, /PostSystem\.viewComments\(\$\{postId\}\)/);
  assert.match(dashboardSource, /Tap “View all” to retry\./);
  assert.match(dashboardSource, /data\.comments \|\| data/);
});

test('group comments use the same offline and retry behavior', () => {
  assert.match(groupSource, /`group-comments-\$\{postId\}`/);
  assert.match(groupSource, /KimbelaNetwork\.commentFeedback\(error\)/);
  assert.match(groupSource, /Tap “View all” to retry\./);
});

test('birthday bootstrap stays deduplicated and pauses while offline', () => {
  assert.match(birthdaySource, /this\.checkInFlight = null;/);
  assert.match(birthdaySource, /if \(this\.checkInFlight\) return this\.checkInFlight;/);
  assert.match(birthdaySource, /"birthdays-today",\s*"\/api\/birthdays\/today"/);
  assert.match(
    birthdaySource,
    /if \(!window\.KimbelaNetwork \|\| window\.KimbelaNetwork\.isOnline\(\)\)/,
  );
});
