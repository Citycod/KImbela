// ========================================
// REACTION SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';

class ReactionSystem {
    constructor() {
        this.csrfToken = config.getCsrfToken();
        this.currentReactionPostId = null;
        this.reactionTimeout = null;
    }

    init() {
        // Keep tooltip open on hover
        document.addEventListener('mouseover', e => {
            if (e.target.closest('.reactions-tooltip')) {
                clearTimeout(this.reactionTimeout);
            }
        });

        document.addEventListener('mouseout', e => {
            if (e.target.closest('.reactions-tooltip') && this.currentReactionPostId) {
                this.hideReactions(this.currentReactionPostId);
            }
        });
    }

    showReactions(postId) {
        const tooltip = document.getElementById(`reactions-${postId}`);
        if (!tooltip) return;

        clearTimeout(this.reactionTimeout);
        tooltip.classList.add('show');
        this.currentReactionPostId = postId;
    }

    hideReactions(postId) {
        const tooltip = document.getElementById(`reactions-${postId}`);
        if (!tooltip) return;

        this.reactionTimeout = setTimeout(() => {
            tooltip.classList.remove('show');
            this.currentReactionPostId = null;
        }, 300);
    }

    async reactToPost(postId, reactionType) {
        const likeBtn = document.getElementById(`like-btn-${postId}`);
        const likeIcon = document.getElementById(`like-icon-${postId}`);
        const likeText = document.getElementById(`like-text-${postId}`);
        const likeCount = document.getElementById(`like-count-${postId}`);
        const tooltip = document.getElementById(`reactions-${postId}`);

        if (!likeBtn || !likeIcon || !likeText) return;

        // Hide tooltip
        if (tooltip) {
            tooltip.classList.remove('show');
        }

        // Optimistic update
        const wasActive = likeBtn.classList.contains(`active-${reactionType}`);
        this.updateReactionUI(postId, reactionType, !wasActive, likeBtn, likeIcon, likeText);

        try {
            const response = await fetch(`/react_post/${postId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({ reaction_type: reactionType })
            });

            const data = await response.json();

            if (data.success) {
                this.updateReactionUI(postId, data.user_reaction || null, true, likeBtn, likeIcon, likeText);
                if (likeCount) {
                    likeCount.textContent = `${data.total_reactions} ${data.total_reactions === 1 ? 'reaction' : 'reactions'}`;
                }
                Toast.show(this.getReactionMessage(data.user_reaction, data.reacted), 'success');
            } else {
                this.updateReactionUI(postId, null, false, likeBtn, likeIcon, likeText);
                Toast.show(data.error || 'Failed to react', 'danger');
            }
        } catch (error) {
            console.error('Reaction error:', error);
            this.updateReactionUI(postId, null, false, likeBtn, likeIcon, likeText);
            Toast.show('Network error', 'danger');
        }
    }

    updateReactionUI(postId, reactionType, isActive, likeBtn, likeIcon, likeText) {
        // Reset
        likeBtn.className = likeBtn.className.replace(/active-\w+|text-\w+-?\d*/g, '').trim();
        likeBtn.classList.add('flex', 'items-center', 'space-x-1', 'md:space-x-2', 'px-2', 'md:px-4', 'py-1', 'md:py-2', 'rounded-lg', 'hover:bg-gray-100', 'transition-colors', 'duration-300');
        likeIcon.className = 'bi bi-hand-thumbs-up';
        likeText.textContent = 'Like';

        if (isActive && reactionType) {
            const config = {
                like:  { icon: 'bi-hand-thumbs-up-fill',  text: 'Liked',   color: 'text-blue-600' },
                love:  { icon: 'bi-heart-fill',           text: 'Loved',   color: 'text-red-600' },
                care:  { icon: 'bi-emoji-heart-eyes',     text: 'Cared',   color: 'text-yellow-600' },
                haha:  { icon: 'bi-emoji-laughing',       text: 'Haha',    color: 'text-yellow-500' },
                wow:   { icon: 'bi-emoji-surprise',       text: 'Wow',     color: 'text-orange-500' },
                sad:   { icon: 'bi-emoji-frown',          text: 'Sad',     color: 'text-indigo-600' },
                angry: { icon: 'bi-emoji-angry',          text: 'Angry',   color: 'text-red-700' }
            };

            const r = config[reactionType];
            if (r) {
                likeBtn.classList.add(`active-${reactionType}`, r.color);
                likeIcon.className = `${r.icon} like-animation`;
                likeText.textContent = r.text;
            }
        }
    }

    getReactionMessage(reactionType, reacted) {
        const messages = {
            like:  reacted ? 'You liked this post!' : 'Like removed',
            love:  reacted ? 'You loved this post!' : 'Love removed',
            care:  reacted ? 'You cared!' : 'Care removed',
            haha:  reacted ? 'Haha!' : 'Haha removed',
            wow:   reacted ? 'Wow!' : 'Wow removed',
            sad:   reacted ? 'Sad' : 'Sad removed',
            angry: reacted ? 'Angry' : 'Angry removed'
        };
        return messages[reactionType] || (reacted ? 'Reacted!' : 'Reaction removed');
    }

    likePost(postId) {
        this.reactToPost(postId, 'like');
    }
}

// Export singleton instance
const reactionSystem = new ReactionSystem();
export default reactionSystem;

// Make available globally for HTML onclick attributes
window.ReactionSystem = reactionSystem;
window.showReactions = (postId) => reactionSystem.showReactions(postId);
window.hideReactions = (postId) => reactionSystem.hideReactions(postId);
window.reactToPost = (postId, reactionType) => reactionSystem.reactToPost(postId, reactionType);
window.likePost = (postId) => reactionSystem.likePost(postId);