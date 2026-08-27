// Public VAPID key matching the backend
const VAPID_PUBLIC_KEY = 'BDaLggC0hKS5i9uXjY9Yt_Bucoo0S9ciHIJ5xZ2tvfcs9ZMpfFnPS_cFGlSQ8pflrX-vpX8BCuw5Y4mgGA6ih9c';
const CANONICAL_SERVICE_WORKER_PATH = '/sw.js';
const CANONICAL_SERVICE_WORKER_SCOPE = '/';
const LEGACY_SERVICE_WORKER_PATH = '/static/sw.js';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/\-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Helper to get CSRF token from meta tag or window global
function getPushCsrfToken() {
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.getAttribute('content');
  if (typeof window.csrfToken === 'string') return window.csrfToken;
  return '';
}

function isStandaloneDisplayMode() {
  return (
    ('standalone' in window.navigator && window.navigator.standalone)
    || window.matchMedia('(display-mode: standalone)').matches
  );
}

function getRegistrationScriptPath(registration) {
  const worker = registration.active || registration.waiting || registration.installing;
  if (!worker || !worker.scriptURL) return '';

  try {
    return new URL(worker.scriptURL, window.location.origin).pathname;
  } catch (error) {
    return '';
  }
}

function waitForRegistrationActivation(registration) {
  if (registration.active) return Promise.resolve(registration);

  const worker = registration.installing || registration.waiting;
  if (!worker) {
    return Promise.reject(new Error('Service worker registration has no worker'));
  }

  if (worker.state === 'activated') return Promise.resolve(registration);
  if (worker.state === 'redundant') {
    return Promise.reject(new Error('Service worker installation failed'));
  }

  return new Promise(function(resolve, reject) {
    worker.addEventListener('statechange', function() {
      if (worker.state === 'activated') {
        resolve(registration);
      } else if (worker.state === 'redundant') {
        reject(new Error('Service worker installation failed'));
      }
    });
  });
}

function savePushSubscription(subscription) {
  const payload = JSON.parse(JSON.stringify(subscription));
  payload.isStandalone = isStandaloneDisplayMode();

  return fetch('/api/pwa/subscribe', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getPushCsrfToken()
    },
    body: JSON.stringify(payload)
  }).then(function(response) {
    const contentType = response.headers
      ? response.headers.get('content-type') || ''
      : '';
    return response.ok && !response.redirected && contentType.includes('application/json');
  }).catch(function(error) {
    console.error('Error saving push subscription:', error);
    return false;
  });
}

function removeStoredPushSubscription(subscription) {
  return fetch('/api/pwa/unsubscribe', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getPushCsrfToken()
    },
    body: JSON.stringify({ endpoint: subscription.endpoint })
  }).then(function(response) {
    return !response.redirected && (response.ok || response.status === 404);
  }).catch(function(error) {
    console.error('Error removing legacy push subscription:', error);
    return false;
  });
}

function getExistingRegistrations() {
  if (navigator.serviceWorker.getRegistrations) {
    return navigator.serviceWorker.getRegistrations();
  }

  if (navigator.serviceWorker.getRegistration) {
    return navigator.serviceWorker.getRegistration('/static/').then(function(registration) {
      return registration ? [registration] : [];
    });
  }

  return Promise.resolve([]);
}

async function initializeCanonicalServiceWorker() {
  const registrations = await getExistingRegistrations();
  const legacyRegistrations = registrations.filter(function(registration) {
    return getRegistrationScriptPath(registration) === LEGACY_SERVICE_WORKER_PATH;
  });
  const canonicalAlreadyExisted = registrations.some(function(registration) {
    return getRegistrationScriptPath(registration) === CANONICAL_SERVICE_WORKER_PATH;
  });

  const legacyStates = [];
  for (const registration of legacyRegistrations) {
    legacyStates.push({
      registration: registration,
      subscription: await registration.pushManager.getSubscription()
    });
  }

  const hasLegacyPushSubscription = legacyStates.some(function(state) {
    return Boolean(state.subscription);
  });

  if (!hasLegacyPushSubscription) {
    await Promise.all(legacyStates.map(function(state) {
      return state.registration.unregister();
    }));
  }

  const canonicalRegistration = await navigator.serviceWorker.register(
    CANONICAL_SERVICE_WORKER_PATH,
    { scope: CANONICAL_SERVICE_WORKER_SCOPE }
  );
  try {
    await waitForRegistrationActivation(canonicalRegistration);
  } catch (error) {
    if (!canonicalAlreadyExisted) {
      await canonicalRegistration.unregister().catch(function() {});
    }
    throw error;
  }

  if (!hasLegacyPushSubscription) {
    return canonicalRegistration;
  }

  let canonicalSubscription = null;
  let createdCanonicalSubscription = false;

  try {
    canonicalSubscription = await canonicalRegistration.pushManager.getSubscription();
    if (!canonicalSubscription) {
      if (!('Notification' in window) || Notification.permission !== 'granted') {
        throw new Error('Push permission is not available for subscription migration');
      }

      canonicalSubscription = await canonicalRegistration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
      });
      createdCanonicalSubscription = true;
    }

    const stored = await savePushSubscription(canonicalSubscription);
    if (!stored) {
      throw new Error('Canonical push subscription could not be stored');
    }

    for (const state of legacyStates) {
      if (state.subscription) {
        await removeStoredPushSubscription(state.subscription);
        await state.subscription.unsubscribe().catch(function(error) {
          console.error('Failed to unsubscribe legacy browser push endpoint:', error);
        });
      }
      await state.registration.unregister().catch(function(error) {
        console.error('Failed to unregister legacy service worker:', error);
      });
    }

    return canonicalRegistration;
  } catch (error) {
    if (createdCanonicalSubscription && canonicalSubscription) {
      await canonicalSubscription.unsubscribe().catch(function() {});
    }
    if (!canonicalAlreadyExisted) {
      await canonicalRegistration.unregister().catch(function() {});
    }
    throw error;
  }
}

