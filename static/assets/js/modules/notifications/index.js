// ========================================
// NOTIFICATION SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';
import Loader from '../../core/loader.js';
import TimeUtils from '../../core/time-utils.js';
import ProfileSystem from '../profile/index.js';

class NotificationSystem {
    constructor() {
        this.csrfToken = config.getCsrfToken();
        this.defaultAvatar = config.getDefaultAvatar();
    }

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
    }

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
    }

    display(notifications, list) {
        if (!notifications || notifications.length === 0) {
            list.innerHTML = '<div class="text-center p-6 text-gray-500"><i class="bi bi-bell text-4xl mb-2"></i><p>No notifications yet</p></div>';
            return;
        }

        list.innerHTML = notifications.map(notification => {
            const actor = notification.actor || {};
            const actorName = actor.name || "Someone";
            const actorAvatar = actor.avatar || this.defaultAvatar;
            const actorId = actor.id || 0;
            const isFriendRequest = notification.type === 'friend_request';

            return `
                <div class="notification-item p-3 border-b border-gray-100 ${notification.is_read ? '' : 'bg-blue-50 border-l-4 border-l-blue-500'} cursor-pointer"
                     onclick="NotificationSystem.handleNotificationClick(event, ${notification.id}, '${notification.type}', ${actorId || 0})">

                    <div class="flex items-start space-x-3">
                        <img src="${actorAvatar}" alt="${actorName}" class="w-10 h-10 rounded-full object-cover"
                             onerror="this.src='${this.defaultAvatar}'">
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
    }

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
    }

    async markAsRead(id) {
        try {
            await fetch(`/notifications/${id}/read`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
            this.updateBadge();
            this.load();
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }

    async acceptFriendRequest(userId, notifId) {
        const button = event?.target;
        if (!button) return;

        Loader.quick(button, 'show');

        try {
            const response = await fetch(`/accept_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
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
    }

    async declineFriendRequest(userId, notifId) {
        const button = event?.target;
        if (!button) return;

        Loader.quick(button, 'show');

        try {
            const response = await fetch(`/decline_friend_request/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
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
    }

    scrollToPost(postId) {
        const el = document.querySelector(`[data-post-id="${postId}"]`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('highlight-animation');
            setTimeout(() => el.classList.remove('highlight-animation'), 2000);
        } else {
            Toast.show('Post not found', 'warning');
        }
    }

    init() {
        this.load();
        this.updateBadge();

        // Set interval for checking notifications
        setInterval(() => this.updateBadge(), 30000);

        const dropdown = document.getElementById('notificationDropdown');
        if (dropdown) {
            dropdown.addEventListener('click', () => this.load());
        }
    }
}

// Export singleton instance
const notificationSystem = new NotificationSystem();
export default notificationSystem;

// Make available globally
window.NotificationSystem = notificationSystem;