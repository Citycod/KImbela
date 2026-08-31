const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const soundSource = fs.readFileSync(
  path.resolve(__dirname, '../../static/assets/js/notification_sound.js'),
  'utf8',
);

class FakeClassList {
  constructor() { this.values = new Set(); }
  toggle(value, force) {
    if (force) this.values.add(value);
    else this.values.delete(value);
  }
}

class FakeControl {
  constructor() {
    this.attributes = new Map();
    this.classList = new FakeClassList();
    this.dataset = {};
    this.handlers = new Map();
    this.icon = { classList: new FakeClassList() };
    this.status = { textContent: '' };
  }
  addEventListener(type, handler) { this.handlers.set(type, handler); }
  querySelector(selector) {
    if (selector === '[data-notification-sound-icon]') return this.icon;
    if (selector === '[data-notification-sound-status]') return this.status;
    return null;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
}

function createRuntime({ rejectPlayback = false } = {}) {
  const documentHandlers = new Map();
  const control = new FakeControl();
  const storage = new Map();
  const audioInstances = [];

  class FakeAudio {
    constructor(url) {
      this.currentTime = 0;
      this.pauseCalls = 0;
      this.playCalls = 0;
      this.preload = '';
      this.url = url;
      this.volume = 1;
      audioInstances.push(this);
    }
    pause() { this.pauseCalls += 1; }
    play() {
      this.playCalls += 1;
      return rejectPlayback
        ? Promise.reject(new Error('autoplay denied'))
        : Promise.resolve();
    }
  }

  const document = {
    addEventListener(type, handler) { documentHandlers.set(type, handler); },
    querySelectorAll(selector) {
      return selector === '[data-notification-sound-toggle]' ? [control] : [];
    },
  };
  const localStorage = {
    getItem(key) { return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value) { storage.set(key, String(value)); },
  };
  const window = {};
  vm.runInNewContext(soundSource, {
    Audio: FakeAudio,
    Promise,
    document,
    localStorage,
    window,
  }, { filename: 'static/assets/js/notification_sound.js' });

  return {
    audio: audioInstances[0],
    audioInstances,
    control,
    documentHandlers,
    sound: window.KimbelaNotificationSound,
    storage,
  };
}

test('notification sounds default on and use one shared local Audio object', () => {
  const runtime = createRuntime();
  runtime.documentHandlers.get('DOMContentLoaded')();

  assert.equal(runtime.sound.isEnabled(), true);
  assert.equal(runtime.audioInstances.length, 1);
  assert.equal(runtime.audio.url, '/static/assets/audio/kimbela-notification.wav');
  assert.equal(runtime.control.attributes.get('aria-checked'), 'true');
  assert.equal(runtime.control.status.textContent, 'On');
});

test('sound preference off prevents playback without affecting notification flow', async () => {
  const runtime = createRuntime();
  runtime.sound.setEnabled(false);

  assert.equal(await runtime.sound.play('message'), false);
  assert.equal(runtime.audio.playCalls, 0);
  assert.equal(runtime.storage.get('kimbela_notification_sounds'), 'off');
});

test('unlocked sound plays repeatedly through the shared Audio object', async () => {
  const runtime = createRuntime();

  runtime.sound.unlock();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(await runtime.sound.play('message'), true);
  assert.equal(await runtime.sound.play('like'), true);

  assert.equal(runtime.audioInstances.length, 1);
  assert.equal(runtime.audio.playCalls, 3);
});

test('browser playback rejection is contained', async () => {
  const runtime = createRuntime({ rejectPlayback: true });

  runtime.sound.unlock();
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(await runtime.sound.play('message'), false);
  assert.equal(runtime.sound.isEnabled(), true);
});
