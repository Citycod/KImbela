// ========================================
// MESSENGER SYSTEM - MAIN MODULE
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';
import Loader from '../../core/loader.js';

class Messenger {
    constructor() {
        this.csrfToken = config.getCsrfToken();
        this.currentUserId = config.getCurrentUserId();
        this.defaultAvatar = config.getDefaultAvatar();

        this.state = {
            socket: null,
            activeFriendId: null,
            isTyping: false,
            typingTimeout: null,
            unreadCounts: {},
            currentFriend: null,
            isConnected: false
        };
    }

    async init() {
        console.log('🔧 Initializing Messenger...');

        this.connectSocket();
        this.setupEventListeners();
        await this.updateUnreadBadge();

        return this;
    }

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

            chatInput.addEventListener('blur', () => {
                this.stopTyping();
            });
        }
    }

    async open() {
        const popup = document.getElementById('messengerPopup');
        if (!popup) {
            console.error('Messenger popup not found');
            return;
        }

        // Close any open profile modal
        const profileModal = document.getElementById('profileModal');
        if (profileModal && !profileModal.classList.contains('hidden')) {
            profileModal.classList.add('hidden');
            document.body.style.overflow = '';
        }

        popup.classList.remove('hidden');
        await this.loadFriends();

        if (!this.state.socket || !this.state.socket.connected) {
            this.connectSocket();
        }
    }

    close() {
        const popup = document.getElementById('messengerPopup');
        if (popup) {
            popup.classList.add('hidden');
            this.backToFriends();
            this.stopTyping();
        }
    }

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
    }

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
    }

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
                    <img src="${friend.avatar || this.defaultAvatar}"
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
    }

    async openChat(friendId, friendName, friendAvatar, friendOnline) {
        // Close any open profile modal
        const profileModal = document.getElementById('profileModal');
        if (profileModal && !profileModal.classList.contains('hidden')) {
            profileModal.classList.add('hidden');
            document.body.style.overflow = '';
        }

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

        // Load messages
        await this.loadMessages(friendId);

        // Scroll to bottom after messages are loaded
        setTimeout(() => {
            this.scrollToBottom(true);
        }, 100);

        // Focus input
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.focus();
        }

        // Mark messages as read
        await this.markAsRead(friendId);
    }

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
    }

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
    }

    appendMessage(msg, shouldScroll = true) {
        const chatContainer = document.getElementById('chatMessages');
        if (!chatContainer) return;

        const isOwnMessage = msg.sender_id === this.currentUserId;
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
                            <img src="${msg.sender_avatar || this.defaultAvatar}"
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
    }

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
    }

    async sendMessageViaAPI(content) {
        try {
            const response = await fetch('/api/messaging/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
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
    }

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

    showTypingIndicator(userName) {
        const indicator = document.getElementById('typingIndicator');
        const userNameEl = document.getElementById('typingUserName');

        if (userNameEl) {
            userNameEl.textContent = `${userName} is typing...`;
        }
        if (indicator) {
            indicator.classList.remove('hidden');
        }
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }
    }

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
            this.state.isConnected = true;
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
    }

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
    }

    async markAsRead(friendId) {
        try {
            await fetch(`/api/messaging/mark-read/${friendId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });
            this.updateUnreadBadge();
        } catch (error) {
            console.error('Error marking as read:', error);
        }
    }

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
    }

    scrollToBottom() {
        const messagesWrapper = document.getElementById('chatMessagesWrapper');
        if (messagesWrapper) {
            setTimeout(() => {
                messagesWrapper.scrollTop = messagesWrapper.scrollHeight;
            }, 50);
        }
    }

    startChat(userId) {
        const profileModal = document.getElementById('profileModal');
        if (profileModal && !profileModal.classList.contains('hidden')) {
            profileModal.classList.add('hidden');
            document.body.style.overflow = '';
        }

        this.open();

        setTimeout(async () => {
            try {
                const response = await fetch(`/api/user_info/${userId}`);
                if (response.ok) {
                    const userData = await response.json();

                    this.openChat(
                        userId,
                        `${userData.first_name} ${userData.last_name}`,
                        userData.profile_pic || this.defaultAvatar,
                        userData.online || false
                    );
                } else {
                    this.openChat(userId, 'User', this.defaultAvatar, false);
                }
            } catch (error) {
                console.error('Error fetching user info:', error);
                const friendElements = document.querySelectorAll('.friend-item');
                friendElements.forEach(el => {
                    if (el.onclick && el.onclick.toString().includes(`openChat(${userId}`)) {
                        el.click();
                    }
                });
            }
        }, 300);
    }
}

// Export singleton instance
const messenger = new Messenger();
export default messenger;

// Make available globally
window.Messenger = messenger;