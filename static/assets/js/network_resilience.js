(function () {
  'use strict';

  if (window.KimbelaNetwork) return;

  const inFlight = new Map();
  const listeners = {
    online: new Set(),
    offline: new Set(),
  };
  let online = navigator.onLine !== false;
  let offlineNoticeTimer = null;
  let noticeHideTimer = null;
  let noticeVisible = false;

  function createError(kind, message, cause) {
    const error = new Error(message);
    error.kind = kind;
    if (cause) error.cause = cause;
    return error;
  }

  function isOnline() {
    return online && navigator.onLine !== false;
  }

  function classifyError(error) {
    if (error && error.kind) return error.kind;
    if (!isOnline()) return 'offline';
    const message = String((error && error.message) || error || '');
    if (
      (error && error.name === 'TypeError') ||
      /failed to fetch|networkerror|network error|load failed/i.test(message)
    ) {
      return 'network';
    }
    return 'server';
  }

  function runOnce(key, task) {
    if (!isOnline()) {
      return Promise.reject(
        createError('offline', "You're offline. Reconnect and try again."),
      );
    }
    if (inFlight.has(key)) return inFlight.get(key);

    const request = Promise.resolve()
      .then(task)
      .catch((error) => {
        if (classifyError(error) === 'network' && !error.kind) {
          throw createError('network', 'The network request failed.', error);
        }
        throw error;
      })
      .finally(() => inFlight.delete(key));
    inFlight.set(key, request);
    return request;
  }

  function requestJson(key, url, options) {
    return runOnce(key, async () => {
      const response = await fetch(url, options);
      if (!response.ok) {
        throw createError(
          'server',
          `Request failed with status ${response.status}`,
        );
      }
      return response.json();
    });
  }

  function commentFeedback(error) {
    const kind = classifyError(error);
    if (kind === 'offline') {
      return "You're offline. Reconnect to load Chimes.";
    }
    if (kind === 'network') {
      return 'Connection lost. Reconnect and try loading Chimes again.';
    }
    return 'Failed to load Chimes';
  }

  function ensureNotice() {
    let notice = document.getElementById('kimbelaConnectivityNotice');
    if (notice || !document.body) return notice;

    notice = document.createElement('div');
    notice.id = 'kimbelaConnectivityNotice';
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    notice.className =
      'fixed left-1/2 bottom-4 z-[10000] hidden max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-xl px-4 py-2.5 text-center text-sm font-medium text-white shadow-lg';
    notice.style.cssText = [
      'position:fixed',
      'left:50%',
      'bottom:1rem',
      'z-index:10000',
      'display:none',
      'max-width:calc(100% - 2rem)',
      'transform:translateX(-50%)',
      'border-radius:0.75rem',
      'padding:0.625rem 1rem',
      'color:white',
      'font-size:0.875rem',
      'font-weight:500',
      'text-align:center',
      'box-shadow:0 10px 15px -3px rgba(0,0,0,0.2)',
    ].join(';');
    document.body.appendChild(notice);
    return notice;
  }

  function showNotice(message, restored) {
    const notice = ensureNotice();
    if (!notice) return;
    if (noticeHideTimer) clearTimeout(noticeHideTimer);
    notice.textContent = message;
    notice.classList.remove('hidden', 'bg-gray-900', 'bg-emerald-600');
    notice.classList.add(restored ? 'bg-emerald-600' : 'bg-gray-900');
    notice.style.display = 'block';
    notice.style.backgroundColor = restored ? '#059669' : '#111827';
    noticeVisible = true;

    if (restored) {
      noticeHideTimer = setTimeout(() => {
        notice.classList.add('hidden');
        notice.style.display = 'none';
        noticeVisible = false;
      }, 2500);
    }
  }

  function notify(type) {
    listeners[type].forEach((callback) => {
      try {
        callback();
      } catch (error) {
        console.error(`Kimbela ${type} recovery callback failed`, error);
      }
    });
  }

  function handleOffline() {
    if (!online) return;
    online = false;
    notify('offline');
    if (offlineNoticeTimer) clearTimeout(offlineNoticeTimer);
    offlineNoticeTimer = setTimeout(() => {
      if (!isOnline()) {
        showNotice(
          "You're offline — some features will update when you're connected.",
          false,
        );
      }
    }, 700);
  }

  function handleOnline() {
    if (online) return;
    online = true;
    if (offlineNoticeTimer) {
      clearTimeout(offlineNoticeTimer);
      offlineNoticeTimer = null;
    }
    if (noticeVisible) showNotice("You're back online.", true);
    notify('online');
  }

  function subscribe(type, callback) {
    listeners[type].add(callback);
    return () => listeners[type].delete(callback);
  }

  window.addEventListener('offline', handleOffline);
  window.addEventListener('online', handleOnline);

  if (!online) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        showNotice(
          "You're offline — some features will update when you're connected.",
          false,
        );
      }, { once: true });
    } else {
      showNotice(
        "You're offline — some features will update when you're connected.",
        false,
      );
    }
  }

  window.KimbelaNetwork = {
    isOnline,
    runOnce,
    requestJson,
    classifyError,
    commentFeedback,
    onOnline(callback) {
      return subscribe('online', callback);
    },
    onOffline(callback) {
      return subscribe('offline', callback);
    },
  };
})();
