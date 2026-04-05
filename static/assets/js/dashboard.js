// ========================================
// DASHBOARD.JS - UPDATED VERSION
// No Messenger conflicts - Uses messenger.js exclusively
// ========================================

// ========================================
// MOBILE MENU FUNCTION
// ========================================

window.toggleMobileMenu = function() {
    const overlay = document.getElementById('mobileSidebarOverlay');
    const sidebar = document.getElementById('mobileSidebar');

    if (!overlay || !sidebar) {
        return;
    }

    // Toggle display
    if (overlay.style.display === 'block' || overlay.classList.contains('block')) {
        overlay.style.display = 'none';
        overlay.classList.remove('block');
        sidebar.classList.remove('translate-x-0');
        sidebar.classList.add('-translate-x-full');
    } else {
        overlay.style.display = 'block';
        overlay.classList.add('block');
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('translate-x-0');
    }
};

// Also add ESC key to close mobile menu
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const overlay = document.getElementById('mobileSidebarOverlay');
        if (overlay && (overlay.style.display === 'block' || overlay.classList.contains('block'))) {
            window.toggleMobileMenu();
        }
    }
});

// Close mobile menu when clicking outside
document.getElementById('mobileSidebarOverlay')?.addEventListener('click', (e) => {
    if (e.target.id === 'mobileSidebarOverlay') {
        window.toggleMobileMenu();
    }
});

// ========================================
// GLOBAL UTILITIES & INITIALIZATION
// ========================================

// Get app config from global object or use defaults
const appConfig = window.APP_CONFIG || {};
const csrfToken = window.csrfToken || '';
const currentUserId = parseInt(window.currentUserId) || null;

// Global state management
const appState = {
    activeFriendId: null,
    typingTimer: null,
    userAdPreferences: JSON.parse(localStorage.getItem('adPreferences') || '{}'),
    notificationCheckInterval: null,
    searchTimeout: null,
    isLoadingPosts: false,
    hasMorePosts: window.hasMorePosts || false,
    nextCursor: window.nextCursor || null,
    blockedUserIds: window.blockedUserIds || []
};

const MobileFeedAds = {
    trackedImpressions: new Set(),

    isMobileViewport() {
        return window.matchMedia('(max-width: 1023px)').matches;
    },

    getCandidates() {
        const node = document.getElementById('mobileFeedAdCandidates');
        if (!node) return [];

        try {
            const candidates = JSON.parse(node.textContent || '[]');
            return Array.isArray(candidates) ? candidates : [];
        } catch (error) {
            return [];
        }
    },

    randomInterval() {
        return Math.floor(Math.random() * 2) + 7;
    },

    shuffle(items) {
        const copy = [...items];
        for (let i = copy.length - 1; i > 0; i -= 1) {
            const j = Math.floor(Math.random() * (i + 1));
            [copy[i], copy[j]] = [copy[j], copy[i]];
        }
        return copy;
    },

    pickCandidate(candidates, usedKeys) {
        const available = candidates.filter(candidate => !usedKeys.has(candidate.key));
        const pool = available.length ? available : candidates;
        const [selected] = this.shuffle(pool);
        return selected || null;
    },

    renderMedia(candidate) {
        const banner = candidate.banner;
        if (!banner?.image_url) {
            return '';
        }

        if (banner.media_type === 'video') {
            return `
                <video class="dashboard-ad-video" autoplay muted loop playsinline preload="metadata">
                    <source src="${banner.image_url}" ${banner.video_mime ? `type="${banner.video_mime}"` : ''}>
                </video>
            `;
        }

        return `
            <img
                src="${banner.image_url}"
                alt="${banner.title || candidate.headline}"
                class="dashboard-ad-image"
                loading="lazy"
            />
        `;
    },

    renderCard(candidate, index) {
        const variantClassMap = {
            sidebar: 'sidebar-ad-banner',
            vertical: 'vertical-ad-banner',
            spotlight: 'right-ad-banner-2'
        };
        const variantClass = variantClassMap[candidate.key] || 'sidebar-ad-banner';
        const href = candidate.href || '#';
        const adIdAttr = candidate.ad_id ? `data-ad-id="${candidate.ad_id}"` : '';
        const hasBanner = Boolean(candidate.banner?.image_url);
        const title = candidate.banner?.title || candidate.headline;
        const ctaHref = href;
        const iconMap = {
            sidebar: 'bi bi-megaphone-fill',
            vertical: 'bi bi-stars',
            spotlight: 'bi bi-lightning-charge-fill'
        };
        const iconClass = iconMap[candidate.key] || 'bi bi-megaphone-fill';

        return `
            <div class="mobile-feed-ad-slot lg:hidden my-5" data-mobile-feed-ad-slot="true">
                <div class="${variantClass} ${hasBanner ? 'has-dashboard-ad' : ''}">
                    ${hasBanner ? `
                        <a
                            class="dashboard-ad-link"
                            href="${href}"
                            target="_blank"
                            rel="noopener"
                            ${adIdAttr}
                            data-mobile-feed-ad-click="true"
                            data-mobile-feed-ad-index="${index}"
                        >
                            ${this.renderMedia(candidate)}
                        </a>
                    ` : `
                        <div class="sidebar-ad-badge">${candidate.label}</div>
                        <div class="sidebar-ad-icon" aria-hidden="true">
                            <i class="${iconClass}"></i>
                        </div>
                        <h3>${title}</h3>
                        <p>${candidate.copy}</p>
                        <a
                            class="sidebar-ad-cta"
                            href="${ctaHref}"
                            data-mobile-feed-ad-click="true"
                            data-mobile-feed-ad-index="${index}"
                        >
                            ${candidate.cta}
                        </a>
                    `}
                </div>
            </div>
        `;
    },

    async trackImpression(adId) {
        if (!adId || this.trackedImpressions.has(adId)) return;
        this.trackedImpressions.add(adId);

        try {
            await fetch(`/api/ads/${adId}/impression`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        } catch (error) {
        }
    },

    async trackClick(adId) {
        if (!adId) return;

        try {
            await fetch(`/api/ads/${adId}/click`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        } catch (error) {
        }
    },

    bindTracking(root) {
        root.querySelectorAll('[data-mobile-feed-ad-click="true"]').forEach(link => {
            if (link.dataset.mobileFeedAdBound === 'true') return;
            link.dataset.mobileFeedAdBound = 'true';

            const adId = link.dataset.adId;
            if (adId) {
                this.trackImpression(adId);
                link.addEventListener('click', () => this.trackClick(adId));
            }
        });
    },

    clearExisting(feed) {
        feed.querySelectorAll('[data-mobile-feed-ad-slot="true"]').forEach(slot => slot.remove());
    },

    refresh() {
        const feed = document.getElementById('posts-feed');
        if (!feed) return;

        this.clearExisting(feed);

        if (!this.isMobileViewport()) {
            return;
        }

        const postCards = [...feed.children].filter(child => child.classList?.contains('post-card'));
        const candidates = this.getCandidates();

        if (!postCards.length || !candidates.length) {
            return;
        }

        let nextInsertAfter = this.randomInterval();
        let usedKeys = new Set();
        let adIndex = 0;

        postCards.forEach((postCard, index) => {
            const postsSeen = index + 1;
            if (postsSeen < nextInsertAfter) return;

            const candidate = this.pickCandidate(candidates, usedKeys);
            if (!candidate) return;

            usedKeys.add(candidate.key);
            adIndex += 1;

            postCard.insertAdjacentHTML('afterend', this.renderCard(candidate, adIndex));
            const inserted = postCard.nextElementSibling;
            if (inserted) {
                this.bindTracking(inserted);
            }

            nextInsertAfter += this.randomInterval();
            if (usedKeys.size >= candidates.length) {
                usedKeys = new Set();
            }
        });
    }
};

// ========================================
// GLOBAL FUNCTIONS FOR HTML ONCLICK ATTRIBUTES
// ========================================







window.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
        modal.style.display = 'none';  // Keep this for safety
        document.body.style.overflow = 'auto';  // Explicitly restore scrolling (use 'visible' if 'auto' doesn't work)
    }
};

window.viewFullProfile = function(userId) {
    // Close the profile modal
    const profileModal = document.getElementById('profileModal');
    if (profileModal) {
        profileModal.classList.add('hidden');
        document.body.style.overflow = '';
    }

    // Show loading toast
    Toast.show('Opening full profile...', 'info');

    // Open in new tab after a short delay
    setTimeout(() => {
        window.open(`/profile/${userId}`, '_blank');
    }, 500);
};



window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'flex';  // Explicitly set display (assuming flex for centering; use 'block' if not)
        document.body.style.overflow = 'hidden';
    }
};



// Add this to your dashboard.js, near the top of the "GLOBAL FUNCTIONS" section:

window.handleMessageButtonClick = function(userId) {
    // Close the profile modal
    Modal.close('profileModal');

    // Show loading toast
    Toast.show('Opening chat...', 'info');

    // Wait a bit for modal to close
    setTimeout(() => {
        // Open the messenger popup
        const messengerPopup = document.getElementById('messengerPopup');
        if (messengerPopup) {
            // Remove hidden class and show it
            messengerPopup.classList.remove('hidden');
            messengerPopup.style.display = 'flex';

            // Ensure Messenger is initialized
            if (typeof Messenger !== 'undefined') {
                // Initialize if not already
                Messenger.init();

                // Load the user's friends list (if not loaded)
                Messenger.loadFriendsList();

                // Small delay to ensure friends list is loaded
                setTimeout(() => {
                    // Try to open chat with the user
                    openChatForUser(userId);
                }, 300);
            } else {
                Toast.show('Messenger not available', 'danger');
            }
        } else {
            Toast.show('Messenger not found', 'danger');
        }
    }, 300);
};

// Helper function to open chat for a specific user
async function openChatForUser(userId) {
    try {
        // First get user info
        const response = await fetch(`/get_user_profile/${userId}`);
        const data = await response.json();

        if (!data.error) {
            // Find the user in friends list or create chat
            if (typeof Messenger !== 'undefined' && Messenger.openChat) {
                Messenger.openChat(
                    userId,
                    `${data.first_name} ${data.last_name}`,
                    data.profile_pic || window.defaultAvatar
                );
            } else {
                // Fallback: show error and refresh
                Toast.show('Opening chat...', 'info');
                setTimeout(() => {
                    // If Messenger isn't available, reload the page with chat open
                    window.location.href = `/dashboard?open_chat=${userId}`;
                }, 500);
            }
        } else {
            Toast.show('Failed to load user info', 'danger');
        }
    } catch (error) {
        Toast.show('Error opening chat', 'danger');
    }
}




function openPostComposer() {
    const postModal = document.getElementById('postModal');
    if (!postModal) return null;

    postModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    return postModal;
}

function focusPostComposer(postModal) {
    const composerModal = postModal || document.getElementById('postModal');
    if (!composerModal) return;

    setTimeout(() => {
        const textarea = composerModal.querySelector('textarea[name="post_content"]');
        if (textarea) {
            textarea.focus();
        }
    }, 50);
}

function syncComposerMediaInput(sourceInput) {
    const modalInput = document.getElementById('mediaInput');
    const sourceFile = sourceInput?.files?.[0];

    if (!modalInput || !sourceFile) {
        return sourceInput;
    }

    if (sourceInput === modalInput) {
        return modalInput;
    }

    if (typeof DataTransfer === 'undefined') {
        return sourceInput;
    }

    const transfer = new DataTransfer();
    transfer.items.add(sourceFile);
    modalInput.files = transfer.files;

    return modalInput;
}

window.previewMedia = function(input) {
    if (!input?.files?.length) return;

    const postModal = openPostComposer();
    const activeInput = syncComposerMediaInput(input);

    if (typeof window.clearSelectedGif === 'function') {
        window.clearSelectedGif();
    }

    MediaPreview.preview(activeInput);
    focusPostComposer(postModal);

    if (input !== activeInput) {
        input.value = '';
    }
};

window.searchGroups = function(query) {
    Groups.search(query);
};

window.loadGroups = function() {
    Groups.load();
};

window.joinGroup = function(groupId) {
    Groups.join(groupId);
};

window.leaveGroup = function(groupId) {
    Groups.leave(groupId);
};

window.openProfileModal = function(userId, fromNotification = false) {
    ProfileSystem.openProfileModal(userId, fromNotification);
};

window.addFriend = function(userId, button) {
    FriendSystem.add(userId, button);
};

window.cancelFriendRequest = function(userId, button) {
    FriendSystem.cancelRequest(userId, button);
};

window.acceptFriendRequest = function(userId, button) {
    FriendSystem.acceptFriendRequest(userId, button);
};

window.declineFriendRequest = function(userId, button) {
    FriendSystem.declineFriendRequest(userId, button);
};

// ========================================
// LOADER UTILITIES
// ========================================

const Loader = {
    show(element, options = {}) {
        const config = {
            type: 'tiny',
            size: 'sm',
            color: 'primary',
            position: 'append',
            text: '',
            preserveText: false,
            ...options
        };

        const originalContent = element.innerHTML;
        let loaderHTML = '';

        switch (config.type) {
            case 'dots':
                loaderHTML = '<span class="dots-loader"><span></span><span></span><span></span></span>';
                break;
            case 'bar':
                loaderHTML = '<span class="bar-loader"></span>';
                break;
            case 'pulse':
                loaderHTML = '<span class="pulse-loader"></span>';
                break;
            default:
                loaderHTML = `<span class="tiny-loader ${config.size}"></span>`;
        }

        if (config.text) {
            loaderHTML = `<span class="btn-loader">${loaderHTML}<span class="text-sm ml-1">${config.text}</span></span>`;
        } else if (config.preserveText) {
            const originalText = element.textContent.trim();
            loaderHTML = `<span class="btn-loader">${loaderHTML}<span class="text-sm ml-1">${originalText}</span></span>`;
        }

        element.dataset.originalContent = originalContent;
        element.dataset.loading = 'true';

        switch (config.position) {
            case 'prepend':
                element.innerHTML = loaderHTML + originalContent;
                break;
            case 'replace':
                element.innerHTML = loaderHTML;
                break;
            case 'inline':
                element.innerHTML = `<span class="inline-flex items-center gap-1">${loaderHTML}${originalContent}</span>`;
                break;
            default:
                element.innerHTML = originalContent + loaderHTML;
        }

        element.disabled = true;
        return element;
    },

    hide(element) {
        if (element.dataset.loading === 'true') {
            element.innerHTML = element.dataset.originalContent || '';
            element.disabled = false;
            delete element.dataset.loading;
            delete element.dataset.originalContent;
        }
        return element;
    },

    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return null;

        const loader = document.createElement('div');
        loader.className = 'modal-loader';
        loader.innerHTML = '<span class="tiny-loader md"></span>';
        modal.appendChild(loader);
        return loader;
    },

    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        const loader = modal.querySelector('.modal-loader');
        if (loader) loader.remove();
    },

    quick(button, action = 'show') {
        if (action === 'show') {
            const originalText = button.innerHTML;
            button.dataset.originalText = originalText;
            button.innerHTML = `<span class="inline-flex items-center gap-1"><span class="tiny-loader xs white"></span>${button.textContent.trim()}</span>`;
            button.disabled = true;
        } else {
            if (button.dataset.originalText) {
                button.innerHTML = button.dataset.originalText;
                delete button.dataset.originalText;
            }
            button.disabled = false;
        }
    }
};

