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
  let leadershipHandler = null;
  let leader = true;
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
      hidden: false,
      visibilityState: 'visible',
      addEventListener() {},
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
      KimbelaPassivePolling: {
        isLeader() { return leader; },
        onLeadershipChange(callback) {
          leadershipHandler = callback;
          callback(leader);
          return () => {};
        },
        publish() {},
        subscribe() { return () => {}; },
      },
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
    async setLeader(value) {
      leader = value;
      leadershipHandler(value);
      await new Promise(resolve => setImmediate(resolve));
    },
  };
}

function loadAdSystem() {
  const helpers = dashboardSource.slice(
    dashboardSource.indexOf('function isDashboardOnline()'),
    dashboardSource.indexOf('const MobileFeedAds ='),
  );
  const adCode = dashboardSource.slice(
    dashboardSource.indexOf('const AdSystem ='),
    dashboardSource.indexOf('// GROUPS SYSTEM'),
  );
  const requests = [];
  const timeouts = [];
  let claimAvailable = true;
  const document = {
    hidden: false,
    visibilityState: 'visible',
    addEventListener() {},
    cookie: '',
    getElementById() { return null; },
    querySelector() { return null; },
  };
  const context = {
    clearInterval() {},
    clearTimeout() {},
    document,
    fetch(url) {
      requests.push(url);
      return Promise.resolve({ ok: true, json: async () => ({}) });
    },
    navigator: { onLine: true },
    setInterval() { return 1; },
    setTimeout(callback, delay) {
      const timer = { callback, delay };
      timeouts.push(timer);
      return timer;
    },
    window: {
      KimbelaPassivePolling: {
        claimOnce() {
          if (!claimAvailable) return false;
          claimAvailable = false;
          return true;
        },
        isLeader() { return true; },
      },
    },
  };
  vm.runInNewContext(
    `${helpers}\nconst csrfToken = 'token';\n${adCode}\nglobalThis.system = AdSystem;`,
    context,
  );
  return { document, requests, system: context.system, timeouts };
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
  assert.equal(runtime.intervals.length, 2);
});

test('notification polling stops for a non-leader and refreshes once on takeover', async () => {
  const runtime = loadNotificationSystem();
  runtime.system.init();
  await runtime.restoreOnline();
  const requestsBeforeHandoff = runtime.requests.length;

  await runtime.setLeader(false);
  assert.ok(runtime.clearedIntervals.length >= 1);
  assert.equal(runtime.requests.length, requestsBeforeHandoff);

  await runtime.setLeader(true);
  assert.equal(runtime.requests.length, requestsBeforeHandoff + 1);
  assert.equal(runtime.intervals.length, 2);
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
  assert.match(birthdaySource, /this\.checkBirthdays\(\{ passive: true \}\)/);
  assert.match(birthdaySource, /window\.KimbelaPassivePolling\.isLeader\(\)/);
  assert.match(birthdaySource, /this\.stopPolling\(\)/);
});

test('ad cycling and impressions are visibility-aware and cross-tab deduplicated', () => {
  assert.match(dashboardSource, /if \(!isDashboardVisible\(\)\) return;/);
  assert.match(dashboardSource, /claimAdImpression\(adId\)/);
  assert.match(dashboardSource, /30 \* 60 \* 1000/);
  assert.match(dashboardSource, /document\.addEventListener\('visibilitychange'/);
});

test('hidden ad system schedules no cycle and duplicate impression writes are suppressed', async () => {
  const runtime = loadAdSystem();
  runtime.system.state.activeAds = [{ id: 5 }];

  runtime.system.scheduleNextAd();
  assert.equal(runtime.timeouts.length, 1);

  runtime.document.hidden = true;
  runtime.document.visibilityState = 'hidden';
  runtime.system.scheduleNextAd();
  runtime.system.displayNextAd();
  await runtime.system.trackAdImpression(5);
  assert.deepEqual(runtime.requests, []);

  runtime.document.hidden = false;
  runtime.document.visibilityState = 'visible';
  await runtime.system.trackAdImpression(5);
  await runtime.system.trackAdImpression(5);
  assert.deepEqual(runtime.requests, ['/api/ads/5/impression']);
});
