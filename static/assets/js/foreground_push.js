(function () {
  'use strict';

  if (window.KimbelaForegroundPush) return;

  let suppressor = () => false;

  function show(notification) {
    if (document.visibilityState !== 'visible' || !notification) return false;
    if (suppressor(notification)) return false;

    document.querySelectorAll('.foreground-push-toast').forEach(toast => toast.remove());
    const toast = document.createElement('div');
    toast.className = 'foreground-push-toast fixed top-4 right-4 z-[10020] max-w-sm rounded-xl bg-blue-600 px-4 py-3 text-white shadow-strong';
    toast.style.cssText = [
      'position:fixed',
      'top:1rem',
      'right:1rem',
      'z-index:10020',
      'max-width:calc(100% - 2rem)',
      'border-radius:0.75rem',
      'background:#2563eb',
      'padding:0.75rem 1rem',
      'color:#fff',
      'box-shadow:0 10px 25px rgba(0,0,0,0.2)',
    ].join(';');
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');

    const title = document.createElement('div');
    title.className = 'font-semibold text-sm';
    title.style.cssText = 'font-size:0.875rem;font-weight:600';
    title.textContent = notification.title || 'Kimbela';
    toast.appendChild(title);

    if (notification.body) {
      const body = document.createElement('div');
      body.className = 'mt-1 text-sm';
      body.style.cssText = 'margin-top:0.25rem;font-size:0.875rem';
      body.textContent = notification.body;
      toast.appendChild(body);
    }

    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
    return true;
  }

  function handleServiceWorkerMessage(event) {
    if (event.data?.type !== 'PUSH_FOREGROUND_NOTIFICATION') return false;
    return show(event.data.notification);
  }

  window.KimbelaForegroundPush = {
    handleServiceWorkerMessage,
    setSuppressor(callback) {
      suppressor = typeof callback === 'function' ? callback : () => false;
    },
    show,
  };

  if (
    typeof navigator !== 'undefined'
    && navigator.serviceWorker
    && typeof navigator.serviceWorker.addEventListener === 'function'
  ) {
    navigator.serviceWorker.addEventListener('message', handleServiceWorkerMessage);
  }
})();
