// ========================================
// COMMENT SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';
import Loader from '../../core/loader.js';

class CommentSystem {
    constructor() {
        this.csrfToken = config.getCsrfToken();
        this.currentUserId = config.getCurrentUserId();
        this.defaultAvatar = config.getDefaultAvatar();

        window.deleteComment = (commentId) => {
            this.deleteComment(commentId);
        };
    }

    init() {
        // Handle comment keypress events
        document.addEventListener('keypress', (e) => {
            if (e.target.classList.contains('add-comment') &&
                e.key === 'Enter' &&
                e.target.value.trim()) {
                const postId = e.target.dataset.postId;
                const content = e.target.value.trim();
                this.addComment(postId, content, e.target);
            }
        });
    }

    async addComment(postId, content, inputElement) {
        if (!content) return;

        const input = inputElement || document.getElementById(`commentInput-${postId}`);
        const container = document.getElementById(`comments-${postId}`);
        const countElement = document.getElementById(`comment-count-${postId}`);

        if (!input) return;

        // Store original state
        input.disabled = true;
        const placeholder = input.placeholder;
        input.placeholder = 'Posting...';

        try {
            const response = await fetch(`/add_comment/${postId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({ content })
            });

            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                if (text.includes('login') || response.status === 401) {
                    throw new Error('Please log in to comment');
                }
                throw new Error('Server error');
            }

            const data = await response.json();

            if (data.success || data.id) {
                const comment = data.comment || data;

                // Create the comment element
                const div = document.createElement('div');
                div.className = 'flex space-x-2 md:space-x-3 mb-3 md:mb-4 comment-item comment-fade-in';
                div.id = `comment-${comment.id || data.id}`;
                div.innerHTML = `
                    <img src="${window.currentUserInfo?.avatar || this.defaultAvatar}"
                         class="w-6 h-6 md:w-8 md:h-8 rounded-full object-cover">
                    <div class="flex-1">
                        <div class="bg-white rounded-xl md:rounded-2xl px-3 py-2 md:px-4 md:py-3">
                            <div class="flex justify-between items-start mb-1">
                                <h5 class="font-semibold text-xs md:text-sm">${window.currentUserInfo?.name || 'You'}</h5>
                                <div class="dropdown relative">
                                    <button class="p-0.5 md:p-1 rounded-full hover:bg-gray-100">
                                        <i class="bi bi-three-dots text-gray-400 text-xs"></i>
                                    </button>
                                    <div class="dropdown-menu absolute right-0 mt-1 w-28 md:w-32 bg-white rounded-lg md:rounded-xl shadow-2xl border border-gray-200 hidden z-10">
                                        <button onclick="CommentSystem.deleteComment(${comment.id || data.id}, ${postId})"
                                                class="w-full text-left px-2 py-1.5 md:px-3 md:py-2 hover:bg-gray-50 text-red-600 text-xs md:text-sm">
                                            <i class="bi bi-trash mr-1 text-xs md:text-sm"></i>Delete
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <p class="text-gray-800 text-xs md:text-sm">${content}</p>
                            <div class="flex items-center space-x-2 md:space-x-3 mt-1 md:mt-2">
                                <span class="text-xs text-gray-400">Just now</span>
                            </div>
                        </div>
                    </div>
                `;

                // Add to container (prepend to show newest first)
                if (container) {
                    if (container.children.length > 0) {
                        container.insertBefore(div, container.firstChild);
                    } else {
                        container.appendChild(div);
                    }
                }

                // Clear input
                input.value = '';

                // Update comment count
                this.updateCommentCount(postId, 1, 'add');

                // Show success message
                Toast.show('Comment added!', 'success');

                // Scroll to the new comment
                setTimeout(() => {
                    div.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }, 100);
            } else {
                Toast.show(data.error || 'Failed to add comment', 'danger');
            }
        } catch (error) {
            console.error('Comment error:', error);

            if (error.message.includes('log in')) {
                Toast.show('Please log in again to comment', 'warning');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 2000);
            } else {
                Toast.show('Failed to add comment: ' + error.message, 'danger');
            }
        } finally {
            // Restore input state
            input.disabled = false;
            input.placeholder = placeholder;
            input.focus();
        }
    }

    async deleteComment(commentId, postId = null) {
        if (!confirm('Delete this comment?')) return;

        try {
            const response = await fetch(`/delete_comment/${commentId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();

            if (data.success) {
                const el = document.getElementById(`comment-${commentId}`);
                if (el) {
                    el.style.opacity = '0';
                    el.style.transform = 'translateX(-50%)';
                    setTimeout(() => el.remove(), 300);
                }

                // Update comment count if we know the postId
                if (postId) {
                    this.updateCommentCount(postId, 1, 'subtract');
                }

                Toast.show('Comment deleted', 'info');
            } else {
                Toast.show(data.error || 'Failed', 'danger');
            }
        } catch (error) {
            console.error(error);
            Toast.show('Network error', 'danger');
        }
    }

    updateCommentCount(postId, change, operation = 'add') {
        const countElement = document.getElementById(`comment-count-${postId}`);
        if (!countElement) return;

        // Get current count from data attribute or text
        let currentCount = parseInt(countElement.getAttribute('data-total-comments')) || 0;

        // Update the count
        if (operation === 'add') {
            currentCount += change;
        } else if (operation === 'subtract') {
            currentCount = Math.max(0, currentCount - change);
        }

        // Update both the text and the data attribute
        countElement.textContent = `${currentCount} ${currentCount === 1 ? 'comment' : 'comments'}`;
        countElement.setAttribute('data-total-comments', currentCount);
    }

    focusCommentInput(postId) {
        document.getElementById(`commentInput-${postId}`)?.focus();
    }

    async loadAllComments(postId) {
        try {
            const countElement = document.getElementById(`comment-count-${postId}`);
            const totalComments = parseInt(countElement?.getAttribute('data-total-comments')) || 0;

            const res = await fetch(`/get_comments/${postId}?limit=${totalComments}`);
            const data = await res.json();

            if (data.comments) {
                const container = document.getElementById(`comments-${postId}`);
                const btn = container.nextElementSibling;
                container.innerHTML = '';

                data.comments.forEach(c => {
                    const div = document.createElement('div');
                    div.className = 'flex space-x-2 md:space-x-3 mb-3 md:mb-4 comment-item';
                    div.id = `comment-${c.id}`;
                    div.innerHTML = `
                        <img src="${c.avatar}" class="w-6 h-6 md:w-8 md:h-8 rounded-full object-cover">
                        <div class="flex-1">
                            <div class="bg-white rounded-xl md:rounded-2xl px-3 py-2 md:px-4 md:py-3">
                                <div class="flex justify-between items-start mb-1">
                                    <h5 class="font-semibold text-xs md:text-sm">${c.author_name}</h5>
                                    <div class="dropdown relative">
                                        <button class="p-0.5 md:p-1 rounded-full hover:bg-gray-100">
                                            <i class="bi bi-three-dots text-gray-400 text-xs"></i>
                                        </button>
                                        <div class="dropdown-menu absolute right-0 mt-1 w-28 md:w-32 bg-white rounded-lg md:rounded-xl shadow-2xl border border-gray-200 hidden z-10">
                                            ${c.author_id === this.currentUserId ?
                                                `<button onclick="CommentSystem.deleteComment(${c.id}, ${postId})"
                                                        class="w-full text-left px-2 py-1.5 md:px-3 md:py-2 hover:bg-gray-50 text-red-600 text-xs md:text-sm">
                                                    <i class="bi bi-trash mr-1 text-xs md:text-sm"></i>Delete
                                                </button>` : ''}
                                        </div>
                                    </div>
                                </div>
                                <p class="text-gray-800 text-xs md:text-sm">${c.content}</p>
                                <div class="flex items-center space-x-2 md:space-x-3 mt-1 md:mt-2">
                                    <span class="text-xs text-gray-400">${c.created_at}</span>
                                </div>
                            </div>
                        </div>
                    `;
                    container.appendChild(div);
                });

                if (btn && btn.tagName === 'BUTTON') btn.remove();
            }
        } catch (error) {
            Toast.show('Failed to load comments', 'danger');
        }
    }
}

// Export singleton instance
const commentSystem = new CommentSystem();
export default commentSystem;

// Make available globally for HTML onclick attributes
window.CommentSystem = commentSystem;