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
    || (
      typeof window.matchMedia === 'function'
      && window.matchMedia('(display-mode: standalone)').matches
    )
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

async function resynchronizeCanonicalSubscription(registration) {
  if (!('Notification' in window) || Notification.permission !== 'granted') {
    return false;
  }

  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return false;

  return savePushSubscription(subscription);
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
    await resynchronizeCanonicalSubscription(canonicalRegistration);
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
  if (navigator.serviceWorker.addEventListener) {
    navigator.serviceWorker.addEventListener('message', function(event) {
      if (
        event.data
        && event.data.type === 'PUSH_SUBSCRIPTION_CHANGED'
        && event.data.subscription
      ) {
        savePushSubscription(event.data.subscription);
      }
    });
  }

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


// Lightweight PWA install discovery. Installation never requests push permission.
const INSTALL_PROMPT_ID = 'kimbela-install-prompt';
const INSTALL_STYLE_ID = 'kimbela-install-prompt-styles';
const INSTALL_DISMISSAL_KEY = 'kimbelaInstallDismissedAt';
const LEGACY_IOS_DISMISSAL_KEY = 'iosInstallPromptDismissed';
const INSTALL_DISMISSAL_MS = 14 * 24 * 60 * 60 * 1000;
const INSTALLING_FEEDBACK_MS = 20 * 1000;
const INSTALL_SUCCESS_FEEDBACK_MS = 3500;

let deferredInstallPrompt = null;
let installPromptElement = null;
let installCompleted = false;
let installDomReady = document.readyState !== 'loading';
let installFeedbackTimer = null;
let installReadinessPromise = null;

function readInstallStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function writeInstallStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    // Installation remains available when storage is blocked.
  }
}

function removeInstallStorage(key) {
  try {
    window.localStorage.removeItem(key);
  } catch (error) {
    // Nothing else is required when storage is blocked.
  }
}

function migrateLegacyInstallDismissal() {
  if (
    readInstallStorage(LEGACY_IOS_DISMISSAL_KEY)
    && !readInstallStorage(INSTALL_DISMISSAL_KEY)
  ) {
    writeInstallStorage(INSTALL_DISMISSAL_KEY, String(Date.now()));
  }
  removeInstallStorage(LEGACY_IOS_DISMISSAL_KEY);
}

function isInstallPromptDismissed() {
  const dismissedAt = Number(readInstallStorage(INSTALL_DISMISSAL_KEY));
  if (!Number.isFinite(dismissedAt) || dismissedAt <= 0) return false;

  const dismissalAge = Date.now() - dismissedAt;
  if (dismissalAge >= 0 && dismissalAge < INSTALL_DISMISSAL_MS) return true;

  removeInstallStorage(INSTALL_DISMISSAL_KEY);
  return false;
}

function dismissInstallPrompt() {
  writeInstallStorage(INSTALL_DISMISSAL_KEY, String(Date.now()));
  deferredInstallPrompt = null;
  hideInstallPrompt();
}

function clearInstallDismissal() {
  removeInstallStorage(INSTALL_DISMISSAL_KEY);
  removeInstallStorage(LEGACY_IOS_DISMISSAL_KEY);
}

function isIosOrIpadOs() {
  const userAgent = window.navigator.userAgent.toLowerCase();
  const classicIos = /iphone|ipad|ipod/.test(userAgent);
  const desktopModeIpad = (
    window.navigator.platform === 'MacIntel'
    && window.navigator.maxTouchPoints > 1
  );
  return classicIos || desktopModeIpad;
}

function canShowInstallPrompt() {
  return (
    !installCompleted
    && !isStandaloneDisplayMode()
    && !isInstallPromptDismissed()
  );
}

function createInstallElement(tagName, className, textContent) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (textContent) element.textContent = textContent;
  return element;
}

