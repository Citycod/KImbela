(function () {
  'use strict';

  if (window.CommentComposer) return;

  const emojis = [
    '😀', '😂', '🥰', '😍', '😊', '😎', '🤔', '😢',
    '😭', '😡', '👍', '👏', '🙌', '🙏', '❤️', '🔥',
    '🎉', '💯', '✨', '🤗', '😮', '😉', '💪', '🌟',
  ];

  function composerFor(element) {
    return element && element.closest
      ? element.closest('.comment-composer')
      : null;
  }

  function inputFor(composer) {
    return composer ? composer.querySelector('.comment-composer-input') : null;
  }

  function sendButtonFor(composer) {
    return composer ? composer.querySelector('.comment-composer-send') : null;
  }

  function isOnline() {
    return window.KimbelaNetwork
      ? window.KimbelaNetwork.isOnline()
      : navigator.onLine !== false;
  }

  function showFeedback(message, type) {
    if (window.Toast && typeof window.Toast.show === 'function') {
      window.Toast.show(message, type);
    } else if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    }
  }

  function sync(composer) {
    const input = inputFor(composer);
    const sendButton = sendButtonFor(composer);
    if (!input || !sendButton) return;

    const submitting = composer.dataset.submitting === 'true';
    sendButton.disabled = submitting || input.value.trim().length === 0;
    sendButton.setAttribute('aria-disabled', String(sendButton.disabled));
  }

  function setSubmitting(composer, submitting) {
    const input = inputFor(composer);
    const sendButton = sendButtonFor(composer);
    const emojiButton = composer.querySelector('.comment-composer-emoji');
    if (!input || !sendButton) return;

    composer.dataset.submitting = submitting ? 'true' : 'false';
    input.disabled = submitting;
    if (emojiButton) emojiButton.disabled = submitting;
    sendButton.setAttribute('aria-busy', String(submitting));
    sendButton.innerHTML = submitting
      ? '<span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden="true"></span><span class="sr-only">Sending</span>'
      : '<i class="bi bi-send-fill" aria-hidden="true"></i><span class="hidden sm:inline">Send</span>';
    sync(composer);
  }

  function closePickers(except) {
    document.querySelectorAll('.comment-emoji-picker').forEach((picker) => {
      if (picker !== except) picker.remove();
    });
  }

  function insertEmoji(input, emoji) {
    const start = Number.isInteger(input.selectionStart)
      ? input.selectionStart
      : input.value.length;
    const end = Number.isInteger(input.selectionEnd)
      ? input.selectionEnd
      : start;
    input.value = `${input.value.slice(0, start)}${emoji}${input.value.slice(end)}`;
    const cursor = start + emoji.length;
    if (typeof input.setSelectionRange === 'function') {
      input.setSelectionRange(cursor, cursor);
    }
    input.focus();
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function toggleEmojiPicker(button) {
    const composer = composerFor(button);
    const input = inputFor(composer);
    if (!composer || !input) return;

    const existing = composer.querySelector('.comment-emoji-picker');
    if (existing) {
      existing.remove();
      input.focus();
      return;
    }

    closePickers();
    const picker = document.createElement('div');
    picker.className = 'comment-emoji-picker absolute bottom-full right-0 z-30 mb-2 grid w-64 grid-cols-8 gap-1 rounded-xl border border-gray-200 bg-white p-2 shadow-lg';
    picker.setAttribute('role', 'listbox');
    picker.setAttribute('aria-label', 'Choose an emoji');

    emojis.forEach((emoji) => {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = 'flex h-7 w-7 items-center justify-center rounded text-lg hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500';
      option.textContent = emoji;
      option.setAttribute('aria-label', `Add ${emoji}`);
      option.addEventListener('click', () => {
        insertEmoji(input, emoji);
        picker.remove();
      });
      picker.appendChild(option);
    });

    composer.appendChild(picker);
    picker.querySelector('button')?.focus();
  }

  async function submit(composer) {
    const input = inputFor(composer);
    if (!input || composer.dataset.submitting === 'true') return false;

    const content = input.value.trim();
    if (!content) {
      sync(composer);
      return false;
    }
    if (!isOnline()) {
      showFeedback("You're offline. Reconnect to post your comment.", 'warning');
      input.focus();
      return false;
    }
    if (typeof window.addComment !== 'function') return false;

    setSubmitting(composer, true);
    closePickers();
    let succeeded = false;
    try {
      succeeded = (await window.addComment(composer.dataset.postId, content)) === true;
      if (succeeded) input.value = '';
      return succeeded;
    } finally {
      setSubmitting(composer, false);
      input.focus();
    }
  }

  document.addEventListener('input', (event) => {
    const composer = composerFor(event.target);
    if (composer && event.target.matches('.comment-composer-input')) sync(composer);
  });

  document.addEventListener('keydown', (event) => {
    const composer = composerFor(event.target);
    if (!composer || !event.target.matches('.comment-composer-input')) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit(composer);
    }
  });

  document.addEventListener('click', (event) => {
    const emojiButton = event.target.closest('.comment-composer-emoji');
    if (emojiButton) {
      event.preventDefault();
      toggleEmojiPicker(emojiButton);
      return;
    }

    const sendButton = event.target.closest('.comment-composer-send');
    if (sendButton) {
      event.preventDefault();
      submit(composerFor(sendButton));
      return;
    }

    if (!event.target.closest('.comment-emoji-picker')) closePickers();
  });

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.comment-composer').forEach(sync);
  });

  window.CommentComposer = {
    insertEmoji,
    setSubmitting,
    submit,
    sync,
    toggleEmojiPicker,
  };
})();
