// ========================================
// POST SYSTEM - MAIN MODULE
// ========================================

import { config } from '../../app/config.js';
import Loader from '../../core/loader.js';
import Toast from '../../core/toast.js';
import Modal from '../../core/modal.js';
import TimeUtils from '../../core/time-utils.js';
import CommentSystem from './comments.js';
import ReactionSystem from './reactions.js';

class PostSystem {
    constructor() {
        this.csrfToken = config.getCsrfToken();
        this.currentUserId = config.getCurrentUserId();
        this.defaultAvatar = config.getDefaultAvatar();
    }

    initInteractions() {
        // Like buttons
        document.addEventListener('click', (e) => {
            const likeBtn = e.target.closest('.like-btn');
            if (likeBtn) {
                const postId = likeBtn.dataset.postId;
                this.like(postId, likeBtn);
            }

            // Delete posts
            const deleteBtn = e.target.closest('.delete-post');
            if (deleteBtn) {
                e.preventDefault();
                const postId = deleteBtn.dataset.postId;
                this.delete(postId, deleteBtn);
            }

            // Edit posts
            const editBtn = e.target.closest('.edit-post');
            if (editBtn) {
                e.preventDefault();
                const postId = editBtn.dataset.postId;
                this.edit(postId);
            }

            // View comments
            const viewCommentsBtn = e.target.closest('.view-comments');
            if (viewCommentsBtn) {
                const postId = viewCommentsBtn.dataset.postId;
                this.viewComments(postId);
            }

            // Share buttons
            const shareBtn = e.target.closest('.share-btn');
            if (shareBtn) {
                navigator.clipboard.writeText(shareBtn.dataset.url);
                Toast.show('Post link copied!', 'success');
            }
        });

        // Initialize comment system
        CommentSystem.init();

        // Initialize reaction system
        ReactionSystem.init();
    }

    async like(postId, likeBtn) {
        if (!likeBtn) return;

        const likeCount = likeBtn.querySelector('.like-count');
        const icon = likeBtn.querySelector('i');
        const originalCount = likeCount?.textContent || '0';
        const originalIcon = icon?.className || 'bi bi-hand-thumbs-up';

        // Show loading state
        if (icon) icon.className = 'bi bi-hourglass';
        likeBtn.disabled = true;

        try {
            const response = await fetch(`/like_post/${postId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();

            // Update UI
            if (likeCount) {
                likeCount.textContent = data.likes;
            }

            if (icon) {
                if (data.liked) {
                    icon.className = 'bi bi-hand-thumbs-up-fill';
                    likeBtn.classList.add('text-blue-600');
                } else {
                    icon.className = 'bi bi-hand-thumbs-up';
                    likeBtn.classList.remove('text-blue-600');
                }
            }

        } catch (error) {
            console.error('Error liking post:', error);
            if (likeCount) likeCount.textContent = originalCount;
            if (icon) icon.className = originalIcon;
        } finally {
            likeBtn.disabled = false;
        }
    }

    async delete(postId, deleteBtn) {
        if (!confirm('Are you sure you want to delete this post?')) return;

        const originalContent = deleteBtn.innerHTML;
        deleteBtn.innerHTML = `<span class="inline-flex items-center gap-1"><span class="tiny-loader xs danger"></span>Deleting...</span>`;
        deleteBtn.disabled = true;

        try {
            const response = await fetch(`/delete_post/${postId}`, {
                method: 'POST',
                headers: { 'X-CSRFToken': this.csrfToken }
            });

            if (!response.ok) throw new Error('Network error');

            const postElement = document.querySelector(`[data-post-id="${postId}"]`);
            if (postElement) {
                postElement.style.opacity = '0.5';
                setTimeout(() => {
                    postElement.remove();
                    Toast.show('Post deleted successfully', 'success');
                }, 500);
            }
        } catch (error) {
            console.error('Error deleting post:', error);
            deleteBtn.innerHTML = originalContent;
            deleteBtn.disabled = false;
            Toast.show('Failed to delete post', 'danger');
        }
    }

    async edit(postId) {
        const post = document.querySelector(`[data-post-id="${postId}"]`);
        if (!post) return;

        const postText = post.querySelector('.post-text');
        if (!postText) return;

        document.getElementById('editPostContent').value = postText.textContent;

        const form = document.getElementById('editPostForm');
        form.onsubmit = async (e) => {
            e.preventDefault();

            const submitBtn = form.querySelector('button[type="submit"]');
            Loader.quick(submitBtn, 'show');

            try {
                const formData = new FormData(form);
                formData.append('post_id', postId);

                const response = await fetch('/edit_post', {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-CSRFToken': this.csrfToken }
                });

                if (!response.ok) throw new Error('Network error');

                Modal.close('editPostModal');
                Toast.show('Post updated successfully', 'success');
                setTimeout(() => location.reload(), 1000);
            } catch (error) {
                console.error('Error editing post:', error);
                Toast.show('Failed to edit post', 'danger');
            } finally {
                Loader.quick(submitBtn, 'hide');
            }
        };

        Modal.open('editPostModal');
    }

    async viewComments(postId) {
        const modalBody = document.getElementById('commentModalBody');
        if (modalBody) {
            modalBody.innerHTML = `
                <div class="flex items-center justify-center p-8">
                    <span class="tiny-loader md"></span>
                    <span class="ml-3 text-gray-500">Loading comments...</span>
                </div>
            `;
        }

        Modal.open('commentModal');

        try {
            const response = await fetch(`/get_comments/${postId}`);
            if (!response.ok) throw new Error('Network error');

            const comments = await response.json();
            this.displayCommentsModal(comments);
        } catch (error) {
            console.error('Error loading comments:', error);
            if (modalBody) {
                modalBody.innerHTML = '<div class="text-center py-8 text-red-500">Failed to load comments</div>';
            }
        }
    }

    displayCommentsModal(comments) {
        const body = document.getElementById('commentModalBody');
        if (!body) return;

        body.innerHTML = '';

        if (!comments || comments.length === 0) {
            body.innerHTML = '<div class="text-center py-8 text-gray-500">No comments yet</div>';
            return;
        }

        comments.forEach(comment => {
            const isLong = comment.content?.length > 150;
            body.innerHTML += `
                <div class="comment mb-5 border-b pb-4">
                    <div class="flex space-x-3">
                        <img src="${comment.avatar || this.defaultAvatar}" class="w-10 h-10 rounded-full object-cover flex-shrink-0">
                        <div class="flex-1">
                            <div class="bg-gray-50 rounded-2xl px-4 py-3">
                                <div class="font-semibold">${comment.name || 'User'}</div>
                                <div class="text-sm ${isLong ? 'truncated' : ''}">
                                    ${comment.content || ''}
                                </div>
                                ${isLong ? `
                                <button class="text-blue-600 text-xs font-medium mt-2" onclick="this.previousElementSibling.classList.toggle('truncated'); this.textContent = this.previousElementSibling.classList.contains('truncated') ? 'See More' : 'See Less'">
                                    See More
                                </button>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    }
}

// Export singleton instance
const postSystem = new PostSystem();
export default postSystem;