// ========================================
// MOBILE MENU FUNCTION (MISSING)
// ========================================

window.toggleMobileMenu = function() {
    const overlay = document.getElementById('mobileSidebarOverlay');
    const sidebar = document.getElementById('mobileSidebar');

    if (!overlay || !sidebar) {
        console.error('Mobile menu elements not found!');
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
//    isTyping: false,
    activeAds: [],
    adShownThisHour: false,
    userAdPreferences: JSON.parse(localStorage.getItem('adPreferences') || '{}'),
    notificationCheckInterval: null,
    searchTimeout: null,
    isLoadingPosts: false,
    hasMorePosts: window.hasMorePosts || false,
    nextCursor: window.nextCursor || null,
    blockedUserIds: window.blockedUserIds || []
};

// ========================================
// GLOBAL FUNCTIONS FOR HTML ONCLICK ATTRIBUTES
// ========================================

// These must be global to work with HTML onclick attributes
window.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
    }
};

window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }
};


function handleChatInputKeypress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        // Check if messenger is initialized
        if (typeof window.Messenger !== 'undefined') {
            window.Messenger.sendMessage();
        } else {
            console.error('Messenger not initialized');
        }
    }
}

// Make it globally available
window.handleChatInputKeypress = handleChatInputKeypress;


window.handleMessageScroll = function() {
    // Check if messenger is initialized
    if (typeof window.Messenger !== 'undefined' &&
        typeof window.Messenger.handleMessageScroll === 'function') {
        window.Messenger.handleMessageScroll();
    }
};

window.toggleMobileMenu = function() {
    const overlay = document.getElementById('mobileSidebarOverlay');
    const sidebar = document.getElementById('mobileSidebar');

    if (!overlay || !sidebar) return;

    if (overlay.style.display === 'block') {
        overlay.style.display = 'none';
        sidebar.classList.remove('translate-x-0');
        sidebar.classList.add('-translate-x-full');
    } else {
        overlay.style.display = 'block';
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('translate-x-0');
    }
};

window.openMessenger = function() {
    Messenger.open();
};

window.closeMessenger = function() {
    Messenger.close();
};

window.backToFriends = function() {
    Messenger.backToFriends();
};

window.previewMedia = function(input) {
    MediaPreview.preview(input);
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

window.openProfileModal = function(userId) {
    ProfileSystem.openProfileModal(userId);
};

window.addFriend = function(userId) {
    const button = event.target;
    FriendSystem.add(userId, button);
};

window.cancelFriendRequest = function(userId) {
    const button = event.target;
    FriendSystem.cancelRequest(userId, button);
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
            console.error('Error liking post:', error);
            if (likeCount) likeCount.textContent = originalCount;
            if (icon) icon.className = originalIcon;
//            Toast.show('Failed to like post', 'danger');
        } finally {
            likeBtn.disabled = false;
        }
    },

    async delete(postId, deleteBtn) {
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
            console.error('Error deleting post:', error);
            deleteBtn.innerHTML = originalContent;
            deleteBtn.disabled = false;
            Toast.show('Failed to delete post', 'danger');
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
                console.error('Error editing post:', error);
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
            console.error('Error loading comments:', error);
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
                    <img src="${comment.avatar || defaultAvatar}" class="w-10 h-10 rounded-full object-cover flex-shrink-0">
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

        // Add comments on Enter
        document.addEventListener('keypress', (e) => {
            if (e.target.classList.contains('add-comment') && e.key === 'Enter' && e.target.value.trim()) {
                const postId = e.target.dataset.postId;
                const content = e.target.value.trim();
                this.addComment(postId, content, e.target);
            }
        });
    }
};

// ========================================
// FRIEND SYSTEM
// ========================================

// ========================================
// FRIEND SYSTEM - COMPLETE VERSION
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
            console.error('Error adding friend:', error);
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
            console.error('Error cancelling friend request:', error);
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
            console.error('Non-JSON response:', text);
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
        console.error('Error accepting friend request:', error);
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
            console.error('Server returned non-JSON:', text.substring(0, 500));
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
        console.error('Error declining friend request:', error);
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
                    <button class="btn btn-primary px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
                            onclick="Messenger.startChat(${userId})">
                        <i class="bi bi-chat-dots mr-1"></i> Message
                    </button>
                    <button class="btn btn-outline-danger px-4 py-2 border border-red-500 text-red-500 rounded-lg font-medium hover:bg-red-50 transition-colors"
                            onclick="BlockSystem.block(${userId})">
                        <i class="bi bi-slash-circle mr-1"></i> Block
                    </button>
                `;
                break;

            default: // 'none'
                buttonHTML = `
                    <button class="btn btn-primary px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
                            onclick="FriendSystem.add(${userId}, this)">
                        <i class="bi bi-person-plus mr-1"></i> Connect
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
            console.error('Error checking friend status:', error);
        }
        return 'none';
    }
};

// Make the functions available globally
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
// PROFILE SYSTEM
// ========================================

// ========================================
// PROFILE SYSTEM - UPDATED VERSION
// ========================================

