(function (global) {
  'use strict';

  const DEFAULT_TIMEOUT_MS = 20000;

  function createController(options = {}) {
    const documentRef = options.document || global.document;
    const fetchImpl = options.fetch || global.fetch.bind(global);
    const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
    const notify = options.notify || function () {};
    let activeButton = null;
    let originalButtonHtml = '';

    function paymentModal() {
      return documentRef.getElementById('paymentModal');
    }

    function begin(button) {
      activeButton = button || null;
      originalButtonHtml = activeButton ? activeButton.innerHTML : '';
      if (activeButton) activeButton.disabled = true;
      const modal = paymentModal();
      if (modal) modal.classList.remove('hidden');
      if (documentRef.body) documentRef.body.style.overflow = 'hidden';
    }

    function finish() {
      const modal = paymentModal();
      if (modal) modal.classList.add('hidden');
      if (documentRef.body) documentRef.body.style.overflow = '';
      if (activeButton) {
        activeButton.innerHTML = originalButtonHtml;
        activeButton.disabled = false;
      }
      activeButton = null;
      originalButtonHtml = '';
    }

    function fail(message) {
      finish();
      notify(message || 'Unable to start payment. Please try again.', 'error');
    }

    async function requestJson(url, requestOptions = {}) {
      const AbortControllerImpl = options.AbortController || global.AbortController;
      const controller = AbortControllerImpl ? new AbortControllerImpl() : null;
      let timer = null;
      const timeout = new Promise((_, reject) => {
        timer = global.setTimeout(() => {
          if (controller) controller.abort();
          const timeoutError = new Error('Payment request timed out.');
          timeoutError.name = 'TimeoutError';
          reject(timeoutError);
        }, timeoutMs);
      });

      try {
        const response = await Promise.race([
          fetchImpl(url, {
            ...requestOptions,
            ...(controller ? { signal: controller.signal } : {}),
          }),
          timeout,
        ]);
        const text = await response.text();
        let payload = {};
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (_error) {
            throw new Error('Payment service returned an invalid response.');
          }
        }
        if (!response.ok) {
          const error = new Error(payload.error || 'Unable to start payment.');
          error.status = response.status;
          error.payload = payload;
          throw error;
        }
        return payload;
      } catch (error) {
        if (error && (error.name === 'AbortError' || error.name === 'TimeoutError')) {
          throw new Error('Payment request timed out. Please check your connection and try again.');
        }
        throw error;
      } finally {
        if (timer !== null) global.clearTimeout(timer);
      }
    }

    return Object.freeze({ begin, fail, finish, recover: finish, requestJson });
  }

  global.KimbelaBoostCheckout = Object.freeze({
    DEFAULT_TIMEOUT_MS,
    createController,
  });
})(window);