// ========================================
// TOAST NOTIFICATIONS
// ========================================

const Toast = {
    show(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-strong text-white animate-fade-in ${
            type === 'success' ? 'bg-green-500' :
            type === 'danger' ? 'bg-red-500' :
            type === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'
        }`;
        toast.textContent = message;
        toast.setAttribute('role', 'alert');
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
};

// ========================================
// TIME UTILITIES
// ========================================

const TimeUtils = {
    formatTimeAgo(dateString) {
        if (!dateString) return 'Never';

        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        const diffWeeks = Math.floor(diffDays / 7);
        const diffMonths = Math.floor(diffDays / 30);
        const diffYears = Math.floor(diffDays / 365);

        if (diffSecs < 60) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        if (diffWeeks < 4) return `${diffWeeks}w ago`;
        if (diffMonths < 12) return `${diffMonths}mo ago`;
        return `${diffYears}y ago`;
    },

    initializeTimeAgo() {
        document.querySelectorAll('.last-seen').forEach(element => {
            const lastSeen = element.getAttribute('data-last-seen');
            if (lastSeen) {
                element.textContent = this.formatTimeAgo(lastSeen);
            }
        });
    },

    formatNotificationTime(timestamp) {
        const now = new Date();
        const notificationTime = new Date(timestamp);
        const diffInSeconds = Math.floor((now - notificationTime) / 1000);

        if (diffInSeconds < 60) return 'Just now';
        if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
        if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
        if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
        return notificationTime.toLocaleDateString();
    },

    calculateAge(birthDate) {
        if (!birthDate) return '';
        const today = new Date();
        const birth = new Date(birthDate);
        let age = today.getFullYear() - birth.getFullYear();
        const monthDiff = today.getMonth() - birth.getMonth();
        if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
            age--;
        }
        return age;
    }
};

// ========================================
// MODAL MANAGEMENT
// ========================================

const Modal = {
    open(modalId) {
        window.openModal(modalId);
    },

    close(modalId) {
        window.closeModal(modalId);
    },

    toggle(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            if (modal.classList.contains('hidden')) {
                this.open(modalId);
            } else {
                this.close(modalId);
            }
        }
    }
};

// ========================================
// DROPDOWN MANAGEMENT
// ========================================

const Dropdown = {
    init() {
        document.addEventListener('click', (e) => {
            // Close all dropdowns if clicking outside
            if (!e.target.closest('.dropdown')) {
                document.querySelectorAll('.dropdown-menu').forEach(menu => {
                    menu.classList.add('hidden');
                });
            }

            // Handle dropdown toggle
            const dropdownToggle = e.target.closest('[data-bs-toggle="dropdown"]');
            if (dropdownToggle) {
                e.preventDefault();
                const dropdown = dropdownToggle.closest('.dropdown');
                const menu = dropdown.querySelector('.dropdown-menu');

                if (menu) {
                    // Close other dropdowns
                    document.querySelectorAll('.dropdown-menu').forEach(otherMenu => {
                        if (otherMenu !== menu) {
                            otherMenu.classList.add('hidden');
                        }
                    });

                    // Toggle current dropdown
                    menu.classList.toggle('hidden');

                    // Load groups if needed
                    if (menu.id.includes('groupsDropdownMenu')) {
                        if (!menu.classList.contains('hidden')) {
                            Groups.load();
                        }
                    }
                }
            }
        });
    }
};

// ========================================
// POST SYSTEM
// ========================================

const PostSystem = {
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
                    'X-CSRFToken': csrfToken
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
            if (likeCount) likeCount.textContent = originalCount;
            if (icon) icon.className = originalIcon;
        } finally {
            likeBtn.disabled = false;
        }
    },

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
                    headers: { 'X-CSRFToken': csrfToken }
                });

                if (!response.ok) throw new Error('Network error');

                Modal.close('editPostModal');
                Toast.show('Post updated successfully', 'success');
                setTimeout(() => location.reload(), 1000);
            } catch (error) {
                Toast.show('Failed to edit post', 'danger');
            } finally {
                Loader.quick(submitBtn, 'hide');
            }
        };

        Modal.open('editPostModal');
    },

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
            if (modalBody) {
                modalBody.innerHTML = '<div class="text-center py-8 text-red-500">Failed to load comments</div>';
            }
        }
    },

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
                        <img src="${comment.avatar || window.defaultAvatar}" class="w-10 h-10 rounded-full object-cover flex-shrink-0">
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
    },

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
                this.deletePost(postId, deleteBtn);
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
                const postId = shareBtn.dataset.postId;
                const shareUrl = shareBtn.dataset.url || '';
                openShareModal(postId, shareUrl);
            }

            // Repost buttons
            const repostBtn = e.target.closest('.repost-btn');
            if (repostBtn) {
                const postId = repostBtn.dataset.postId;
                this.repost(postId, repostBtn);
            }
        });

        // Add comments on Enter
        document.addEventListener('keypress', (e) => {
            if (e.target.classList.contains('add-comment') && e.key === 'Enter' && e.target.value.trim()) {
                const postId = e.target.dataset.postId;
                const content = e.target.value.trim();
                this.addComment(postId, content, e.target);
            }
        });
    },

    async deletePost(postId, deleteBtn) {
        if (!confirm('Are you sure you want to delete this post?')) return;

        const originalContent = deleteBtn.innerHTML;
        deleteBtn.innerHTML = `<span class="inline-flex items-center gap-1"><span class="tiny-loader xs danger"></span>Deleting...</span>`;
        deleteBtn.disabled = true;

        try {
            const response = await fetch(`/delete_post/${postId}`, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken }
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
            deleteBtn.innerHTML = originalContent;
            deleteBtn.disabled = false;
            Toast.show('Failed to delete post', 'danger');
        }
    },

    async repost(postId, repostBtn) {
        if (!postId) return;

        const originalContent = repostBtn.innerHTML;
        repostBtn.innerHTML = `<span class="inline-flex items-center gap-1"><span class="tiny-loader xs"></span>Reposting...</span>`;
        repostBtn.disabled = true;

        try {
            const response = await fetch(`/repost/${postId}`, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken }
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Failed to repost');
            }

            Toast.show('Reposted to your feed!', 'success');
            setTimeout(() => location.reload(), 800);
        } catch (error) {
            repostBtn.innerHTML = originalContent;
            repostBtn.disabled = false;
            Toast.show(error.message || 'Failed to repost', 'danger');
        }
    },

    async addComment(postId, content, inputElement) {
        if (!content.trim()) return;

        inputElement.disabled = true;
        const originalPlaceholder = inputElement.placeholder;
        inputElement.placeholder = 'Posting...';

        try {
            const response = await fetch(`/add_comment/${postId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ content: content })
            });

            const data = await response.json();
            if (data.success) {
                inputElement.value = '';
                Toast.show('Comment added!', 'success');

                // Reload comments if modal is open
                const modal = document.getElementById('commentModal');
                if (modal && !modal.classList.contains('hidden')) {
                    this.viewComments(postId);
                }
            } else {
                Toast.show(data.error || 'Failed to add comment', 'danger');
            }
        } catch (error) {
            Toast.show('Failed to add comment', 'danger');
        } finally {
            inputElement.disabled = false;
            inputElement.placeholder = originalPlaceholder;
        }
    }
};

// ========================================
// FRIEND SYSTEM
// ========================================

const FriendSystem = {
    async add(userId, button) {
        if (!button) return;

        const originalHTML = button.innerHTML;
        const originalClass = button.className;

        // Show loading state
        button.innerHTML = '<span class="inline-flex items-center gap-1"><span class="tiny-loader xs white"></span>Sending...</span>';
        button.disabled = true;

        try {
            const response = await fetch(`/add_friend/${userId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });

            const data = await response.json();

            if (data.success) {
                // Update button to "Cancel Request"
                button.innerHTML = '<i class="bi bi-clock-history mr-1"></i> Cancel Request';
                button.className = 'w-full py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors';
                button.onclick = (e) => {
                    e.stopPropagation();
                    this.cancelRequest(userId, button);
                };
                button.classList.remove('btn-add-friend');
                button.classList.add('btn-cancel-request');

                Toast.show('Friend request sent!', 'success');

                // Update the profile modal button if it's open
                this.updateProfileModalButton(userId, 'sent');
            } else {
                button.innerHTML = originalHTML;
                button.className = originalClass;
                button.disabled = false;
                Toast.show(data.error || 'Failed to send request', 'danger');
            }
        } catch (error) {
            button.innerHTML = originalHTML;
            button.className = originalClass;
            button.disabled = false;
            Toast.show('Network error. Please try again.', 'danger');
        }
    },

    async cancelRequest(userId, button) {
        if (!button) return;

        const originalHTML = button.innerHTML;
        const originalClass = button.className;

        // Show loading state
        button.innerHTML = '<span class="inline-flex items-center gap-1"><span class="tiny-loader xs"></span>Cancelling...</span>';
        button.disabled = true;

        try {
            const response = await fetch(`/cancel_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });

            const data = await response.json();

            if (data.success) {
                // Update button back to "Connect"
                button.innerHTML = '<i class="bi bi-person-plus mr-1"></i> Connect';
                button.className = 'w-full py-2 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors';
                button.onclick = (e) => {
                    e.stopPropagation();
                    this.add(userId, button);
                };
                button.classList.remove('btn-cancel-request');
                button.classList.add('btn-add-friend');
                button.style.background = 'linear-gradient(135deg, #5a4500, #b88900)';

                Toast.show('Friend request cancelled!', 'info');

                // Update the profile modal button if it's open
                this.updateProfileModalButton(userId, 'none');
            } else {
                button.innerHTML = originalHTML;
                button.className = originalClass;
                button.disabled = false;
                Toast.show(data.error || 'Failed to cancel request', 'danger');
            }
        } catch (error) {
            button.innerHTML = originalHTML;
            button.className = originalClass;
            button.disabled = false;
            Toast.show('Network error. Please try again.', 'danger');
        }
    },

    async acceptFriendRequest(userId, button) {
        if (!button) return;

        const container = button.closest('.suggestion-card') || button.closest('.profile-actions') || document.getElementById('profileActions');

        Loader.quick(button, 'show');

        try {
            // Get notification ID if it exists (from notification dropdown)
            const notificationId = button.closest('.notification-item')?.dataset?.notificationId ||
                                   button.dataset.notificationId || null;

            const response = await fetch(`/accept_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken || '',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    notification_id: notificationId || null
                })
            });

            // Check content type safely
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                throw new Error('Server error (possible login issue or bad request)');
            }

            const data = await response.json();

            if (data.success) {
                // Update suggestion card or profile actions
                if (container) {
                    container.innerHTML = `
                        <button class="w-full py-2.5 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors flex items-center justify-center gap-2"
                                onclick="event.stopPropagation(); Messenger.startChat(${userId})">
                            <i class="bi bi-chat-dots"></i> Message
                        </button>
                    `;
                }

                Toast.show('Friend request accepted!', 'success');

                // Refresh profile modal buttons if open
                if (typeof ProfileSystem !== 'undefined') {
                    ProfileSystem.updateProfileActions(userId);
                }

                // Update notification badge
                if (typeof NotificationSystem !== 'undefined') {
                    NotificationSystem.updateBadge();
                }
            } else {
                Toast.show(data.error || 'Failed to accept request', 'danger');
            }
        } catch (error) {
            Toast.show('Failed to accept. Please try again.', 'danger');
        } finally {
            Loader.quick(button, 'hide');
        }
    },

    async declineFriendRequest(userId, button) {
        if (!button) return;

        const container = button.closest('.suggestion-card') || button.closest('.profile-actions');

        Loader.quick(button, 'show');

        try {
            // Get notification ID if it exists
            const notificationId = button.closest('.notification-item')?.dataset?.notificationId ||
                                   button.dataset.notificationId || null;

            const response = await fetch(`/decline_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken || '',
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    notification_id: notificationId || null
                })
            });

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                throw new Error('Server error - please check login status');
            }

            const data = await response.json();

            if (data.success) {
                if (container) {
                    container.innerHTML = `
                        <button
                            class="btn-add-friend w-full py-2 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
                            onclick="event.stopPropagation(); FriendSystem.add(${userId}, this)"
                            style="background: linear-gradient(135deg, #5a4500, #b88900);"
                        >
                            <i class="bi bi-person-plus mr-1"></i> Connect
                        </button>
                    `;
                }

                Toast.show('Friend request declined', 'info');

                if (typeof ProfileSystem !== 'undefined') {
                    ProfileSystem.updateProfileActions(userId);
                }

                // Update notification badge
                if (typeof NotificationSystem !== 'undefined') {
                    NotificationSystem.updateBadge();
                }
            } else {
                Toast.show(data.error || 'Failed to decline request', 'danger');
            }
        } catch (error) {
            Toast.show('Failed to decline request. Check login status.', 'danger');
        } finally {
            Loader.quick(button, 'hide');
        }
    },

    updateProfileModalButton(userId, status) {
        const profileActions = document.getElementById('profileActions');
        if (!profileActions) return;

        let buttonHTML = '';

        switch(status) {
            case 'sent':
                buttonHTML = `
                    <button class="btn btn-secondary px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
                            onclick="FriendSystem.cancelRequest(${userId}, this)">
                        <i class="bi bi-clock-history mr-1"></i> Cancel Request
                    </button>
                `;
                break;

            case 'received':
                buttonHTML = `
                    <div class="flex space-x-2">
                        <button class="btn btn-success px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors"
                                onclick="FriendSystem.acceptFriendRequest(${userId}, this)">
                            <i class="bi bi-check-lg mr-1"></i> Accept
                        </button>
                        <button class="btn btn-danger px-4 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors"
                                onclick="FriendSystem.declineFriendRequest(${userId}, this)">
                            <i class="bi bi-x-lg mr-1"></i> Decline
                        </button>
                    </div>
                `;
                break;

            case 'friends':
                buttonHTML = `
                    <button class="relative px-5 py-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                            onclick="window.handleMessageButtonClick(${userId})">
                        <!-- Shimmer effect -->
                        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                        <!-- Content -->
                        <div class="relative flex items-center gap-2">
                            <i class="bi bi-chat-dots text-sm group-hover:scale-110 transition-transform duration-300"></i>
                            <span class="text-xs group-hover:font-medium transition-all duration-300">Message</span>
                            <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                        </div>
                    </button>
                    <button class="btn btn-outline-danger px-4 py-2 border border-red-500 text-red-500 rounded-lg font-medium hover:bg-red-50 transition-colors"
                            onclick="BlockSystem.block(${userId})">
                        <i class="bi bi-slash-circle mr-1"></i> Block
                    </button>
                `;
                break;

            default: // 'none'
                buttonHTML = `
                    <button class="relative px-5 py-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-md hover:shadow-lg"
        onclick="FriendSystem.add(${userId}, this)">
    <!-- Shimmer overlay -->
    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

    <!-- Content -->
    <div class="relative flex items-center gap-2">
        <i class="bi bi-person-plus text-base group-hover:scale-110 transition-transform duration-300"></i>
        <span class="text-sm group-hover:font-medium transition-all duration-300">Connect</span>
        <i class="bi bi-arrow-right-short text-sm opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
    </div>
</button>
                `;
                break;
        }

        profileActions.innerHTML = buttonHTML;
    },

    async checkFriendStatus(userId) {
        try {
            const response = await fetch(`/check_friend_status/${userId}`);
            if (response.ok) {
                const data = await response.json();
                return data.status;
            }
        } catch (error) {
        }
        return 'none';
    }
};

