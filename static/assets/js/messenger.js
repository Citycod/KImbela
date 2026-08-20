// messenger.js - COMPLETE FIXED VERSION WITH ALL ISSUES RESOLVED
(function() {
        // Private state
        let socket = null;
        let currentChatUserId = null;
        let currentChatUserName = null;
        let currentChatAvatar = null;
        let typingTimeout = null;
        let isTyping = false;
        let isInitialized = false;
        let uploadInProgress = false;
        let sentMessageIds = new Set(); // Track sent messages to prevent duplicates
        let messageLoader = null; // Small loader element
        const GIF_PROXY_URL = '/api/gifs';
        let gifCurrentOffset = 0;
        let gifSearchQuery = '';
        let gifIsLoading = false;
        let gifSearchTimeout = null;

        // ========================================
        // SOCKET.IO SETUP
        // ========================================
        function initSocket() {
            if (socket && socket.connected) return;

            if (typeof io === 'undefined') {
                console.error("Socket.IO failed to load from CDN. Messenger features will be disabled.");
                return;
            }

            socket = io({
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 1000
            });

            socket.on('connect', () => {
                if (window.currentUserId) {
                    socket.emit('user_connected', { user_id: window.currentUserId });
                }
                loadFriendsList();
                updateUnreadBadge();
            });

            socket.on('connect_error', (error) => {
                loadFriendsList();
                updateUnreadBadge();
            });

            socket.on('disconnect', (reason) => {
            });

            // Message events
            socket.on('new_message', handleNewMessage);
            socket.on('typing', handleTyping);
            socket.on('stop_typing', handleStopTyping);
            socket.on('user_online', handleUserOnline);
            socket.on('user_offline', handleUserOffline);
        }

        // ========================================
        // MESSAGE HANDLING - FIXED FOR DUPLICATES
        // ========================================
        function handleNewMessage(data) {
            const senderId = parseInt(data.sender_id);
            const receiverId = parseInt(data.receiver_id);
            const isMine = senderId === window.currentUserId;

            const isCurrentChat = currentChatUserId && (
                senderId === currentChatUserId || receiverId === currentChatUserId
            );

            // 1) If this is my message and it has temp_id, REPLACE the temp bubble
            if (isMine && data.temp_id) {
                const tempEl = document.querySelector(`[data-message-id="${data.temp_id}"]`);
                if (tempEl) {
                    // Update with real message ID
                    tempEl.setAttribute('data-message-id', data.id);

                    // Remove temp loader if present
                    const loader = tempEl.querySelector('.message-loader');
                    if (loader) loader.remove();

                    // Update status icon
                    const statusEl = tempEl.querySelector('.message-status');
                    if (statusEl) statusEl.innerHTML = `<i class="bi bi-check-all text-xs"></i>`;

                    // Add to sent messages set to prevent duplicates
                    sentMessageIds.add(data.id);
                    return; // Stop here so we don't append a duplicate
                }
            }

            // 2) Hard dedupe: if message already exists by real id, do nothing
            const existing = document.querySelector(`[data-message-id="${data.id}"]`);
            if (existing) {
                return;
            }

            // 3) Add to sent messages set
            sentMessageIds.add(data.id);

            if (isCurrentChat) {
                const type = isMine ? 'sent' : 'received';
                appendMessage(data, type);
                scrollToBottom();

                // Mark as read if it's received
                if (!isMine && data.status === 'sent') {
                    markMessageAsRead(data.id);
                    updateUnreadBadge();
                }
            } else {
                updateFriendsListUnreadCount(senderId);
                updateUnreadBadge();
            }
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
                            friendEl.className = `friend-item group flex items-center gap-3 p-3.5 rounded-2xl cursor-pointer border border-gray-100 bg-white/80 shadow-sm hover:shadow-md hover:border-blue-200 hover:bg-white transition-all ${friend.unread_count > 0 ? 'bg-blue-50 border-blue-100 shadow-md' : ''}`;
                            friendEl.dataset.userId = friend.id;

                            friendEl.innerHTML = `
                    <div class="relative flex-shrink-0">
                        <img src="${friend.avatar || window.defaultAvatar}"
                             class="w-12 h-12 rounded-full object-cover ring-2 ring-white shadow-md"
                             onerror="this.src='${window.defaultAvatar}'">
                        <span class="absolute bottom-0 right-0 w-3.5 h-3.5 ${friend.is_online ? 'bg-emerald-500' : 'bg-gray-400'} rounded-full border-2 border-white shadow-sm"></span>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="text-sm font-semibold text-gray-900 truncate group-hover:text-blue-700 transition-colors">${friend.name}</div>
                        <div class="text-xs text-gray-500 truncate">${friend.last_message || 'Start chatting!'}</div>
                    </div>
                    ${friend.unread_count > 0 ? `
                        <span class="bg-gradient-to-br from-rose-500 to-pink-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center shadow-sm">
                            ${friend.unread_count > 99 ? '99+' : friend.unread_count}
                        </span>
                    ` : ''}
                `;

                friendEl.onclick = () => openChat(friend.id, friend.name, friend.avatar);
                container.appendChild(friendEl);
            });

        } catch (error) {
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

            if (result.messages && result.messages.length) {
                // Clear sent messages set for this chat
                sentMessageIds.clear();

                result.messages.reverse();
                result.messages.forEach(msg => {
                    // Add to sent messages set
                    sentMessageIds.add(msg.id);

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

        } catch (error) {
            container.innerHTML = `
                <div class="text-center py-12 text-red-500">
                    Failed to load messages
                </div>
            `;
        }
    }

    // ========================================
    // APPEND MESSAGE - COMPLETELY FIXED VERSION
    // ========================================
    function appendMessage(msg, type) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        // Remove empty state if present
        const emptyState = container.querySelector('.text-center.py-12');
        if (emptyState) {
            emptyState.remove();
        }

        let content = msg.content || '';

        // Check if content contains a URL (image, video, file, or link)
        const urlRegex = /((?:https?:\/\/[^\s]+|\/uploads\/[^\s]+))/gi;

        const toAbsolute = (u) => {
            if (!u) return u;
            if (u.startsWith('/')) return window.location.origin + u;
            return u;
        };


        // Replace all URLs with proper media elements
        content = content.replace(urlRegex, (url) => {
            const lowerUrl = url.toLowerCase();
            const finalUrl = toAbsolute(url);


            // Extract clean filename (remove query parameters and get original filename)
            let filename = '';
            try {
                // Decode URL-encoded characters
                const decodedUrl = decodeURIComponent(url);
                // Get the filename part
                const pathParts = decodedUrl.split('/');
                filename = pathParts[pathParts.length - 1];
                // Remove query parameters if any
                filename = filename.split('?')[0];
            } catch (e) {
                filename = 'file';
            }

            const imageMatch = lowerUrl.match(/\.(jpg|jpeg|png|gif|webp|bmp)(?:\?|$)/);
            const videoMatch = lowerUrl.match(/\.(mp4|webm|mov|avi|ogg)(?:\?|$)/);
            const fileMatch = lowerUrl.match(/\.(pdf|doc|docx|txt|xls|xlsx|ppt|pptx)(?:\?|$)/);
            const isGiphy = lowerUrl.includes('giphy.com');
            const isGif = isGiphy || (imageMatch && lowerUrl.includes('.gif'));

            // GIF handling - NO BACKGROUND, SMALL PREVIEW
            if (isGif) {
                let gifUrl = finalUrl;
                if (isGiphy && !lowerUrl.endsWith('.gif')) {
                    const idMatch = lowerUrl.match(/giphy\.com\/gifs\/[^/]*-([a-z0-9]+)$/i) || lowerUrl.match(/giphy\.com\/gifs\/([a-z0-9]+)$/i);
                    if (idMatch && idMatch[1]) {
                        gifUrl = `https://media.giphy.com/media/${idMatch[1]}/giphy.gif`;
                    }
                }
                return `
                    <div class="message-media">
                        <img src="${gifUrl}" alt="GIF" loading="lazy"
                             class="rounded-lg cursor-pointer hover:shadow-lg transition-shadow"
                             style="max-width: 100px; max-height: 100px;"
                             onclick="window.open('${gifUrl}', '_blank')">
                    </div>`;
            }

            // Image handling - NO BACKGROUND, NO CAPTION
            if (imageMatch) {
                return `
                  <div class="message-media">
                    <img src="${finalUrl}" alt="${filename}" loading="lazy"
                      class="rounded-lg max-w-sm max-h-96 object-contain cursor-pointer hover:shadow-lg transition-shadow"
                      onclick="window.open('${finalUrl}', '_blank')">
                  </div>`;
            }

            // Video handling - NO BACKGROUND, NO CAPTION
            else if (videoMatch) {
                return `
                  <div class="message-media">
                    <video controls class="rounded-lg max-w-sm max-h-96">
                      <source src="${finalUrl}" type="video/mp4">
                      Your browser does not support video.
                    </video>
                  </div>`;
            }

            // File handling - NO BACKGROUND, SHOW ORIGINAL FILENAME
            else if (fileMatch) {
                return `
                  <div class="message-file">
                    <a href="${finalUrl}" target="_blank"
                      class="flex items-center text-blue-600 hover:underline p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors">
                      <i class="bi bi-file-earmark-text mr-2 text-lg"></i>
                      <span class="truncate max-w-xs font-medium">${filename}</span>
                    </a>
                  </div>`;
            }

            // Regular link (not media)
            return `<a href="${url}" target="_blank" class="text-blue-600 underline break-all">${url}</a>`;
        });

        // Extract attachments so sent media/files can sit outside the gradient bubble
        const attachmentRegex = /<div class="(?:message-media|message-file)[\s\S]*?<\/div>/g;
        const attachmentBlocks = content.match(attachmentRegex) || [];
        const attachmentsHtml = attachmentBlocks.join('');
        content = content.replace(attachmentRegex, '').trim();

        // Calculate time and date
        const msgTimestamp = msg.timestamp ? new Date(msg.timestamp) : new Date();
        const time = msgTimestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const date = msgTimestamp.toLocaleDateString();

        // Check if we need to add a date separator
        const lastMessage = container.lastElementChild;
        let addDateSeparator = false;

        if (lastMessage && lastMessage.dataset && lastMessage.dataset.date) {
            if (lastMessage.dataset.date !== date) {
                addDateSeparator = true;
            }
        } else if (!lastMessage) {
            addDateSeparator = true;
        }

        if (addDateSeparator) {
            const dateSeparator = document.createElement('div');
            dateSeparator.className = 'date-separator text-center my-4 text-gray-500 font-medium';
            dateSeparator.textContent = date;
            container.appendChild(dateSeparator);
        }

        const div = document.createElement('div');
        const wrapperClass = type === 'sent'
            ? 'message-wrapper sent flex flex-col items-end w-full'
            : 'message-wrapper received flex flex-col items-start w-full';
        const hasContent = !!content;
        const bubbleClass = type === 'sent'
            ? `message-bubble sent px-3 py-2 rounded-2xl rounded-br-md text-white shadow-md ${hasContent ? 'bg-gradient-to-br from-blue-600 via-sky-600 to-emerald-500' : 'bg-transparent shadow-none px-0 py-0 text-gray-700'}`
            : `message-bubble received px-3 py-2 rounded-2xl rounded-bl-md border border-gray-200 text-gray-900 shadow-sm ${hasContent ? 'bg-white' : 'bg-transparent border-none shadow-none px-0 py-0'}`;
        const attachmentsClass = type === 'sent'
            ? 'message-attachments sent mb-1 flex justify-end w-full'
            : 'message-attachments received mb-1 flex justify-start w-full';
        div.className = wrapperClass;
        const msgKey = msg.id || msg.temp_id || ('temp-' + Date.now());
        div.setAttribute('data-message-id', msgKey);
        div.dataset.date = date;

        // Build message bubble - FIXED FOR BOTH SENDER AND RECEIVER
        div.innerHTML = `
        ${attachmentsHtml ? `<div class="${attachmentsClass}">${attachmentsHtml}</div>` : ''}
        <div class="${bubbleClass}">
            ${content ? `<div class="message-content whitespace-pre-wrap">${content}</div>` : ''}
            <div class="message-footer flex justify-between items-center mt-1">
                <span class="message-time text-xs opacity-70">${time}</span>
                ${type === 'sent' ?
                    `<span class="message-status text-xs opacity-70">
                        ${msg.temp_id ?
                            '<div class="tiny-upload-loader inline-block ml-1"></div>' :
                            '<i class="bi bi-check-all"></i>'
                        }
                    </span>` :
                    ''
                }
            </div>
        </div>
    `;

        container.appendChild(div);
        scrollToBottom();
    }

    // ========================================
    // SEND MESSAGE - WITH SMALL UPLOAD LOADER
    // ========================================
    function sendMessageWithContent(content) {
        if (!currentChatUserId) return;
        const trimmed = (content || '').trim();
        if (!trimmed) return;

        const tempId = 'temp-' + Date.now();
        appendMessage({
            id: tempId,
            content: trimmed,
            sender_id: window.currentUserId,
            temp_id: tempId
        }, 'sent');

        if (socket) {
            socket.emit('send_message', {
                receiver_id: currentChatUserId,
                content: trimmed,
                temp_id: tempId
            });
        }
    }

    function sendMessage() {
        const input = document.getElementById('chatInput');
        if (!input || !currentChatUserId) return;

        const content = input.value.trim();
        if (!content) return;

        sendMessageWithContent(content);

        input.value = '';
        autoResizeTextarea(input);
        scrollToBottom();
    }

    // ========================================
    // FILE UPLOAD - WITH VISUAL LOADER
    // ========================================
    async function uploadFiles(files) {
    if (!currentChatUserId) {
        alert('No chat open');
        return;
    }

    if (uploadInProgress) {
        alert('Please wait for current upload to complete');
        return;
    }

    uploadInProgress = true;
    showUploadLoader();

    // Upload each file one by one
    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('to_id', currentChatUserId);

        let type = 'document';
        if (file.type.startsWith('image/')) type = 'image';
        else if (file.type.startsWith('video/')) type = 'video';
        else if (file.type.startsWith('audio/')) type = 'audio';
        formData.append('type', type);

        // Get the correct CSRF token
        let csrfToken = '';

        // Try multiple ways to get CSRF token
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            csrfToken = metaTag.getAttribute('content');
        } else if (window.csrfToken) {
            csrfToken = window.csrfToken;
        } else {
            // Try to get from cookie
            const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
            if (cookieMatch) csrfToken = cookieMatch[1];
        }

        try {
            const response = await fetch('/api/messaging/upload', {
                method: 'POST',
                body: formData,
                // DO NOT set Content-Type header - let browser set it for FormData
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-CSRF-Token': csrfToken
                },
                credentials: 'include' // Important for cookies
            });

            const contentType = response.headers.get("content-type");
            let result;

            if (contentType && contentType.includes("application/json")) {
                result = await response.json();
            } else {
                const text = await response.text();
                throw new Error(`Server returned non-JSON: ${text}`);
            }

            if (!response.ok) {
                throw new Error(result.error || `Upload failed with status: ${response.status}`);
            }

            if (result.success && socket) {
                const content = result.url;
                const tempId = 'temp-' + Date.now();

                appendMessage({
                    id: tempId,
                    content: content,
                    sender_id: window.currentUserId,
                    timestamp: new Date().toISOString(),
                    temp_id: tempId
                }, 'sent');

                socket.emit('send_message', {
                    receiver_id: currentChatUserId,
                    content: content,
                    temp_id: tempId
                });
            } else {
                throw new Error(result.error || 'Unknown error');
            }
        } catch (error) {
            alert(`Failed to upload ${file.name}: ${error.message}`);
        }
    }

    uploadInProgress = false;
    hideUploadLoader();
}

    // ========================================
    // TINY UPLOAD LOADER FUNCTIONS
    // ========================================
    function showUploadLoader() {
        // Create or show tiny loader in message input area
        const inputContainer = document.querySelector('.message-input-area');
        if (!inputContainer) return;

        // Remove existing loader
        hideUploadLoader();

        // Create tiny loader
        messageLoader = document.createElement('div');
        messageLoader.className = 'tiny-upload-loader active';
        messageLoader.innerHTML = `
            <div class="loader-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
            <span class="loader-text text-xs text-gray-500">Sending...</span>
        `;

        // Position loader near send button
        const sendBtn = document.getElementById('sendMessageBtn');
        if (sendBtn) {
            const inputContainer = sendBtn.closest('.input-container');
            if (inputContainer) {
                inputContainer.appendChild(messageLoader);
            }
        }
    }

    function hideUploadLoader() {
        if (messageLoader) {
            messageLoader.remove();
            messageLoader = null;
        }
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

    function handleUserOnline(data) {
        updateFriendOnlineStatus(data.user_id, true);
    }

    function handleUserOffline(data) {
        updateFriendOnlineStatus(data.user_id, false);
    }

    function markConversationAsRead(userId) {
        fetch(`/api/messaging/mark-conversation-read/${userId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.csrfToken || ''
            }
        }).catch(() => {})
          .finally(() => updateUnreadBadge());
    }

    function markMessageAsRead(messageId) {
        if (!messageId) return;

        fetch(`/api/messaging/mark-read/${messageId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.csrfToken || ''
            }
        }).catch(() => {});
    }

    function ensureNavbarBadge() {
        const openBtn = document.getElementById('openMessaging');
        if (!openBtn) return null;
        let badge = openBtn.querySelector('#unreadMessagesBadge');
        if (!badge) {
            badge = document.createElement('span');
            badge.id = 'unreadMessagesBadge';
            badge.className = 'notification-badge absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center hidden';
            badge.textContent = '0';
            openBtn.appendChild(badge);
        }
        return badge;
    }

    function updateUnreadBadge() {
        fetch('/api/messaging/unread-count')
            .then(response => response.json())
            .then(data => {
                const badge = ensureNavbarBadge();
                const openBtnBadge = badge;

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
            .catch(() => {});
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
                const badge = document.createElement('span');
                badge.className = 'bg-red-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center';
                badge.textContent = '1';
                friendItem.appendChild(badge);
                friendItem.classList.add('bg-blue-50');
            }
        }
    }

    // ========================================
    // EVENT LISTENERS SETUP
    // ========================================
    function setupEventListeners() {
        // Chat input events
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.addEventListener('input', function(e) {
                autoResizeTextarea(this);
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

        // File/Image attachment button
        const paperclipIcon = document.querySelector('.input-btn .bi-paperclip');
        const fileBtn = paperclipIcon ? paperclipIcon.closest('.input-btn') : null;
        if (fileBtn) {
            fileBtn.addEventListener('click', function() {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'image/*,.pdf,.doc,.docx,.txt,audio/*,video/*';
                input.multiple = true;
                input.onchange = function(e) {
                    if (e.target.files.length > 0) {
                        uploadFiles(e.target.files);
                    }
                };
                input.click();
            });
        }

        // GIF button
        const gifBtn = document.getElementById('gifPickerButton');
        if (gifBtn) {
            gifBtn.addEventListener('click', openGifPicker);
        }

        const gifSearchInput = document.getElementById('messengerGifSearchInput');
        if (gifSearchInput) {
            gifSearchInput.addEventListener('input', function(e) {
                clearTimeout(gifSearchTimeout);
                const query = e.target.value.trim();
                gifSearchTimeout = setTimeout(() => {
                    gifSearchQuery = query;
                    if (query === '') {
                        loadTrendingGifs(true);
                    } else {
                        searchGifs(query, true);
                    }
                }, 350);
            });
            gifSearchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const query = gifSearchInput.value.trim();
                    gifSearchTimeout && clearTimeout(gifSearchTimeout);
                    gifSearchQuery = query;
                    if (query === '') {
                        loadTrendingGifs(true);
                    } else {
                        searchGifs(query, true);
                    }
                }
            });
        }

        // Emoji button
        const emojiBtn = document.getElementById('emojiPickerButton');
        if (emojiBtn) {
            emojiBtn.addEventListener('click', function() {
                if (!window.emojiPickerInitialized) {
                    initEmojiPicker();
                }
                const picker = document.querySelector('emoji-picker');
                const container = document.getElementById('messengerEmojiPickerContainer');
                if (container) container.classList.remove('hidden');
                if (picker) {
                    const shouldShow = picker.style.display === 'none' || picker.style.display === '';
                    picker.style.display = shouldShow ? 'block' : 'none';
                }
            });
        }

        // Back to friends button
        const backBtn = document.querySelector('.back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', function() {
                document.getElementById('chatArea').classList.add('hidden');
                document.getElementById('friendList').classList.remove('hidden');
                currentChatUserId = null;
                loadFriendsList();
            });
        }

        // Close GIF modal
        const closeGifBtn = document.querySelector('#messengerGifModal .header-btn');
        if (closeGifBtn) {
            closeGifBtn.addEventListener('click', closeGifPicker);
        }

        const gifLoadMoreBtn = document.getElementById('messengerGifLoadMore');
        if (gifLoadMoreBtn) {
            gifLoadMoreBtn.addEventListener('click', handleGifLoadMore);
        }
    }

    // ========================================
    // EMOJI PICKER
    // ========================================
    function initEmojiPicker() {
        if (window.emojiPickerInitialized) return;

        const emojiContainer = document.getElementById('messengerEmojiPickerContainer');
        if (!emojiContainer) return;
        emojiContainer.classList.remove('hidden');

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

    // ========================================
    // GIF PICKER FUNCTIONS
    // ========================================
    function normalizeGifResults(data) {
        const rawGifs = (data && (data.gifs || data.data)) ? (data.gifs || data.data) : [];
        return rawGifs.map(gif => {
            const previewUrl = gif.preview_url || gif.images?.fixed_height_small?.url || gif.images?.fixed_width_small?.url || gif.url;
            const originalUrl = gif.url || gif.images?.original?.url || gif.images?.fixed_height?.url || previewUrl;
            return {
                title: gif.title || gif.slug || 'GIF',
                preview_url: previewUrl,
                url: originalUrl
            };
        }).filter(gif => gif.preview_url || gif.url);
    }

    function openGifPicker() {
        const modal = document.getElementById('messengerGifModal');
        if (!modal) return;

        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        gifCurrentOffset = 0;
        gifSearchQuery = '';
        const searchInput = document.getElementById('messengerGifSearchInput');
        if (searchInput) {
            searchInput.value = '';
            searchInput.focus();
        }

        loadTrendingGifs(true);
    }

    function closeGifPicker() {
        const modal = document.getElementById('messengerGifModal');
        if (!modal) return;

        modal.classList.add('hidden');
        document.body.style.overflow = '';
        gifCurrentOffset = 0;
        gifSearchQuery = '';
        gifIsLoading = false;
        const gifGrid = document.getElementById('messengerGifGrid');
        if (gifGrid) gifGrid.innerHTML = '';
        const loadMoreBtn = document.getElementById('messengerGifLoadMore');
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');
        if (gifSearchTimeout) {
            clearTimeout(gifSearchTimeout);
            gifSearchTimeout = null;
        }
    }

    async function loadTrendingGifs(reset = true) {
        if (gifIsLoading) return;
        gifIsLoading = true;
        if (reset) gifCurrentOffset = 0;
        showGifLoading(reset);

        try {
            const response = await fetch(`${GIF_PROXY_URL}?q=trending&limit=20&offset=${gifCurrentOffset}`);
            const data = await response.json();
            const gifs = normalizeGifResults(data);
            if (gifs.length > 0) {
                displayGifs(gifs, 'trending', reset);
            } else {
                showNoGifsMessage('No trending GIFs found');
            }
        } catch (error) {
            showNoGifsMessage('Failed to load GIFs. Please try again.');
        } finally {
            gifIsLoading = false;
        }
    }

    async function searchGifs(query, reset = true) {
        if (gifIsLoading) return;
        if (!query) {
            loadTrendingGifs(true);
            return;
        }

        gifIsLoading = true;
        gifSearchQuery = query;
        if (reset) gifCurrentOffset = 0;
        showGifLoading(reset);

        try {
            const response = await fetch(`${GIF_PROXY_URL}?q=${encodeURIComponent(query)}&limit=20&offset=${gifCurrentOffset}`);
            const data = await response.json();
            const gifs = normalizeGifResults(data);
            if (gifs.length > 0) {
                displayGifs(gifs, 'search', reset);
            } else if (reset) {
                showNoGifsMessage(`No GIFs found for "${query}"`);
            }
        } catch (error) {
            if (reset) showNoGifsMessage('Search failed. Please try again.');
        } finally {
            gifIsLoading = false;
        }
    }

    function handleGifLoadMore() {
        if (gifIsLoading) return;
        gifCurrentOffset += 20;
        if (gifSearchQuery) {
            searchGifs(gifSearchQuery, false);
        } else {
            loadTrendingGifs(false);
        }
    }

    function displayGifs(gifs, type, reset = true) {
        const gifGrid = document.getElementById('messengerGifGrid');
        const loadMoreBtn = document.getElementById('messengerGifLoadMore');
        const resultsTitle = document.getElementById('messengerGifResultsTitle');
        if (!gifGrid) return;

        if (reset) gifGrid.innerHTML = '';
        hideGifLoading();

        if (resultsTitle) {
            if (type === 'trending') {
                resultsTitle.textContent = 'Trending GIFs';
            } else {
                const searchInput = document.getElementById('messengerGifSearchInput');
                const query = searchInput?.value.trim();
                resultsTitle.textContent = query ? `Results for "${query}"` : 'Search Results';
            }
        }

        gifs.forEach(gif => {
            const gifElement = document.createElement('div');
            gifElement.className = 'gif-item group relative cursor-pointer rounded-lg overflow-hidden bg-gray-100';
            gifElement.innerHTML = `
                <div class="aspect-square w-full overflow-hidden">
                    <img
                        src="${gif.preview_url || gif.url}"
                        alt="${gif.title || 'GIF'}"
                        class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
                        data-original="${gif.url || gif.preview_url}"
                        data-title="${gif.title || ''}"
                        loading="lazy"
                    />
                    <div class="absolute inset-0 bg-black opacity-0 group-hover:opacity-10 transition-opacity duration-300"></div>
                </div>
                <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <p class="text-white text-xs truncate">${gif.title || 'GIF'}</p>
                </div>
            `;
            const img = gifElement.querySelector('img');
            const gifUrl = img ? img.dataset.original : gif.url;
            const title = img ? img.dataset.title : gif.title;
            gifElement.onclick = () => selectGif(gifUrl, title);
            gifGrid.appendChild(gifElement);
        });

        if (loadMoreBtn) {
            if (gifs.length >= 20) {
                loadMoreBtn.classList.remove('hidden');
            } else {
                loadMoreBtn.classList.add('hidden');
            }
        }
    }

    function showGifLoading(reset = true) {
        const gifGrid = document.getElementById('messengerGifGrid');
        if (!gifGrid) return;
        if (reset) {
            gifGrid.innerHTML = `
                <div class="gif-loading col-span-3 flex flex-col items-center justify-center gap-2 text-sm text-gray-500">
                    <div class="animate-spin rounded-full h-6 w-6 border-2 border-t-blue-600 border-gray-300"></div>
                    Loading GIFs…
                </div>
            `;
        }
        const loadMoreBtn = document.getElementById('messengerGifLoadMore');
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');
    }

    function hideGifLoading() {
        const gifGrid = document.getElementById('messengerGifGrid');
        if (!gifGrid) return;
        const loadingEl = gifGrid.querySelector('.gif-loading');
        if (loadingEl) loadingEl.remove();
    }

    function showNoGifsMessage(message) {
        const gifGrid = document.getElementById('messengerGifGrid');
        const loadMoreBtn = document.getElementById('messengerGifLoadMore');
        if (gifGrid) {
            gifGrid.innerHTML = `
                <div class="col-span-3 flex flex-col items-center justify-center gap-2 text-sm text-gray-500">
                    <i class="bi bi-emoji-frown text-xl"></i>
                    <p>${message}</p>
                </div>
            `;
        }
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');
    }

    function selectGif(url, title = '') {
        sendMessageWithContent(url);
        closeGifPicker();
    }

    // ========================================
    // PUBLIC API
    // ========================================
    window.Messenger = {
        // Initialization
        init: function() {
            if (isInitialized) return;


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
    // INITIALIZATION
    // ========================================
    document.addEventListener('DOMContentLoaded', function() {
        if (document.getElementById('messengerPopup')) {
            setTimeout(() => {
                if (typeof window.Messenger !== 'undefined' && window.Messenger.init) {
                    window.Messenger.init();
                }
            }, 1000);
        }
    });

    // ========================================
    // GLOBAL HELPERS FOR TEMPLATE HOOKS
    // ========================================
    window.openMessenger = function(userId) {
        const popup = document.getElementById('messengerPopup');
        if (!popup) return;
        popup.classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        if (!isInitialized && typeof window.Messenger !== 'undefined' && window.Messenger.init) {
            window.Messenger.init();
        }

        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');
        if (friendList) friendList.classList.remove('hidden');
        if (chatArea) chatArea.classList.add('hidden');

        if (userId) {
            const item = document.querySelector(`.friend-item[data-user-id="${userId}"]`);
            const name = item?.querySelector('.font-semibold')?.textContent?.trim() || '';
            const avatar = item?.querySelector('img')?.getAttribute('src') || window.defaultAvatar;
            openChat(parseInt(userId), name, avatar);
        }
    };

    window.closeMessenger = function() {
        const popup = document.getElementById('messengerPopup');
        if (!popup) return;
        popup.classList.add('hidden');
        document.body.style.overflow = '';
    };

    window.backToFriends = function() {
        const friendList = document.getElementById('friendList');
        const chatArea = document.getElementById('chatArea');
        if (friendList) friendList.classList.remove('hidden');
        if (chatArea) chatArea.classList.add('hidden');
        currentChatUserId = null;
        loadFriendsList();
    };

    window.closeGifPicker = function() { closeGifPicker(); };
    window.openGifPicker = function() { openGifPicker(); };
})();
