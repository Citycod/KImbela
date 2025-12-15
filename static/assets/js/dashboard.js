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
    isTyping: false,
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
            Toast.show('Failed to like post', 'danger');
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

    async addComment(postId, content, inputElement) {
        const originalPlaceholder = inputElement.placeholder;
        inputElement.placeholder = 'Posting...';
        inputElement.disabled = true;

        try {
            const response = await fetch(`/add_comment/${postId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ content })
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            inputElement.value = '';

            // Add comment to UI
            const container = inputElement.closest('.comments-section');
            if (container) {
                const commentHTML = `
                    <div class="comment flex space-x-2 mb-3 animate-fadeIn">
                        <img src="${data.avatar || window.defaultAvatar}" alt="" class="w-8 h-8 rounded-full object-cover flex-shrink-0">
                        <div class="flex-1">
                            <div class="bg-white rounded-2xl px-3 py-2">
                                <div class="font-semibold text-sm">${data.name || 'User'}</div>
                                <div class="text-sm">${data.content}</div>
                            </div>
                        </div>
                    </div>
                `;
                container.insertAdjacentHTML('beforeend', commentHTML);
            }

            Toast.show('Comment added!', 'success');
        } catch (error) {
            console.error('Error adding comment:', error);
            Toast.show('Failed to add comment', 'danger');
        } finally {
            inputElement.placeholder = originalPlaceholder;
            inputElement.disabled = false;
        }
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
                // Update button back to "Add Friend"
                button.innerHTML = '<i class="bi bi-person-plus mr-1"></i> Add Friend';
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

        const container = button.closest('.suggestion-card') || button.closest('.profile-actions');
        const originalHTML = container ? container.innerHTML : null;

        Loader.quick(button, 'show');

        try {
            const response = await fetch(`/accept_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });

            const data = await response.json();

            if (data.success) {
                // Update UI to show "Friends" status
                if (container) {
                    container.innerHTML = `
                        <button
                            class="w-full py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors"
                            onclick="event.stopPropagation(); Messenger.startChat(${userId})"
                        >
                            <i class="bi bi-chat-dots mr-1"></i> Message
                        </button>
                    `;
                }

                Toast.show('Friend request accepted!', 'success');

                // Update the profile modal
                this.updateProfileModalButton(userId, 'friends');
            } else {
                Toast.show(data.error || 'Failed to accept request', 'danger');
            }
        } catch (error) {
            console.error('Error accepting friend request:', error);
            Toast.show('Network error. Please try again.', 'danger');
        } finally {
            Loader.quick(button, 'hide');
        }
    },

    async declineFriendRequest(userId, button) {
        if (!button) return;

        const container = button.closest('.suggestion-card') || button.closest('.profile-actions');
        const originalHTML = container ? container.innerHTML : null;

        Loader.quick(button, 'show');

        try {
            const response = await fetch(`/decline_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });

            const data = await response.json();

            if (data.success) {
                // Update UI to show "Add Friend" again
                if (container) {
                    container.innerHTML = `
                        <button
                            class="btn-add-friend w-full py-2 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
                            onclick="event.stopPropagation(); FriendSystem.add(${userId}, this)"
                            style="background: linear-gradient(135deg, #5a4500, #b88900);"
                        >
                            <i class="bi bi-person-plus mr-1"></i> Add Friend
                        </button>
                    `;
                }

                Toast.show('Friend request declined', 'info');

                // Update the profile modal
                this.updateProfileModalButton(userId, 'none');
            } else {
                Toast.show(data.error || 'Failed to decline request', 'danger');
            }
        } catch (error) {
            console.error('Error declining friend request:', error);
            Toast.show('Network error. Please try again.', 'danger');
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
                        <i class="bi bi-person-plus mr-1"></i> Add Friend
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

const ProfileSystem = {
    async openProfileModal(userId) {
        const modalBody = document.getElementById('profileModalBody');
        const profileActions = document.getElementById('profileActions');

        if (modalBody) {
            modalBody.innerHTML = `
                <div class="flex flex-col items-center justify-center p-8">
                    <span class="tiny-loader md"></span>
                    <div class="text-gray-500 mt-2">Loading profile...</div>
                </div>
            `;
        }

        Modal.open('profileModal');

        try {
            const response = await fetch(`/get_user_profile/${userId}`);
            if (!response.ok) throw new Error('Failed to load profile');

            const data = await response.json();
            this.displayProfileModal(data, userId);
        } catch (error) {
            console.error('Error loading profile:', error);
            if (modalBody) {
                modalBody.innerHTML = `
                    <div class="text-center p-8 text-red-500">
                        <i class="bi bi-exclamation-triangle text-3xl mb-3"></i>
                        <p>Failed to load profile</p>
                    </div>
                `;
            }
            Toast.show('Failed to load profile', 'danger');
        }
    },

    displayProfileModal(data, userId) {
        const modalBody = document.getElementById('profileModalBody');
        const profileActions = document.getElementById('profileActions');

        if (!modalBody || !profileActions) return;

        const dob = data.dob ? new Date(data.dob).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        }) : 'Not specified';

        const age = data.dob ? TimeUtils.calculateAge(new Date(data.dob)) : '';

        modalBody.innerHTML = `
            <div class="profile-modal-content">
                <div class="profile-header relative">
                    <div class="cover-photo-container h-48 overflow-hidden rounded-t-2xl">
                        <img src="${data.cover_pic || 'https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg'}"
                             alt="Cover" class="cover-photo w-full h-full object-cover">
                    </div>
                    <div class="profile-info-container text-center relative -mt-16 pb-6 px-6">
                        <div class="profile-avatar-container inline-block">
                            <img src="${data.profile_pic || window.defaultAvatar}" alt="${data.first_name}"
                                 class="profile-avatar w-32 h-32 rounded-full border-4 border-white object-cover shadow-strong">
                        </div>
                        <div class="profile-text-content mt-4">
                            <h3 class="profile-name text-2xl font-bold">${data.first_name || ''} ${data.last_name || ''}</h3>
                            <div class="profile-details flex flex-wrap justify-center gap-2 mt-2">
                                ${data.marital_status ? `<span class="inline-flex items-center gap-1 bg-gray-100 px-2 py-1 rounded-full text-sm"><i class="bi bi-heart-fill text-red-500 text-xs"></i> ${data.marital_status}</span>` : ''}
                                ${data.city && data.country ? `<span class="inline-flex items-center gap-1 bg-gray-100 px-2 py-1 rounded-full text-sm"><i class="bi bi-geo-alt-fill text-blue-500 text-xs"></i> ${data.city}, ${data.country}</span>` : ''}
                                ${age ? `<span class="inline-flex items-center gap-1 bg-gray-100 px-2 py-1 rounded-full text-sm"><i class="bi bi-balloon-fill text-purple-500 text-xs"></i> ${age}</span>` : ''}
                            </div>
                            ${data.bio ? `<div class="profile-bio mt-3 max-w-2xl mx-auto"><p class="bio-text text-gray-700">${data.bio}</p></div>` : ''}
                        </div>
                    </div>
                </div>

                <div class="profile-details-section mt-6 px-6 pb-6">
                    <div class="grid md:grid-cols-2 gap-6">
                        <div class="detail-card bg-gray-50 rounded-2xl p-6">
                            <h6 class="detail-card-title font-semibold text-lg mb-4 flex items-center"><i class="bi bi-person-badge-fill mr-2 text-blue-500"></i>Personal Info</h6>
                            <div class="detail-list space-y-3">
                                ${data.email ? `<div class="detail-row flex"><span class="detail-label font-medium text-gray-600 min-w-24">Email:</span><span class="detail-value text-sm">${data.email}</span></div>` : ''}
                                ${data.phone_number ? `<div class="detail-row flex"><span class="detail-label font-medium text-gray-600 min-w-24">Phone:</span><span class="detail-value text-sm">${data.phone_number}</span></div>` : ''}
                                ${data.gender ? `<div class="detail-row flex"><span class="detail-label font-medium text-gray-600 min-w-24">Gender:</span><span class="detail-value text-sm">${data.gender}</span></div>` : ''}
                                ${data.dob ? `<div class="detail-row flex"><span class="detail-label font-medium text-gray-600 min-w-24">Birth:</span><span class="detail-value text-sm">${dob}</span></div>` : ''}
                            </div>
                        </div>
                        <div class="detail-card bg-gray-50 rounded-2xl p-6">
                            <h6 class="detail-card-title font-semibold text-lg mb-4 flex items-center"><i class="bi bi-geo-fill mr-2 text-green-500"></i>Location & Interests</h6>
                            <div class="detail-list space-y-3">
                                ${data.city ? `<div class="detail-row flex"><span class="detail-label font-medium text-gray-600 min-w-24">City:</span><span class="detail-value text-sm">${data.city}</span></div>` : ''}
                                ${data.country ? `<div class="detail-row flex"><span class="detail-label font-medium text-gray-600 min-w-24">Country:</span><span class="detail-value text-sm">${data.country}</span></div>` : ''}
                                ${data.interests ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24 flex-shrink-0">Interests:</span><span class="detail-value text-sm">${data.interests}</span></div>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const isFriend = window.friendIds?.includes(userId) || false;
        const isBlocked = appState.blockedUserIds?.includes(userId) || false;

        let actionsHTML = '';
        if (isFriend) {
            actionsHTML = `
                <button class="btn btn-primary px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors" onclick="Messenger.startChat(${userId})">
                    <i class="bi bi-chat-dots me-1"></i> Message
                </button>
                ${isBlocked ? `
                    <button class="btn btn-success px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors" onclick="BlockSystem.unblock(${userId})">
                        <i class="bi bi-check-circle me-1"></i> Unblock
                    </button>
                ` : `
                    <button class="btn btn-outline-danger px-4 py-2 border border-red-500 text-red-500 rounded-lg font-medium hover:bg-red-50 transition-colors" onclick="BlockSystem.block(${userId})">
                        <i class="bi bi-slash-circle me-1"></i> Block
                    </button>
                `}
            `;
        } else {
            actionsHTML = `
                <button class="btn btn-primary px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors" onclick="FriendSystem.add(${userId}, this)">
                    <i class="bi bi-person-plus me-1"></i> Add Friend
                </button>
            `;
        }

        profileActions.innerHTML = actionsHTML;
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
                <div class="notification-item p-3 border-b border-gray-100 ${notification.is_read ? '' : 'bg-blue-50 border-l-4 border-l-blue-500'}"
                    ${!isFriendRequest ? `onclick="NotificationSystem.handleClick(${notification.id}, '${notification.type}', ${notification.entity_id || 0})"` : ''}>

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
                                ` : `<small class="text-gray-500 text-xs">Request pending</small>`}
                            </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    async handleClick(id, type, entityId) {
        await this.markAsRead(id);

        switch (type) {
            case 'friend_request':
            case 'friend_accepted':
            case 'profile_update':
                ProfileSystem.openProfileModal(entityId);
                break;
            case 'post_like':
            case 'new_comment':
                this.scrollToPost(entityId);
                break;
        }

        const dropdownMenu = document.getElementById('notificationDropdownMenu');
        if (dropdownMenu) dropdownMenu.classList.add('hidden');
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

const Messenger = {
    state: {
        socket: null,
        activeFriendId: null,
        isTyping: false,
        typingTimeout: null
    },

    async open() {
        const popup = document.getElementById('messengerPopup');
        if (!popup) return;

        popup.classList.remove('hidden');
        await this.loadFriends();
        this.connectSocket();
    },

    close() {
        const popup = document.getElementById('messengerPopup');
        if (popup) {
            popup.classList.add('hidden');
            this.backToFriends();
        }
    },

    backToFriends() {
        this.state.activeFriendId = null;

        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');

        if (friendList) friendList.classList.remove('hidden');
        if (chatArea) chatArea.classList.add('hidden');

        const messagesContainer = document.getElementById('chatMessages');
        if (messagesContainer) messagesContainer.innerHTML = '';

        const chatInput = document.getElementById('chatInput');
        if (chatInput) chatInput.value = '';

        this.hideTypingIndicator();
    },

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

            const response = await fetch('/api/friends'); // Changed from '/friends' to '/api/friends'
            if (!response.ok) throw new Error('Network error');

            const friends = await response.json();
            this.displayFriends(friends);
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
            friendElement.className = 'flex items-center p-3 hover:bg-gray-50 cursor-pointer rounded-lg transition-colors';
            friendElement.onclick = () => this.openChat(friend.id, friend.name, friend.avatar, friend.online);

            friendElement.innerHTML = `
                <div class="relative">
                    <img src="${friend.avatar || window.defaultAvatar}" alt="${friend.name}" class="w-12 h-12 rounded-full object-cover">
                    ${friend.online ? `
                        <span class="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white"></span>
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

    openChat(friendId, friendName, friendAvatar, friendOnline) {
        this.state.activeFriendId = friendId;

        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');
        const chatName = document.getElementById('chatName');
        const chatAvatar = document.getElementById('chatAvatar');
        const chatStatus = document.getElementById('chatStatus');

        if (friendList) friendList.classList.add('hidden');
        if (chatArea) chatArea.classList.remove('hidden');
        if (chatName) chatName.textContent = friendName;
        if (chatAvatar) chatAvatar.src = friendAvatar || window.defaultAvatar;
        if (chatStatus) {
            chatStatus.textContent = friendOnline ? 'Online' : 'Offline';
            chatStatus.className = `text-xs ${friendOnline ? 'text-green-600' : 'text-gray-500'}`;
        }

        this.loadMessages(friendId);
        this.state.socket?.emit('join_chat', { friend_id: friendId });

        const chatInput = document.getElementById('chatInput');
        if (chatInput) chatInput.focus();
    },

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

            const response = await fetch(`/api/messages/${friendId}`); // Changed from `/messages/${friendId}`
            if (!response.ok) throw new Error('Network error');

            const messages = await response.json();
            this.displayMessages(messages);
        } catch (error) {
            console.error('Error loading messages:', error);
            const chatContainer = document.getElementById('chatMessages');
            if (chatContainer) {
                chatContainer.innerHTML = `
                    <div class="text-center p-6 text-gray-500">
                        <i class="bi bi-chat-dots text-2xl mb-2"></i>
                        <p class="text-sm">No messages yet</p>
                    </div>
                `;
            }
        }
    },

    displayMessages(messages) {
        const chatContainer = document.getElementById('chatMessages');
        if (!chatContainer) return;

        chatContainer.innerHTML = '';

        if (!messages || messages.length === 0) {
            chatContainer.innerHTML = `
                <div class="text-center p-6 text-gray-500">
                    <i class="bi bi-chat-dots text-2xl mb-2"></i>
                    <p class="text-sm">No messages yet</p>
                </div>
            `;
            return;
        }

        messages.forEach(msg => {
            this.appendMessage(msg, false);
        });

        this.scrollToBottom();
    },

    appendMessage(msg, shouldScroll = true) {
        const chatContainer = document.getElementById('chatMessages');
        if (!chatContainer) return;

        const isOwnMessage = msg.sender_id === currentUserId;
        const time = new Date(msg.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });

        const messageElement = document.createElement('div');
        messageElement.className = `flex ${isOwnMessage ? 'justify-end' : 'justify-start'} mb-2`;

        messageElement.innerHTML = `
            <div class="max-w-xs lg:max-w-md">
                <div class="${isOwnMessage ? 'bg-blue-100' : 'bg-gray-100'} rounded-2xl px-4 py-2">
                    ${!isOwnMessage ? `<div class="font-semibold text-sm mb-1">${msg.sender_name || 'User'}</div>` : ''}
                    <div class="text-sm">${msg.content || ''}</div>
                    <div class="text-xs text-gray-500 mt-1 text-right">
                        ${time}
                        ${isOwnMessage ?
                            `<span class="ml-1">${msg.status === 'read' ? '✓✓' : msg.status === 'delivered' ? '✓✓' : '✓'}</span>` :
                            ''}
                    </div>
                </div>
            </div>
        `;

        chatContainer.appendChild(messageElement);

        if (shouldScroll) {
            this.scrollToBottom();
        }
    },

    scrollToBottom() {
        const messagesWrapper = document.getElementById('chatMessagesWrapper');
        if (messagesWrapper) {
            setTimeout(() => {
                messagesWrapper.scrollTop = messagesWrapper.scrollHeight;
            }, 50);
        }
    },

    sendMessage() {
        const input = document.getElementById('chatInput');
        if (!input || !this.state.activeFriendId) return;

        const content = input.value.trim();
        if (!content) return;

        if (this.state.socket?.connected) {
            this.state.socket.emit('send_message', {
                friend_id: this.state.activeFriendId,
                content: content
            });
        } else {
            this.sendMessageViaAPI(content);
        }

        input.value = '';
        this.sendTypingIndicator('stop');
    },

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

    sendTypingIndicator(action) {
        if (!this.state.activeFriendId || !this.state.socket?.connected) return;

        if (action === 'start' && !this.state.isTyping) {
            this.state.isTyping = true;
            this.state.socket.emit('typing_start', { friend_id: this.state.activeFriendId });

            if (this.state.typingTimeout) {
                clearTimeout(this.state.typingTimeout);
            }

            this.state.typingTimeout = setTimeout(() => {
                this.sendTypingIndicator('stop');
            }, 2000);

        } else if (action === 'stop' && this.state.isTyping) {
            this.state.isTyping = false;
            this.state.socket.emit('typing_stop', { friend_id: this.state.activeFriendId });

            if (this.state.typingTimeout) {
                clearTimeout(this.state.typingTimeout);
                this.state.typingTimeout = null;
            }
        }
    },

    showTypingIndicator(userName) {
        const typingIndicator = document.getElementById('typingIndicator');
        const typingUserName = document.getElementById('typingUserName');

        if (typingIndicator && typingUserName) {
            typingUserName.textContent = `${userName} is typing...`;
            typingIndicator.classList.remove('hidden');
        }
    },

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.classList.add('hidden');
        }
    },

    connectSocket() {
        if (this.state.socket?.connected) return;

        // In your Socket.IO connection setup
        socket.on('friend_request_update', (data) => {
            switch(data.type) {
                case 'request_sent':
                    Toast.show('Friend request sent!', 'success');
                    break;
                case 'request_cancelled':
                    Toast.show('Friend request cancelled', 'info');
                    // Update any UI elements showing this user
                    updateFriendButtons(data.sender_id, 'none');
                    break;
        case 'request_accepted':
            Toast.show(`You are now friends with ${data.friend_name}!`, 'success');
            // Update any UI elements showing this user
            updateFriendButtons(data.friend_id, 'friends');
            break;
    }
});

        this.state.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5
        });

        this.state.socket.on('connect', () => {
            console.log('✅ Connected to messaging');
        });

        this.state.socket.on('new_message', (msg) => {
            if (msg.sender_id === this.state.activeFriendId || msg.receiver_id === this.state.activeFriendId) {
                this.appendMessage(msg, true);
            }
            this.updateUnreadBadge();
        });

        this.state.socket.on('user_typing', (data) => {
            if (data.user_id === this.state.activeFriendId) {
                this.showTypingIndicator(data.user_name);
            }
        });

        this.state.socket.on('user_stopped_typing', () => {
            this.hideTypingIndicator();
        });
    },




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

    startChat(userId) {
        this.open();
        setTimeout(() => {
            // Find and open chat with user
            const friendElements = document.querySelectorAll('.friend-item');
            friendElements.forEach(el => {
                if (el.onclick && el.onclick.toString().includes(userId)) {
                    el.click();
                }
            });
        }, 500);
    },

    init() {
        const openBtn = document.getElementById('openMessaging');
        const sendBtn = document.getElementById('sendChatBtn');
        const chatInput = document.getElementById('chatInput');
        const backBtn = document.querySelector('[onclick="backToFriends()"]');

        if (openBtn) openBtn.addEventListener('click', () => this.open());
        if (sendBtn) sendBtn.addEventListener('click', () => this.sendMessage());
        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            chatInput.addEventListener('input', () => {
                if (this.state.activeFriendId && chatInput.value.trim()) {
                    this.sendTypingIndicator('start');
                } else {
                    this.sendTypingIndicator('stop');
                }
            });
        }
        if (backBtn) backBtn.addEventListener('click', () => this.backToFriends());

        this.updateUnreadBadge();
        setInterval(() => this.updateUnreadBadge(), 30000);
    }
};


function updateFriendButtons(userId, status) {
    // Update suggestion cards
    const suggestionCard = document.querySelector(`.suggestion-card[onclick*="${userId}"]`);
    if (suggestionCard) {
        const button = suggestionCard.querySelector('button');
        if (button) {
            switch(status) {
                case 'none':
                    button.innerHTML = '<i class="bi bi-person-plus mr-1"></i> Add Friend';
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