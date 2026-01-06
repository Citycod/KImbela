// ========================================
// FRIEND SYSTEM - COMPLETE VERSION
// ========================================

import { config } from '../../app/config.js';
import Loader from '../../core/loader.js';
import Toast from '../../core/toast.js';
import Modal from '../../core/modal.js';

class FriendSystem {
    constructor() {
        this.csrfToken = config.getCsrfToken();
        this.currentUserId = config.getCurrentUserId();
    }

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
                    'X-CSRFToken': this.csrfToken
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
    }

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
                    'X-CSRFToken': this.csrfToken
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
    }

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
                    'X-CSRFToken': this.csrfToken || '',
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
                const ProfileSystem = await import('../profile/index.js').then(m => m.default);
                if (ProfileSystem) {
                    ProfileSystem.updateProfileActions(userId);
                }

                // Update notification badge
                const NotificationSystem = await import('../notifications/index.js').then(m => m.default);
                if (NotificationSystem) {
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
    }

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
                    'X-CSRFToken': this.csrfToken || '',
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

                const ProfileSystem = await import('../profile/index.js').then(m => m.default);
                if (ProfileSystem) {
                    ProfileSystem.updateProfileActions(userId);
                }

                // Update notification badge
                const NotificationSystem = await import('../notifications/index.js').then(m => m.default);
                if (NotificationSystem) {
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
    }

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
                            onclick="handleMessageButtonClick(${userId})">
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
    }

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

    async updateFriendButtons(userId, status) {
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
                            this.add(userId, button);
                        };
                        break;
                    case 'friends':
                        button.innerHTML = '<i class="bi bi-chat-dots mr-1"></i> Message';
                        button.className = 'w-full py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors';
                        button.onclick = (e) => {
                            e.stopPropagation();
                            // Import Messenger dynamically
                            import('../messenger/index.js').then(module => {
                                module.default.startChat(userId);
                            });
                        };
                        break;
                }
            }
        }

        // Update profile modal if open
        if (document.getElementById('profileModal') &&
            !document.getElementById('profileModal').classList.contains('hidden')) {
            this.updateProfileModalButton(userId, status);
        }
    }
}

// Export singleton instance
const friendSystem = new FriendSystem();
export default friendSystem;

// Make the functions available globally for HTML onclick
window.FriendSystem = friendSystem;