const ProfileSystem = {
    async openProfileModal(userId, fromFriendRequestNotification = false) {
        try {
            const modalBody = document.getElementById('profileModalBody');
            const profileActions = document.getElementById('profileActions');

            if (!modalBody || !profileActions) {
                console.error('Profile modal elements not found');
                return;
            }

            // Show loading state
            modalBody.innerHTML = `
                <div class="flex flex-col items-center justify-center p-8 min-h-[400px]">
                    <span class="tiny-loader md"></span>
                    <div class="text-gray-500 mt-3">Loading profile...</div>
                </div>
            `;

            // Clear previous actions
            profileActions.innerHTML = '';

            // Open modal first
            Modal.open('profileModal');

            // Load profile data
            const response = await fetch(`/get_user_profile/${userId}`);

            console.log('Response status:', response.status);
            console.log('Response headers:', Object.fromEntries([...response.headers.entries()]));

            // Try to get response text first to see what the server is returning
            const responseText = await response.text();
            console.log('Raw response text:', responseText.substring(0, 500)); // First 500 chars

            if (!response.ok) {
                // Try to parse as JSON if possible
                let errorMessage = `HTTP ${response.status}: Failed to load profile`;
                try {
                    const errorData = JSON.parse(responseText);
                    errorMessage = errorData.error || errorData.message || errorMessage;
                } catch (e) {
                    // Not JSON, use raw text or status
                    if (responseText.includes('<!DOCTYPE html>') || responseText.includes('<html')) {
                        errorMessage = 'Server returned HTML instead of JSON. Please check server logs.';
                    } else if (responseText.trim()) {
                        errorMessage = responseText.substring(0, 200);
                    }
                }
                throw new Error(errorMessage);
            }

            // Try to parse as JSON
            let data;
            try {
                data = JSON.parse(responseText);
            } catch (e) {
                console.error('Failed to parse JSON:', e);
                console.error('Response text that failed to parse:', responseText);
                throw new Error('Server returned invalid JSON. Please check server logs.');
            }

            if (data.error) {
                throw new Error(data.error);
            }

            console.log('Profile data loaded successfully:', data);
            this.displayProfileModal(data, userId, fromFriendRequestNotification);

        } catch (error) {
            console.error('Error loading profile:', error);
            console.error('Full error:', error.stack);

            const modalBody = document.getElementById('profileModalBody');
            if (modalBody) {
                modalBody.innerHTML = `
                    <div class="text-center p-8 text-red-500 min-h-[400px] flex flex-col items-center justify-center">
                        <i class="bi bi-exclamation-triangle text-4xl mb-4"></i>
                        <p class="text-lg font-medium mb-2">Failed to load profile</p>
                        <p class="text-sm text-gray-600 mb-4">${error.message}</p>
                        <div class="flex space-x-2">
                            <button onclick="ProfileSystem.openProfileModal(${userId}, false)"
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
                    <div class="flex flex-wrap gap-4 justify-center py-6">
                        <button class="px-8 py-3.5 bg-green-600 text-white text-lg font-medium rounded-xl hover:bg-green-700 transition-all shadow-lg flex items-center gap-2"
                                onclick="FriendSystem.acceptFriendRequest(${userId}, this)">
                            <i class="bi bi-check-lg text-xl"></i> Accept
                        </button>
                        <button class="px-8 py-3.5 bg-red-600 text-white text-lg font-medium rounded-xl hover:bg-red-700 transition-all shadow-lg flex items-center gap-2"
                                onclick="FriendSystem.declineFriendRequest(${userId}, this)">
                            <i class="bi bi-x-lg text-xl"></i> Decline
                        </button>
                        <button class="px-8 py-3.5 bg-gray-300 text-gray-800 text-lg font-medium rounded-xl hover:bg-gray-400 transition-all"
                                onclick="Modal.close('profileModal')">
                            Cancel
                        </button>
                    </div>
                `;
            } else {
                this.updateProfileActions(userId);
            }

        } catch (error) {
            console.error('Error displaying profile modal:', error);
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
                            <div class="flex flex-wrap gap-2">
                                <button class="btn btn-primary px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
                                        onclick="Messenger.startChat(${userId})">
                                    <i class="bi bi-chat-dots mr-1"></i> Message
                                </button>
                                <button class="btn btn-outline-danger px-4 py-2 border border-red-500 text-red-500 rounded-lg font-medium hover:bg-red-50 transition-colors"
                                        onclick="BlockSystem.block(${userId})">
                                    <i class="bi bi-slash-circle mr-1"></i> Block
                                </button>
                            </div>
                        `;
                        break;

                    case 'request_sent':
                        actionsHTML = `
                            <button class="btn btn-secondary px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
                                    onclick="FriendSystem.cancelRequest(${userId}, this)">
                                <i class="bi bi-clock-history mr-1"></i> Cancel Request
                            </button>
                        `;
                        break;

                    case 'request_received':
                        actionsHTML = `
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

                    default:
                        actionsHTML = `
                            <button class="btn btn-primary px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg font-medium hover:from-blue-600 hover:to-purple-700 transition-all"
                                    onclick="FriendSystem.add(${userId}, this)">
                                <i class="bi bi-person-plus mr-1"></i> Connect
                            </button>
                        `;
                }

                profileActions.innerHTML = actionsHTML;
            }
        } catch (error) {
            console.error('Error checking friend status:', error);
            // Fallback to basic add friend button
            profileActions.innerHTML = `
                <button class="btn btn-primary px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg font-medium hover:from-blue-600 hover:to-purple-700 transition-all"
                        onclick="FriendSystem.add(${userId}, this)">
                    <i class="bi bi-person-plus mr-1"></i> Connect
                </button>
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
            console.error('Error blocking user:', error);
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
            console.error('Error unblocking user:', error);
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
            console.error('Error updating notification badge:', error);
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

            const notifications = await response.json();
            this.display(notifications, list);
        } catch (error) {
            console.error('Error loading notifications:', error);
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
            console.error('Error marking notification as read:', error);
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
            console.error('Error accepting friend request:', error);
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
            console.error('Error declining friend request:', error);
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
            console.error('Error performing search:', error);
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
                console.error('Error viewing post:', error);
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
                            <div class="text-sm text-gray-500">${new Date(post.created_at).toLocaleString()}</div>
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
// MESSENGER SYSTEM
// ========================================

// ========================================
// MESSENGER SYSTEM - SINGLE VERSION
// ========================================

const Messenger = {
    state: {
        socket: null,
        activeFriendId: null,
        isTyping: false,
        typingTimeout: null,
        unreadCounts: {},
        currentFriend: null
    },

    // Initialize messenger
    init() {
        this.connectSocket();
        this.setupEventListeners();
        this.updateUnreadBadge();

        // Check for Messenger popup elements
        if (document.getElementById('messengerPopup')) {
            console.log('✅ Messenger initialized');
        }

        return this;
    },

    // Setup all event listeners
    setupEventListeners() {
        // Open/close messenger
        const openBtn = document.getElementById('openMessaging');
        const closeBtn = document.querySelector('[onclick="closeMessenger()"]');
        const backBtn = document.querySelector('[onclick="backToFriends()"]');
        const sendBtn = document.getElementById('sendChatBtn');
        const chatInput = document.getElementById('chatInput');

        if (openBtn) {
            openBtn.addEventListener('click', () => this.open());
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }

        if (backBtn) {
            backBtn.addEventListener('click', () => this.backToFriends());
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            chatInput.addEventListener('input', (e) => {
                this.handleTyping();
            });

            // Stop typing when input is cleared
            chatInput.addEventListener('blur', () => {
                this.stopTyping();
            });
        }
    },

    // Open messenger popup
    async open() {
        const popup = document.getElementById('messengerPopup');
        if (!popup) {
            console.error('Messenger popup not found');
            return;
        }

        popup.classList.remove('hidden');
        await this.loadFriends();

        if (!this.state.socket || !this.state.socket.connected) {
            this.connectSocket();
        }
    },

    // Close messenger popup
    close() {
        const popup = document.getElementById('messengerPopup');
        if (popup) {
            popup.classList.add('hidden');
            this.backToFriends();
            this.stopTyping();
        }
    },

    // Go back to friends list
    backToFriends() {
        this.state.activeFriendId = null;
        this.state.currentFriend = null;

        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');

        if (friendList) friendList.classList.remove('hidden');
        if (chatArea) chatArea.classList.add('hidden');

        const chatInput = document.getElementById('chatInput');
        if (chatInput) chatInput.value = '';

        this.hideTypingIndicator();
        this.stopTyping();
    },

    // Load friends list
    async loadFriends() {
        try {
            const friendsContainer = document.getElementById('friendsContainer');
            if (friendsContainer) {
                friendsContainer.innerHTML = `
                    <div class="flex justify-center items-center p-8">
                        <span class="tiny-loader md"></span>
                        <span class="ml-3 text-gray-500">Loading friends...</span>
                    </div>
                `;
            }

            const response = await fetch('/api/messaging/friends');
            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                this.displayFriends(data.friends);
                this.updateUnreadBadge();
            }
        } catch (error) {
            console.error('Error loading friends:', error);
            const friendsContainer = document.getElementById('friendsContainer');
            if (friendsContainer) {
                friendsContainer.innerHTML = `
                    <div class="text-center p-6 text-gray-500">
                        <i class="bi bi-people text-3xl mb-2"></i>
                        <p class="text-sm">No friends available</p>
                    </div>
                `;
            }
        }
    },

    // Display friends in the list
    displayFriends(friends) {
        const container = document.getElementById('friendsContainer');
        if (!container) return;

        container.innerHTML = '';

        if (!friends || friends.length === 0) {
            container.innerHTML = `
                <div class="text-center p-6 text-gray-500">
                    <i class="bi bi-people text-3xl mb-2"></i>
                    <p class="text-sm">No friends yet</p>
                </div>
            `;
            return;
        }

        friends.forEach(friend => {
            const friendElement = document.createElement('div');
            friendElement.className = 'flex items-center p-3 hover:bg-gray-50 cursor-pointer rounded-lg transition-colors mb-1';
            friendElement.onclick = () => this.openChat(friend.id, friend.name, friend.avatar, friend.online);

            friendElement.innerHTML = `
                <div class="relative">
                    <img src="${friend.avatar || window.defaultAvatar}"
                         alt="${friend.name}"
                         class="w-12 h-12 rounded-full object-cover">
                    ${friend.online ? `
                        <span class="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white"></span>
                    ` : ''}
                    ${friend.unread_count > 0 ? `
                        <span class="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                            ${friend.unread_count > 9 ? '9+' : friend.unread_count}
                        </span>
                    ` : ''}
                </div>
                <div class="ml-3 flex-1">
                    <p class="font-medium text-sm">${friend.name}</p>
                    <p class="text-xs ${friend.online ? 'text-green-600' : 'text-gray-500'}">
                        ${friend.online ? 'Online' : 'Offline'}
                    </p>
                </div>
            `;

            container.appendChild(friendElement);
        });
    },

    // Open chat with a friend
    async openChat(friendId, friendName, friendAvatar, friendOnline) {
        this.state.activeFriendId = friendId;
        this.state.currentFriend = {
            id: friendId,
            name: friendName,
            avatar: friendAvatar,
            online: friendOnline
        };

        // Update UI
        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');
        const chatName = document.getElementById('chatName');
        const chatLastSeen = document.getElementById('chatLastSeen');

        if (friendList) {
            friendList.classList.add('hidden');
        }

        if (chatArea) {
            chatArea.classList.remove('hidden');
        }

        if (chatName) {
            chatName.textContent = friendName || 'Friend';
        }

        if (chatLastSeen) {
            chatLastSeen.textContent = friendOnline ? 'Online' : 'Offline';
            chatLastSeen.className = `text-xs ${friendOnline ? 'text-green-600' : 'text-gray-500'} mt-0.5`;
        }

        // Load messages - IMPORTANT: Wait for messages to load before scrolling
        await this.loadMessages(friendId);

        // Scroll to bottom after messages are loaded
        setTimeout(() => {
            this.scrollToBottom(true); // Force scroll to bottom
        }, 100);

        // Focus input
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.focus();
            this.toggleSendVoiceButtons();
        }

        // Mark messages as read
        await this.markAsRead(friendId);
    },

    // Load messages for a chat
    async loadMessages(friendId) {
        try {
            const chatContainer = document.getElementById('chatMessages');
            if (chatContainer) {
                chatContainer.innerHTML = `
                    <div class="flex justify-center items-center py-8">
                        <span class="tiny-loader md"></span>
                        <span class="ml-2 text-gray-500 text-sm">Loading messages...</span>
                    </div>
                `;
            }

            const response = await fetch(`/api/messaging/messages/${friendId}`);
            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                this.displayMessages(data.messages);
            }
        } catch (error) {
            console.error('Error loading messages:', error);
            const chatContainer = document.getElementById('chatMessages');
            if (chatContainer) {
                chatContainer.innerHTML = `
                    <div class="text-center p-6 text-gray-500">
                        <i class="bi bi-chat-dots text-2xl mb-2"></i>
                        <p class="text-sm">Failed to load messages</p>
                    </div>
                `;
            }
        }
    },

    // Display messages in chat
    displayMessages(messages) {
        const chatContainer = document.getElementById('chatMessages');
        if (!chatContainer) return;

        chatContainer.innerHTML = '';

        if (!messages || messages.length === 0) {
            chatContainer.innerHTML = `
                <div class="text-center p-6 text-gray-500">
                    <i class="bi bi-chat-dots text-2xl mb-2"></i>
                    <p class="text-sm">No messages yet. Start a conversation!</p>
                </div>
            `;
            return;
        }

        messages.forEach(msg => {
            this.appendMessage(msg, false);
        });

        this.scrollToBottom();
    },

    // Append a single message
    appendMessage(msg, shouldScroll = true) {
        const chatContainer = document.getElementById('chatMessages');
        if (!chatContainer) return;

        const isOwnMessage = msg.sender_id === currentUserId;
        const time = new Date(msg.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });

        const messageElement = document.createElement('div');
        messageElement.className = `flex ${isOwnMessage ? 'justify-end' : 'justify-start'} mb-3`;
        messageElement.innerHTML = `
            <div class="max-w-xs lg:max-w-md">
                <div class="${isOwnMessage ? 'bg-blue-100' : 'bg-gray-100'} rounded-2xl px-4 py-2">
                    ${!isOwnMessage ? `
                        <div class="flex items-center mb-1">
                            <img src="${msg.sender_avatar || window.defaultAvatar}"
                                 class="w-4 h-4 rounded-full mr-1">
                            <span class="text-xs font-medium">${msg.sender_name || 'User'}</span>
                        </div>
                    ` : ''}
                    <div class="text-sm">${msg.content || ''}</div>
                    <div class="flex justify-end items-center mt-1">
                        <span class="text-[10px] text-gray-500">${time}</span>
                        ${isOwnMessage ? `
                            <i class="bi ${msg.status === 'read' ? 'bi-check2-all text-blue-500' : 'bi-check2 text-gray-400'} ml-1 text-xs"></i>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;

        chatContainer.appendChild(messageElement);

        if (shouldScroll) {
            this.scrollToBottom();
        }
    },

    // Send a message
    async sendMessage() {
        const input = document.getElementById('chatInput');
        if (!input || !this.state.activeFriendId) return;

        const content = input.value.trim();
        if (!content) return;

        if (this.state.socket && this.state.socket.connected) {
            // Send via WebSocket for real-time
            this.state.socket.emit('send_message', {
                friend_id: this.state.activeFriendId,
                content: content
            });
        } else {
            // Fallback to HTTP API
            await this.sendMessageViaAPI(content);
        }

        input.value = '';
        this.stopTyping();
    },

    // Send message via HTTP API (fallback)
    async sendMessageViaAPI(content) {
        try {
            const response = await fetch('/api/messaging/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    friend_id: this.state.activeFriendId,
                    content: content
                })
            });

            const data = await response.json();
            if (data.success && data.message) {
                this.appendMessage(data.message, true);
            } else if (data.error) {
                Toast.show(data.error, 'danger');
            }
        } catch (error) {
            console.error('Error sending message:', error);
            Toast.show('Failed to send message', 'danger');
        }
    },

    // Handle typing indicator
    handleTyping() {
        if (!this.state.activeFriendId || !this.state.socket) return;

        if (!this.state.isTyping) {
            this.state.isTyping = true;
            this.state.socket.emit('typing_start', { friend_id: this.state.activeFriendId });
        }

        // Clear existing timeout
        if (this.state.typingTimeout) {
            clearTimeout(this.state.typingTimeout);
        }

        // Set timeout to stop typing
        this.state.typingTimeout = setTimeout(() => {
            this.stopTyping();
        }, 2000);
    },

    // Stop typing indicator
    stopTyping() {
        if (this.state.isTyping && this.state.activeFriendId && this.state.socket) {
            this.state.isTyping = false;
            this.state.socket.emit('typing_stop', { friend_id: this.state.activeFriendId });
        }

        if (this.state.typingTimeout) {
            clearTimeout(this.state.typingTimeout);
            this.state.typingTimeout = null;
        }
    },

    // Show typing indicator for other user
    showTypingIndicator(userName) {
        const indicator = document.getElementById('typingIndicator');
        const userNameEl = document.getElementById('typingUserName');

        if (userNameEl) {
            userNameEl.textContent = `${userName} is typing...`;
        }
        if (indicator) {
            indicator.classList.remove('hidden');
        }
    },

    // Hide typing indicator
    hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }
    },

    // Connect to Socket.IO
    connectSocket() {
        if (this.state.socket && this.state.socket.connected) {
            return;
        }

        this.state.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5
        });

        // Socket event handlers
        this.state.socket.on('connect', () => {
            console.log('✅ Connected to messaging server');
        });

        this.state.socket.on('new_message', (msg) => {
            if (msg.sender_id === this.state.activeFriendId ||
                msg.receiver_id === this.state.activeFriendId) {
                this.appendMessage(msg, true);
            }
            this.updateUnreadBadge();
        });

        this.state.socket.on('user_typing', (data) => {
            if (data.user_id === this.state.activeFriendId) {
                this.showTypingIndicator(data.user_name);
            }
        });

        this.state.socket.on('user_stopped_typing', (data) => {
            if (data.user_id === this.state.activeFriendId) {
                this.hideTypingIndicator();
            }
        });

        this.state.socket.on('friend_online', (data) => {
            console.log(`Friend ${data.user_id} is online`);
            this.updateFriendStatus(data.user_id, true);
        });

        this.state.socket.on('friend_offline', (data) => {
            console.log(`Friend ${data.user_id} is offline`);
            this.updateFriendStatus(data.user_id, false);
        });

        this.state.socket.on('error', (error) => {
            console.error('Socket error:', error);
        });
    },

    // Update friend online status
    updateFriendStatus(friendId, isOnline) {
        // Update in friends list if open
        const friendElement = document.querySelector(`[onclick*="openChat(${friendId}"]`);
        if (friendElement) {
            const statusIndicator = friendElement.querySelector('.status-indicator');
            const statusText = friendElement.querySelector('.status-text');

            if (statusIndicator) {
                statusIndicator.className = `absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-white ${isOnline ? 'bg-green-500' : 'bg-gray-400'}`;
            }

            if (statusText) {
                statusText.textContent = isOnline ? 'Online' : 'Offline';
                statusText.className = `text-xs ${isOnline ? 'text-green-600' : 'text-gray-500'}`;
            }
        }

        // Update in chat header if active
        if (this.state.activeFriendId === friendId) {
            const chatStatus = document.getElementById('chatStatus');
            if (chatStatus) {
                chatStatus.textContent = isOnline ? 'Online' : 'Offline';
                chatStatus.className = `text-xs ${isOnline ? 'text-green-600' : 'text-gray-500'}`;
            }
        }
    },

    // Mark messages as read
    async markAsRead(friendId) {
        try {
            await fetch(`/api/messaging/mark-read/${friendId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                }
            });
            this.updateUnreadBadge();
        } catch (error) {
            console.error('Error marking as read:', error);
        }
    },

    // Update unread badge
    async updateUnreadBadge() {
        try {
            const response = await fetch('/api/messaging/unread_count');
            if (!response.ok) return;

            const data = await response.json();
            if (data.success) {
                const badge = document.getElementById('unreadMessagesBadge');
                if (badge) {
                    if (data.unread_count > 0) {
                        badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                }
            }
        } catch (error) {
            console.error('Error updating unread count:', error);
        }
    },

    // Scroll chat to bottom
    scrollToBottom() {
        const messagesWrapper = document.getElementById('chatMessagesWrapper');
        if (messagesWrapper) {
            setTimeout(() => {
                messagesWrapper.scrollTop = messagesWrapper.scrollHeight;
            }, 50);
        }
    },

    // Start chat with user (called from profile, etc.)
    startChat(userId) {
        this.open();
        setTimeout(() => {
            // Try to find and click the friend in the list
            const friendElements = document.querySelectorAll('#friendsContainer > div');
            friendElements.forEach(el => {
                if (el.onclick && el.onclick.toString().includes(`openChat(${userId}`)) {
                    el.click();
                }
            });
        }, 500);
    }
};