function ensureInstallPromptStyles() {
  if (document.getElementById(INSTALL_STYLE_ID)) return;

  const style = document.createElement('style');
  style.id = INSTALL_STYLE_ID;
  style.textContent = `
    .kimbela-install-card {
      position: fixed;
      left: 50%;
      bottom: max(16px, env(safe-area-inset-bottom));
      transform: translateX(-50%);
      width: min(calc(100% - 28px), 420px);
      box-sizing: border-box;
      padding: 16px;
      border: 1px solid rgba(15, 23, 42, 0.12);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.98);
      color: #1f2937;
      box-shadow: 0 14px 35px rgba(15, 23, 42, 0.18);
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }
    .kimbela-install-title {
      margin: 0 0 5px;
      color: #111827;
      font-size: 16px;
      font-weight: 700;
    }
    .kimbela-install-description {
      margin: 0;
      color: #4b5563;
      font-size: 14px;
      line-height: 1.45;
    }
    .kimbela-install-steps {
      margin: 12px 0 0;
      padding-left: 22px;
      color: #374151;
      font-size: 13px;
      line-height: 1.55;
    }
    .kimbela-install-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 14px;
    }
    .kimbela-install-button {
      min-height: 38px;
      padding: 8px 14px;
      border: 0;
      border-radius: 10px;
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
    .kimbela-install-button:focus-visible {
      outline: 3px solid rgba(13, 110, 253, 0.3);
      outline-offset: 2px;
    }
    .kimbela-install-button-primary {
      background: #0d6efd;
      color: #ffffff;
    }
    .kimbela-install-button-secondary {
      background: #f3f4f6;
      color: #374151;
    }
    .kimbela-install-button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    .kimbela-install-card[role="status"] {
      pointer-events: none;
    }
  `;
  document.head.appendChild(style);
}

function clearInstallFeedbackTimer() {
  if (installFeedbackTimer !== null) {
    window.clearTimeout(installFeedbackTimer);
    installFeedbackTimer = null;
  }
}

function hideInstallPrompt() {
  clearInstallFeedbackTimer();
  if (installPromptElement) {
    installPromptElement.remove();
    installPromptElement = null;
  }
}

function showInstallFeedback(state) {
  hideInstallPrompt();
  if (isStandaloneDisplayMode()) return false;

  ensureInstallPromptStyles();
  const card = createInstallElement('aside', 'kimbela-install-card');
  card.id = INSTALL_PROMPT_ID;
  card.setAttribute('role', 'status');
  card.setAttribute('aria-live', 'polite');

  const isSuccess = state === 'success';
  const title = createInstallElement(
    'h2',
    'kimbela-install-title',
    isSuccess ? 'Kimbela installed successfully' : 'Installing Kimbela…'
  );
  card.appendChild(title);

  if (!isSuccess) {
    card.appendChild(createInstallElement(
      'p',
      'kimbela-install-description',
      'This may take a moment on slower connections. You can continue using Kimbela.'
    ));
  }

  document.body.appendChild(card);
  installPromptElement = card;
  installFeedbackTimer = window.setTimeout(
    hideInstallPrompt,
    isSuccess ? INSTALL_SUCCESS_FEEDBACK_MS : INSTALLING_FEEDBACK_MS
  );
  return true;
}

function waitForInstallReadiness() {
  if (!('serviceWorker' in navigator)) return Promise.resolve(false);
  if (installReadinessPromise) return installReadinessPromise;

  const registrationPromise = window._swRegistrationPromise
    || navigator.serviceWorker.ready;
  installReadinessPromise = Promise.resolve(registrationPromise)
    .then(function(registration) {
      // The worker install fails if the manifest, icons, or offline page cannot
      // be precached, so an active canonical registration is our readiness gate.
      return Boolean(registration && registration.active);
    })
    .catch(function() {
      return false;
    });
  return installReadinessPromise;
}

function revealInstallPromptWhenReady(mode) {
  if (!installDomReady) return;

  waitForInstallReadiness().then(function(ready) {
    if (!ready || !installDomReady) return;
    showInstallPrompt(mode);
  });
}

