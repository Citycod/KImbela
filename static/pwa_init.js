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
