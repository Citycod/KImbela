(function (global) {
  'use strict';

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function showStatus(message, isError) {
    const existing = document.getElementById('kimbela-post-action-status');
    if (existing) existing.remove();
    const status = document.createElement('div');
    status.id = 'kimbela-post-action-status';
    status.setAttribute('role', isError ? 'alert' : 'status');
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
      fontSize: '0.875rem',
      fontWeight: '600',
    });
    document.body.appendChild(status);
    global.setTimeout(() => status.remove(), 3000);
  }

  async function deletePost(trigger) {
    const postId = trigger && trigger.dataset.postId;
    if (!postId || trigger.dataset.deletePending === 'true') return false;
    if (!global.confirm('Are you sure you want to delete this post?')) return false;

    const originalHtml = trigger.innerHTML;
    trigger.dataset.deletePending = 'true';
    trigger.disabled = true;
    trigger.textContent = 'Deleting...';

    try {
      const response = await global.fetch(`/delete_post/${encodeURIComponent(postId)}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'X-CSRFToken': csrfToken(),
        },
      });
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new Error('Your session may have expired. Refresh and try again.');
      }
      const payload = await response.json();
      if (!response.ok || payload.success !== true) {
        throw new Error(payload.error || 'Unable to delete post.');
      }

      const card = trigger.closest('.card-hover[data-post-id]');
      if (card) card.remove();
      showStatus('Post deleted successfully.', false);
      return true;
    } catch (error) {
      trigger.innerHTML = originalHtml;
      trigger.disabled = false;
      showStatus(error.message || 'Unable to delete post.', true);
      return false;
    } finally {
      trigger.dataset.deletePending = 'false';
    }
  }

  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-profile-delete-post]');
    if (!trigger) return;
    event.preventDefault();
    deletePost(trigger);
  });

  global.KimbelaProfilePostActions = Object.freeze({ deletePost });
})(window);
