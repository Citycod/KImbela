(function (global) {
  'use strict';

  const POST_SHARE_REVISION = '1';
  const POST_SHARE_ORIGIN = 'https://kimbela.com';

  function publicBaseUrl(baseUrl) {
    return String(
      baseUrl
      || global.publicBaseUrl
      || (global.location && global.location.origin)
      || '',
    ).replace(/\/$/, '');
  }

  function postUrl(postId, shareUrl = '', baseUrl = '') {
    const base = publicBaseUrl(baseUrl);
    let identifier = postId ? String(postId) : '';
    if (!identifier && shareUrl) {
      const sourceUrl = /^https?:\/\//i.test(shareUrl)
        ? new URL(shareUrl)
        : new URL(shareUrl, `${base}/`);
      const match = sourceUrl.pathname.match(/^\/(?:share\/)?post\/([^/]+)\/?$/);
      identifier = match ? decodeURIComponent(match[1]) : '';
    }
    if (!identifier) return '';

    const url = new URL(
      `/share/post/${encodeURIComponent(identifier)}`,
      `${POST_SHARE_ORIGIN}/`,
    );
    url.searchParams.set('v', POST_SHARE_REVISION);
    return url.toString();
  }

  function legacyCopyText(text) {
    const textarea = document.createElement('textarea');
    textarea.value = String(text || '');
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);

    let copied = false;
    try {
      copied = document.execCommand('copy');
    } finally {
      textarea.remove();
    }
    if (!copied) throw new Error('Copy is not supported by this browser');
  }

  async function copyText(text) {
    const value = String(text || '');
    if (!value) throw new Error('There is no link to copy');

    if (
      global.isSecureContext !== false
      && navigator.clipboard
      && typeof navigator.clipboard.writeText === 'function'
    ) {
      try {
        await navigator.clipboard.writeText(value);
        return;
      } catch (_error) {
        // Android webviews and some installed PWAs expose the API but reject it.
      }
    }

    legacyCopyText(value);
  }

  function showCopyStatus(message, isError) {
    const existing = document.getElementById('kimbela-share-status');
    if (existing) existing.remove();

    const status = document.createElement('div');
    status.id = 'kimbela-share-status';
    status.setAttribute('role', isError ? 'alert' : 'status');
    status.setAttribute('aria-live', isError ? 'assertive' : 'polite');
    status.textContent = message;
    Object.assign(status.style, {
      position: 'fixed',
      right: '1rem',
      bottom: '1rem',
      zIndex: '10000',
      padding: '0.75rem 1rem',
      borderRadius: '0.75rem',
      color: '#fff',
      background: isError ? '#b91c1c' : '#047857',
      boxShadow: '0 10px 25px rgba(15, 23, 42, 0.2)',
      fontSize: '0.875rem',
      fontWeight: '600',
    });
    document.body.appendChild(status);
    global.setTimeout(() => status.remove(), 3000);
  }

  async function copyFromTrigger(trigger) {
    if (!trigger || trigger.dataset.copyPending === 'true') return false;

    const postId = trigger.dataset.postId || '';
    const url = postUrl(postId, trigger.dataset.url || '');
    const label = trigger.querySelector('[data-copy-label]');
    const originalLabel = label ? label.textContent : '';
    trigger.dataset.copyPending = 'true';
    trigger.disabled = true;

    try {
      await copyText(url);
      if (label) label.textContent = 'Copied';
      showCopyStatus('Post link copied.', false);
      trigger.dispatchEvent(new CustomEvent('kimbela:copy-success', {
        bubbles: true,
        detail: { url },
      }));
      global.setTimeout(() => {
        if (label) label.textContent = originalLabel;
      }, 1800);
      return true;
    } catch (error) {
      if (label) label.textContent = 'Copy failed';
      showCopyStatus(error.message || 'Unable to copy this link.', true);
      trigger.dispatchEvent(new CustomEvent('kimbela:copy-error', {
        bubbles: true,
        detail: { error },
      }));
      global.setTimeout(() => {
        if (label) label.textContent = originalLabel;
      }, 2500);
      return false;
    } finally {
      trigger.dataset.copyPending = 'false';
      trigger.disabled = false;
    }
  }

  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-copy-post-link]');
    if (!trigger) return;
    event.preventDefault();
    copyFromTrigger(trigger);
  });

  global.KimbelaShare = Object.freeze({
    POST_SHARE_REVISION,
    POST_SHARE_ORIGIN,
    copyFromTrigger,
    copyText,
    postUrl,
  });
})(window);