// ========================================
// PROFILE SYSTEM
// ========================================

const ProfileSystem = {
    async openProfileModal(userId, fromFriendRequestNotification = false) {
        try {
            const modalBody = document.getElementById('profileModalBody');
            const profileActions = document.getElementById('profileActions');

            if (!modalBody || !profileActions) {
                return;
            }

            // Show loading state
            modalBody.innerHTML = `
                <div class="flex flex-col items-center justify-center p-8 min-h-[400px]">
                    <span class="tiny-loader md"></span>
                    <div class="text-gray-500 mt-3">Loading profile...</div>
                </div>
            `;

            profileActions.innerHTML = '';

            // After you successfully fetch and display the profile
            const profileModal = document.getElementById('profileModal');
            if (profileModal) {
                // Remove Tailwind's hidden class
                profileModal.classList.remove('hidden');

                // FORCE display with inline style + !important override
                profileModal.style.cssText = `
                    display: flex !important;
                    visibility: visible !important;
                    opacity: 1 !important;
                    z-index: 50 !important;
                `;

                document.body.style.overflow = 'hidden';

            } else {
            }

            // Load profile data
            const response = await fetch(`/get_user_profile/${userId}`);

            if (!response.ok) {
                const text = await response.text();
                let errorMessage = `HTTP ${response.status}: Failed to load profile`;
                try {
                    const errorData = JSON.parse(text);
                    errorMessage = errorData.error || errorData.message || errorMessage;
                } catch {}
                throw new Error(errorMessage);
            }

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            this.displayProfileModal(data, userId, fromFriendRequestNotification);

        } catch (error) {

            const modalBody = document.getElementById('profileModalBody');
            if (modalBody) {
                modalBody.innerHTML = `
                    <div class="text-center p-8 text-red-500 min-h-[400px] flex flex-col items-center justify-center">
                        <i class="bi bi-exclamation-triangle text-4xl mb-4"></i>
                        <p class="text-lg font-medium mb-2">Failed to load profile</p>
                        <p class="text-sm text-gray-600 mb-4">${error.message}</p>
                        <div class="flex space-x-2">
                            <button onclick="ProfileSystem.openProfileModal(${userId})"
                                    class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                                Try Again
                            </button>
                            <button onclick="Modal.close('profileModal')"
                                    class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors">
                                Close
                            </button>
                        </div>
                    </div>
                `;
            }

            Toast.show('Failed to load profile: ' + error.message, 'danger');
        }
    },

    displayProfileModal(data, userId, fromFriendRequestNotification = false) {
        const modalBody = document.getElementById('profileModalBody');
        const profileActions = document.getElementById('profileActions');

        if (!modalBody || !profileActions) return;

        try {
            // Safely parse data with defaults
            const userData = {
                first_name: data.first_name || '',
                last_name: data.last_name || '',
                profile_pic: data.profile_pic || window.defaultAvatar || '/static/assets/img/default-avatar.png',
                cover_pic: data.cover_pic || 'https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg',
                bio: data.bio || '',
                email: data.email || '',
                phone_number: data.phone_number || '',
                gender: data.gender || '',
                dob: data.dob || '',
                religion: data.religion || '',
                marital_status: data.marital_status || '',
                city: data.city || '',
                state: data.state || '',
                country: data.country || '',
                interests: data.interests || ''
            };

            // Format date of birth
            const dob = userData.dob ? new Date(userData.dob).toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            }) : 'Not specified';

            const age = userData.dob ? TimeUtils.calculateAge(userData.dob) : '';

            modalBody.innerHTML = `
                <div class="profile-modal-content">
                    <div class="profile-header relative">
                        <div class="cover-photo-container h-48 overflow-hidden rounded-t-2xl">
                            <img src="${userData.cover_pic}"
                                 alt="Cover"
                                 class="cover-photo w-full h-full object-cover"
                                 onerror="this.src='https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg'">
                        </div>
                        <div class="profile-info-container text-center relative -mt-16 pb-6 px-6">
                            <div class="profile-avatar-container inline-block">
                                <img src="${userData.profile_pic}"
                                     alt="${userData.first_name}"
                                     class="profile-avatar w-32 h-32 rounded-full border-4 border-white object-cover shadow-strong"
                                     onerror="this.src='${window.defaultAvatar || '/static/assets/img/default-avatar.png'}'">
                            </div>
                            <div class="profile-text-content mt-4">
                                <h3 class="profile-name text-2xl font-bold">${userData.first_name} ${userData.last_name}</h3>
                                <div class="profile-details flex flex-wrap justify-center gap-2 mt-2">
                                    ${userData.marital_status ? `
                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
                                            <i class="bi bi-heart-fill text-red-500 text-xs"></i>
                                            ${userData.marital_status}
                                        </span>` : ''}
                                    ${userData.city && userData.country ? `
                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
                                            <i class="bi bi-geo-alt-fill text-blue-500 text-xs"></i>
                                            ${userData.city}, ${userData.country}
                                        </span>` : ''}
                                    ${age ? `
                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
                                            <i class="bi bi-balloon-fill text-purple-500 text-xs"></i>
                                            ${age}
                                        </span>` : ''}
                                    ${userData.religion ? `
                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
                                            <i class="bi bi-star-fill text-yellow-500 text-xs"></i>
                                            ${userData.religion}
                                        </span>` : ''}
                                </div>
                                ${userData.bio ? `
                                    <div class="profile-bio mt-4 max-w-2xl mx-auto">
                                        <p class="bio-text text-gray-700 text-sm leading-relaxed">${userData.bio}</p>
                                    </div>` : ''}
                            </div>
                        </div>
                    </div>

                    <div class="profile-details-section mt-6 px-6 pb-6">
                        <div class="grid md:grid-cols-2 gap-6">
                            <div class="detail-card bg-gray-50 rounded-2xl p-6">
                                <h6 class="detail-card-title font-semibold text-lg mb-4 flex items-center">
                                    <i class="bi bi-person-badge-fill mr-2 text-blue-500"></i>Personal Info
                                </h6>
                                <div class="detail-list space-y-3">
                                    ${userData.email ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Email:</span>
                                            <span class="detail-value text-sm">${userData.email}</span>
                                        </div>` : ''}
                                    ${userData.phone_number ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Phone:</span>
                                            <span class="detail-value text-sm">${userData.phone_number}</span>
                                        </div>` : ''}
                                    ${userData.gender ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Gender:</span>
                                            <span class="detail-value text-sm">${userData.gender}</span>
                                        </div>` : ''}
                                    ${userData.dob ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Birth:</span>
                                            <span class="detail-value text-sm">${dob}</span>
                                        </div>` : ''}
                                    ${userData.religion ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Religion:</span>
                                            <span class="detail-value text-sm">${userData.religion}</span>
                                        </div>` : ''}
                                </div>
                            </div>
                            <div class="detail-card bg-gray-50 rounded-2xl p-6">
                                <h6 class="detail-card-title font-semibold text-lg mb-4 flex items-center">
                                    <i class="bi bi-geo-fill mr-2 text-green-500"></i>Location & Interests
                                </h6>
                                <div class="detail-list space-y-3">
                                    ${userData.city ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">City:</span>
                                            <span class="detail-value text-sm">${userData.city}</span>
                                        </div>` : ''}
                                    ${userData.state ? `
                                    <div class="detail-row flex items-start">
                                        <span class="detail-label font-medium text-gray-600 min-w-24">State:</span>
                                        <span class="detail-value text-sm">${userData.state}</span>
                                    </div>` : ''}
                                    ${userData.country ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Country:</span>
                                            <span class="detail-value text-sm">${userData.country}</span>
                                        </div>` : ''}
                                    ${userData.interests ? `
                                        <div class="detail-row flex items-start">
                                            <span class="detail-label font-medium text-gray-600 min-w-24">Interests:</span>
                                            <span class="detail-value text-sm">${userData.interests}</span>
                                        </div>` : ''}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Set action buttons based on how the modal was opened
            if (fromFriendRequestNotification) {
                profileActions.innerHTML = `
                    <div class="flex flex-wrap gap-3 justify-center py-6">
                        <!-- Accept Button -->
                        <button class="relative px-5 py-2 bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                onclick="FriendSystem.acceptFriendRequest(${userId}, this)">
                            <!-- Shimmer effect -->
                            <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                            <!-- Content -->
                            <div class="relative flex items-center gap-2">
                                <i class="bi bi-check-lg text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                <span class="text-xs group-hover:font-medium transition-all duration-300">Accept</span>
                                <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                            </div>
                        </button>

                        <!-- Decline Button -->
                        <button class="relative px-5 py-2 bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                onclick="FriendSystem.declineFriendRequest(${userId}, this)">
                            <!-- Shimmer effect -->
                            <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                            <!-- Content -->
                            <div class="relative flex items-center gap-2">
                                <i class="bi bi-x-lg text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                <span class="text-xs group-hover:font-medium transition-all duration-300">Decline</span>
                                <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                            </div>
                        </button>

                        <!-- Cancel Button -->
                        <button class="relative px-5 py-2 bg-gradient-to-r from-gray-400 to-gray-600 hover:from-gray-500 hover:to-gray-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                onclick="Modal.close('profileModal')">
                            <!-- Shimmer effect -->
                            <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/15 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                            <!-- Content -->
                            <div class="relative flex items-center gap-2">
                                <i class="bi bi-x-circle text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                <span class="text-xs group-hover:font-medium transition-all duration-300">Cancel</span>
                                <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                            </div>
                        </button>

                        <!-- View Full Profile Button -->
                        <a href="/profile/${userId}"
                           class="relative px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md border border-blue-600"
                           onclick="Modal.close('profileModal')">
                            <!-- Subtle background effect -->
                            <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/0 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                            <!-- Content -->
                            <div class="relative flex items-center gap-2">
                                <i class="bi bi-person-square text-sm text-white group-hover:text-white transition-colors duration-300"></i>
                                <span class="text-sm font-semibold text-white group-hover:text-white transition-colors duration-300">View Full Profile</span>
                                <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                            </div>
                        </a>
                    </div>
                `;
            } else {
                this.updateProfileActions(userId);
            }

        } catch (error) {
            modalBody.innerHTML = `
                <div class="text-center p-8 text-red-500 min-h-[400px] flex flex-col items-center justify-center">
                    <i class="bi bi-exclamation-triangle text-5xl mb-4"></i>
                    <p class="text-xl font-medium">Error displaying profile</p>
                    <p class="text-sm mt-2 text-gray-600">${error.message || 'Unknown error'}</p>
                </div>
            `;
        }
    },

    async updateProfileActions(userId) {
        const profileActions = document.getElementById('profileActions');
        if (!profileActions) return;

        try {
            // Check friend status
            const response = await fetch(`/check_friend_status/${userId}`);
            if (response.ok) {
                const data = await response.json();

                let actionsHTML = '';

                switch(data.status) {
                    case 'friends':
                        actionsHTML = `
                            <div class="flex flex-wrap gap-3 justify-center py-6">
                                <!-- Message Button -->
                                <button class="relative px-5 py-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                        onclick="window.handleMessageButtonClick(${userId})">
                                    <!-- Shimmer effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-chat-dots text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                        <span class="text-xs group-hover:font-medium transition-all duration-300">Message</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </button>

                                <!-- Block Button -->
                                <button class="relative px-5 py-2 bg-gradient-to-r from-red-500 to-pink-600 hover:from-red-600 hover:to-pink-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                        onclick="BlockSystem.block(${userId})">
                                    <!-- Shimmer effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-slash-circle text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                        <span class="text-xs group-hover:font-medium transition-all duration-300">Block</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </button>

                                <!-- View Full Profile Button -->
                                <a href="/profile/${userId}"
                                   class="relative px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md border border-blue-600"
                                   onclick="Modal.close('profileModal')">
                                    <!-- Subtle background effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/0 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-person-square text-sm text-white group-hover:text-white transition-colors duration-300"></i>
                                        <span class="text-sm font-semibold text-white group-hover:text-white transition-colors duration-300">View Full Profile</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </a>
                            </div>
                        `;
                        break;

                    case 'request_sent':
                        actionsHTML = `
                            <div class="flex flex-wrap gap-3 justify-center py-6">
                                <!-- Cancel Request Button -->
                                <button class="relative px-5 py-2 bg-gradient-to-r from-gray-400 to-gray-600 hover:from-gray-500 hover:to-gray-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                        onclick="FriendSystem.cancelRequest(${userId}, this)">
                                    <!-- Shimmer effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/15 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-clock-history text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                        <span class="text-xs group-hover:font-medium transition-all duration-300">Cancel Request</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </button>

                                <!-- View Full Profile Button -->
                                <a href="/profile/${userId}"
                                   class="relative px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md border border-blue-600"
                                   onclick="Modal.close('profileModal')">
                                    <!-- Subtle background effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/0 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-person-square text-sm text-white group-hover:text-white transition-colors duration-300"></i>
                                        <span class="text-sm font-semibold text-white group-hover:text-white transition-colors duration-300">View Full Profile</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </a>
                            </div>
                        `;
                        break;

                    case 'request_received':
                        actionsHTML = `
                            <div class="flex flex-wrap gap-3 justify-center py-6">
                                <!-- Accept Button -->
                                <button class="relative px-5 py-2 bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                        onclick="FriendSystem.acceptFriendRequest(${userId}, this)">
                                    <!-- Shimmer effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-check-lg text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                        <span class="text-xs group-hover:font-medium transition-all duration-300">Accept</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </button>

                                <!-- Decline Button -->
                                <button class="relative px-5 py-2 bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                        onclick="FriendSystem.declineFriendRequest(${userId}, this)">
                                    <!-- Shimmer effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-x-lg text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                        <span class="text-xs group-hover:font-medium transition-all duration-300">Decline</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </button>

                                <!-- View Full Profile Button -->
                                <a href="/profile/${userId}"
                                   class="relative px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md border border-blue-600"
                                   onclick="Modal.close('profileModal')">
                                    <!-- Subtle background effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/0 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-person-square text-sm text-white group-hover:text-white transition-colors duration-300"></i>
                                        <span class="text-sm font-semibold text-white group-hover:text-white transition-colors duration-300">View Full Profile</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </a>
                            </div>
                        `;
                        break;

                    default:
                        actionsHTML = `
                            <div class="flex flex-wrap gap-3 justify-center py-6">
                                <!-- Connect Button -->
                                <button class="relative px-5 py-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                                        onclick="FriendSystem.add(${userId}, this)">
                                    <!-- Shimmer effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-person-plus text-sm group-hover:scale-110 transition-transform duration-300"></i>
                                        <span class="text-xs group-hover:font-medium transition-all duration-300">Connect</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </button>

                                <!-- View Full Profile Button -->
                                <a href="/profile/${userId}"
                                   class="relative px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md border border-blue-600"
                                   onclick="Modal.close('profileModal')">
                                    <!-- Subtle background effect -->
                                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/0 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                                    <!-- Content -->
                                    <div class="relative flex items-center gap-2">
                                        <i class="bi bi-person-square text-sm text-white group-hover:text-white transition-colors duration-300"></i>
                                        <span class="text-sm font-semibold text-white group-hover:text-white transition-colors duration-300">View Full Profile</span>
                                        <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                                    </div>
                                </a>
                            </div>
                        `;
                }

                profileActions.innerHTML = actionsHTML;
            }
        } catch (error) {
            // Fallback with beautiful buttons
            profileActions.innerHTML = `
                <div class="flex flex-wrap gap-3 justify-center py-6">
                    <!-- Connect Button -->
                    <button class="relative px-5 py-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white rounded-xl font-medium transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md"
                            onclick="FriendSystem.add(${userId}, this)">
                        <!-- Shimmer effect -->
                        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                        <!-- Content -->
                        <div class="relative flex items-center gap-2">
                            <i class="bi bi-person-plus text-sm group-hover:scale-110 transition-transform duration-300"></i>
                            <span class="text-xs group-hover:font-medium transition-all duration-300">Connect</span>
                            <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                        </div>
                    </button>

                    <!-- View Full Profile Button -->
                    <a href="/profile/${userId}"
                       class="relative px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-all duration-300 overflow-hidden group shadow-sm hover:shadow-md border border-blue-600"
                       onclick="Modal.close('profileModal')">
                        <!-- Subtle background effect -->
                        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/0 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>

                        <!-- Content -->
                        <div class="relative flex items-center gap-2">
                            <i class="bi bi-person-square text-sm text-white group-hover:text-white transition-colors duration-300"></i>
                            <span class="text-sm font-semibold text-white group-hover:text-white transition-colors duration-300">View Full Profile</span>
                            <i class="bi bi-arrow-right-short text-xs opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300 ml-1"></i>
                        </div>
                    </a>
                </div>
            `;
        }
    }
};