// Make sure to update the global function references
// Replace the openMessenger function:
window.openMessenger = function() {
    const popup = document.getElementById('messengerPopup');
    if (popup) {
        // Ensure friends list is shown, chat area is hidden
        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');

        if (friendList) {
            friendList.classList.remove('hidden');
            friendList.style.display = 'flex';
        }

        if (chatArea) {
            chatArea.classList.add('hidden');
            chatArea.style.display = 'none';
        }

        // Show popup with animation
        popup.classList.remove('hidden', 'scale-95', 'opacity-0');
        popup.classList.add('flex', 'scale-100', 'opacity-100');

        // Load friends
        if (window.Messenger) {
            window.Messenger.loadFriends();
        }
    }
};

// Replace the closeMessenger function:
window.closeMessenger = function() {
    const popup = document.getElementById('messengerPopup');
    if (popup) {
        // Hide with animation
        popup.classList.remove('scale-100', 'opacity-100');
        popup.classList.add('scale-95', 'opacity-0');

        setTimeout(() => {
            popup.classList.add('hidden');
            popup.classList.remove('flex');

            // Reset to friends list
            window.backToFriends();

            // Clear any active state
            if (window.Messenger) {
                window.Messenger.state.activeFriendId = null;
                window.Messenger.state.currentFriend = null;
            }
        }, 300);
    }
};

// Replace the existing backToFriends function with this:

window.backToFriends = function() {
    // Check if messenger exists and has the method
    if (window.Messenger && typeof window.Messenger.backToFriends === 'function') {
        window.Messenger.backToFriends();
    } else {
        // Fallback implementation
        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');

        if (friendList && chatArea) {
            // Show friends list
            friendList.classList.remove('hidden');
            friendList.style.display = 'flex';

            // Hide chat area
            chatArea.classList.add('hidden');
            chatArea.style.display = 'none';
        }

        // Clear chat input
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.value = '';
            chatInput.style.height = 'auto';
        }

        // Clear any active chat state
        if (window.Messenger) {
            window.Messenger.state.activeFriendId = null;
            window.Messenger.state.currentFriend = null;
        }
    }
};

window.handleTyping = function() {
    if (window.Messenger) {
        window.Messenger.handleTyping();
    }
};

