// ========================================
// APPLICATION CONFIGURATION
// ========================================

export class AppConfig {
    constructor() {
        // Get config from global object or use defaults
        this.config = window.APP_CONFIG || {};
        this.csrfToken = window.csrfToken || '';
        this.currentUserId = parseInt(window.currentUserId) || null;
        this.defaultAvatar = window.defaultAvatar || '/static/assets/img/default-avatar.png';
        this.blockedUserIds = window.blockedUserIds || [];
        this.hasMorePosts = window.hasMorePosts || false;
        this.nextCursor = window.nextCursor || null;
    }

    get(key, defaultValue = null) {
        return this.config[key] !== undefined ? this.config[key] : defaultValue;
    }

    set(key, value) {
        this.config[key] = value;
    }

    getCsrfToken() {
        return this.csrfToken;
    }

    getCurrentUserId() {
        return this.currentUserId;
    }

    getDefaultAvatar() {
        return this.defaultAvatar;
    }

    isUserBlocked(userId) {
        return this.blockedUserIds.includes(parseInt(userId));
    }

    getPaginationInfo() {
        return {
            hasMorePosts: this.hasMorePosts,
            nextCursor: this.nextCursor
        };
    }
}

// Export singleton instance
export const config = new AppConfig();