// ========================================
// BLOCK SYSTEM
// ========================================

const BlockSystem = {
    async block(userId) {
        if (!confirm("Block this user? They won't see your posts or be able to contact you.")) return;

        const button = event?.target;
        if (button) Loader.quick(button, 'show');

        try {
            const response = await fetch(`/block_user/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                Toast.show('User blocked successfully!', 'success');
                Modal.close('profileModal');
                setTimeout(() => location.reload(), 1500);
            } else {
                Toast.show(data.error || 'Error blocking user', 'danger');
            }
        } catch (error) {
            Toast.show('Error blocking user. Please try again.', 'danger');
        } finally {
            if (button) Loader.quick(button, 'hide');
        }
    },

    async unblock(userId) {
        if (!confirm("Unblock this user? They will be able to see your posts again.")) return;

        const button = event?.target;
        if (button) Loader.quick(button, 'show');

        try {
            const response = await fetch(`/unblock_user/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                Toast.show('User unblocked!', 'success');
                Modal.close('profileModal');
            } else {
                Toast.show(data.error || 'Failed to unblock', 'danger');
            }
        } catch (error) {
            Toast.show('Error unblocking user', 'danger');
        } finally {
            if (button) Loader.quick(button, 'hide');
        }
    }
};

// ========================================
// NOTIFICATION SYSTEM
// ========================================