window.sendMessage = function() {
    if (window.Messenger) {
        window.Messenger.sendMessage();
    }
};

// Initialize messenger when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if messenger elements exist and not already initialized
    if (document.getElementById('messengerPopup') && !window.messengerInitialized) {
        window.Messenger = new EnhancedMessenger();
        window.Messenger.init();
        window.messengerInitialized = true;

        // Add scroll event listener for the chat area
        const chatArea = document.getElementById('chatMessagesWrapper');
        if (chatArea) {
            chatArea.addEventListener('DOMNodeInserted', () => {
                // When new messages are added, scroll to bottom if at bottom
                if (window.Messenger) {
                    const isNearBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100;
                    if (isNearBottom) {
                        setTimeout(() => {
                            window.Messenger.scrollToBottom(true);
                        }, 50);
                    }
                }
            });
        }

    }
});







// ========================================
// SPONSORED ADS SYSTEM - UPDATED WITH SMART INTERVALS
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
        console.log('🤑 Initializing Ad System with smart intervals...');

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
            console.log('✅ Ad System initialized successfully');
            return this;

        } catch (error) {
            console.error('❌ Failed to initialize Ad System:', error);
            this.showErrorState('Initialization failed');
            throw error;
        }
    },

    // Start the ad display cycle
    startAdCycle() {
        if (this.state.activeAds.length === 0) {
            console.log('📭 No ads to display');
            this.showNoAdsMessage();
            return;
        }

        console.log(`🔄 Starting ad cycle with ${this.state.activeAds.length} ads`);

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

        console.log(`⏰ Next ad in ${Math.round(interval/1000)} seconds`);

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

        console.log(`📢 Displaying ad: ${ad.title} (Index: ${this.state.currentAdIndex})`);

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
            console.log('🔄 Resetting ad display tracking');
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
            console.error('❌ Max retries reached');
            this.showErrorState('Failed to load ads after multiple attempts');
            return;
        }

        try {
            console.log('📡 Loading sponsored ads...');

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

                console.log(`✅ Loaded ${data.ads.length} sponsored ads`);

            } else {
                console.log('📭 No sponsored ads available');
                this.showNoAdsMessage();
            }

        } catch (error) {
            console.error('❌ Error loading ads:', error);
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
            console.log(`User not interested in ad ${currentAd.id}`);

            try {
                await fetch(`/api/ads/${currentAd.id}/not_interested`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-Token': this.state.csrfToken,
                        'Content-Type': 'application/json'
                    }
                });
            } catch (error) {
                console.error('Failed to track not interested:', error);
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
        console.log(`📊 Tracking click for ad ${adId}`);

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
            console.error('Failed to track click:', error);
        }
    },

    // Track ad impression
    async trackAdImpression(adId) {
        console.log(`📊 Tracking impression for ad ${adId}`);

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
            console.error('Failed to track impression:', error);
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
        console.log('🔄 Refreshing Ad System...');

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
        console.log('🧹 Cleaning up Ad System...');

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

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AdSystem.init());
} else {
    AdSystem.init();
}

// Make available globally
window.AdSystem = AdSystem;



function updateFriendButtons(userId, status) {
    // Update suggestion cards
    const suggestionCard = document.querySelector(`.suggestion-card[onclick*="${userId}"]`);
    if (suggestionCard) {
        const button = suggestionCard.querySelector('button');
        if (button) {
            switch(status) {
                case 'none':
                    button.innerHTML = '<i class="bi bi-person-plus mr-1"></i> Connect';
                    button.className = 'w-full py-2 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors';
                    button.style.background = 'linear-gradient(135deg, #5a4500, #b88900)';
                    button.onclick = (e) => {
                        e.stopPropagation();
                        FriendSystem.add(userId, button);
                    };
                    break;
                case 'friends':
                    button.innerHTML = '<i class="bi bi-chat-dots mr-1"></i> Message';
                    button.className = 'w-full py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors';
                    button.onclick = (e) => {
                        e.stopPropagation();
                        Messenger.startChat(userId);
                    };
                    break;
            }
        }
    }

    // Update profile modal if open
    if (document.getElementById('profileModal') &&
        !document.getElementById('profileModal').classList.contains('hidden')) {
        FriendSystem.updateProfileModalButton(userId, status);
    }
}


// ========================================
// GROUPS SYSTEM
// ========================================

// ========================================
// GROUPS SYSTEM - COMPLETELY REWRITTEN
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
        console.log('🔧 Groups system initialized');

        // Set up event listeners for dropdowns
        this.setupDropdownListeners();

        // Load groups when page loads
        if (document.querySelector('#groupsList, #groupsListMobile')) {
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
        console.log('📥 Loading groups...');

        // Check cache first
        const now = Date.now();
        if (this.cache.groups && this.cache.lastFetch &&
            (now - this.cache.lastFetch) < this.cache.expiry) {
            console.log('📦 Using cached groups');
            this.displayGroups(this.cache.groups);
            return;
        }

        // Show loading state in both lists
        this.showLoading(['groupsList', 'groupsListMobile']);

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

            console.log(`✅ Loaded ${groups.length} groups`);

            // Cache the results
            this.cache.groups = groups;
            this.cache.lastFetch = Date.now();

            // Display groups
            this.displayGroups(groups);

        } catch (error) {
            console.error('❌ Error loading groups:', error);
            this.showError(['groupsList', 'groupsListMobile'], error.message);

            // Clear cache on error
            this.cache.groups = null;
            this.cache.lastFetch = null;
        }
    },

    // Display groups in dropdowns
    displayGroups(groups) {
        const lists = ['groupsList', 'groupsListMobile'];

        lists.forEach(listId => {
            const list = document.getElementById(listId);
            if (!list) return;

            // Clear any existing content
            list.innerHTML = '';

            if (!groups || groups.length === 0) {
                this.showEmptyState(list);
                return;
            }

            // Create document fragment for better performance
            const fragment = document.createDocumentFragment();

            groups.forEach(group => {
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
                this.showLoading(['groupsList', 'groupsListMobile']);

                const response = await fetch(`/search_groups?q=${encodeURIComponent(query)}`);
                const results = await response.json();

                if (Array.isArray(results)) {
                    this.displayGroups(results);
                } else {
                    throw new Error('Invalid search results');
                }
            } catch (error) {
                console.error('Search error:', error);
                this.showError(['groupsList', 'groupsListMobile'], 'Search failed');
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
            console.error('Error joining group:', error);
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
            console.error('Error leaving group:', error);
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
        console.log('🧹 Groups cache cleared');
    },

    // Refresh groups (force reload)
    refresh() {
        this.clearCache();
        this.load();
    }
};

// Initialize groups system when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Check if groups dropdown exists on page
    if (document.getElementById('groupsList') || document.getElementById('groupsListMobile')) {
        Groups.init();
    }

    // Initialize Ad System
    if (document.getElementById('nativeAd') || document.getElementById('floatingAd')) {
        setTimeout(() => {
            AdSystem.init();
        }, 2000); // Wait 2 seconds after page load
    }
});

// Make Groups globally available
window.Groups = Groups;
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
            console.error('Error loading more posts:', error);
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

        // Simulate video upload progress (in a real app, this would be from actual upload)
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
            el.className = 'w-full h-48 rounded-lg object-cover border border-gray-200';

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
    Messenger.init();
    TimeUtils.initializeTimeAgo();
    setInterval(() => TimeUtils.initializeTimeAgo(), 60000);
    InfiniteScroll.init();

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
    // Initialize post creation with AJAX
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
                    body: new FormData(this)
                });

                if (response.ok) {
                    Toast.show('Post created successfully!', 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    throw new Error('Failed to create post');
                }
            }
        } catch (error) {
            console.error('Error creating post:', error);
            Toast.show('Failed to create post', 'danger');
        } finally {
            Loader.quick(submitBtn, 'hide');
        }
    });
}

    console.log('Dashboard initialized successfully');
});


document.addEventListener('DOMContentLoaded', function() {
    // Initialize groups dropdown toggle
    const groupsToggle = document.getElementById('groups-dropdown-toggle');
    const groupsDropdown = document.getElementById('groups-dropdown');

    if (groupsToggle && groupsDropdown) {
        groupsToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            groupsDropdown.classList.toggle('hidden');

            // Load groups when dropdown is opened
            if (!groupsDropdown.classList.contains('hidden')) {
                Groups.load();
            }
        });
    }

    // Close dropdown when clicking outside
    document.addEventListener('click', function() {
        if (groupsDropdown && !groupsDropdown.classList.contains('hidden')) {
            groupsDropdown.classList.add('hidden');
        }
    });

    // Load groups on page load
    if (typeof Groups !== 'undefined') {
        Groups.load();
    }
});



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
    // In a real implementation, you would abort the XHR request
    const progressContainer = document.getElementById('uploadProgressContainer');
    const preview = document.getElementById('mediaPreview');
    const fileInput = document.getElementById('mediaInput');

    if (progressContainer) progressContainer.classList.add('hidden');
    if (preview) preview.innerHTML = '';
    if (fileInput) fileInput.value = '';

    Toast.show('Upload cancelled', 'info');
};





// ========================================
// ENHANCED MESSENGER - COMPLETE REWRITTEN VERSION
// ========================================

// Modern Enhanced Messenger
class ModernMessenger {
    constructor() {
        this.state = {
            socket: null,
            activeFriendId: null,
            isTyping: false,
            typingTimeout: null,
            unreadCounts: {},
            currentFriend: null,
            isConnected: false,
            voiceRecording: false,
            recordingStartTime: null,
            recordingInterval: null
        };

        this.init();
    }

