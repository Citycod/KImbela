(function () {
  'use strict';

  if (window.KimbelaForegroundPush) return;

  let suppressor = () => false;
  const recentlyShown = new Map();

  function notificationKey(notification) {
    return notification.tag
      ? [notification.tag, notification.body || ''].join('|')
      : [notification.url, notification.title, notification.body].join('|');
  }

  function show(notification) {
    if (document.visibilityState !== 'visible' || !notification) return false;
    if (suppressor(notification)) return false;

    const key = notificationKey(notification);
    const now = Date.now();
    if (recentlyShown.has(key) && now - recentlyShown.get(key) < 5000) return false;
    recentlyShown.set(key, now);
    recentlyShown.forEach((shownAt, shownKey) => {
      if (now - shownAt > 30000) recentlyShown.delete(shownKey);
    });

    let existingToasts = document.querySelectorAll('.foreground-push-toast');
    if (existingToasts.length >= 3) existingToasts[0].remove();
    existingToasts = document.querySelectorAll('.foreground-push-toast');
    const toast = document.createElement(notification.url ? 'button' : 'div');
    toast.className = 'foreground-push-toast fixed top-4 right-4 z-[10020] max-w-sm rounded-xl bg-white px-4 py-3 text-left text-slate-900 shadow-strong';
    toast.style.cssText = [
      'position:fixed',
      `top:${1 + existingToasts.length * 5.5}rem`,
      'right:1rem',
      'z-index:10020',
      'max-width:calc(100% - 2rem)',
      'border-radius:0.75rem',
      'background:#fff',
      'padding:0.75rem 1rem',
      'color:#1f2937',
      'box-shadow:0 10px 25px rgba(0,0,0,0.2)',
      'border:1px solid rgba(124,58,237,0.18)',
      'cursor:pointer',
    ].join(';');
    toast.setAttribute('role', notification.url ? 'button' : 'status');
    toast.setAttribute('aria-live', 'polite');
    if (notification.url) {
      toast.type = 'button';
      toast.setAttribute('aria-label', `Open ${notification.title || 'notification'}`);
      toast.addEventListener('click', () => window.location.assign(notification.url));
    }

    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:flex-start;gap:0.75rem';
    toast.appendChild(row);

    if (notification.avatar) {
      const avatar = document.createElement('img');
      avatar.src = notification.avatar;
      avatar.alt = '';
      avatar.style.cssText = 'width:2.5rem;height:2.5rem;border-radius:9999px;object-fit:cover;flex:none';
      row.appendChild(avatar);
    }

    const copy = document.createElement('div');
    copy.style.cssText = 'min-width:0;flex:1';
    row.appendChild(copy);

    const titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;align-items:center;gap:0.35rem';
    copy.appendChild(titleRow);

    if (notification.eventType === 'chime' || notification.eventType === 'reply') {
      const chimeIcon = document.createElement('img');
      chimeIcon.src = '/static/assets/img/microphone2.png';
      chimeIcon.alt = '';
      chimeIcon.style.cssText = 'width:1rem;height:1rem;object-fit:contain';
      titleRow.appendChild(chimeIcon);
    } else {
      const indicator = document.createElement('i');
      indicator.className = notification.eventType === 'like'
        ? 'bi bi-heart-fill'
        : 'bi bi-chat-dots-fill';
      indicator.style.cssText = notification.eventType === 'like'
        ? 'color:#ec4899'
        : 'color:#7c3aed';
      indicator.setAttribute('aria-hidden', 'true');
      titleRow.appendChild(indicator);
    }

    const title = document.createElement('div');
    title.className = 'font-semibold text-sm';
    title.style.cssText = 'font-size:0.875rem;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    title.textContent = notification.title || 'Kimbela';
    titleRow.appendChild(title);

    if (notification.body) {
      const body = document.createElement('div');
      body.className = 'mt-1 text-sm';
      body.style.cssText = 'margin-top:0.25rem;font-size:0.875rem';
      body.textContent = notification.body;
      body.style.cssText += ';color:#4b5563;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
      copy.appendChild(body);
    }

    const timestamp = document.createElement('div');
    timestamp.className = 'mt-1 text-xs';
    timestamp.style.cssText = 'margin-top:0.25rem;font-size:0.72rem;color:#6b7280';
    const when = notification.timestamp ? new Date(notification.timestamp) : new Date();
    timestamp.textContent = Number.isNaN(when.getTime())
      ? 'Just now'
      : when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    copy.appendChild(timestamp);

    document.body.appendChild(toast);
    if (window.KimbelaNotificationSound) {
      window.KimbelaNotificationSound.play(notification.eventType);
    }
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
