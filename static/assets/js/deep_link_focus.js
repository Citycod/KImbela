(function () {
  'use strict';

  function focusDeepLinkTarget() {
    const rawHash = window.location.hash;
    if (!rawHash || !/^#(?:comment|post)-\d+$/.test(rawHash)) return false;

    const target = document.getElementById(rawHash.slice(1));
    if (!target) return false;

    target.setAttribute('tabindex', '-1');
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.focus({ preventScroll: true });
    target.classList.add('kimbela-deep-link-target');
    window.setTimeout(() => {
      target.classList.remove('kimbela-deep-link-target');
      target.removeAttribute('tabindex');
    }, 2800);
    return true;
  }

  window.KimbelaDeepLinkFocus = { focus: focusDeepLinkTarget };
  window.addEventListener('hashchange', focusDeepLinkTarget);
  window.addEventListener('DOMContentLoaded', () => {
    window.setTimeout(focusDeepLinkTarget, 80);
  });
})();