const NotificationSystem = {
    async updateBadge() {
        try {
            const response = await fetch('/notifications/count');
            if (!response.ok) return;
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) return;

            const data = await response.json();
            const badge = document.getElementById('notificationBadge');
            if (!badge) return;

            if (data.count > 0) {
                badge.textContent = data.count > 99 ? '99+' : data.count;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        } catch (error) {
        }
    },

    async load() {
        const list = document.getElementById('notificationsList');
        if (!list) return;

        list.innerHTML = `
            <div class="space-y-3 p-3">
                ${Array(3).fill().map(() => `
                    <div class="flex items-center space-x-3 p-3 animate-pulse">
                        <div class="w-10 h-10 rounded-full bg-gray-200"></div>
                        <div class="flex-1 space-y-2">
                            <div class="h-3 bg-gray-200 rounded w-3/4"></div>
                            <div class="h-2 bg-gray-200 rounded w-1/2"></div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        try {
            const response = await fetch('/notifications');
            if (!response.ok) throw new Error('Network error');
            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                throw new Error('Invalid notifications response');
            }
            const notifications = await response.json();
            this.display(notifications, list);
        } catch (error) {
            list.innerHTML = '<div class="text-center p-4 text-red-500"><i class="bi bi-exclamation-triangle"></i><p>Error loading notifications</p></div>';
        }
    },

    display(notifications, list) {
        if (!notifications || notifications.length === 0) {
            list.innerHTML = '<div class="text-center p-6 text-gray-500"><i class="bi bi-bell text-4xl mb-2"></i><p>No notifications yet</p></div>';
            return;
        }

        list.innerHTML = notifications.map(notification => {
            const actor = notification.actor || {};
            const actorName = actor.name || "Someone";
            const actorAvatar = actor.avatar || window.defaultAvatar || '/static/assets/img/default-avatar.png';
            const actorId = actor.id || 0;
            const isFriendRequest = notification.type === 'friend_request';

            return `
                            <div class="notification-item p-3 border-b border-gray-100 ${notification.is_read ? '' : 'bg-blue-50 border-l-4 border-l-blue-500'} cursor-pointer"
                onclick="NotificationSystem.handleNotificationClick(event, ${notification.id}, '${notification.type}', ${actorId || 0})">

                <div class="flex items-start space-x-3">
                    <img src="${actorAvatar}" alt="${actorName}" class="w-10 h-10 rounded-full object-cover"
                         onerror="this.src='${window.defaultAvatar || '/static/assets/img/default-avatar.png'}'">
                    <div class="flex-1">
                        <div class="notification-text text-sm">${notification.message || ''}</div>
                        <div class="notification-time text-xs text-gray-500 mt-1">${TimeUtils.formatNotificationTime(notification.created_at)}</div>
                        ${isFriendRequest ? `
                        <div class="notification-actions flex space-x-2 mt-2">
                            ${!notification.is_read && actorId ? `
                                <button class="notification-action-btn px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors"
                                        onclick="event.stopPropagation(); NotificationSystem.acceptFriendRequest(${actorId}, ${notification.id})">
                                        Accept
                                </button>
                                <button class="notification-action-btn px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded-lg hover:bg-gray-300 transition-colors"
                                        onclick="event.stopPropagation(); NotificationSystem.declineFriendRequest(${actorId}, ${notification.id})">
                                        Decline
                                </button>
                            ` : `<small class="text-gray-500 text-xs">Request handled</small>`}
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
            `;
        }).join('');
    },

    async handleNotificationClick(event, id, type, actorId) {
        // Prevent action if clicked on Accept/Decline buttons in notification
        if (event.target.closest('.notification-action-btn')) {
            return;
        }

        // Mark as read
        await this.markAsRead(id);

        let openFromFriendRequest = false;

        // Special case: if it's a friend request notification, remember that
        if (type === 'friend_request' && actorId) {
            openFromFriendRequest = true;
        }

        // Open profile modal with extra context
        ProfileSystem.openProfileModal(actorId, openFromFriendRequest);

        // Close dropdown
        const dropdownElement = document.getElementById('notificationDropdown');
        const bsDropdown = bootstrap.Dropdown.getInstance(dropdownElement);
        if (bsDropdown) {
            bsDropdown.hide();
        }
    },

    async markAsRead(id) {
        try {
            await fetch(`/notifications/${id}/read`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });
            this.updateBadge();
            this.load();
        } catch (error) {
        }
    },

    async acceptFriendRequest(userId, notifId) {
        const button = event?.target;
        if (!button) return;

        Loader.quick(button, 'show');

        try {
            const response = await fetch(`/accept_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ notification_id: notifId })
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                await this.markAsRead(notifId);
                button.innerHTML = `<i class="bi bi-check"></i> Accepted`;
                button.className = 'px-3 py-1 bg-green-100 text-green-700 text-xs rounded-lg';
                Toast.show('Friend request accepted!', 'success');
            } else {
                throw new Error(data.error || 'Failed to accept request');
            }
        } catch (error) {
            Toast.show('Failed to accept friend request', 'danger');
        }
    },

    async declineFriendRequest(userId, notifId) {
        const button = event?.target;
        if (!button) return;

        Loader.quick(button, 'show');

        try {
            const response = await fetch(`/decline_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ notification_id: notifId })
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                await this.markAsRead(notifId);
                button.innerHTML = `<i class="bi bi-x"></i> Declined`;
                button.className = 'px-3 py-1 bg-gray-100 text-gray-700 text-xs rounded-lg';
                Toast.show('Request declined', 'info');
            } else {
                throw new Error(data.error || 'Failed to decline request');
            }
        } catch (error) {
            Toast.show('Failed to decline friend request', 'danger');
        }
    },

    scrollToPost(postId) {
        const el = document.querySelector(`[data-post-id="${postId}"]`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('highlight-animation');
            setTimeout(() => el.classList.remove('highlight-animation'), 2000);
        } else {
            Toast.show('Post not found', 'warning');
        }
    },

    init() {
        if (appState.notificationCheckInterval) {
            clearInterval(appState.notificationCheckInterval);
        }

        this.load();
        this.updateBadge();
        appState.notificationCheckInterval = setInterval(() => this.updateBadge(), 30000);

        const dropdown = document.getElementById('notificationDropdown');
        if (dropdown) {
            dropdown.addEventListener('click', () => this.load());
        }
    }
};

// ========================================
// SEARCH SYSTEM
// ========================================

const SearchSystem = {
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    highlightMatch(text, query) {
        if (!query || !query.trim()) return text;
        const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedQuery})`, 'gi');
        return text.replace(regex, '<span class="bg-yellow-200 px-1 rounded">$1</span>');
    },

    async perform(query) {
        if (!query.trim()) {
            this.hideResults();
            return;
        }

        this.showLoading();

        try {
            const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            this.displayResults(data, query);
        } catch (error) {
            this.showError();
        }
    },

    displayResults(results, query) {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = '';

        if (!results.users?.length && !results.posts?.length) {
            this.showNoResults();
            return;
        }

        let html = '';

        if (results.users?.length > 0) {
            results.users.forEach(user => {
                const name = this.highlightMatch(`${user.first_name} ${user.last_name}`, query);
                html += `
                    <div class="search-result-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors" onclick="openProfileModal(${user.id})">
                        <div class="search-result-user flex items-center space-x-3">
                            <img src="${user.profile_pic || window.defaultAvatar}" class="search-result-avatar w-10 h-10 rounded-full object-cover">
                            <div class="search-result-info">
                                <div class="search-result-name font-medium">${name}</div>
                                <div class="search-result-type text-xs text-gray-500">User</div>
                            </div>
                        </div>
                    </div>
                `;
            });
        }

        if (results.posts?.length > 0) {
            results.posts.forEach(post => {
                const content = this.highlightMatch(post.content.substring(0, 100), query);
                html += `
                    <div class="search-result-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors" onclick="SearchSystem.viewPost(${post.id})">
                        <div class="search-result-post">
                            <div class="search-result-content text-sm">${content}${post.content.length > 100 ? '...' : ''}</div>
                            <div class="search-result-author text-xs text-gray-500 mt-1">By ${post.author_first_name} ${post.author_last_name}</div>
                            <div class="search-result-type text-xs text-gray-500">Post</div>
                        </div>
                    </div>
                `;
            });
        }

        searchResultsBody.innerHTML = html;
        this.showResults();
    },

    showLoading() {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = `
            <div class="search-loading text-center p-6">
                <div class="flex flex-col items-center justify-center">
                    <span class="tiny-loader md mb-3"></span>
                    <div class="text-gray-500 text-sm">Searching...</div>
                </div>
            </div>
        `;
        this.showResults();
    },

    showNoResults() {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = `
            <div class="no-results text-center p-6 text-gray-500">
                <i class="bi bi-search text-3xl mb-2"></i>
                <p>No results</p>
            </div>
        `;
        this.showResults();
    },

    showError() {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = `
            <div class="no-results text-center p-6 text-red-500">
                <i class="bi bi-exclamation-triangle text-3xl mb-2"></i>
                <p>Search failed</p>
            </div>
        `;
        this.showResults();
    },

    showResults() {
        const searchResults = document.getElementById('searchResults');
        if (searchResults) searchResults.classList.remove('hidden');
    },

    hideResults() {
        const searchResults = document.getElementById('searchResults');
        if (searchResults) searchResults.classList.add('hidden');
    },

    async viewPost(postId) {
        this.hideResults();

        const searchInput = document.getElementById('globalSearch');
        if (searchInput) searchInput.value = '';

        const el = document.querySelector(`[data-post-id="${postId}"]`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('highlight-animation');
            setTimeout(() => el.classList.remove('highlight-animation'), 2000);
        } else {
            try {
                const response = await fetch(`/get_post/${postId}`);
                if (!response.ok) throw new Error('Network error');

                const post = await response.json();
                if (post.error) throw new Error(post.error);

                this.displayPostModal(post);
            } catch (error) {
                Toast.show('Post not found', 'danger');
            }
        }
    },

    displayPostModal(post) {
        const body = document.getElementById('commentModalBody');
        if (!body) return;

        body.innerHTML = `
            <div class="post-card bg-white rounded-2xl shadow-soft overflow-hidden">
                <div class="p-4 flex justify-between items-start">
                    <div class="flex items-start space-x-3">
                        <img src="${post.author_profile_pic || window.defaultAvatar}" class="w-10 h-10 rounded-full object-cover">
                        <div>
                            <div class="font-semibold">${post.author_first_name || ''} ${post.author_last_name || ''}</div>
                            <div class="text-sm text-gray-500">
                                ${new Date(post.created_at).toLocaleString()}
                                ${post.location ? `<span class="mx-1">•</span><span class="inline-flex items-center gap-1 text-blue-600"><i class="bi bi-geo-alt-fill"></i>Posting from ${post.location}</span>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
                <div class="px-4 pb-3">
                    <p class="post-text">${post.content || ''}</p>
                    ${post.image ? `<div class="post-media mt-3"><img src="${post.image}" alt="Post" class="w-full rounded-2xl max-h-96 object-cover"></div>` : ''}
                    ${post.video ? `<div class="post-media mt-3"><video controls class="w-full rounded-2xl max-h-96"><source src="${post.video}"></video></div>` : ''}
                </div>
            </div>
        `;
        Modal.open('commentModal');
    },

    init() {
        const searchInput = document.getElementById('globalSearch');
        const searchResults = document.getElementById('searchResults');
        const searchResultsBody = document.getElementById('searchResultsBody');

        if (!searchInput || !searchResults || !searchResultsBody) return;

        const debouncedSearch = this.debounce((query) => {
            this.perform(query);
        }, 300);

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            if (query.length >= 2) {
                debouncedSearch(query);
            } else {
                this.hideResults();
            }
        });

        searchInput.addEventListener('focus', (e) => {
            const query = e.target.value.trim();
            if (query.length >= 2) {
                this.perform(query);
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchResults.contains(e.target) && e.target !== searchInput) {
                this.hideResults();
            }
        });
    }
};

// ========================================
// SPONSORED ADS SYSTEM
// ========================================

const AdSystem = {
    // Configuration - Updated timing
    config: {
        adInterval: 40000, // 70 seconds between ads (adjustable between 60-90s)
        rotationInterval: 60000, // 90 seconds between different ads
        modalDisplayTime: 10000, // 10 seconds for modal display
        maxRetries: 3,
        retryDelay: 2000,
        initialDelay: 3000, // Wait 3 seconds before showing first ad
        randomizeInterval: true // Add randomness to intervals
    },

    // DOM elements cache
    elements: {
        native: null,
        floating: null,
        modal: null,
        modalContent: null,
        nativeElements: {},
        floatingElements: {},
        modalElements: {}
    },

    // State management
    state: {
        activeAds: [],
        displayedIndices: [],
        currentAdIndex: 0,
        rotationTimer: null,
        modalTimer: null,
        intervalTimer: null,
        adQueue: [],
        nextAdTime: null,
        initialized: false,
        retryCount: 0,
        csrfToken: null,
        isShowingAd: false
    },

    // Initialize ad system
    async init() {

        try {
            // Cache DOM elements
            this.cacheElements();

            // Get CSRF token
            this.state.csrfToken = this.getCsrfToken();

            // Show containers if they exist
            this.showContainers();

            // Load ads but don't display immediately
            await this.loadAds();

            // Wait initial delay before showing first ad
            setTimeout(() => {
                this.startAdCycle();
            }, this.config.initialDelay);

            this.state.initialized = true;
            return this;

        } catch (error) {
            this.showErrorState('Initialization failed');
            throw error;
        }
    },

    // Start the ad display cycle
    startAdCycle() {
        if (this.state.activeAds.length === 0) {
            this.showNoAdsMessage();
            return;
        }


        // Clear any existing timers
        this.clearAllTimers();

        // Schedule first ad
        this.scheduleNextAd();
    },

    // Schedule next ad display
    scheduleNextAd() {
        // Clear existing timer
        if (this.state.intervalTimer) {
            clearTimeout(this.state.intervalTimer);
            this.state.intervalTimer = null;
        }

        // Calculate next interval (with optional randomness)
        let interval = this.config.adInterval;
        if (this.config.randomizeInterval) {
            // Add ±10 seconds randomness
            interval += (Math.random() * 20000 - 10000);
            interval = Math.max(60000, Math.min(90000, interval)); // Keep between 60-90s
        }


        // Set timer for next ad
        this.state.intervalTimer = setTimeout(() => {
            this.displayNextAd();
        }, interval);

        // Store next ad time
        this.state.nextAdTime = Date.now() + interval;
    },

    // Display the next ad
    displayNextAd() {
        if (this.state.activeAds.length === 0 || this.state.isShowingAd) {
            this.scheduleNextAd();
            return;
        }

        this.state.isShowingAd = true;

        // Get random ad
        const ad = this.getNextAd();
        if (!ad) {
            this.state.isShowingAd = false;
            this.scheduleNextAd();
            return;
        }


        // Update all ad displays
        this.updateNativeAd(ad);
        this.updateFloatingAd(ad);
        this.showAdModal(ad);

        // Track impression
        this.trackAdImpression(ad.id);

        // Hide the ad after modal display time
        setTimeout(() => {
            this.state.isShowingAd = false;
            // Schedule next ad
            this.scheduleNextAd();
        }, this.config.modalDisplayTime + 3000); // Add 3 seconds buffer
    },

    // Get next ad to display
    getNextAd() {
        if (this.state.activeAds.length === 0) return null;

        // Reset if all ads have been shown
        if (this.state.displayedIndices.length >= this.state.activeAds.length) {
            this.state.displayedIndices = [];
        }

        // Get available indices (not shown recently)
        const availableIndices = [];
        for (let i = 0; i < this.state.activeAds.length; i++) {
            if (!this.state.displayedIndices.includes(i)) {
                availableIndices.push(i);
            }
        }

        // If no new ads, use random from all
        const useIndices = availableIndices.length > 0 ? availableIndices :
                          Array.from({length: this.state.activeAds.length}, (_, i) => i);

        // Pick random
        const randomIndex = Math.floor(Math.random() * useIndices.length);
        const selectedIndex = useIndices[randomIndex];

        // Track displayed ad
        this.state.displayedIndices.push(selectedIndex);
        this.state.currentAdIndex = selectedIndex;

        return this.state.activeAds[selectedIndex];
    },

    // Cache DOM elements for better performance
    cacheElements() {
        // Main containers
        this.elements.native = document.getElementById('nativeAd');
        this.elements.floating = document.getElementById('floatingAdContent');
        this.elements.modal = document.getElementById('adModal');

        if (this.elements.modal) {
            this.elements.modalContent = this.elements.modal.querySelector('.ad-modal-content');
        }

        // Native ad elements
        this.elements.nativeElements = {
            advertiser: document.getElementById('nativeAdAdvertiser'),
            title: document.getElementById('nativeAdTitle'),
            description: document.getElementById('nativeAdDescription'),
            image: document.getElementById('nativeAdImage'),
            link: document.getElementById('nativeAdLink'),
            cta: document.getElementById('nativeAdCTA')
        };

        // Floating ad elements
        this.elements.floatingElements = {
            title: document.getElementById('floatingAdTitle'),
            desc: document.getElementById('floatingAdDesc'),
            link: document.getElementById('floatingAdLink')
        };

        // Modal elements
        this.elements.modalElements = {
            image: document.getElementById('adModalImage'),
            title: document.getElementById('adModalTitle'),
            description: document.getElementById('adModalDescription'),
            link: document.getElementById('adModalLink'),
            cta: document.getElementById('adModalCTA')
        };
    },

    // Get CSRF token from meta tag or cookie
    getCsrfToken() {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) return metaTag.getAttribute('content');

        const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
        if (cookieMatch) return cookieMatch[1];

        return window.csrfToken || null;
    },

    // Show/hide containers
    showContainers() {
        if (this.elements.native) {
            this.elements.native.classList.remove('hidden');
        }

        if (this.elements.floating) {
            this.elements.floating.classList.remove('hidden');
        }
    },

    hideContainers() {
        if (this.elements.native) {
            this.elements.native.classList.add('hidden');
        }

        if (this.elements.floating) {
            this.elements.floating.classList.add('hidden');
        }
    },

    // Load ads from server with retry logic
    async loadAds() {
        if (this.state.retryCount >= this.config.maxRetries) {
            this.showErrorState('Failed to load ads after multiple attempts');
            return;
        }

        try {

            const response = await fetch('/api/ads/sponsored', {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Cache-Control': 'no-cache'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success && data.ads && Array.isArray(data.ads) && data.ads.length > 0) {
                this.state.activeAds = data.ads;
                this.state.displayedIndices = [];
                this.state.retryCount = 0;


            } else {
                this.showNoAdsMessage();
            }

        } catch (error) {
            this.state.retryCount++;

            // Retry with exponential backoff
            setTimeout(() => {
                this.loadAds();
            }, this.config.retryDelay * Math.pow(2, this.state.retryCount - 1));

            this.showErrorState('Temporarily unavailable');
        }
    },

    // Update native ad
    updateNativeAd(ad) {
        if (!this.elements.native || !ad) return;

        const { nativeElements } = this.elements;

        // Helper to safely update element
        const updateElement = (element, value, fallback = '') => {
            if (element) {
                element.textContent = value || fallback;
            }
        };

        updateElement(nativeElements.advertiser, ad.advertiser_name, 'Sponsored Partner');
        updateElement(nativeElements.title, ad.title, 'Special Offer');
        updateElement(nativeElements.description, ad.description, 'Check out this amazing offer!');
        updateElement(nativeElements.cta, ad.cta_text, 'Learn More');

        // Update image
        if (nativeElements.image) {
            const imageUrl = ad.image_url || 'https://via.placeholder.com/400x200/3B82F6/FFFFFF?text=Sponsored+Ad';
            nativeElements.image.src = imageUrl;
            nativeElements.image.alt = ad.title || 'Sponsored Advertisement';
            nativeElements.image.onerror = () => {
                nativeElements.image.src = 'https://via.placeholder.com/400x200/3B82F6/FFFFFF?text=Sponsored+Ad';
            };
        }

        // Update link
        if (nativeElements.link) {
            nativeElements.link.href = ad.cta_url || '#';
            nativeElements.link.target = '_blank';
            nativeElements.link.onclick = (e) => {
                this.trackAdClick(ad.id);
                return true;
            };
        }

        // Ensure container is visible
        this.elements.native.classList.remove('hidden');
    },

    // Update floating ad
    updateFloatingAd(ad) {
        if (!this.elements.floating || !ad) return;

        const { floatingElements } = this.elements;

        if (floatingElements.title) {
            floatingElements.title.textContent = (ad.title || 'Special Offer!').substring(0, 30);
        }

        if (floatingElements.desc) {
            floatingElements.desc.textContent = (ad.description || 'Amazing deals available').substring(0, 40);
        }

        if (floatingElements.link) {
            floatingElements.link.href = ad.cta_url || '#';
            floatingElements.link.onclick = (e) => {
                this.trackAdClick(ad.id);
                return true;
            };
        }
    },

    // Show ad modal
    showAdModal(ad) {
        if (!this.elements.modal || !ad) return;

        const { modalElements } = this.elements;

        // Update modal content
        if (modalElements.image) {
            const imageUrl = ad.image_url || 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Sponsored+Ad';
            modalElements.image.src = imageUrl;
            modalElements.image.alt = ad.title || 'Sponsored Advertisement';
            modalElements.image.onerror = () => {
                modalElements.image.src = 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Sponsored+Ad';
            };
        }

        if (modalElements.title) {
            modalElements.title.textContent = ad.title || 'Special Offer';
        }

        if (modalElements.description) {
            modalElements.description.textContent = ad.description || 'Check out this amazing offer!';
        }

        if (modalElements.link) {
            modalElements.link.href = ad.cta_url || '#';
            modalElements.link.target = '_blank';
            modalElements.link.onclick = () => this.trackAdClick(ad.id);
        }

        if (modalElements.cta) {
            modalElements.cta.textContent = ad.cta_text || 'Learn More';
        }

        // Show modal with animation
        this.elements.modal.classList.remove('hidden');
        setTimeout(() => {
            if (this.elements.modalContent) {
                this.elements.modalContent.classList.remove('scale-95', 'opacity-0');
                this.elements.modalContent.classList.add('scale-100', 'opacity-100');
            }
        }, 50);

        // Clear any existing timer
        if (this.state.modalTimer) {
            clearTimeout(this.state.modalTimer);
        }

        // Auto-hide after configured time
        this.state.modalTimer = setTimeout(() => {
            this.closeAdModal();
        }, this.config.modalDisplayTime);
    },

    // Close ad modal
    closeAdModal() {
        if (!this.elements.modal) return;

        if (this.elements.modalContent) {
            this.elements.modalContent.classList.remove('scale-100', 'opacity-100');
            this.elements.modalContent.classList.add('scale-95', 'opacity-0');
        }

        setTimeout(() => {
            this.elements.modal.classList.add('hidden');
        }, 300);
    },

    // User not interested
    async adNotInterested() {
        const currentAd = this.state.activeAds[this.state.currentAdIndex];
        if (currentAd) {

            try {
                await fetch(`/api/ads/${currentAd.id}/not_interested`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-Token': this.state.csrfToken,
                        'Content-Type': 'application/json'
                    }
                });
            } catch (error) {
            }
        }

        this.closeAdModal();

        // Continue with next ad schedule
        this.state.isShowingAd = false;
        this.scheduleNextAd();
    },

    // Clear all timers
    clearAllTimers() {
        if (this.state.rotationTimer) {
            clearInterval(this.state.rotationTimer);
            this.state.rotationTimer = null;
        }

        if (this.state.modalTimer) {
            clearTimeout(this.state.modalTimer);
            this.state.modalTimer = null;
        }

        if (this.state.intervalTimer) {
            clearTimeout(this.state.intervalTimer);
            this.state.intervalTimer = null;
        }
    },

    // Track ad click
    async trackAdClick(adId) {

        // Analytics
        if (typeof gtag === 'function') {
            gtag('event', 'ad_click', {
                'ad_id': adId,
                'event_category': 'ads',
                'event_label': 'sponsored_ad'
            });
        }

        // Server tracking
        try {
            await fetch(`/api/ads/${adId}/click`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': this.state.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        } catch (error) {
        }
    },

    // Track ad impression
    async trackAdImpression(adId) {

        // Analytics
        if (typeof gtag === 'function') {
            gtag('event', 'ad_impression', {
                'ad_id': adId,
                'event_category': 'ads',
                'event_label': 'sponsored_ad'
            });
        }

        // Server tracking
        try {
            await fetch(`/api/ads/${adId}/impression`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': this.state.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        } catch (error) {
        }
    },

    // Show no ads message
    showNoAdsMessage() {
        if (this.elements.native) {
            this.elements.native.innerHTML = `
                <div class="p-6 text-center">
                    <i class="bi bi-megaphone text-3xl text-gray-300 mb-3"></i>
                    <p class="text-gray-500">No sponsored ads available at the moment</p>
                    <p class="text-sm text-gray-400 mt-1">Check back later for amazing offers!</p>
                </div>
            `;
        }
    },

    // Show error state
    showErrorState(message = 'Unable to load ads') {
        if (this.elements.native) {
            this.elements.native.innerHTML = `
                <div class="p-6 text-center">
                    <i class="bi bi-exclamation-triangle text-3xl text-yellow-500 mb-3"></i>
                    <p class="text-gray-500">${message}</p>
                    <button onclick="AdSystem.refresh()"
                            class="mt-3 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors">
                        Retry
                    </button>
                </div>
            `;
        }
    },

    // Toggle floating ad visibility
    toggleFloatingAd() {
        if (!this.elements.floating) return;

        const isHidden = this.elements.floating.classList.contains('hidden');

        if (isHidden) {
            this.elements.floating.classList.remove('hidden');
            setTimeout(() => {
                this.elements.floating.classList.remove('opacity-0', 'scale-95');
                this.elements.floating.classList.add('opacity-100', 'scale-100');
            }, 10);
        } else {
            this.elements.floating.classList.add('opacity-0', 'scale-95');
            setTimeout(() => {
                this.elements.floating.classList.add('hidden');
            }, 300);
        }
    },

    // Refresh system
    refresh() {

        this.clearAllTimers();
        this.state.isShowingAd = false;
        this.state.displayedIndices = [];
        this.state.retryCount = 0;

        this.loadAds().then(() => {
            setTimeout(() => {
                this.startAdCycle();
            }, 3000);
        });
    },

    // Destroy/cleanup
    destroy() {

        this.clearAllTimers();
        this.closeAdModal();
        this.hideContainers();

        this.state = {
            activeAds: [],
            displayedIndices: [],
            currentAdIndex: 0,
            rotationTimer: null,
            modalTimer: null,
            intervalTimer: null,
            adQueue: [],
            nextAdTime: null,
            initialized: false,
            retryCount: 0,
            csrfToken: null,
            isShowingAd: false
        };
    }
};

// ========================================
// GROUPS SYSTEM
// ========================================

const Groups = {
    // Cache to prevent multiple simultaneous loads
    cache: {
        groups: null,
        lastFetch: null,
        expiry: 30000 // 30 seconds
    },

    // Debounce search
    searchTimer: null,

    // Initialize groups system
    init() {

        // Set up event listeners for dropdowns
        this.setupDropdownListeners();

        // Load groups when page loads
        if (document.querySelector('#groupsList, #groupsListMobile, #groupsListDesktop')) {
            this.load();
        }

        return this;
    },

    // Set up dropdown toggle listeners
    setupDropdownListeners() {
        // Desktop dropdown
        const desktopToggle = document.querySelector('[data-bs-toggle="groups-dropdown"]');
        const desktopDropdown = document.getElementById('groupsDropdownMenu');

        if (desktopToggle && desktopDropdown) {
            desktopToggle.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                desktopDropdown.classList.toggle('hidden');

                if (!desktopDropdown.classList.contains('hidden')) {
                    this.load();
                }
            });
        }

        // Mobile dropdown
        const mobileToggle = document.querySelector('[data-bs-toggle="groups-dropdown-mobile"]');
        const mobileDropdown = document.getElementById('groupsDropdownMenuMobile');

        if (mobileToggle && mobileDropdown) {
            mobileToggle.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                mobileDropdown.classList.toggle('hidden');

                if (!mobileDropdown.classList.contains('hidden')) {
                    this.load();
                }
            });
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.dropdown')) {
                if (desktopDropdown) desktopDropdown.classList.add('hidden');
                if (mobileDropdown) mobileDropdown.classList.add('hidden');
            }
        });
    },

    // Main load function
    async load() {

        // Check cache first
        const now = Date.now();
        if (this.cache.groups && this.cache.lastFetch &&
            (now - this.cache.lastFetch) < this.cache.expiry) {
            this.displayGroups(this.cache.groups);
            return;
        }

        // Show loading state in both lists
        this.showLoading(['groupsList', 'groupsListMobile', 'groupsListDesktop']);

        try {
            const response = await fetch('/get_user_groups', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                },
                cache: 'no-cache' // Prevent browser caching
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const groups = await response.json();

            if (!Array.isArray(groups)) {
                throw new Error('Invalid response format: Expected array');
            }


            // Cache the results
            this.cache.groups = groups;
            this.cache.lastFetch = Date.now();

            // Display groups
            this.displayGroups(groups);

        } catch (error) {
            this.showError(['groupsList', 'groupsListMobile', 'groupsListDesktop'], error.message);

            // Clear cache on error
            this.cache.groups = null;
            this.cache.lastFetch = null;
        }
    },

    // Display groups in dropdowns
    displayGroups(groups) {
        const isAlumniMarriedGroup = (name) => {
            const normalized = (name || '').trim().toLowerCase();
            return normalized.includes('alumni') && normalized.includes('married');
        };

        const orderedGroups = [...(groups || [])].sort((a, b) => {
            const aIsLast = isAlumniMarriedGroup(a?.name);
            const bIsLast = isAlumniMarriedGroup(b?.name);

            if (aIsLast === bIsLast) return 0;
            return aIsLast ? 1 : -1;
        });

        const lists = ['groupsList', 'groupsListMobile', 'groupsListDesktop'];

        lists.forEach(listId => {
            const list = document.getElementById(listId);
            if (!list) return;

            // Clear any existing content
            list.innerHTML = '';

            if (!orderedGroups || orderedGroups.length === 0) {
                this.showEmptyState(list);
                return;
            }

            // Create document fragment for better performance
            const fragment = document.createDocumentFragment();

            orderedGroups.forEach(group => {
                const groupElement = this.createGroupElement(group);
                fragment.appendChild(groupElement);
            });

            list.appendChild(fragment);

            // Add scroll indicator if many groups
            if (groups.length > 5) {
                const scrollIndicator = document.createElement('div');
                scrollIndicator.className = 'text-center py-2 text-xs text-gray-400';
                scrollIndicator.textContent = 'Scroll for more groups...';
                list.appendChild(scrollIndicator);
            }
        });
    },

    // Create individual group element
    createGroupElement(group) {
        const div = document.createElement('div');
        div.className = 'group-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors active:scale-[0.98]';

        // Determine if user is a member
        const isMember = group.is_member || false;

        div.innerHTML = `
            <div class="flex items-center space-x-3" data-group-id="${group.id}">
                <div class="relative flex-shrink-0">
                    <div class="w-10 h-10 rounded-lg bg-gradient-to-r from-blue-400 to-purple-500 overflow-hidden">
                        <img src="${group.cover_pic || 'https://via.placeholder.com/40x40/3B82F6/FFFFFF?text=G'}"
                             alt="${group.name}"
                             class="w-full h-full object-cover"
                             onerror="this.src='https://via.placeholder.com/40x40/3B82F6/FFFFFF?text=G'">
                    </div>
                    ${isMember ? `
                        <div class="absolute -bottom-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white">
                            <i class="bi bi-check text-white text-[10px] flex items-center justify-center w-full h-full"></i>
                        </div>
                    ` : ''}
                </div>
                <div class="flex-1 min-w-0">
                    <h4 class="font-semibold text-gray-800 text-sm truncate" title="${group.name}">
                        ${group.name}
                    </h4>
                    <div class="flex items-center mt-0.5">
                        <span class="text-xs text-gray-500 flex items-center">
                            <i class="bi bi-people mr-1"></i>
                            ${group.member_count || 0} members
                        </span>
                    </div>
                </div>
                ${!isMember ? `
                    <button class="join-group-btn px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors flex-shrink-0"
                            data-group-id="${group.id}">
                        Join
                    </button>
                ` : `
                    <button class="leave-group-btn px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded-lg hover:bg-gray-300 transition-colors flex-shrink-0"
                            data-group-id="${group.id}">
                        Joined
                    </button>
                `}
            </div>
        `;

        // Add click event for group item
        div.addEventListener('click', (e) => {
            // Don't trigger if clicking on buttons
            if (!e.target.closest('.join-group-btn, .leave-group-btn')) {
                window.location.href = `/groups/${group.id}`;
            }
        });

        // Add click events for buttons
        const joinBtn = div.querySelector('.join-group-btn');
        const leaveBtn = div.querySelector('.leave-group-btn');

        if (joinBtn) {
            joinBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.join(group.id, joinBtn);
            });
        }

        if (leaveBtn) {
            leaveBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.leave(group.id, leaveBtn);
            });
        }

        return div;
    },

    // Search groups
    search(query) {
        clearTimeout(this.searchTimer);

        this.searchTimer = setTimeout(async () => {
            if (!query || query.trim().length < 2) {
                // If search is empty, show all groups
                if (this.cache.groups) {
                    this.displayGroups(this.cache.groups);
                } else {
                    this.load();
                }
                return;
            }

            try {
                // Show loading state
                this.showLoading(['groupsList', 'groupsListMobile', 'groupsListDesktop']);

                const response = await fetch(`/search_groups?q=${encodeURIComponent(query)}`);
                const results = await response.json();

                if (Array.isArray(results)) {
                    this.displayGroups(results);
                } else {
                    throw new Error('Invalid search results');
                }
            } catch (error) {
                this.showError(['groupsList', 'groupsListMobile', 'groupsListDesktop'], 'Search failed');
            }
        }, 300); // Debounce for 300ms
    },

    // Join group
    async join(groupId, button) {
        if (!button) return;

        const originalText = button.innerHTML;
        const originalClass = button.className;

        // Show loading state
        button.innerHTML = '<span class="inline-flex items-center gap-1"><span class="tiny-loader xs white"></span></span>';
        button.disabled = true;

        try {
            const response = await fetch(`/groups/${groupId}/join`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            if (data.success) {
                // Update button
                button.innerHTML = 'Joined';
                button.className = 'px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded-lg hover:bg-gray-300 transition-colors flex-shrink-0';
                button.classList.remove('join-group-btn');
                button.classList.add('leave-group-btn');

                // Update click handler
                button.onclick = (e) => {
                    e.stopPropagation();
                    this.leave(groupId, button);
                };

                // Update cache
                if (this.cache.groups) {
                    const groupIndex = this.cache.groups.findIndex(g => g.id === groupId);
                    if (groupIndex !== -1) {
                        this.cache.groups[groupIndex].is_member = true;
                        this.cache.groups[groupIndex].member_count =
                            (this.cache.groups[groupIndex].member_count || 0) + 1;
                    }
                }

                Toast.show('Successfully joined group!', 'success');
            } else {
                throw new Error(data.error || 'Failed to join group');
            }
        } catch (error) {
            button.innerHTML = originalText;
            button.className = originalClass;
            button.disabled = false;
            Toast.show(error.message, 'danger');
        }
    },

    // Leave group
    async leave(groupId, button) {
        if (!button) return;

        const originalText = button.innerHTML;
        const originalClass = button.className;

        // Show loading state
        button.innerHTML = '<span class="inline-flex items-center gap-1"><span class="tiny-loader xs"></span></span>';
        button.disabled = true;

        try {
            const response = await fetch(`/groups/${groupId}/leave`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            if (data.success) {
                // Update button
                button.innerHTML = 'Join';
                button.className = 'px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors flex-shrink-0';
                button.classList.remove('leave-group-btn');
                button.classList.add('join-group-btn');

                // Update click handler
                button.onclick = (e) => {
                    e.stopPropagation();
                    this.join(groupId, button);
                };

                // Update cache
                if (this.cache.groups) {
                    const groupIndex = this.cache.groups.findIndex(g => g.id === groupId);
                    if (groupIndex !== -1) {
                        this.cache.groups[groupIndex].is_member = false;
                        this.cache.groups[groupIndex].member_count =
                            Math.max((this.cache.groups[groupIndex].member_count || 1) - 1, 0);
                    }
                }

                Toast.show('Left group', 'info');
            } else {
                throw new Error(data.error || 'Failed to leave group');
            }
        } catch (error) {
            button.innerHTML = originalText;
            button.className = originalClass;
            button.disabled = false;
            Toast.show(error.message, 'danger');
        }
    },

    // Show loading state
    showLoading(listIds) {
        listIds.forEach(listId => {
            const list = document.getElementById(listId);
            if (list) {
                list.innerHTML = `
                    <div class="flex flex-col items-center justify-center p-6">
                        <div class="relative">
                            <div class="w-8 h-8 border-3 border-blue-100 border-t-blue-600 rounded-full animate-spin"></div>
                            <div class="absolute inset-0 flex items-center justify-center">
                                <i class="bi bi-people text-blue-600 text-sm"></i>
                            </div>
                        </div>
                        <p class="text-sm text-gray-500 mt-2">Loading groups...</p>
                    </div>
                `;
            }
        });
    },

    // Show error state
    showError(listIds, message) {
        listIds.forEach(listId => {
            const list = document.getElementById(listId);
            if (list) {
                list.innerHTML = `
                    <div class="text-center p-6">
                        <div class="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-3">
                            <i class="bi bi-exclamation-triangle text-red-600"></i>
                        </div>
                        <p class="text-sm text-gray-700 mb-1">Couldn't load groups</p>
                        <p class="text-xs text-gray-500">${message}</p>
                        <button class="mt-3 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                                onclick="Groups.load()">
                            Try Again
                        </button>
                    </div>
                `;
            }
        });
    },

    // Show empty state
    showEmptyState(list) {
        list.innerHTML = `
            <div class="text-center p-6">
                <div class="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                    <i class="bi bi-people text-gray-400"></i>
                </div>
                <p class="text-sm text-gray-700 mb-2">No groups yet</p>
                <p class="text-xs text-gray-500 mb-4">Discover and join groups to see them here</p>
                <a href="/groups"
                   class="inline-block px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white text-sm rounded-lg hover:from-blue-600 hover:to-purple-700 transition-all transform hover:scale-105">
                    <i class="bi bi-compass mr-1"></i>
                    Explore Groups
                </a>
            </div>
        `;
    },

    // Clear cache
    clearCache() {
        this.cache.groups = null;
        this.cache.lastFetch = null;
    },

    // Refresh groups (force reload)
    refresh() {
        this.clearCache();
        this.load();
    }
};

// ========================================
// INFINITE SCROLL
// ========================================

const InfiniteScroll = {
    async loadMore() {
        if (appState.isLoadingPosts || !appState.hasMorePosts || !appState.nextCursor) return;

        appState.isLoadingPosts = true;
        const loadingSpinner = document.getElementById('loading-spinner');
        const loadMoreBtn = document.getElementById('load-more-btn');

        if (loadingSpinner) loadingSpinner.classList.remove('hidden');
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');

        try {
            const response = await fetch(`/user_dashboard?cursor=${appState.nextCursor}&limit=10`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();

            if (data.success) {
                if (data.posts) {
                    const postsFeed = document.getElementById('posts-feed');
                    if (postsFeed) {
                        postsFeed.insertAdjacentHTML('beforeend', data.posts);
                        MobileFeedAds.refresh();
                        PostSystem.initInteractions();
                    }
                }

                appState.hasMorePosts = data.has_more;
                appState.nextCursor = data.next_cursor;

                if (loadMoreBtn && data.has_more) {
                    loadMoreBtn.classList.remove('hidden');
                } else {
                    const endOfFeed = document.getElementById('end-of-feed');
                    if (endOfFeed) endOfFeed.classList.remove('hidden');
                }

                if (data.count > 0) {
                    Toast.show(`Loaded ${data.count} more posts`, 'success');
                }
            }
        } catch (error) {
            Toast.show('Failed to load more posts', 'danger');
            if (loadMoreBtn) loadMoreBtn.classList.remove('hidden');
        } finally {
            appState.isLoadingPosts = false;
            if (loadingSpinner) loadingSpinner.classList.add('hidden');
        }
    },

    init() {
        const loadMoreBtn = document.getElementById('load-more-btn');
        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', () => this.loadMore());
        }

        window.addEventListener('scroll', () => {
            const scrollPosition = window.innerHeight + window.scrollY;
            const threshold = document.body.offsetHeight - 500;

            if (scrollPosition >= threshold && !appState.isLoadingPosts && appState.hasMorePosts) {
                this.loadMore();
            }
        });
    }
};

// ========================================
// MEDIA UPLOAD
// ========================================

function validateAndOpenFilePicker() {
    const fileInput = document.getElementById('mediaInput');
    if (fileInput) {
        fileInput.click();
    }
}

// ========================================
// FILE UPLOAD HANDLING
// ========================================

window.handleFileSelection = function(input) {
    const preview = document.getElementById('mediaPreview');
    const uploadProgressContainer = document.getElementById('uploadProgressContainer');
    const uploadProgressBar = document.getElementById('uploadProgressBar');
    const uploadPercentage = document.getElementById('uploadPercentage');
    const uploadStatus = document.getElementById('uploadStatus');
    const uploadSpeed = document.getElementById('uploadSpeed');

    if (!input || !input.files || !input.files[0]) return;

    const file = input.files[0];

    // Clear previous preview
    if (preview) preview.innerHTML = '';

    // Validate file size (100MB limit)
    const maxSize = 100 * 1024 * 1024; // 100MB
    if (file.size > maxSize) {
        Toast.show(`File is too large! Maximum size is ${maxSize/(1024*1024)}MB`, 'danger');
        input.value = '';
        return;
    }

    // Show preview immediately
    showFilePreview(file, preview);

    // Show upload progress container
    if (uploadProgressContainer) {
        uploadProgressContainer.classList.remove('hidden');
        uploadProgressBar.style.width = '0%';
        uploadPercentage.textContent = '0%';
        uploadStatus.textContent = 'Ready to upload';
        uploadSpeed.textContent = '-';
    }
};

function showFilePreview(file, previewContainer) {
    if (!file || !previewContainer) return;

    const isVideo = file.type.startsWith('video/');
    const isImage = file.type.startsWith('image/');
    const fileSize = formatFileSize(file.size);

    let previewHTML = '';

    if (isImage) {
        const reader = new FileReader();
        reader.onload = function(e) {
            previewContainer.innerHTML = `
                <div class="file-preview relative rounded-xl overflow-hidden border border-gray-200">
                    <img src="${e.target.result}" alt="Preview" class="w-full h-48 object-cover">
                    <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                        <div class="text-white text-sm">
                            <div class="font-medium">${file.name}</div>
                            <div class="text-xs opacity-80">${fileSize} • ${file.type}</div>
                        </div>
                    </div>
                    <button type="button" onclick="removeFilePreview(this)" class="absolute top-2 right-2 w-8 h-8 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                        <i class="bi bi-x text-sm"></i>
                    </button>
                </div>
            `;
        };
        reader.readAsDataURL(file);
    } else if (isVideo) {
        const url = URL.createObjectURL(file);
        previewContainer.innerHTML = `
            <div class="file-preview relative rounded-xl overflow-hidden border border-gray-200">
                <video controls class="w-full h-48 object-cover bg-black">
                    <source src="${url}" type="${file.type}">
                </video>
                <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                    <div class="text-white text-sm">
                        <div class="font-medium">${file.name}</div>
                        <div class="text-xs opacity-80">${fileSize} • ${file.type}</div>
                        <div id="videoUploadProgress" class="mt-1">
                            <div class="w-full bg-gray-700 rounded-full h-1">
                                <div id="videoProgressBar" class="h-1 bg-blue-500 rounded-full" style="width: 0%"></div>
                            </div>
                            <div class="flex justify-between text-xs mt-1">
                                <span id="videoProgressText">0%</span>
                                <span id="videoTimeRemaining">-</span>
                            </div>
                        </div>
                    </div>
                </div>
                <button type="button" onclick="removeFilePreview(this)" class="absolute top-2 right-2 w-8 h-8 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                    <i class="bi bi-x text-sm"></i>
                </button>
            </div>
        `;

        // Simulate video upload progress
        simulateVideoUploadProgress();
    } else {
        previewContainer.innerHTML = `
            <div class="file-preview bg-gray-100 rounded-xl p-4 border border-gray-200">
                <div class="flex items-center">
                    <div class="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-3">
                        <i class="bi bi-file-earmark text-blue-600 text-xl"></i>
                    </div>
                    <div>
                        <div class="font-medium truncate">${file.name}</div>
                        <div class="text-sm text-gray-500">${fileSize} • ${file.type}</div>
                    </div>
                    <button type="button" onclick="removeFilePreview(this)" class="ml-auto w-8 h-8 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                        <i class="bi bi-x text-sm"></i>
                    </button>
                </div>
            </div>
        `;
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function simulateVideoUploadProgress() {
    const videoProgressBar = document.getElementById('videoProgressBar');
    const videoProgressText = document.getElementById('videoProgressText');
    const videoTimeRemaining = document.getElementById('videoTimeRemaining');
    const uploadProgressBar = document.getElementById('uploadProgressBar');
    const uploadPercentage = document.getElementById('uploadPercentage');
    const uploadStatus = document.getElementById('uploadStatus');
    const uploadSpeed = document.getElementById('uploadSpeed');

    if (!videoProgressBar) return;

    let progress = 0;
    const interval = setInterval(() => {
        progress += Math.random() * 10;
        if (progress > 100) progress = 100;

        // Update both progress bars
        if (videoProgressBar) videoProgressBar.style.width = progress + '%';
        if (videoProgressText) videoProgressText.textContent = Math.round(progress) + '%';
        if (uploadProgressBar) uploadProgressBar.style.width = progress + '%';
        if (uploadPercentage) uploadPercentage.textContent = Math.round(progress) + '%';

        // Update status and speed
        if (uploadStatus) {
            if (progress < 100) {
                uploadStatus.textContent = 'Uploading...';
            } else {
                uploadStatus.textContent = 'Upload complete!';
            }
        }

        // Simulate upload speed
        if (uploadSpeed && progress < 100) {
            const speeds = ['500 KB/s', '1.2 MB/s', '800 KB/s', '2.1 MB/s', '1.5 MB/s'];
            const randomSpeed = speeds[Math.floor(Math.random() * speeds.length)];
            uploadSpeed.textContent = randomSpeed;
        }

        // Simulate time remaining
        if (videoTimeRemaining && progress < 100) {
            const times = ['30s remaining', '1m remaining', '45s remaining', '2m remaining'];
            const randomTime = times[Math.floor(Math.random() * times.length)];
            videoTimeRemaining.textContent = randomTime;
        }

        if (progress >= 100) {
            clearInterval(interval);
            if (uploadStatus) uploadStatus.textContent = 'Processing video...';
            setTimeout(() => {
                if (uploadStatus) uploadStatus.textContent = 'Ready to post!';
                if (uploadSpeed) uploadSpeed.textContent = 'Complete';
                if (videoTimeRemaining) videoTimeRemaining.textContent = 'Ready';
            }, 1500);
        }
    }, 300);
}

window.removeFilePreview = function(button) {
    const previewContainer = document.getElementById('mediaPreview');
    const fileInput = document.getElementById('mediaInput');
    const uploadProgressContainer = document.getElementById('uploadProgressContainer');

    if (previewContainer) {
        previewContainer.innerHTML = '';
    }

    if (fileInput) {
        fileInput.value = '';
    }

    if (uploadProgressContainer) {
        uploadProgressContainer.classList.add('hidden');
    }

    Toast.show('File removed', 'info');
};

// ========================================
// MEDIA PREVIEW
// ========================================

const MediaPreview = {
    preview(input) {
        const preview = document.getElementById('mediaPreview') || document.getElementById('editMediaPreview');
        if (!preview) return;

        preview.innerHTML = '';
        const file = input.files[0];
        if (!file) return;

        preview.innerHTML = `
            <div class="flex items-center justify-center p-3 bg-gray-50 rounded-xl">
                <span class="tiny-loader sm"></span>
                <span class="ml-2 text-gray-600 text-xs">Preparing...</span>
            </div>
        `;

        setTimeout(() => {
            const url = URL.createObjectURL(file);
            const isVideo = file.type.startsWith('video/');
            const el = isVideo ? document.createElement('video') : document.createElement('img');

            el.src = url;
            if (isVideo) el.controls = true;
            el.className = 'w-full max-h-32 rounded-lg object-contain border border-gray-200 bg-gray-50';

            preview.innerHTML = '';
            preview.appendChild(el);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'mt-2 px-3 py-1.5 bg-red-100 text-red-600 text-xs rounded-lg hover:bg-red-200 transition-colors flex items-center';
            removeBtn.innerHTML = '<i class="bi bi-trash mr-1"></i> Remove';
            removeBtn.onclick = () => {
                preview.innerHTML = '';
                input.value = '';
            };

            preview.appendChild(removeBtn);
        }, 300);
    }
};

// ========================================
// AJAX POST UPLOAD
// ========================================

const PostUploader = {
    async uploadWithProgress(form, submitBtn) {
        const formData = new FormData(form);
        const postContent = formData.get('post_content');
        const mediaFile = formData.get('media');

        if (!postContent && !mediaFile) {
            Toast.show('Please add some content or media to your post', 'warning');
            return false;
        }

        const xhr = new XMLHttpRequest();

        // Show progress UI
        this.showUploadProgress(mediaFile);

        return new Promise((resolve, reject) => {
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    this.updateProgress(percentComplete, e.loaded, e.total);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            Toast.show('Post created successfully!', 'success');
                            setTimeout(() => location.reload(), 1500);
                            resolve(true);
                        } else {
                            Toast.show(response.error || 'Failed to create post', 'danger');
                            reject(new Error(response.error));
                        }
                    } catch (e) {
                        // If response is HTML (regular form submit), reload page
                        Toast.show('Post created!', 'success');
                        setTimeout(() => location.reload(), 1000);
                        resolve(true);
                    }
                } else {
                    Toast.show('Upload failed. Please try again.', 'danger');
                    reject(new Error('Upload failed'));
                }
                this.hideUploadProgress();
            });

            xhr.addEventListener('error', () => {
                Toast.show('Network error. Please check your connection.', 'danger');
                this.hideUploadProgress();
                reject(new Error('Network error'));
            });

            xhr.open('POST', form.action);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        });
    },

    showUploadProgress(file) {
        const progressContainer = document.getElementById('uploadProgressContainer');
        const fileName = document.getElementById('uploadFileName');

        if (progressContainer) {
            progressContainer.classList.remove('hidden');
        }

        if (fileName && file) {
            fileName.textContent = file.name;
        }

        // Show video processing details if it's a video
        const videoDetails = document.getElementById('videoUploadDetails');
        if (videoDetails && file && file.type.startsWith('video/')) {
            videoDetails.classList.remove('hidden');
        }
    },

    updateProgress(percent, loaded, total) {
        const progressBar = document.getElementById('uploadProgressBar');
        const percentage = document.getElementById('uploadPercentage');
        const status = document.getElementById('uploadStatus');
        const speed = document.getElementById('uploadSpeed');
        const timeRemaining = document.getElementById('uploadTimeRemaining');

        if (progressBar) {
            progressBar.style.width = percent + '%';
        }

        if (percentage) {
            percentage.textContent = Math.round(percent) + '%';
        }

        if (status) {
            if (percent < 100) {
                status.textContent = 'Uploading...';
            } else {
                status.textContent = 'Processing...';
            }
        }

        // Calculate upload speed
        if (speed) {
            const uploadSpeed = this.calculateSpeed(loaded, total, percent);
            speed.textContent = uploadSpeed;
        }

        // Calculate time remaining
        if (timeRemaining && percent < 100) {
            const remaining = this.calculateTimeRemaining(loaded, total, percent);
            timeRemaining.textContent = remaining;
        }

        // Update video processing progress if needed
        if (percent >= 100) {
            this.simulateVideoProcessing();
        }
    },

    calculateSpeed(loaded, total, percent) {
        // Simulate speed calculation
        const speeds = ['500 KB/s', '750 KB/s', '1.2 MB/s', '850 KB/s', '2.1 MB/s', '1.5 MB/s'];
        return speeds[Math.floor(Math.random() * speeds.length)];
    },

    calculateTimeRemaining(loaded, total, percent) {
        if (percent === 0) return 'Calculating...';

        const remainingBytes = total - loaded;
        const bytesPerPercent = loaded / percent;
        const remainingPercent = 100 - percent;
        const remainingBytes2 = bytesPerPercent * remainingPercent;

        // Estimate time (very rough estimate)
        const secondsRemaining = Math.round(remainingBytes2 / (1024 * 500)); // Assume 500KB/s

        if (secondsRemaining < 60) {
            return `${secondsRemaining}s remaining`;
        } else {
            const minutes = Math.floor(secondsRemaining / 60);
            const seconds = secondsRemaining % 60;
            return `${minutes}m ${seconds}s remaining`;
        }
    },

    simulateVideoProcessing() {
        const videoBar = document.getElementById('videoProcessingBar');
        const videoStatus = document.getElementById('videoProcessingStatus');

        if (!videoBar || !videoStatus) return;

        let progress = 0;
        const interval = setInterval(() => {
            progress += 2;
            if (progress > 100) progress = 100;

            videoBar.style.width = progress + '%';

            if (progress < 30) videoStatus.textContent = 'Analyzing...';
            else if (progress < 60) videoStatus.textContent = 'Encoding...';
            else if (progress < 90) videoStatus.textContent = 'Optimizing...';
            else videoStatus.textContent = 'Finalizing...';

            if (progress >= 100) {
                clearInterval(interval);
                videoStatus.textContent = 'Complete!';
                videoStatus.className = 'text-green-600 font-medium';
            }
        }, 100);
    },

    hideUploadProgress() {
        const progressContainer = document.getElementById('uploadProgressContainer');
        if (progressContainer) {
            setTimeout(() => {
                progressContainer.classList.add('hidden');
            }, 2000);
        }
    }
};

// Cancel upload function
window.cancelUpload = function() {
    const progressContainer = document.getElementById('uploadProgressContainer');
    const preview = document.getElementById('mediaPreview');
    const fileInput = document.getElementById('mediaInput');

    if (progressContainer) progressContainer.classList.add('hidden');
    if (preview) preview.innerHTML = '';
    if (fileInput) fileInput.value = '';

    Toast.show('Upload cancelled', 'info');
};

// ========================================
// REACTION SYSTEM
// ========================================

let currentReactionPostId = null;
let reactionTimeout = null;

function showReactions(postId) {
    const tooltip = document.getElementById(`reactions-${postId}`);
    if (!tooltip) return;

    clearTimeout(reactionTimeout);
    tooltip.classList.add('show');
    currentReactionPostId = postId;
}

function hideReactions(postId) {
    const tooltip = document.getElementById(`reactions-${postId}`);
    if (!tooltip) return;

    reactionTimeout = setTimeout(() => {
        tooltip.classList.remove('show');
        currentReactionPostId = null;
    }, 300);
}

async function reactToPost(postId, reactionType) {
    const likeBtn = document.getElementById(`like-btn-${postId}`);
    const likeIcon = document.getElementById(`like-icon-${postId}`);
    const likeText = document.getElementById(`like-text-${postId}`);
    const reactionCount = document.getElementById(`reaction-count-${postId}`);
    const tooltip = document.getElementById(`reactions-${postId}`);

    if (!likeBtn || !likeIcon || !likeText) return;

    // Hide tooltip
    tooltip?.classList.remove('show');

    // Optimistic update
    const wasActive = likeBtn.classList.contains(`active-${reactionType}`);
    updateReactionUI(postId, reactionType, !wasActive, likeBtn, likeIcon, likeText);

    try {
        const response = await fetch(`/react_post/${postId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ reaction_type: reactionType })
        });

        const data = await response.json();

        if (data.success) {
            updateReactionUI(postId, data.user_reaction || null, true, likeBtn, likeIcon, likeText);
            reactionCount.textContent = `${data.total_reactions} ${data.total_reactions === 1 ? 'reaction' : 'reactions'}`;
            Toast.show(getReactionMessage(data.user_reaction, data.reacted), 'success');
        } else {
            updateReactionUI(postId, null, false, likeBtn, likeIcon, likeText);
            Toast.show(data.error || 'Failed to react', 'danger');
        }
    } catch (error) {
        updateReactionUI(postId, null, false, likeBtn, likeIcon, likeText);
        Toast.show('Network error', 'danger');
    }
}