    // Initialize messenger
    init() {
        this.connectSocket();
        this.setupEventListeners();
        this.updateUnreadBadge();
        this.setupVoiceRecording();

        console.log('🎯 Modern Messenger initialized');
        return this;
    }

    // ========================================
// CHAT INPUT HANDLER
// ========================================



    // Setup all event listeners
    setupEventListeners() {
        // Open/close messenger
        const openBtn = document.getElementById('openMessaging');
        const closeBtn = document.querySelector('[onclick="closeMessenger()"]');
        const backBtn = document.querySelector('[onclick="backToFriends()"]');
        const sendBtn = document.getElementById('sendChatBtn');
        const chatInput = document.getElementById('chatInput');
        const voiceBtn = document.getElementById('voiceMessageBtn');

        if (openBtn) {
            openBtn.addEventListener('click', () => this.open());
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }

        if (backBtn) {
            backBtn.addEventListener('click', () => this.backToFriends());
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        if (voiceBtn) {
            voiceBtn.addEventListener('click', () => this.startVoiceMessage());
        }

        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            chatInput.addEventListener('input', (e) => {
                this.handleTyping();
                this.toggleSendVoiceButtons();
            });

            chatInput.addEventListener('blur', () => {
                this.stopTyping();
            });

            // Auto-resize textarea
            chatInput.addEventListener('input', (e) => {
                this.autoResizeTextarea(e.target);
            });
        }

        // Tab switching
        document.querySelectorAll('.tab-button').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabName = e.currentTarget.dataset.tab;
                this.switchTab(tabName);
            });
        });

        // Chat actions
        this.setupChatActions();
    }

    // Setup chat action listeners
    setupChatActions() {
        // Call buttons
        const voiceCallBtn = document.querySelector('[onclick="startVoiceCall()"]');
        const videoCallBtn = document.querySelector('[onclick="startVideoCall()"]');

        if (voiceCallBtn) {
            voiceCallBtn.addEventListener('click', () => this.startVoiceCall());
        }

        if (videoCallBtn) {
            videoCallBtn.addEventListener('click', () => this.startVideoCall());
        }

        // Attachment menu
        const attachBtn = document.querySelector('[onclick="toggleAttachmentMenu()"]');
        if (attachBtn) {
            attachBtn.addEventListener('click', (e) => this.toggleAttachmentMenu(e));
        }

        // Emoji picker
        const emojiBtn = document.querySelector('[onclick="toggleEmojiPicker()"]');
        if (emojiBtn) {
            emojiBtn.addEventListener('click', () => this.toggleEmojiPicker());
        }

        // Quick actions
        document.querySelectorAll('#quickActions button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.currentTarget.textContent.toLowerCase();
                this.handleQuickAction(action);
            });
        });

        // Scroll to bottom button
        const scrollBtn = document.getElementById('scrollToBottomBtn');
        if (scrollBtn) {
            scrollBtn.addEventListener('click', () => this.scrollToBottom());
        }

        // Handle message scroll
        const messagesWrapper = document.getElementById('chatMessagesWrapper');
        if (messagesWrapper) {
            messagesWrapper.addEventListener('scroll', () => this.handleMessageScroll());
        }
    }

    // Auto-resize textarea
    autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        const maxHeight = 128; // Max 6 lines
        const newHeight = Math.min(textarea.scrollHeight, maxHeight);
        textarea.style.height = newHeight + 'px';
    }

    // Toggle between send and voice buttons
    toggleSendVoiceButtons() {
        const chatInput = document.getElementById('chatInput');
        const voiceBtn = document.getElementById('voiceMessageBtn');
        const sendBtn = document.getElementById('sendChatBtn');

        if (!chatInput || !voiceBtn || !sendBtn) return;

        if (chatInput.value.trim() === '') {
            voiceBtn.classList.remove('hidden');
            sendBtn.classList.add('hidden');
            sendBtn.disabled = true;
        } else {
            voiceBtn.classList.add('hidden');
            sendBtn.classList.remove('hidden');
            sendBtn.disabled = false;
        }
    }

    // Switch between tabs
    switchTab(tabName) {
        // Update active tab
        document.querySelectorAll('.tab-button').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Show selected content
        document.querySelectorAll('[data-tab]').forEach(content => {
            content.classList.toggle('hidden', content.dataset.tab !== tabName);
        });

        // Load content for tab
        if (tabName === 'chats') this.loadFriends();
        else if (tabName === 'online') this.loadOnlineFriends();
        else if (tabName === 'requests') this.loadChatRequests();
    }

    // Open messenger popup
    async open() {
        const popup = document.getElementById('messengerPopup');
        if (!popup) {
            console.error('Messenger popup not found');
            return;
        }

        // Show with animation
        popup.classList.remove('hidden', 'scale-95', 'opacity-0');
        popup.classList.add('flex', 'scale-100', 'opacity-100');

        await this.loadFriends();

        if (!this.state.socket || !this.state.isConnected) {
            this.connectSocket();
        }
    }

    // Close messenger popup
    close() {
        const popup = document.getElementById('messengerPopup');
        if (popup) {
            popup.classList.remove('scale-100', 'opacity-100');
            popup.classList.add('scale-95', 'opacity-0');
            setTimeout(() => {
                popup.classList.add('hidden');
                popup.classList.remove('flex');
                this.backToFriends();
                this.stopTyping();
            }, 300);
        }
    }

    // Go back to friends list
    backToFriends() {
        this.state.activeFriendId = null;
        this.state.currentFriend = null;

        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');

        if (friendList) friendList.classList.remove('hidden');
        if (chatArea) chatArea.classList.add('hidden');

        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.value = '';
            this.autoResizeTextarea(chatInput);
        }

        this.hideTypingIndicator();
        this.stopTyping();
        this.toggleSendVoiceButtons();
    }

    // Load friends list with modern design
    async loadFriends() {
        try {
            const friendsContainer = document.getElementById('friendsContainer');
            if (friendsContainer) {
                friendsContainer.innerHTML = `
                    <div class="flex flex-col items-center justify-center p-8 text-gray-500">
                        <div class="relative mb-4">
                            <div class="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                            <div class="absolute inset-0 flex items-center justify-center">
                                <i class="bi bi-people text-blue-600 text-xl"></i>
                            </div>
                        </div>
                        <p class="text-sm font-medium text-gray-600">Loading conversations...</p>
                        <p class="text-xs mt-1 text-gray-400">Getting your messages ready</p>
                    </div>
                `;
            }

            const response = await fetch('/api/messaging/friends');
            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                this.displayFriends(data.friends);
                this.updateUnreadBadge();

                // Show/hide empty state
                const noChats = document.getElementById('noChats');
                if (noChats) {
                    noChats.classList.toggle('hidden', data.friends && data.friends.length > 0);
                }
            }
        } catch (error) {
            console.error('Error loading friends:', error);
            const friendsContainer = document.getElementById('friendsContainer');
            if (friendsContainer) {
                friendsContainer.innerHTML = `
                    <div id="noChats" class="flex flex-col items-center justify-center p-8 text-gray-400">
                        <div class="w-16 h-16 bg-gradient-to-r from-blue-100 to-purple-100 rounded-full flex items-center justify-center mb-4">
                            <i class="bi bi-chat-dots text-2xl text-gray-300"></i>
                        </div>
                        <p class="text-sm font-medium text-gray-500">No conversations yet</p>
                        <p class="text-xs mt-1">Start a conversation with friends!</p>
                        <button onclick="suggestFriends()"
                                class="mt-4 px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white text-sm rounded-lg hover:from-blue-600 hover:to-purple-600 transition-all duration-300 transform hover:scale-105">
                            <i class="bi bi-plus-circle mr-2"></i>
                            Find Friends
                        </button>
                    </div>
                `;
            }
        }
    }

    // Display friends in modern design
    displayFriends(friends) {
        const container = document.getElementById('friendsContainer');
        if (!container) return;

        container.innerHTML = '';

        if (!friends || friends.length === 0) {
            container.innerHTML = `
                <div id="noChats" class="flex flex-col items-center justify-center p-8 text-gray-400">
                    <div class="w-16 h-16 bg-gradient-to-r from-blue-100 to-purple-100 rounded-full flex items-center justify-center mb-4">
                        <i class="bi bi-chat-dots text-2xl text-gray-300"></i>
                    </div>
                    <p class="text-sm font-medium text-gray-500">No conversations yet</p>
                    <p class="text-xs mt-1">Start a conversation with friends!</p>
                    <button onclick="suggestFriends()"
                            class="mt-4 px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white text-sm rounded-lg hover:from-blue-600 hover:to-purple-600 transition-all duration-300 transform hover:scale-105">
                        <i class="bi bi-plus-circle mr-2"></i>
                        Find Friends
                    </button>
                </div>
            `;
            return;
        }

        friends.forEach(friend => {
            const friendElement = this.createFriendElement(friend);
            container.appendChild(friendElement);
        });
    }

    // Create modern friend element
    createFriendElement(friend) {
        const element = document.createElement('div');
        element.className = 'friend-item flex items-center p-3 rounded-xl hover:bg-gray-50/80 transition-all duration-300 cursor-pointer hover-lift';
        element.onclick = () => this.openChat(friend.id, friend.name, friend.avatar, friend.online);

        element.innerHTML = `
            <div class="relative">
                <img src="${friend.avatar || window.defaultAvatar}"
                     alt="${friend.name}"
                     class="w-12 h-12 rounded-2xl object-cover border-2 border-white shadow">
                ${friend.online ? `
                    <div class="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white status-pulse"></div>
                ` : ''}
                ${friend.unread_count > 0 ? `
                    <span class="absolute -top-1 -right-1 bg-gradient-to-r from-blue-500 to-purple-500 text-white text-xs px-1.5 py-0.5 rounded-full shadow">
                        ${friend.unread_count > 9 ? '9+' : friend.unread_count}
                    </span>
                ` : ''}
            </div>
            <div class="flex-1 ml-3 min-w-0">
                <div class="flex items-center space-x-2">
                    <h4 class="font-semibold text-gray-900 truncate">${friend.name}</h4>
                    ${friend.is_verified ? `
                        <i class="bi bi-patch-check-fill text-blue-500 text-sm"></i>
                    ` : ''}
                </div>
                <div class="flex items-center justify-between mt-1">
                    <p class="text-xs text-gray-500 truncate">
                        ${friend.last_message ? friend.last_message.content || 'Sent a message' : 'No messages yet'}
                    </p>
                    ${friend.last_message ? `
                        <span class="text-xs text-gray-400 ml-2">
                            ${new Date(friend.last_message.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </span>
                    ` : ''}
                </div>
            </div>
        `;

        return element;
    }



    // Open chat with a friend
    // In your ModernMessenger class, update the openChat method:

async openChat(friendId, friendName, friendAvatar, friendOnline) {
    this.state.activeFriendId = friendId;
    this.state.currentFriend = {
        id: friendId,
        name: friendName,
        avatar: friendAvatar,
        online: friendOnline
    };

    // Update UI - Hide friends list, show chat area
    const friendList = document.getElementById('friendList');
    const chatArea = document.getElementById('chatArea');
    const chatName = document.getElementById('chatName');
    const chatLastSeen = document.getElementById('chatLastSeen');

    if (friendList) {
        friendList.classList.add('hidden');
//        friendList.style.display = 'none';
    }

    if (chatArea) {
        chatArea.classList.remove('hidden');
//        chatArea.style.display = 'flex';
    }

    // Set friend info
    if (chatName) {
        chatName.textContent = friendName || 'Friend';
    }

    if (chatLastSeen) {
        chatLastSeen.textContent = friendOnline ? 'Online' : 'Offline';
        chatLastSeen.className = `text-xs ${friendOnline ? 'text-green-600' : 'text-gray-500'} mt-0.5`;
    }

    // Load messages
    await this.loadMessages(friendId);

    // Focus input
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.focus();
        this.toggleSendVoiceButtons();
    }

    // Mark messages as read
    await this.markAsRead(friendId);
}

    // Load messages with modern design
    async loadMessages(friendId, loadMore = false) {
        try {
            const chatContainer = document.getElementById('chatMessages');
            const messagesLoading = document.getElementById('messagesLoading');

            if (!loadMore) {
                if (chatContainer) {
                    chatContainer.innerHTML = `
                        <div class="flex flex-col items-center justify-center py-8">
                            <div class="flex space-x-1 mb-2">
                                <div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                                <div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                                <div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                            </div>
                            <p class="text-xs text-gray-500">Loading messages...</p>
                        </div>
                    `;
                }
            } else if (messagesLoading) {
                messagesLoading.classList.remove('hidden');
            }

            const response = await fetch(`/api/messaging/messages/${friendId}${loadMore ? '?older=true' : ''}`);
            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                this.displayMessages(data.messages, loadMore);
            }
        } catch (error) {
            console.error('Error loading messages:', error);
            const chatContainer = document.getElementById('chatMessages');
            if (chatContainer) {
                chatContainer.innerHTML = `
                    <div id="noMessages" class="flex flex-col items-center justify-center py-12 text-gray-400">
                        <div class="w-20 h-20 bg-gradient-to-r from-blue-100 to-purple-100 rounded-full flex items-center justify-center mb-4">
                            <i class="bi bi-chat-dots text-3xl text-gray-300"></i>
                        </div>
                        <p class="text-sm font-medium text-gray-500">No messages yet</p>
                        <p class="text-xs mt-1 text-gray-400">Say hello and start the conversation!</p>
                        <button onclick="sendFirstMessage()"
                                class="mt-4 px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white text-sm rounded-lg hover:from-blue-600 hover:to-purple-600 transition-all duration-300 transform hover:scale-105">
                            <i class="bi bi-send mr-2"></i>
                            Send First Message
                        </button>
                    </div>
                `;
            }
        } finally {
            const messagesLoading = document.getElementById('messagesLoading');
            if (messagesLoading) {
                messagesLoading.classList.add('hidden');
            }
        }
    }

    // Display messages with modern design
    displayMessages(messages, prepend = false) {
    const chatContainer = document.getElementById('chatMessages');
    if (!chatContainer) return;

    if (!messages || messages.length === 0) {
        const noMessages = document.getElementById('noMessages');
        if (noMessages) {
            noMessages.classList.remove('hidden');
        } else {
            chatContainer.innerHTML = `
                <div id="noMessages" class="flex flex-col items-center justify-center py-12 text-gray-400">
                    <div class="w-20 h-20 bg-gradient-to-r from-blue-100 to-purple-100 rounded-full flex items-center justify-center mb-4">
                        <i class="bi bi-chat-dots text-3xl text-gray-300"></i>
                    </div>
                    <p class="text-sm font-medium text-gray-500">No messages yet</p>
                    <p class="text-xs mt-1 text-gray-400">Say hello and start the conversation!</p>
                    <button onclick="sendFirstMessage()"
                            class="mt-4 px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white text-sm rounded-lg hover:from-blue-600 hover:to-purple-600 transition-all duration-300 transform hover:scale-105">
                        <i class="bi bi-send mr-2"></i>
                        Send First Message
                    </button>
                </div>
            `;
        }
        return;
    }

    // Hide no messages
    const noMessages = document.getElementById('noMessages');
    if (noMessages) noMessages.classList.add('hidden');

    if (prepend) {
        // Prepend older messages at the beginning
        const fragment = document.createDocumentFragment();
        messages.reverse().forEach(msg => {
            const messageElement = this.createMessageElement(msg);
            fragment.prepend(messageElement);
        });
        chatContainer.prepend(fragment);
    } else {
        // Clear and show new messages
        chatContainer.innerHTML = '';
        messages.forEach(msg => {
            this.appendMessage(msg, false);
        });

        // Scroll to bottom after all messages are added
        setTimeout(() => {
            this.scrollToBottom(true);
        }, 50);
    }
}

    // Create modern message element
    createMessageElement(msg) {
        const isOwnMessage = msg.sender_id === window.currentUserId;
        const time = new Date(msg.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });

        const element = document.createElement('div');
        element.className = `flex ${isOwnMessage ? 'justify-end' : 'justify-start'} mb-3 message-bubble ${isOwnMessage ? 'sent' : 'received'}`;

        element.innerHTML = `
            <div class="max-w-xs lg:max-w-md">
                <div class="p-3">
                    ${!isOwnMessage ? `
                        <div class="flex items-center mb-1">
                            <img src="${msg.sender_avatar || window.defaultAvatar}"
                                 class="w-4 h-4 rounded-full mr-1 object-cover">
                            <span class="text-xs font-medium">${msg.sender_name || 'User'}</span>
                        </div>
                    ` : ''}
                    <div class="text-sm">${msg.content || ''}</div>
                    <div class="flex justify-end items-center mt-1 space-x-2">
                        <span class="message-time text-xs opacity-70">${time}</span>
                        ${isOwnMessage ? `
                            <span class="message-status ${msg.status} text-xs">
                                <i class="bi ${msg.status === 'read' ? 'bi-check2-all text-blue-500' : 'bi-check2 text-gray-400'}"></i>
                            </span>
                        ` : ''}
                    </div>
                </div>
                ${msg.reaction ? `
                    <div class="message-reaction">
                        <span class="text-lg">${msg.reaction}</span>
                        <span class="text-xs">${msg.reactionCount || 1}</span>
                    </div>
                ` : ''}
            </div>
        `;

        return element;
    }

    // Append a single message
    appendMessage(msg, shouldScroll = true) {
        const chatContainer = document.getElementById('chatMessages');
        if (!chatContainer) return;

        // Hide no messages
        const noMessages = document.getElementById('noMessages');
        if (noMessages) noMessages.classList.add('hidden');

        const messageElement = this.createMessageElement(msg);
        chatContainer.appendChild(messageElement);

        if (shouldScroll) {
            this.scrollToBottom();
        }
    }

    // Send a message
    async sendMessage() {
        const input = document.getElementById('chatInput');
        if (!input || !this.state.activeFriendId) return;

        const content = input.value.trim();
        if (!content) return;

        if (this.state.socket && this.state.isConnected) {
            // Send via WebSocket for real-time
            this.state.socket.emit('send_message', {
                friend_id: this.state.activeFriendId,
                content: content
            });
        } else {
            // Fallback to HTTP API
            await this.sendMessageViaAPI(content);
        }

        input.value = '';
        this.autoResizeTextarea(input);
        this.stopTyping();
        this.toggleSendVoiceButtons();
    }

    // Send message via HTTP API (fallback)
    async sendMessageViaAPI(content) {
        try {
            const response = await fetch('/api/messaging/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    friend_id: this.state.activeFriendId,
                    content: content
                })
            });

            const data = await response.json();
            if (data.success && data.message) {
                this.appendMessage(data.message, true);
            } else if (data.error) {
                Toast.show(data.error, 'danger');
            }
        } catch (error) {
            console.error('Error sending message:', error);
            Toast.show('Failed to send message', 'danger');
        }
    }

    // Handle typing indicator
    handleTyping() {
        if (!this.state.activeFriendId || !this.state.socket) return;

        if (!this.state.isTyping) {
            this.state.isTyping = true;
            this.state.socket.emit('typing_start', {
                friend_id: this.state.activeFriendId,
                user_name: window.currentUserName || 'Someone'
            });
        }

        // Clear existing timeout
        if (this.state.typingTimeout) {
            clearTimeout(this.state.typingTimeout);
        }

        // Set timeout to stop typing
        this.state.typingTimeout = setTimeout(() => {
            this.stopTyping();
        }, 2000);
    }

    // Stop typing indicator
    stopTyping() {
        if (this.state.isTyping && this.state.activeFriendId && this.state.socket) {
            this.state.isTyping = false;
            this.state.socket.emit('typing_stop', { friend_id: this.state.activeFriendId });
        }

        if (this.state.typingTimeout) {
            clearTimeout(this.state.typingTimeout);
            this.state.typingTimeout = null;
        }
    }

    // Show typing indicator for other user
    showTypingIndicator(userName) {
        const indicator = document.getElementById('typingIndicator');
        const userNameEl = document.getElementById('typingUserName');

        if (userNameEl) {
            userNameEl.textContent = userName;
        }
        if (indicator) {
            indicator.classList.remove('hidden');
        }
    }

    // Hide typing indicator
    hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }
    }

    // Connect to Socket.IO with modern features
    connectSocket() {
        if (this.state.socket && this.state.isConnected) {
            return;
        }

        this.state.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000
        });

        // Socket event handlers
        this.state.socket.on('connect', () => {
            console.log('✅ Connected to messaging server');
            this.state.isConnected = true;

            // Update connection status indicator
            const popup = document.getElementById('messengerPopup');
            if (popup) {
                popup.classList.remove('disconnected');
                popup.classList.add('connected');
            }
        });

        this.state.socket.on('disconnect', () => {
            console.log('🔌 Disconnected from messaging server');
            this.state.isConnected = false;

            // Update connection status indicator
            const popup = document.getElementById('messengerPopup');
            if (popup) {
                popup.classList.remove('connected');
                popup.classList.add('disconnected');
            }
        });

        this.state.socket.on('new_message', (msg) => {
            if (msg.sender_id === this.state.activeFriendId ||
                msg.receiver_id === this.state.activeFriendId) {
                this.appendMessage(msg, true);

                // Play notification sound if not in active chat
                if (msg.sender_id !== window.currentUserId) {
                    this.playNotificationSound();
                }
            }
            this.updateUnreadBadge();
        });

        this.state.socket.on('user_typing', (data) => {
            if (data.user_id === this.state.activeFriendId) {
                this.showTypingIndicator(data.user_name);
            }
        });

        this.state.socket.on('user_stopped_typing', (data) => {
            if (data.user_id === this.state.activeFriendId) {
                this.hideTypingIndicator();
            }
        });

        this.state.socket.on('friend_online', (data) => {
            console.log(`Friend ${data.user_id} is online`);
            this.updateFriendStatus(data.user_id, true);
        });

        this.state.socket.on('friend_offline', (data) => {
            console.log(`Friend ${data.user_id} is offline`);
            this.updateFriendStatus(data.user_id, false);
        });

        this.state.socket.on('message_delivered', (data) => {
            this.updateMessageStatus(data.message_id, 'delivered');
        });

        this.state.socket.on('message_read', (data) => {
            this.updateMessageStatus(data.message_id, 'read');
        });

        this.state.socket.on('error', (error) => {
            console.error('Socket error:', error);
            Toast.show('Connection error', 'danger');
        });
    }

    // Update friend online status
    updateFriendStatus(friendId, isOnline) {
        // Update in friends list if open
        const friendElements = document.querySelectorAll('.friend-item');
        friendElements.forEach(element => {
            const statusIndicator = element.querySelector('.status-pulse, .bg-green-500, .bg-gray-400');
            if (statusIndicator && element.onclick && element.onclick.toString().includes(`openChat(${friendId}`)) {
                statusIndicator.className = `absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-white ${isOnline ? 'bg-green-500 status-pulse' : 'bg-gray-400'}`;
            }
        });

        // Update in chat header if active
        if (this.state.activeFriendId === friendId) {
            const chatStatus = document.getElementById('chatStatus');
            const lastSeen = document.getElementById('chatLastSeen');

            if (chatStatus) {
                chatStatus.className = `absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-white ${isOnline ? 'bg-green-500 status-pulse' : 'bg-gray-400'}`;
            }

            if (lastSeen) {
                lastSeen.textContent = isOnline ? 'Online' : 'Last seen recently';
            }
        }
    }

    // Update message status
    updateMessageStatus(messageId, status) {
        const messageElements = document.querySelectorAll('.message-bubble.sent');
        messageElements.forEach(element => {
            const statusIcon = element.querySelector('.message-status i');
            if (statusIcon) {
                statusIcon.className = `bi ${status === 'read' ? 'bi-check2-all text-blue-500' : 'bi-check2 text-gray-400'}`;
            }
        });
    }

    // Mark messages as read
    async markAsRead(friendId) {
        try {
            await fetch(`/api/messaging/mark-read/${friendId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                }
            });
            this.updateUnreadBadge();
        } catch (error) {
            console.error('Error marking as read:', error);
        }
    }

    // Update unread badge
    async updateUnreadBadge() {
        try {
            const response = await fetch('/api/messaging/unread_count');
            if (!response.ok) return;

            const data = await response.json();
            if (data.success) {
                const badge = document.getElementById('unreadMessagesBadge');
                const chatBadge = document.getElementById('unreadChatsBadge');

                if (badge) {
                    if (data.unread_count > 0) {
                        badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                }

                if (chatBadge) {
                    if (data.unread_count > 0) {
                        chatBadge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
                        chatBadge.classList.remove('hidden');
                    } else {
                        chatBadge.classList.add('hidden');
                    }
                }
            }
        } catch (error) {
            console.error('Error updating unread count:', error);
        }
    }

    // Scroll chat to bottom
    scrollToBottom(force = false) {
    const wrapper = document.getElementById('chatMessagesWrapper');
    const container = document.getElementById('chatMessages');

    if (!wrapper || !container) {
        console.warn('Chat wrapper or container not found');
        return;
    }

    // Use requestAnimationFrame for smooth scrolling
    requestAnimationFrame(() => {
        // Always scroll to bottom when opening a chat (force = true)
        if (force) {
            wrapper.scrollTop = wrapper.scrollHeight;
        } else {
            // Only auto-scroll if user is near bottom
            const isNearBottom = wrapper.scrollHeight - wrapper.scrollTop - wrapper.clientHeight < 200;
            if (isNearBottom) {
                wrapper.scrollTop = wrapper.scrollHeight;
            }
        }
    });
}

scrollToLatestMessage() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;

    const messages = chatMessages.querySelectorAll('.message-bubble');
    if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1];
        lastMessage.scrollIntoView({
            behavior: 'smooth',
            block: 'end',
            inline: 'nearest'
        });
    }
}


    // Handle message scroll
    handleMessageScroll() {
        const wrapper = document.getElementById('chatMessagesWrapper');
        const scrollBtn = document.getElementById('scrollToBottomBtn');

        if (wrapper && scrollBtn) {
            // Show scroll to bottom button if scrolled up
            const isAtBottom = wrapper.scrollHeight - wrapper.scrollTop <= wrapper.clientHeight + 100;
            scrollBtn.classList.toggle('hidden', isAtBottom);

            // Load more messages when near top
            if (wrapper.scrollTop < 100 && this.state.activeFriendId) {
                this.loadMoreMessages();
            }
        }
    }

    // Load more messages
    async loadMoreMessages() {
        if (!this.state.activeFriendId) return;

        // Prevent multiple simultaneous loads
        if (this.isLoadingMore) return;
        this.isLoadingMore = true;

        await this.loadMessages(this.state.activeFriendId, true);
        this.isLoadingMore = false;
    }

    // Start chat with user (called from profile, etc.)
    startChat(userId) {
        this.open();
        setTimeout(() => {
            // Try to find and click the friend in the list
            const friendElements = document.querySelectorAll('.friend-item');
            friendElements.forEach(el => {
                if (el.onclick && el.onclick.toString().includes(`openChat(${userId}`)) {
                    el.click();
                }
            });
        }, 500);
    }

    // Voice message functionality
    setupVoiceRecording() {
        const recordButton = document.getElementById('recordButton');
        if (recordButton) {
            recordButton.addEventListener('mousedown', () => this.startRecording());
            recordButton.addEventListener('mouseup', () => this.stopRecording());
            recordButton.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.startRecording();
            });
            recordButton.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.stopRecording();
            });
        }
    }

    startVoiceMessage() {
        const recorder = document.getElementById('voiceRecorder');
        if (recorder) {
            recorder.classList.remove('hidden');
        }
    }

    closeVoiceRecorder() {
        const recorder = document.getElementById('voiceRecorder');
        if (recorder) {
            recorder.classList.add('hidden');
        }
        this.stopRecording();
    }

    startRecording() {
        if (!this.state.activeFriendId) return;

        this.state.voiceRecording = true;
        this.state.recordingStartTime = Date.now();

        // Update UI
        const recordButton = document.getElementById('recordButton');
        const timer = document.getElementById('recordingTimer');

        if (recordButton) {
            recordButton.textContent = 'Release to send';
            recordButton.classList.remove('from-red-500', 'to-pink-500');
            recordButton.classList.add('from-red-600', 'to-pink-600');
        }

        // Start timer
        this.state.recordingInterval = setInterval(() => {
            if (timer) {
                const elapsed = Date.now() - this.state.recordingStartTime;
                const seconds = Math.floor(elapsed / 1000);
                const minutes = Math.floor(seconds / 60);
                timer.textContent = `${minutes.toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
            }
        }, 1000);
    }

    stopRecording() {
        if (!this.state.voiceRecording) return;

        this.state.voiceRecording = false;

        // Clear interval
        if (this.state.recordingInterval) {
            clearInterval(this.state.recordingInterval);
            this.state.recordingInterval = null;
        }

        // Send voice message if recording was long enough
        const duration = Date.now() - this.state.recordingStartTime;
        if (duration > 1000) { // At least 1 second
            this.sendVoiceMessage(duration);
        }

        // Reset UI
        const recordButton = document.getElementById('recordButton');
        const timer = document.getElementById('recordingTimer');

        if (recordButton) {
            recordButton.textContent = 'Hold to Record';
            recordButton.classList.remove('from-red-600', 'to-pink-600');
            recordButton.classList.add('from-red-500', 'to-pink-500');
        }

        if (timer) {
            timer.textContent = '00:00';
        }

        this.closeVoiceRecorder();
    }

    async sendVoiceMessage(duration) {
        try {
            // In a real app, you would upload the audio blob here
            const response = await fetch('/api/messaging/send-voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    friend_id: this.state.activeFriendId,
                    duration: duration,
                    audio_url: '' // You would upload and get URL
                })
            });

            const data = await response.json();
            if (data.success) {
                Toast.show('Voice message sent', 'success');
            }
        } catch (error) {
            console.error('Error sending voice message:', error);
            Toast.show('Failed to send voice message', 'danger');
        }
    }

    // Additional features
    toggleAttachmentMenu(e) {
        const menu = document.querySelector('.dropdown-menu');
        if (menu) {
            menu.classList.toggle('hidden');
            if (e) e.stopPropagation();
        }
    }

    toggleEmojiPicker() {
        // Implement emoji picker
        Toast.show('Emoji picker coming soon', 'info');
    }

    handleQuickAction(action) {
        switch(action) {
            case 'quick reply':
                this.insertQuickReply();
                break;
            case 'translate':
                this.translateMessage();
                break;
            case 'schedule':
                this.scheduleMessage();
                break;
        }
    }

    insertQuickReply() {
        const input = document.getElementById('chatInput');
        if (input) {
            const quickReplies = [
                "👍",
                "Sounds good!",
                "Let me check and get back to you",
                "😂",
                "Perfect!",
                "On my way!"
            ];
            const randomReply = quickReplies[Math.floor(Math.random() * quickReplies.length)];
            input.value = randomReply;
            this.autoResizeTextarea(input);
            this.toggleSendVoiceButtons();
        }
    }

    translateMessage() {
        Toast.show('Translation feature coming soon', 'info');
    }

    scheduleMessage() {
        Toast.show('Schedule message feature coming soon', 'info');
    }

    startVoiceCall() {
        Toast.show('Voice call feature coming soon', 'info');
    }

    startVideoCall() {
        Toast.show('Video call feature coming soon', 'info');
    }

    playNotificationSound() {
        // Play a subtle notification sound
        const audio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ'); // Empty sound
        audio.volume = 0.3;
        audio.play().catch(() => {});
    }

    // Load online friends
    async loadOnlineFriends() {
        // Implement online friends list
        const container = document.getElementById('onlineFriends');
        if (container) {
            container.innerHTML = `
                <div class="flex flex-col items-center justify-center p-8 text-gray-500">
                    <i class="bi bi-wifi text-3xl mb-3"></i>
                    <p class="text-sm font-medium">Loading online friends...</p>
                </div>
            `;
        }
    }

    // Load chat requests
    async loadChatRequests() {
        // Implement chat requests
        const container = document.getElementById('chatRequests');
        if (container) {
            container.innerHTML = `
                <div class="flex flex-col items-center justify-center p-8 text-gray-500">
                    <i class="bi bi-envelope text-3xl mb-3"></i>
                    <p class="text-sm font-medium">No pending requests</p>
                    <p class="text-xs mt-1 text-gray-400">When someone sends you a message request, it'll appear here</p>
                </div>
            `;
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('messengerPopup') && !window.messengerInitialized) {
        window.Messenger = new ModernMessenger();
        window.messengerInitialized = true;
    }
});

