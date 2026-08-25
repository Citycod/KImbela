// Public VAPID key matching the backend
const VAPID_PUBLIC_KEY = 'BDaLggC0hKS5i9uXjY9Yt_Bucoo0S9ciHIJ5xZ2tvfcs9ZMpfFnPS_cFGlSQ8pflrX-vpX8BCuw5Y4mgGA6ih9c';

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

// Register service worker on load (needed for caching), but do NOT auto-prompt for push
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    // Unregister any old /static/ scoped service workers to prevent orphaned instances
    navigator.serviceWorker.getRegistrations().then(function(registrations) {
      for (let registration of registrations) {
        if (registration.scope.includes('/static/')) {
          console.log('Unregistering old /static/ scoped Service Worker');
          registration.unregister();
        }
      }
    }).then(function() {
      // Register the new root-scoped service worker
      navigator.serviceWorker.register('/sw.js')
        .then(function(registration) {
          console.log('ServiceWorker registration successful with scope: ', registration.scope);
          // Store registration for later use by enablePushNotifications()
          window._swRegistration = registration;
        }, function(err) {
          console.error('ServiceWorker registration failed: ', err);
        });
    });
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
  var regPromise = window._swRegistration
    ? Promise.resolve(window._swRegistration)
    : navigator.serviceWorker.ready;

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
  
  // First, check if there's an existing subscription (with old keys) and clear it
  return registration.pushManager.getSubscription()
    .then(function(existingSubscription) {
      if (existingSubscription) {
        console.log('Clearing old subscription before re-subscribing...');
        return existingSubscription.unsubscribe();
      }
    })
    .then(function() {
      // Now create a fresh subscription with the new keys
      return registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey
      });
    })
    .then(function(subscription) {
      console.log('User is subscribed to Push:', subscription);

      const payload = JSON.parse(JSON.stringify(subscription));
      payload.isStandalone = ('standalone' in window.navigator && window.navigator.standalone) || window.matchMedia('(display-mode: standalone)').matches;

      // Send subscription to backend with CSRF token
      return fetch('/api/pwa/subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getPushCsrfToken()
        },
        body: JSON.stringify(payload)
      })
      .then(function(response) {
        if (!response.ok) {
          console.error('Failed to save subscription on backend (status ' + response.status + ')');
          return false;
        }
        console.log('Subscription saved on backend.');
        return true;
      })
      .catch(function(err) {
        console.error('Error saving subscription:', err);
        return false;
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
