(function (global) {
  'use strict';

  const POST_SHARE_REVISION = '2';

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
    const rawUrl = shareUrl || (postId ? `/post/${encodeURIComponent(String(postId))}` : '');
    if (!rawUrl) return '';

    const url = /^https?:\/\//i.test(rawUrl)
      ? new URL(rawUrl)
      : new URL(rawUrl, `${base}/`);
    url.searchParams.set('share_v', POST_SHARE_REVISION);
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

  global.KimbelaShare = Object.freeze({
    POST_SHARE_REVISION,
    copyText,
    postUrl,
  });
})(window);
