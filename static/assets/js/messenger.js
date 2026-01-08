// messenger.js - FIXED VERSION
(function() {
    // Private state
    let socket = null;
    let currentChatUserId = null;
    let currentChatUserName = null;
    let currentChatAvatar = null;
    let typingTimeout = null;
    let isTyping = false;
    let isInitialized = false;

    // ========================================
    // SOCKET.IO SETUP (Simple Version)
    // ========================================
    function initSocket() {
        if (socket?.connected) return;

        console.log('Initializing Socket.IO...');

        socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000
        });

        socket.on('connect', () => {
            console.log('✅ Socket.IO connected');
            if (window.currentUserId) {
                socket.emit('user_connected', { user_id: window.currentUserId });
            }
            loadFriendsList();
            updateUnreadBadge();
        });

        socket.on('connect_error', (error) => {
            console.error('❌ Socket connection error:', error);

            loadFriendsList();
            updateUnreadBadge();
        });

        socket.on('disconnect', (reason) => {
            console.log('⚠️ Socket disconnected:', reason);
        });

        // Message events
        socket.on('new_message', handleNewMessage);
        socket.on('typing', handleTyping);
        socket.on('stop_typing', handleStopTyping);
        socket.on('user_online', handleUserOnline);
        socket.on('user_offline', handleUserOffline);
    }

    // ========================================
    // MESSAGE HANDLING
    // ========================================
    // messenger.js - Fix field names throughout

    function handleNewMessage(data) {
      console.log('New message received:', data);

      updateUnreadBadge();

      const senderId = parseInt(data.sender_id);
      const receiverId = parseInt(data.receiver_id);
      const isMine = senderId === window.currentUserId;

      const isCurrentChat = currentChatUserId && (
        senderId === currentChatUserId || receiverId === currentChatUserId
      );

      // ✅ 1) If this is my message and it has temp_id, REPLACE the temp bubble
      if (isMine && data.temp_id) {
        const tempEl = document.querySelector(`[data-message-id="${data.temp_id}"]`);
        if (tempEl) {
          tempEl.setAttribute('data-message-id', data.id);

          // update status icon (optional)
          const statusEl = tempEl.querySelector('.message-status');
          if (statusEl) statusEl.innerHTML = `<i class="bi bi-check-all"></i>`;

          return; // ✅ stop here so we don’t append a duplicate
        }
      }

      // ✅ 2) Hard dedupe: if message already exists by real id, do nothing
      const existing = document.querySelector(`[data-message-id="${data.id}"]`);
      if (existing) return;

      if (isCurrentChat) {
        const type = isMine ? 'sent' : 'received';
        appendMessage(data, type);
        scrollToBottom();

        // mark as read if it's received
        if (!isMine && data.status === 'sent') {
          markMessageAsRead(data.id);
        }
      } else {
        updateFriendsListUnreadCount(senderId);
      }
    }



    function loadChatHistory(userId) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        try {
            container.innerHTML = '<div class="text-center py-12 text-gray-400">Loading messages...</div>';

            fetch(`/api/messaging/messages/${userId}?limit=50`)
                .then(response => response.json())
                .then(result => {
                    container.innerHTML = '';

                    if (result.success && result.messages?.length) {
                        result.messages.forEach(msg => {
                            const type = parseInt(msg.sender_id) === window.currentUserId ? 'sent' : 'received';
                            appendMessage(msg, type);
                        });

                        // Mark all as read since we're viewing them
                        markConversationAsRead(userId);
                    } else {
                        container.innerHTML = `
                            <div class="text-center py-12 text-gray-400">
                                <i class="bi bi-chat-left-dots text-4xl mb-4"></i>
                                <p>No messages yet</p>
                                <p class="text-sm">Say hello to start the conversation!</p>
                            </div>
                        `;
                    }

                    scrollToBottom();
                })
                .catch(error => {
                    console.error('Error loading chat history:', error);
                    container.innerHTML = `
                        <div class="text-center py-12 text-red-500">
                            Failed to load messages
                        </div>
                    `;
                });

        } catch (error) {
            console.error('Error loading chat history:', error);
            container.innerHTML = `
                <div class="text-center py-12 text-red-500">
                    Failed to load messages
                </div>
            `;
        }
    }

    // Add this function to mark entire conversation as read
    function markConversationAsRead(userId) {
        fetch(`/api/messaging/mark-conversation-read/${userId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.csrfToken || ''
            }
        }).catch(error => console.error('Error marking conversation as read:', error));
    }

    function handleTyping(data) {
        if (currentChatUserId && parseInt(data.user_id) === currentChatUserId) {
            showTypingIndicator(data.user_name || 'Someone');
        }
    }

    function handleStopTyping(data) {
        if (currentChatUserId && parseInt(data.user_id) === currentChatUserId) {
            hideTypingIndicator();
        }
    }

    function handleUserOnline(data) {
        updateFriendOnlineStatus(data.user_id, true);
    }

    function handleUserOffline(data) {
        updateFriendOnlineStatus(data.user_id, false);
    }

    // ========================================
    // FRIENDS LIST
    // ========================================
    async function loadFriendsList() {
        const container = document.getElementById('friendsContainer');
        if (!container) return;

        try {
            container.innerHTML = `
                <div class="text-center py-12">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-3"></div>
                    <p class="text-gray-600 text-sm">Loading conversations...</p>
                </div>
            `;

            const response = await fetch('/api/messaging/friends');
            const result = await response.json();

            if (!result.success || result.friends.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-12 text-gray-500">
                        <i class="bi bi-chat-dots text-4xl mb-4"></i>
                        <p>No conversations yet</p>
                        <p class="text-sm mt-2">Connect with friends to start chatting!</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = '';
            result.friends.forEach(friend => {
                const friendEl = document.createElement('div');
                friendEl.className = `friend-item flex items-center space-x-3 p-4 rounded-xl cursor-pointer hover:bg-gray-100 transition-all ${friend.unread_count > 0 ? 'bg-blue-50' : ''}`;
                friendEl.dataset.userId = friend.id;

                friendEl.innerHTML = `
                    <div class="relative flex-shrink-0">
                        <img src="${friend.avatar || window.defaultAvatar}"
                             class="w-12 h-12 rounded-full object-cover border-2 border-white shadow-sm"
                             onerror="this.src='${window.defaultAvatar}'">
                        <span class="absolute bottom-0 right-0 w-3.5 h-3.5 ${friend.is_online ? 'bg-green-500' : 'bg-gray-400'} rounded-full border-2 border-white"></span>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="font-semibold text-gray-900 truncate">${friend.name}</div>
                        <div class="text-xs text-gray-500 truncate">${friend.last_message || 'Start chatting!'}</div>
                    </div>
                    ${friend.unread_count > 0 ? `
                        <span class="bg-red-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center">
                            ${friend.unread_count > 99 ? '99+' : friend.unread_count}
                        </span>
                    ` : ''}
                `;

                friendEl.onclick = () => openChat(friend.id, friend.name, friend.avatar);
                container.appendChild(friendEl);
            });

        } catch (error) {
            console.error('Error loading friends:', error);
            container.innerHTML = `
                <div class="text-center py-12 text-red-500">
                    <i class="bi bi-exclamation-triangle text-2xl mb-2"></i>
                    <p>Failed to load conversations</p>
                </div>
            `;
        }
    }

    // ========================================
    // CHAT FUNCTIONS
    // ========================================
    function openChat(userId, userName, avatar) {
        currentChatUserId = userId;
        currentChatUserName = userName;
        currentChatAvatar = avatar;

        document.getElementById('friendList').classList.add('hidden');
        document.getElementById('chatArea').classList.remove('hidden');

        document.getElementById('chatName').textContent = userName;
        document.getElementById('chatAvatar').src = avatar || window.defaultAvatar;

        loadChatHistory(userId);

        // Focus input
        setTimeout(() => {
            const input = document.getElementById('chatInput');
            if (input) input.focus();
        }, 100);
    }

    async function loadChatHistory(userId) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        try {
            container.innerHTML = '<div class="text-center py-12 text-gray-400">Loading messages...</div>';

            const response = await fetch(`/api/messaging/messages/${userId}?limit=50`);
            const result = await response.json();

            container.innerHTML = '';

            if (result.messages?.length) {
                result.messages.reverse();
                result.messages.forEach(msg => {
                    const type = parseInt(msg.sender_id) === window.currentUserId ? 'sent' : 'received';
                    appendMessage(msg, type);
                });
            } else {
                container.innerHTML = `
                    <div class="text-center py-12 text-gray-400">
                        <i class="bi bi-chat-left-dots text-4xl mb-4"></i>
                        <p>No messages yet</p>
                        <p class="text-sm">Say hello to start the conversation!</p>
                    </div>
                `;
            }

            scrollToBottom();

        } catch (error) {
            console.error('Error loading chat history:', error);
            container.innerHTML = `
                <div class="text-center py-12 text-red-500">
                    Failed to load messages
                </div>
            `;
        }
    }

    function appendMessage(msg, type) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        // Remove empty state if present
        const emptyState = container.querySelector('.text-center.py-12');
        if (emptyState) {
            emptyState.remove();
        }

        const div = document.createElement('div');
        div.className = `message-wrapper ${type}`;
        const msgKey = msg.id || msg.temp_id || ('temp-' + Date.now());
        div.setAttribute('data-message-id', msgKey);


        let content = msg.content || '';

        // Parse GIFs
        content = content.replace(/\[GIF:(.*?)\](https?:\/\/[^\s]+)/g,
            (match, title, url) => `
            <div class="message-gif mt-2">
                <img src="${url}" alt="${title}" class="rounded-lg max-w-xs">
                ${title ? `<div class="text-xs text-gray-500 mt-1">${title}</div>` : ''}
            </div>`);

        const time = new Date(msg.timestamp || Date.now()).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });

        const date = new Date(msg.timestamp || Date.now()).toLocaleDateString();

        // Check if we need to add a date separator
        const lastMessage = container.lastElementChild;
        let addDateSeparator = false;

        if (lastMessage) {
            const lastDate = lastMessage.dataset.date;
            if (lastDate !== date) {
                addDateSeparator = true;
            }
        } else {
            addDateSeparator = true;
        }

        if (addDateSeparator) {
            const dateSeparator = document.createElement('div');
            dateSeparator.className = 'date-separator text-center my-4';
            dateSeparator.textContent = date;
            container.appendChild(dateSeparator);
        }

        div.dataset.date = date;
        div.innerHTML = `
            <div class="message-bubble ${type}">
                <div class="message-content whitespace-pre-wrap">${content}</div>
                <div class="message-footer flex justify-between items-center mt-1">
                    <span class="message-time text-xs opacity-70">${time}</span>
                    ${type === 'sent' ?
                        '<span class="message-status text-xs opacity-70"><i class="bi bi-check-all"></i></span>' :
                        ''}
                </div>
            </div>
        `;

        container.appendChild(div);
        scrollToBottom();
    }

    function sendMessage() {
        const input = document.getElementById('chatInput');
        if (!input || !currentChatUserId) return;

        const content = input.value.trim();
        if (!content) return;

        const tempId = 'temp-' + Date.now();
        appendMessage({
            id: tempId,
            content,
            sender_id: window.currentUserId
        }, 'sent');

        if (socket) {
            socket.emit('send_message', {
                receiver_id: currentChatUserId,
                content: content,
                temp_id: tempId
            });
        }

        input.value = '';
        autoResizeTextarea(input);
        scrollToBottom();
    }

    // ========================================
    // TYPING INDICATORS
    // ========================================
    function handleTypingEvent() {
        if (!currentChatUserId || !socket) return;

        if (!isTyping) {
            socket.emit('typing', { receiver_id: currentChatUserId });
            isTyping = true;
        }

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('stop_typing', { receiver_id: currentChatUserId });
            isTyping = false;
        }, 1000);
    }

    function showTypingIndicator(name) {
        const el = document.getElementById('typingIndicator');
        if (el) {
            el.classList.remove('hidden');
            document.getElementById('typingUserName').textContent = `${name} is typing...`;
        }
    }

    function hideTypingIndicator() {
        const el = document.getElementById('typingIndicator');
        if (el) el.classList.add('hidden');
    }

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================
    function scrollToBottom() {
        const wrapper = document.getElementById('chatMessagesWrapper');
        if (wrapper) {
            wrapper.scrollTop = wrapper.scrollHeight;
        }
    }

    function autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        const newHeight = Math.min(textarea.scrollHeight, 120);
        textarea.style.height = newHeight + 'px';
    }

    function updateFriendOnlineStatus(userId, isOnline) {
        const friendItems = document.querySelectorAll('.friend-item');
        friendItems.forEach(item => {
            if (parseInt(item.dataset.userId) === userId) {
                const dot = item.querySelector('.absolute.bottom-0.right-0');
                if (dot) {
                    dot.className = `absolute bottom-0 right-0 w-3.5 h-3.5 ${isOnline ? 'bg-green-500' : 'bg-gray-400'} rounded-full border-2 border-white`;
                }
            }
        });

        // Update chat status if open
        if (currentChatUserId === userId) {
            const statusEl = document.getElementById('chatStatus');
            const indicator = document.getElementById('chatStatusIndicator');
            if (statusEl && indicator) {
                statusEl.textContent = isOnline ? 'Online' : 'Offline';
                indicator.className = `status-indicator ${isOnline ? 'online' : 'offline'}`;
            }
        }
    }

    // ========================================
    // GIF PICKER
    // ========================================
    function openGifPicker() {
        const modal = document.getElementById('gifModal');
        if (modal) {
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    }

    function closeGifPicker() {
        const modal = document.getElementById('gifModal');
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = '';
        }
    }

    function selectGif(url, title = '') {
        const input = document.getElementById('chatInput');
        if (input) {
            input.value += ` [GIF:${title}]${url} `;
            input.focus();
            input.dispatchEvent(new Event('input'));
        }
        closeGifPicker();
    }

    function updateUnreadBadge() {
        fetch('/api/messaging/unread-count')
            .then(response => response.json())
            .then(data => {
                const badge = document.getElementById('unreadMessagesBadge');
                const openBtnBadge = document.getElementById('openMessaging').querySelector('.notification-badge');

                if (data.unread_count > 0) {
                    if (badge) {
                        badge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                        badge.classList.remove('hidden');
                    }
                    if (openBtnBadge) {
                        openBtnBadge.textContent = data.unread_count > 99 ? '99+' : data.unread_count;
                        openBtnBadge.classList.remove('hidden');
                    }
                } else {
                    if (badge) badge.classList.add('hidden');
                    if (openBtnBadge) openBtnBadge.classList.add('hidden');
                }
            })
            .catch(error => console.error('Error updating unread count:', error));
    }


    function updateFriendsListUnreadCount(fromUserId) {
        const friendItem = document.querySelector(`.friend-item[data-user-id="${fromUserId}"]`);
        if (friendItem) {
            const unreadBadge = friendItem.querySelector('.bg-red-500');
            if (unreadBadge) {
                const currentCount = parseInt(unreadBadge.textContent) || 0;
                unreadBadge.textContent = currentCount + 1 > 99 ? '99+' : currentCount + 1;
                friendItem.classList.add('bg-blue-50');
            } else {
                // Create unread badge if it doesn't exist
                const badge = document.createElement('span');
                badge.className = 'bg-red-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center';
                badge.textContent = '1';
                friendItem.appendChild(badge);
                friendItem.classList.add('bg-blue-50');
            }
        }
    }

    // ========================================
    // PUBLIC API
    // ========================================
    window.Messenger = {
        // Initialization
        init: function() {
            if (isInitialized) return;

            console.log('🚀 Initializing Messenger...');

            loadFriendsList();
            updateUnreadBadge();

            initSocket();
            setupEventListeners();
            isInitialized = true;
        },

        // Public methods
        openChat: openChat,
        sendMessage: sendMessage,
        loadFriendsList: loadFriendsList,
        openGifPicker: openGifPicker,
        closeGifPicker: closeGifPicker,
        selectGif: selectGif
    };

    // ========================================
    // EVENT LISTENERS SETUP
    // ========================================
    function setupEventListeners() {
        // Chat input events
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.addEventListener('input', function(e) {
                window.autoResizeTextarea(this);
                handleTypingEvent();
            });

            chatInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }

        // Send button
        const sendBtn = document.getElementById('sendMessageBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', sendMessage);
        }

        // GIF button
        const gifBtn = document.getElementById('gifPickerButton');
        if (gifBtn) {
            gifBtn.addEventListener('click', openGifPicker);
        }

        // Emoji button
        const emojiBtn = document.getElementById('emojiPickerButton');
        if (emojiBtn) {
            emojiBtn.addEventListener('click', function() {
                // Initialize emoji picker
                if (!window.emojiPickerInitialized) {
                    initEmojiPicker();
                }

                const picker = document.querySelector('emoji-picker');
                if (picker) {
                    picker.style.display = picker.style.display === 'none' ? 'block' : 'none';
                }
            });
        }

        // File/Image attachment button
        const fileBtn = document.querySelector('.input-btn .bi-paperclip')?.closest('.input-btn');
        if (fileBtn) {
            fileBtn.addEventListener('click', function() {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'image/*,.pdf,.doc,.docx,.txt';
                input.multiple = true;
                input.onchange = function(e) {
                    if (e.target.files.length > 0) {
                        uploadFiles(e.target.files);
                    }
                };
                input.click();
            });
        }

        // Close GIF modal
        const closeGifBtn = document.querySelector('#gifModal .header-btn');
        if (closeGifBtn) {
            closeGifBtn.addEventListener('click', closeGifPicker);
        }

        // Back to friends button
        const backBtn = document.querySelector('.back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', function() {
                document.getElementById('chatArea').classList.add('hidden');
                document.getElementById('friendList').classList.remove('hidden');
                currentChatUserId = null;

                // Refresh friends list to update unread counts
                loadFriendsList();
            });
        }
    }


    function initEmojiPicker() {
        if (window.emojiPickerInitialized) return;

        const emojiContainer = document.getElementById('emojiPicker');
        if (!emojiContainer) return;

        const picker = document.createElement('emoji-picker');
        picker.style.position = 'absolute';
        picker.style.bottom = '60px';
        picker.style.right = '20px';
        picker.style.zIndex = '1000';
        picker.style.display = 'none';

        picker.addEventListener('emoji-click', event => {
            const input = document.getElementById('chatInput');
            if (input) {
                const emoji = event.detail.unicode;
                const start = input.selectionStart;
                const end = input.selectionEnd;
                const value = input.value;

                input.value = value.substring(0, start) + emoji + value.substring(end);
                input.selectionStart = input.selectionEnd = start + emoji.length;
                input.focus();
                input.dispatchEvent(new Event('input'));
            }
            picker.style.display = 'none';
        });

        emojiContainer.appendChild(picker);
        window.emojiPickerInitialized = true;
    }

    async function uploadFiles(files) {
        const formData = new FormData();

        for (let file of files) {
            formData.append('files[]', file);
        }
        formData.append('receiver_id', currentChatUserId);

        try {
            const response = await fetch('/api/messaging/upload', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': window.csrfToken || ''
                }
            });

            const result = await response.json();

            if (result.success && socket) {
                result.files.forEach(file => {
                    socket.emit('send_message', {
                        receiver_id: currentChatUserId,
                        content: `[FILE:${file.name}]${file.url}`,
                        file_type: file.type
                    });
                });
            }
        } catch (error) {
            console.error('Error uploading files:', error);
            alert('Failed to upload files');
        }
    }

    function markMessageAsRead(messageId) {
        if (!messageId) return;

        fetch(`/api/messaging/mark-read/${messageId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.csrfToken || ''
            }
        }).catch(error => console.error('Error marking message as read:', error));
    }

    // ========================================
    // INITIALIZATION
    // ========================================
    document.addEventListener('DOMContentLoaded', function() {
        if (document.getElementById('messengerPopup')) {
            setTimeout(() => {
                if (typeof window.Messenger !== 'undefined' && window.Messenger.init) {
                    window.Messenger.init();
                    console.log('✅ Messenger initialized');
                }
            }, 1000);
        }
    });
})();