function updateReactionUI(postId, reactionType, isActive, likeBtn, likeIcon, likeText) {
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

function getReactionMessage(reactionType, reacted) {
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

function likePost(postId) {
    reactToPost(postId, 'like');
}

// Keep tooltip open on hover
document.addEventListener('mouseover', e => {
    if (e.target.closest('.reactions-tooltip')) clearTimeout(reactionTimeout);
});
document.addEventListener('mouseout', e => {
    if (e.target.closest('.reactions-tooltip') && currentReactionPostId) {
        hideReactions(currentReactionPostId);
    }
});

// ========================================
// COMMENT SYSTEM
// ========================================

function handleCommentKeypress(event, postId) {
    if (event.key === 'Enter' && !event.shiftKey && event.target.value.trim()) {
        event.preventDefault();
        addComment(postId, event.target.value.trim());
    }
}

async function addComment(postId, content) {
    const input = document.getElementById(`commentInput-${postId}`);
    if (!input) {
        return;
    }

    // Store original state
    input.disabled = true;
    const originalPlaceholder = input.placeholder;
    input.placeholder = 'Posting...';

    try {
        const response = await fetch(`/add_comment/${postId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ content })
        });

        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text.substring(0, 100)}`);
        }

        const data = await response.json();

        if (data.success || data.id) {
            // Use global user info
            const userAvatar = window.currentUserInfo?.avatar || window.defaultAvatar;
            const userName = window.currentUserInfo?.name || 'You';

            // Create the comment element
            const div = document.createElement('div');
            div.className = 'flex space-x-3 comment-item comment-fade-in';
            div.id = `comment-${data.id || Date.now()}`;
            div.innerHTML = `
                <img src="${userAvatar}" class="w-9 h-9 rounded-full object-cover flex-shrink-0">
                <div class="flex-1">
                    <div class="bg-white rounded-2xl px-4 py-3 shadow-sm">
                        <div class="flex justify-between items-start">
                            <h6 class="font-semibold text-sm">
                                ${userName}
                            </h6>
                            <span class="text-xs text-gray-500">
                                Just now
                            </span>
                        </div>
                        <p class="text-gray-800 text-sm mt-2 leading-relaxed">
                            ${content}
                        </p>
                    </div>
                </div>
            `;

            // Find the comments container
            const commentsSection = input.closest('.comments-section');
            if (!commentsSection) {
                // Fallback: try to find the post by its ID
                const postElement = document.querySelector(`[data-post-id="${postId}"]`);
                if (postElement) {
                    const commentsContainers = postElement.querySelectorAll('[class*="comment"], .space-y-4');
                    if (commentsContainers.length > 0) {
                        // ⭐⭐ PREPEND to the comments container (newest first) ⭐⭐
                        commentsContainers[0].prepend(div);
                    } else {
                        // Create a new comments container
                        const newContainer = document.createElement('div');
                        newContainer.className = 'space-y-4 mt-4';
                        newContainer.appendChild(div);
                        postElement.querySelector('.border-t').after(newContainer);
                    }
                }
            } else {
                // Find or create the comments list container
                let commentsList = commentsSection.querySelector('.space-y-4');

                if (!commentsList) {
                    // Create a new comments list container
                    commentsList = document.createElement('div');
                    commentsList.className = 'space-y-4 mt-4';

                    // Insert it after the input section
                    const inputSection = commentsSection.querySelector('.flex.items-center.space-x-3');
                    if (inputSection) {
                        inputSection.after(commentsList);
                    } else {
                        commentsSection.appendChild(commentsList);
                    }
                }

                // Remove "no comments" message if it exists
                const noCommentsMsg = commentsList.querySelector('.text-center');
                if (noCommentsMsg) {
                    noCommentsMsg.remove();
                }

                // ⭐⭐ PREPEND the new comment to the comments list (newest first) ⭐⭐
                commentsList.prepend(div);
            }

            // Clear input
            input.value = '';

            // Update comment count
            updateCommentCount(postId, 1, 'add');

            // Show success message
            Toast.show('Comment added!', 'success');

            // Scroll to the top to show the new comment
            setTimeout(() => {
                div.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
        } else {
            Toast.show(data.error || 'Failed to add comment', 'danger');
        }
    } catch (error) {

        if (error.message.includes('401') || error.message.includes('login')) {
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
        input.placeholder = originalPlaceholder;
        input.focus();
    }
}

// Helper function to update comment count
function updateCommentCount(postId, change, operation = 'add') {
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

    // Also update the count animation
    countElement.classList.add('comment-count-update');
    setTimeout(() => {
        countElement.classList.remove('comment-count-update');
    }, 500);
}

// Update deleteComment function to accept postId
async function deleteComment(commentId, postId = null) {
    if (!confirm('Delete this comment?')) return;

    try {
        const response = await fetch(`/delete_comment/${commentId}`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            const el = document.getElementById(`comment-${commentId}`);
            el.style.opacity = '0';
            el.style.transform = 'translateX(-50%)';
            setTimeout(() => el.remove(), 300);

            // Update comment count if we know the postId
            if (postId) {
                updateCommentCount(postId, 1, 'subtract');
            }

            Toast.show('Comment deleted', 'info');
        } else {
            Toast.show(data.error || 'Failed', 'danger');
        }
    } catch (error) {
        Toast.show('Network error', 'danger');
    }
}

function focusCommentInput(postId) {
    document.getElementById(`commentInput-${postId}`)?.focus();
}

async function loadAllComments(postId) {
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
                                    <button class="p-0.5 md:p-1 rounded-full hover:bg-gray-100"><i class="bi bi-three-dots text-gray-400 text-xs"></i></button>
                                    <div class="dropdown-menu absolute right-0 mt-1 w-28 md:w-32 bg-white rounded-lg md:rounded-xl shadow-2xl border border-gray-200 hidden z-10">
                                        ${c.author_id === currentUserId ? `<button onclick="deleteComment(${c.id}, ${postId})" class="w-full text-left px-2 py-1.5 md:px-3 md:py-2 hover:bg-gray-50 text-red-600 text-xs md:text-sm"><i class="bi bi-trash mr-1 text-xs md:text-sm"></i>Delete</button>` : ''}
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

// ========================================
// SHARE MODAL
// ========================================

let currentSharePostId = null;
let currentSharePostUrl = '';

function getPublicBaseUrl() {
    return (window.publicBaseUrl || window.location.origin || '').replace(/\/$/, '');
}

function buildPublicPostUrl(postId) {
    return `${getPublicBaseUrl()}/post/${postId}`;
}

function normalizeShareUrl(postId, shareUrl = '') {
    if (shareUrl) {
        return new URL(shareUrl, `${getPublicBaseUrl()}/`).toString();
    }

    return postId ? buildPublicPostUrl(postId) : '';
}

function openShareModal(postId, shareUrl = '') {
    currentSharePostId = postId;
    currentSharePostUrl = normalizeShareUrl(postId, shareUrl);
    const messageInput = document.getElementById('sharePostMessage');
    if (messageInput) {
        messageInput.value = '';
    }
    Modal.open('shareModal');
}

function closeShareModal() {
    Modal.close('shareModal');
    currentSharePostId = null;
    currentSharePostUrl = '';
}

async function shareToFeed() {
    if (!currentSharePostId) return;

    const messageInput = document.getElementById('sharePostMessage');
    const content = messageInput ? messageInput.value.trim() : '';

    try {
        const response = await fetch(`/share_post/${currentSharePostId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ content })
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to share post');
        }

        Toast.show('Shared to your feed!', 'success');
        closeShareModal();
        setTimeout(() => location.reload(), 800);
    } catch (error) {
        Toast.show(error.message || 'Failed to share post', 'danger');
    }
}

function copyPostLink() {
    if (!currentSharePostId) {
        Toast.show('Select a post to share first.', 'warning');
        return;
    }
    const url = currentSharePostUrl || buildPublicPostUrl(currentSharePostId);
    navigator.clipboard.writeText(url).then(() => {
        Toast.show('Link copied!', 'success');
    }).catch(() => {
        const textarea = document.createElement('textarea');
        textarea.value = url;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        Toast.show('Link copied!', 'success');
    });
}

function getSharePayload() {
    const messageInput = document.getElementById('sharePostMessage');
    const message = messageInput ? messageInput.value.trim() : '';
    const url = currentSharePostUrl || (currentSharePostId ? buildPublicPostUrl(currentSharePostId) : '');
    const text = message || 'Check this out on Kimbela';
    return { url, text };
}

function shareNativeShare() {
    if (!currentSharePostId) {
        Toast.show('Select a post to share first.', 'warning');
        return;
    }
    const { url, text } = getSharePayload();
    if (navigator.share) {
        navigator.share({ title: 'Kimbela Post', text, url }).catch(() => {});
    } else {
        copyPostLink();
    }
}

function shareExternally(platform) {
    if (!currentSharePostId) {
        Toast.show('Select a post to share first.', 'warning');
        return;
    }
    const { url, text } = getSharePayload();
    if (platform === 'instagram') {
        if (navigator.share) {
            navigator.share({ title: 'Kimbela Post', text, url })
                .then(() => Toast.show('Choose Instagram from your share apps.', 'success'))
                .catch(() => {});
            return;
        }

        navigator.clipboard.writeText(url).then(() => {
            Toast.show('Link copied. Paste it into Instagram.', 'success');
        }).catch(() => {
            Toast.show('Copy the link and paste it into Instagram.', 'info');
        });

        const instagramWindow = window.open('https://www.instagram.com/', '_blank');
        if (!instagramWindow) {
            window.location.href = 'https://www.instagram.com/';
        }
        return;
    }

    const encodedUrl = encodeURIComponent(url);
    const encodedText = encodeURIComponent(text);
    const shareUrls = {
        facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`,
        x: `https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedText}`,
        whatsapp: `https://wa.me/?text=${encodedText}%20${encodedUrl}`,
        linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`
    };
    const shareUrl = shareUrls[platform];
    if (shareUrl) {
        const shareWindow = window.open(shareUrl, '_blank');
        if (!shareWindow) {
            window.location.href = shareUrl;
        }
    }
}

// ========================================
// INITIALIZATION
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    // Hide loader
    setTimeout(() => {
        const loader = document.getElementById('loader');
        if (loader) {
            loader.style.opacity = '0';
            setTimeout(() => loader.style.display = 'none', 300);
        }
    }, 500);

    // Initialize Ad System FIRST
    setTimeout(() => {
        if (document.getElementById('nativeAd') || document.getElementById('floatingAd')) {
            AdSystem.init();
        }
    }, 1000);

    // Initialize all systems
    Dropdown.init();
    PostSystem.initInteractions();
    NotificationSystem.init();
    SearchSystem.init();
    TimeUtils.initializeTimeAgo();
    setInterval(() => TimeUtils.initializeTimeAgo(), 60000);
    InfiniteScroll.init();
    MobileFeedAds.refresh();

    window.addEventListener('resize', () => {
        clearTimeout(window.__mobileFeedAdsResizeTimer);
        window.__mobileFeedAdsResizeTimer = setTimeout(() => {
            MobileFeedAds.refresh();
        }, 150);
    });

    // Initialize groups dropdown
    const groupsToggle = document.getElementById('groups-dropdown-toggle');
    const groupsDropdown = document.getElementById('groupsDropdownMenu');

    if (groupsToggle && groupsDropdown) {
        groupsToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            groupsDropdown.classList.toggle('hidden');

            if (!groupsDropdown.classList.contains('hidden')) {
                Groups.load();
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!groupsDropdown.contains(e.target) && e.target !== groupsToggle) {
                groupsDropdown.classList.add('hidden');
            }
        });
    }

    // Initialize groups
    Groups.load();

    // Navbar glass dropdowns (Groups / Match)
    const navDropdowns = document.querySelectorAll('.nav-item.nav-dropdown');
    if (navDropdowns.length) {
        const closeAllNavDropdowns = (except) => {
            navDropdowns.forEach((dropdown) => {
                if (dropdown !== except) {
                    dropdown.classList.remove('dropdown-open');
                    const trigger = dropdown.querySelector('.nav-dropdown-trigger');
                    if (trigger) {
                        trigger.setAttribute('aria-expanded', 'false');
                    }
                }
            });
        };

        navDropdowns.forEach((dropdown) => {
            const trigger = dropdown.querySelector('.nav-dropdown-trigger');
            if (!trigger) return;

            trigger.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const willOpen = !dropdown.classList.contains('dropdown-open');
                closeAllNavDropdowns(dropdown);
                dropdown.classList.toggle('dropdown-open', willOpen);
                trigger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            });

            const menu = dropdown.querySelector('.groups-dropdown-glass, .match-dropdown-glass');
            if (menu) {
                menu.addEventListener('click', (e) => e.stopPropagation());
            }
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.nav-item.nav-dropdown')) {
                closeAllNavDropdowns();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeAllNavDropdowns();
            }
        });
    }

    // Initialize modals
    document.querySelectorAll('[data-bs-toggle="modal"]').forEach(trigger => {
        trigger.addEventListener('click', function() {
            const target = this.getAttribute('data-bs-target');
            if (target) {
                window.openModal(target.replace('#', ''));
            }
        });
    });

    // Close modals on outside click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                window.closeModal(this.id);
            }
        });
    });

    // Initialize post creation
    const createPostForm = document.getElementById('createPostForm');
    if (createPostForm) {
        createPostForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitBtn = this.querySelector('button[type="submit"]');
            Loader.quick(submitBtn, 'show');

            try {
                // Check if we should use AJAX (for progress tracking)
                const mediaFile = document.getElementById('mediaInput').files[0];

                if (mediaFile && mediaFile.size > 10 * 1024 * 1024) { // 10MB threshold
                    // Use AJAX for large files
                    await PostUploader.uploadWithProgress(this, submitBtn);
                } else {
                    // Use regular form submit for small files
                    const response = await fetch(this.action, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': csrfToken
                        },
                        body: new FormData(this)
                    });

                    if (response.ok) {
                        Toast.show('Post created successfully!', 'success');
                        setTimeout(() => location.reload(), 1000);
                    } else {
                        const errorText = await response.text();
                        throw new Error('Failed to create post');
                    }
                }
            } catch (error) {
                Toast.show('Failed to create post', 'danger');
            } finally {
                Loader.quick(submitBtn, 'hide');
            }
        });
    }

    // Close dropdowns
    document.addEventListener('click', e => {
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.add('hidden'));
        }
        if (e.target.closest('.dropdown button')) {
            const menu = e.target.closest('.dropdown').querySelector('.dropdown-menu');
            menu.classList.toggle('hidden');
        }
    });

});

// Make functions globally available
window.showReactions = showReactions;
window.hideReactions = hideReactions;
window.reactToPost = reactToPost;
window.likePost = likePost;
window.handleCommentKeypress = handleCommentKeypress;
window.addComment = addComment;
window.deleteComment = deleteComment;
window.focusCommentInput = focusCommentInput;
window.loadAllComments = loadAllComments;
window.openShareModal = openShareModal;
window.closeShareModal = closeShareModal;
window.shareToFeed = shareToFeed;
window.copyPostLink = copyPostLink;
window.shareNativeShare = shareNativeShare;
window.shareExternally = shareExternally;

// Make functions globally available
window.toggleFloatingAd = function() {
    AdSystem.toggleFloatingAd();
};

window.refreshAds = function() {
    AdSystem.refresh();
};
