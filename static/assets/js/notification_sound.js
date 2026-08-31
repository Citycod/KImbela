(function () {
  'use strict';

  if (window.KimbelaNotificationSound) return;

  const STORAGE_KEY = 'kimbela_notification_sounds';
  const SOUND_URL = '/static/assets/audio/kimbela-notification.wav';
  const audio = new Audio(SOUND_URL);
  audio.preload = 'auto';
  audio.volume = 0.28;
  let unlocked = false;

  function isEnabled() {
    return localStorage.getItem(STORAGE_KEY) !== 'off';
  }

  function updateControls() {
    const enabled = isEnabled();
    document.querySelectorAll('[data-notification-sound-toggle]').forEach(button => {
      button.setAttribute('aria-checked', String(enabled));
      button.setAttribute('title', `Notification sounds ${enabled ? 'on' : 'off'}`);
      const status = button.querySelector('[data-notification-sound-status]');
      if (status) status.textContent = enabled ? 'On' : 'Off';
      const icon = button.querySelector('[data-notification-sound-icon]');
      if (icon) {
        icon.classList.toggle('bi-volume-up-fill', enabled);
        icon.classList.toggle('bi-volume-mute-fill', !enabled);
      }
    });
  }

  function unlock() {
    if (unlocked) return;
    const previousVolume = audio.volume;
    audio.volume = 0;
    const attempt = audio.play();
    if (!attempt || typeof attempt.then !== 'function') {
      unlocked = true;
      audio.pause();
      audio.currentTime = 0;
      audio.volume = previousVolume;
      return;
    }
    attempt.then(() => {
      unlocked = true;
      audio.pause();
      audio.currentTime = 0;
    }).catch(() => {
      unlocked = false;
    }).finally(() => {
      audio.volume = previousVolume;
    });
  }

  function play() {
    if (!isEnabled() || !unlocked) return Promise.resolve(false);
    try {
      audio.currentTime = 0;
      const attempt = audio.play();
      return attempt && typeof attempt.catch === 'function'
        ? attempt.then(() => true).catch(() => false)
        : Promise.resolve(true);
    } catch (_error) {
      return Promise.resolve(false);
    }
  }

  function setEnabled(enabled) {
    localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off');
    updateControls();
    return enabled;
  }

  function toggle() {
    unlock();
    return setEnabled(!isEnabled());
  }

  function bindControls() {
    updateControls();
    document.querySelectorAll('[data-notification-sound-toggle]').forEach(button => {
      if (button.dataset.soundBound === 'true') return;
      button.dataset.soundBound = 'true';
      button.addEventListener('click', toggle);
    });
  }

  ['pointerdown', 'touchstart', 'keydown'].forEach(eventName => {
    document.addEventListener(eventName, unlock, { once: true, passive: eventName !== 'keydown' });
  });
  document.addEventListener('DOMContentLoaded', bindControls);

  window.KimbelaNotificationSound = {
    audio,
    bindControls,
    isEnabled,
    play,
    setEnabled,
    toggle,
    unlock,
  };
})();