async function runNativeInstallPrompt(installButton) {
  const promptEvent = deferredInstallPrompt;
  if (!promptEvent) return;

  deferredInstallPrompt = null;
  installButton.disabled = true;

  try {
    await promptEvent.prompt();
    const choice = await promptEvent.userChoice;
    if (choice && choice.outcome === 'accepted') {
      clearInstallDismissal();
      if (!installCompleted) showInstallFeedback('installing');
      return;
    }

    dismissInstallPrompt();
  } catch (error) {
    console.error('Unable to open the PWA install prompt:', error);
    hideInstallPrompt();
  }
}

function showInstallPrompt(mode) {
  if (!canShowInstallPrompt() || installPromptElement) return false;
  if (mode === 'native' && !deferredInstallPrompt) return false;

  ensureInstallPromptStyles();

  const card = createInstallElement('aside', 'kimbela-install-card');
  card.id = INSTALL_PROMPT_ID;
  card.setAttribute('role', 'dialog');
  card.setAttribute('aria-labelledby', 'kimbela-install-title');

  const title = createInstallElement(
    'h2',
    'kimbela-install-title',
    'Install Kimbela'
  );
  title.id = 'kimbela-install-title';
  card.appendChild(title);

  const description = createInstallElement(
    'p',
    'kimbela-install-description',
    mode === 'ios'
      ? 'Add Kimbela to your Home Screen for faster access and notifications.'
      : 'Add Kimbela to your device for faster access and notifications.'
  );
  card.appendChild(description);

  let instructions = null;
  if (mode === 'ios') {
    instructions = createInstallElement('ol', 'kimbela-install-steps');
    instructions.tabIndex = -1;
    [
      'Tap the Share button',
      'Choose “Add to Home Screen”',
      'Tap Add',
    ].forEach(function(instruction) {
      instructions.appendChild(createInstallElement('li', '', instruction));
    });
    card.appendChild(instructions);
  }

  const actions = createInstallElement('div', 'kimbela-install-actions');

  if (mode === 'native') {
    const installButton = createInstallElement(
      'button',
      'kimbela-install-button kimbela-install-button-primary',
      'Install'
    );
    installButton.type = 'button';
    installButton.dataset.action = 'install';
    installButton.addEventListener('click', function() {
      return runNativeInstallPrompt(installButton);
    });
    actions.appendChild(installButton);
  } else {
    const helpButton = createInstallElement(
      'button',
      'kimbela-install-button kimbela-install-button-primary',
      'How to install'
    );
    helpButton.type = 'button';
    helpButton.dataset.action = 'ios-help';
    helpButton.addEventListener('click', function() {
      if (instructions && instructions.focus) instructions.focus();
    });
    actions.appendChild(helpButton);
  }

  const dismissButton = createInstallElement(
    'button',
    'kimbela-install-button kimbela-install-button-secondary',
    'Not now'
  );
  dismissButton.type = 'button';
  dismissButton.dataset.action = 'dismiss';
  dismissButton.addEventListener('click', dismissInstallPrompt);
  actions.appendChild(dismissButton);
  card.appendChild(actions);

  document.body.appendChild(card);
  installPromptElement = card;
  return true;
}

function initializeInstallExperience() {
  installDomReady = true;
  migrateLegacyInstallDismissal();

  if (isStandaloneDisplayMode()) {
    installCompleted = true;
    hideInstallPrompt();
    return;
  }

  if (isIosOrIpadOs()) {
    revealInstallPromptWhenReady('ios');
  } else if (deferredInstallPrompt) {
    revealInstallPromptWhenReady('native');
  }
}

window.addEventListener('beforeinstallprompt', function(event) {
  event.preventDefault();
  deferredInstallPrompt = event;
  revealInstallPromptWhenReady('native');
});

window.addEventListener('appinstalled', function() {
  deferredInstallPrompt = null;
  installCompleted = true;
  clearInstallDismissal();
  showInstallFeedback('success');
});

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', initializeInstallExperience, { once: true });
} else {
  initializeInstallExperience();
}

if (typeof window.matchMedia === 'function') {
  const standaloneMediaQuery = window.matchMedia('(display-mode: standalone)');
  if (standaloneMediaQuery.addEventListener) {
    standaloneMediaQuery.addEventListener('change', function(event) {
      if (event.matches) {
        installCompleted = true;
        hideInstallPrompt();
      }
    });
  }
}
