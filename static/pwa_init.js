// Public VAPID key matching the backend
const VAPID_PUBLIC_KEY = 'BEDkdKrV_wzT_rf6xiiafzstYXCVdZsL9BH8_-l9Lnh6Iiv5E86CsQ0Rzl_guT3X-zk1OglKTYNEgGXYARQq7_k';

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

if ('serviceWorker' in navigator && 'PushManager' in window) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/sw.js')
      .then(function(registration) {
        console.log('ServiceWorker registration successful with scope: ', registration.scope);
        
        // Request notification permission and subscribe
        if (Notification.permission !== 'denied') {
          Notification.requestPermission().then(function(permission) {
            if (permission === 'granted') {
              subscribeUser(registration);
            }
          });
        }
      }, function(err) {
        console.error('ServiceWorker registration failed: ', err);
      });
  });
}

function subscribeUser(registration) {
  const applicationServerKey = urlBase64ToUint8Array(VAPID_PUBLIC_KEY);
  registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: applicationServerKey
  })
  .then(function(subscription) {
    console.log('User is subscribed to Push:', subscription);
    
    // Send subscription to backend
    fetch('/api/pwa/subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(subscription)
    })
    .then(response => {
      if (!response.ok) {
        console.error('Failed to save subscription on backend');
      }
    })
    .catch(err => console.error('Error saving subscription:', err));
    
  })
  .catch(function(err) {
    console.log('Failed to subscribe the user: ', err);
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
