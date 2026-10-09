(function (global) {
  'use strict';

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

  global.KimbelaShare = Object.freeze({ copyText });
})(window);