// Global function wrappers
window.openMessenger = () => window.Messenger?.open();
window.closeMessenger = () => window.Messenger?.close();
window.backToFriends = () => window.Messenger?.backToFriends();
window.handleTyping = () => window.Messenger?.handleTyping();
window.sendMessage = () => window.Messenger?.sendMessage();
window.startVoiceMessage = () => window.Messenger?.startVoiceMessage();
window.closeVoiceRecorder = () => window.Messenger?.closeVoiceRecorder();
window.startVoiceCall = () => window.Messenger?.startVoiceCall();
window.startVideoCall = () => window.Messenger?.startVideoCall();
window.toggleAttachmentMenu = (e) => window.Messenger?.toggleAttachmentMenu(e);
window.toggleEmojiPicker = () => window.Messenger?.toggleEmojiPicker();
window.scrollToBottom = () => window.Messenger?.scrollToBottom();

// For profile buttons
window.startChat = (userId) => window.Messenger?.startChat(userId);


// ==================== REACTION SYSTEM ====================
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
    const likeCount = document.getElementById(`like-count-${postId}`);
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
            likeCount.textContent = `${data.total_reactions} ${data.total_reactions === 1 ? 'reaction' : 'reactions'}`;
            Toast.show(getReactionMessage(data.user_reaction, data.reacted), 'success');
        } else {
            updateReactionUI(postId, null, false, likeBtn, likeIcon, likeText);
            Toast.show(data.error || 'Failed to react', 'danger');
        }
    } catch (error) {
        console.error('Reaction error:', error);
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




// ==================== COMMENT SYSTEM ====================
function handleCommentKeypress(event, postId) {
    if (event.key === 'Enter' && !event.shiftKey && event.target.value.trim()) {
        event.preventDefault();
        addComment(postId, event.target.value.trim());
    }
}

async function addComment(postId, content) {
    const input = document.getElementById(`commentInput-${postId}`);
    const container = document.getElementById(`comments-${postId}`);
    const countElement = document.getElementById(`comment-count-${postId}`);

    // Store original state
    input.disabled = true;
    const placeholder = input.placeholder;
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

            // Use global user info
            const userAvatar = window.currentUserInfo?.avatar || window.defaultAvatar;
            const userName = window.currentUserInfo?.name || 'You';

            // Create the comment element
            const div = document.createElement('div');
            div.className = 'flex space-x-2 md:space-x-3 mb-3 md:mb-4 comment-item comment-fade-in';
            div.id = `comment-${comment.id || data.id}`;
            div.innerHTML = `
                <img src="${userAvatar}" class="w-6 h-6 md:w-8 md:h-8 rounded-full object-cover">
                <div class="flex-1">
                    <div class="bg-white rounded-xl md:rounded-2xl px-3 py-2 md:px-4 md:py-3">
                        <div class="flex justify-between items-start mb-1">
                            <h5 class="font-semibold text-xs md:text-sm">${userName}</h5>
                            <div class="dropdown relative">
                                <button class="p-0.5 md:p-1 rounded-full hover:bg-gray-100"><i class="bi bi-three-dots text-gray-400 text-xs"></i></button>
                                <div class="dropdown-menu absolute right-0 mt-1 w-28 md:w-32 bg-white rounded-lg md:rounded-xl shadow-2xl border border-gray-200 hidden z-10">
                                    <button onclick="deleteComment(${comment.id || data.id}, ${postId})" class="w-full text-left px-2 py-1.5 md:px-3 md:py-2 hover:bg-gray-50 text-red-600 text-xs md:text-sm">
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
            if (container.children.length > 0) {
                container.insertBefore(div, container.firstChild);
            } else {
                container.appendChild(div);
            }

            // Clear input
            input.value = '';

            // Update comment count
            updateCommentCount(postId, 1, 'add');

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
        console.error(error);
        Toast.show('Network error', 'danger');
    }
}

async function deleteComment(commentId) {
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
            Toast.show('Comment deleted', 'info');
        } else {
            Toast.show(data.error || 'Failed', 'danger');
        }
    } catch (error) {
        console.error(error);
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

// ==================== SHARE MODAL ====================
let currentSharePostId = null;

function openShareModal(postId) {
    currentSharePostId = postId;
    // You can implement a share modal here similar to the group page
    // For now, let's just copy the link
    copyPostLink();
}

function copyPostLink() {
    const url = `${window.location.origin}/post/${currentSharePostId}`;
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

// ==================== EVENT LISTENERS ====================
document.addEventListener('DOMContentLoaded', () => {
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

// Expose functions to HTML
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
window.copyPostLink = copyPostLink;






// Make functions globally available
window.toggleFloatingAd = function() {
    AdSystem.toggleFloatingAd();
};

window.refreshAds = function() {
    AdSystem.refresh();
};

window.cycleNextAd = function() {
    AdSystem.cycleNextAd();
};

window.cyclePreviousAd = function() {
    AdSystem.cyclePreviousAd();
};