// Register one canonical root-scoped worker. Permission prompts remain user initiated.
if ('serviceWorker' in navigator) {
  window._swRegistrationPromise = new Promise(function(resolve, reject) {
    window.addEventListener('load', function() {
      initializeCanonicalServiceWorker().then(resolve, reject);
    }, { once: true });
  });

  window._swRegistrationPromise.then(function(registration) {
    window._swRegistration = registration;
    console.log('ServiceWorker registration successful with scope: ', registration.scope);
  }).catch(function(error) {
    console.error('ServiceWorker registration or migration failed: ', error);
  });
}

/**
 * Call this from a user-initiated action (button click) to request push permission
 * and subscribe. Do NOT call on page load — browsers penalize auto-prompts.
 *
 * Usage: <button onclick="enablePushNotifications()">Enable Notifications</button>
 *
 * Returns a Promise that resolves to true (subscribed) or false (denied/unsupported).
 */
window.enablePushNotifications = function() {
  // Check browser support
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    alert('Push notifications are not supported in this browser. For the best experience, use Chrome or add Kimbela to your home screen.');
    return Promise.resolve(false);
  }

  // Wait for SW registration
  var regPromise = window._swRegistrationPromise
    || (window._swRegistration
      ? Promise.resolve(window._swRegistration)
      : navigator.serviceWorker.ready);

  return regPromise.then(function(registration) {
    return Notification.requestPermission().then(function(permission) {
      if (permission !== 'granted') {
        console.log('Push notification permission denied.');
        return false;
      }
      return subscribeUser(registration);
    });
  }).catch(function(err) {
    console.error('Error enabling push notifications:', err);
    return false;
  });
};

function subscribeUser(registration) {
  const applicationServerKey = urlBase64ToUint8Array(VAPID_PUBLIC_KEY);

  return registration.pushManager.getSubscription()
    .then(function(existingSubscription) {
      if (existingSubscription) {
        return existingSubscription;
      }

      return registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey
      });
    })
    .then(function(subscription) {
      return savePushSubscription(subscription).then(function(stored) {
        if (!stored) {
          console.error('Failed to save subscription on backend.');
        }
        return stored;
      });
    })
    .catch(function(err) {
      console.log('Failed to subscribe the user: ', err);
      return false;
    });
}


// iOS Add to Home Screen Prompt
function showIosInstallPrompt() {
  const isIos = () => {
    const userAgent = window.navigator.userAgent.toLowerCase();
    return /iphone|ipad|ipod/.test(userAgent);
  };

  const isStandalone = () => {
    return ('standalone' in window.navigator) && window.navigator.standalone;
  };

  if (isIos() && !isStandalone() && !localStorage.getItem('iosInstallPromptDismissed')) {
    // Inject CSS
    const style = document.createElement('style');
    style.innerHTML = `
      .ios-prompt-container {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        width: 90%;
        max-width: 400px;
        background-color: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        border-radius: 12px;
        padding: 15px;
        z-index: 999999;
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        animation: slideUp 0.5s ease-out;
      }
      .ios-prompt-container p {
        margin: 0 0 10px 0;
        font-size: 14px;
        color: #333;
        line-height: 1.4;
      }
      .ios-prompt-close {
        position: absolute;
        top: 5px;
        right: 10px;
        background: none;
        border: none;
        font-size: 20px;
        color: #999;
        cursor: pointer;
      }
      @keyframes slideUp {
        from { bottom: -100px; opacity: 0; }
        to { bottom: 20px; opacity: 1; }
      }
      .ios-icon-share {
        display: inline-block;
        width: 16px;
        height: 16px;
        background: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" fill="none" stroke="%230d6efd" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>') no-repeat center;
        vertical-align: middle;
      }
      .ios-icon-add {
        display: inline-block;
        width: 16px;
        height: 16px;
        background: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" fill="none" stroke="%23333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>') no-repeat center;
        vertical-align: middle;
      }
    `;
    document.head.appendChild(style);

    // Inject HTML
    const prompt = document.createElement('div');
    prompt.className = 'ios-prompt-container';
    prompt.innerHTML = `
      <button class="ios-prompt-close" aria-label="Close">&times;</button>
      <p><strong>Install Kimbela</strong></p>
      <p>Install this app on your device for the best experience. Tap the <span class="ios-icon-share"></span> <strong>Share</strong> button at the bottom of your screen, then tap <span class="ios-icon-add"></span> <strong>Add to Home Screen</strong>.</p>
    `;
    document.body.appendChild(prompt);

    // Handle Close
    prompt.querySelector('.ios-prompt-close').addEventListener('click', () => {
      prompt.style.display = 'none';
      localStorage.setItem('iosInstallPromptDismissed', 'true');
    });
  }
}

// Call on load
window.addEventListener('DOMContentLoaded', showIosInstallPrompt);
