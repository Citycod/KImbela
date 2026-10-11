(function loginSubmissionState(global, document) {
  'use strict';

  function initializeLoginForm(root = document) {
    const form = root.getElementById('loginForm');
    const submitButton = root.getElementById('loginSubmitButton');
    if (!form || !submitButton || form.dataset.submissionStateBound === 'true') {
      return null;
    }

    form.dataset.submissionStateBound = 'true';
    let submitting = false;

    const reset = () => {
      submitting = false;
      submitButton.disabled = false;
      submitButton.setAttribute('aria-disabled', 'false');
      submitButton.removeAttribute('aria-busy');
      submitButton.textContent = submitButton.dataset.idleLabel || 'Sign In';
    };

    form.addEventListener('submit', (event) => {
      if (submitting) {
        event.preventDefault();
        return;
      }

      if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
        reset();
        return;
      }

      submitting = true;
      submitButton.disabled = true;
      submitButton.setAttribute('aria-disabled', 'true');
      submitButton.setAttribute('aria-busy', 'true');
      submitButton.textContent = submitButton.dataset.loadingLabel || 'Signing in...';

      // Another validation listener can still cancel this submission. Restore the
      // control after all submit listeners have had a chance to run.
      global.setTimeout(() => {
        if (event.defaultPrevented) reset();
      }, 0);
    });

    global.addEventListener('pageshow', reset);
    reset();
    return { reset };
  }

  global.KimbelaLogin = { initializeLoginForm };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initializeLoginForm());
  } else {
    initializeLoginForm();
  }
})(window, document);
