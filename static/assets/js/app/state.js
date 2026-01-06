// ========================================
// APPLICATION STATE MANAGEMENT
// ========================================

import { config } from './config.js';

export class AppState {
    constructor() {
        this.activeFriendId = null;
        this.typingTimer = null;
        this.activeAds = [];
        this.adShownThisHour = false;
        this.userAdPreferences = JSON.parse(localStorage.getItem('adPreferences') || '{}');
        this.notificationCheckInterval = null;
        this.searchTimeout = null;
        this.isLoadingPosts = false;

        // Initialize from config
        const pagination = config.getPaginationInfo();
        this.hasMorePosts = pagination.hasMorePosts;
        this.nextCursor = pagination.nextCursor;

        // Messenger state
        this.messenger = {
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

        // Cache for various systems
        this.cache = {
            groups: {
                data: null,
                lastFetch: null,
                expiry: 30000 // 30 seconds
            },
            profile: {},
            friends: {}
        };
    }

    // Messenger state methods
    setMessengerState(key, value) {
        this.messenger[key] = value;
    }

    getMessengerState(key) {
        return this.messenger[key];
    }

    // Cache management
    setCache(namespace, key, value) {
        if (!this.cache[namespace]) {
            this.cache[namespace] = {};
        }
        this.cache[namespace][key] = value;
    }

    getCache(namespace, key) {
        return this.cache[namespace]?.[key];
    }

    clearCache(namespace = null) {
        if (namespace && this.cache[namespace]) {
            this.cache[namespace] = {};
        } else if (!namespace) {
            this.cache = {
                groups: { data: null, lastFetch: null },
                profile: {},
                friends: {}
            };
        }
    }

    // Ad preferences
    updateAdPreference(adType, value) {
        this.userAdPreferences[adType] = value;
        localStorage.setItem('adPreferences', JSON.stringify(this.userAdPreferences));
    }

    getAdPreference(adType, defaultValue = true) {
        return this.userAdPreferences[adType] !== undefined
            ? this.userAdPreferences[adType]
            : defaultValue;
    }

    // Pagination state
    updatePagination(hasMorePosts, nextCursor) {
        this.hasMorePosts = hasMorePosts;
        this.nextCursor = nextCursor;
        this.isLoadingPosts = false;
    }

    setLoadingPosts(isLoading) {
        this.isLoadingPosts = isLoading;
    }

    canLoadMorePosts() {
        return !this.isLoadingPosts && this.hasMorePosts && this.nextCursor;
    }

    // Cleanup
    cleanup() {
        if (this.typingTimer) clearTimeout(this.typingTimer);
        if (this.notificationCheckInterval) clearInterval(this.notificationCheckInterval);
        if (this.searchTimeout) clearTimeout(this.searchTimeout);

        if (this.messenger.typingTimeout) {
            clearTimeout(this.messenger.typingTimeout);
        }

        if (this.messenger.recordingInterval) {
            clearInterval(this.messenger.recordingInterval);
        }
    }
}

// Export singleton instance
export const appState = new AppState();