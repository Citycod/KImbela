// ========================================
// MAIN APPLICATION INITIALIZER
// ========================================

import { AppConfig } from './config.js';
import { AppState } from './state.js';
import Loader from '../core/loader.js';
import Toast from '../core/toast.js';
import TimeUtils from '../core/time-utils.js';
import Modal from '../core/modal.js';
import Dropdown from '../core/dropdown.js';
import PostSystem from '../modules/posts/index.js';
import FriendSystem from '../modules/friends/index.js';
//import ProfileSystem from '../modules/profile/index.js';
import Messenger from '../modules/messenger/index.js';
import NotificationSystem from '../modules/notifications/index.js';
import SearchSystem from '../modules/search/index.js';
import AdSystem from '../modules/ads/index.js';
import Groups from '../modules/groups/index.js';
import InfiniteScroll from '../ui/infinite-scroll.js';
import MobileMenu from '../ui/mobile-menu.js';
import { initFileUpload } from '../ui/file-upload.js';

class DashboardApp {
    constructor() {
        this.config = new AppConfig();
        this.state = new AppState();
        this.modules = {};
        this.isInitialized = false;
    }

    async init() {
        if (this.isInitialized) {
            return;
        }


        try {
            // Initialize core utilities first
            this.initCoreUtilities();

            // Initialize UI components
            this.initUIComponents();

            // Initialize feature modules
            await this.initFeatureModules();

            // Set up global event listeners
            this.setupGlobalListeners();

            // Initialize legacy global functions
            this.initLegacyGlobals();

            this.isInitialized = true;

        } catch (error) {
            Toast.show('Application initialization failed', 'danger');
        }
    }

    initCoreUtilities() {
        // These are static utilities, no need to store instances

        // Initialize time ago displays
        TimeUtils.initializeTimeAgo();
        setInterval(() => TimeUtils.initializeTimeAgo(), 60000);

        // Initialize dropdown system
        Dropdown.init();

        // Initialize modal system
        // Modal system is already static
    }

    initUIComponents() {

        // Initialize mobile menu
        MobileMenu.init();

        // Initialize infinite scroll
        if (document.getElementById('load-more-btn') ||
            document.getElementById('loading-spinner')) {
            InfiniteScroll.init();
        }

        // Initialize file upload
        initFileUpload();

        // Hide loader with animation
        setTimeout(() => {
            const loader = document.getElementById('loader');
            if (loader) {
                loader.style.opacity = '0';
                setTimeout(() => loader.style.display = 'none', 300);
            }
        }, 500);
    }

    async initFeatureModules() {

        // Initialize modules based on page requirements
        const modulePromises = [];

        // Posts system (always needed)
        modulePromises.push(this.initModule('posts', () => {
            this.modules.posts = PostSystem;
            PostSystem.initInteractions();
            return true;
        }));

        // Friend system
        if (document.querySelector('[onclick*="addFriend"]') ||
            document.querySelector('.suggestion-card')) {
            modulePromises.push(this.initModule('friends', () => {
                this.modules.friends = FriendSystem;
                return true;
            }));
        }

        // Profile system
//        if (document.getElementById('profileModal')) {
//            modulePromises.push(this.initModule('profile', () => {
//                this.modules.profile = ProfileSystem;
//                return true;
//            }));
//        }

        // Messenger
        if (document.getElementById('messengerPopup')) {
            modulePromises.push(this.initModule('messenger', async () => {
                this.modules.messenger = Messenger;
                await Messenger.init();
                return true;
            }));
        }

        // Notifications
        if (document.getElementById('notificationDropdown')) {
            modulePromises.push(this.initModule('notifications', () => {
                this.modules.notifications = NotificationSystem;
                NotificationSystem.init();
                return true;
            }));
        }

        // Search system
        if (document.getElementById('globalSearch')) {
            modulePromises.push(this.initModule('search', () => {
                this.modules.search = SearchSystem;
                SearchSystem.init();
                return true;
            }));
        }

        // Ad system
        if (document.getElementById('nativeAd') ||
            document.getElementById('floatingAd')) {
            modulePromises.push(this.initModule('ads', async () => {
                this.modules.ads = AdSystem;
                await AdSystem.init();
                return true;
            }));
        }

        // Groups system
        if (document.getElementById('groupsList') ||
            document.getElementById('groupsListMobile')) {
            modulePromises.push(this.initModule('groups', () => {
                this.modules.groups = Groups;
                Groups.init();
                return true;
            }));
        }

        // Wait for all modules to initialize
        await Promise.allSettled(modulePromises);
    }

    async initModule(name, initFunction) {
        try {
            const result = await initFunction();
            return result;
        } catch (error) {
            return false;
        }
    }

    setupGlobalListeners() {

        // Initialize modals
        document.querySelectorAll('[data-bs-toggle="modal"]').forEach(trigger => {
            trigger.addEventListener('click', function() {
                const target = this.getAttribute('data-bs-target');
                if (target) {
                    Modal.open(target.replace('#', ''));
                }
            });
        });

        // Close modals on outside click
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) {
                if (e.target === this) {
                    Modal.close(this.id);
                }
            });
        });

        // Post creation form
        const createPostForm = document.getElementById('createPostForm');
        if (createPostForm) {
            createPostForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                const submitBtn = this.querySelector('button[type="submit"]');
                Loader.quick(submitBtn, 'show');

                try {
                    const mediaFile = document.getElementById('mediaInput').files[0];

                    if (mediaFile && mediaFile.size > 10 * 1024 * 1024) {
                        // Use AJAX for large files
                        const PostUploader = await import('../ui/file-upload.js');
                        await PostUploader.uploadWithProgress(this, submitBtn);
                    } else {
                        // Use regular form submit for small files
                        const response = await fetch(this.action, {
                            method: 'POST',
                            body: new FormData(this)
                        });

                        if (response.ok) {
                            Toast.show('Post created successfully!', 'success');
                            
                            // Clear form explicitly
                            createPostForm.reset();
                            const mInput = document.getElementById('mediaInput');
                            if (mInput) mInput.value = '';
                            const mPre = document.getElementById('mediaPreview');
                            if (mPre) {
                                mPre.innerHTML = '';
                                mPre.classList.add('hidden');
                            }
                            const sGifUrl = document.getElementById('selectedGifUrl');
                            if (sGifUrl) sGifUrl.value = '';

                            setTimeout(() => location.reload(), 1000);
                        } else {
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
    }

    initLegacyGlobals() {

        // These functions are called from HTML onclick attributes
        // We need to keep them globally available

        // Modal functions
        window.openModal = Modal.open;
        window.closeModal = Modal.close;

        // Messenger functions
        window.openMessenger = () => this.modules.messenger?.open();
        window.closeMessenger = () => this.modules.messenger?.close();
        window.backToFriends = () => this.modules.messenger?.backToFriends();
        window.handleChatInputKeypress = (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.modules.messenger?.sendMessage();
            }
        };
        window.sendMessage = () => this.modules.messenger?.sendMessage();

        // Friend functions
        window.addFriend = (userId, button) =>
            this.modules.friends?.add(userId, button);
        window.cancelFriendRequest = (userId, button) =>
            this.modules.friends?.cancelRequest(userId, button);
        window.acceptFriendRequest = (userId, button) =>
            this.modules.friends?.acceptFriendRequest(userId, button);
        window.declineFriendRequest = (userId, button) =>
            this.modules.friends?.declineFriendRequest(userId, button);

        // Profile functions
        window.openProfileModal = (userId, fromNotification = false) =>
            this.modules.profile?.openProfileModal(userId, fromNotification);
        window.viewFullProfile = (userId) => {
            const profileModal = document.getElementById('profileModal');
            if (profileModal) {
                profileModal.classList.add('hidden');
                document.body.style.overflow = '';
            }

            Toast.show('Opening full profile...', 'info');
            setTimeout(() => {
                window.open(`/profile/${userId}`, '_blank');
            }, 500);
        };

        // Message button click handler
        window.handleMessageButtonClick = (userId) => {
            const profileModal = document.getElementById('profileModal');
            if (profileModal) {
                profileModal.classList.add('hidden');
                document.body.style.overflow = '';
            }

            if (this.modules.messenger) {
                this.modules.messenger.open();
                setTimeout(() => {
                    this.modules.messenger.startChat(userId);
                }, 500);
            } else {
                Toast.show('Messenger not available', 'danger');
            }
        };

        // Groups functions
        window.searchGroups = (query) => this.modules.groups?.search(query);
        window.loadGroups = () => this.modules.groups?.load();
        window.joinGroup = (groupId) => this.modules.groups?.join(groupId);
        window.leaveGroup = (groupId) => this.modules.groups?.leave(groupId);

        // Media functions
        window.previewMedia = (input) => {
            // MediaPreview is part of file-upload module
            import('../ui/file-upload.js').then(module => {
                module.previewMedia(input);
            });
        };

        // Ad functions
        window.toggleFloatingAd = () => this.modules.ads?.toggleFloatingAd();
        window.refreshAds = () => this.modules.ads?.refresh();
        window.cycleNextAd = () => this.modules.ads?.cycleNextAd();
        window.cyclePreviousAd = () => this.modules.ads?.cyclePreviousAd();
    }

    // Utility method to check if module is available
    hasModule(name) {
        return !!this.modules[name];
    }

    // Get module instance
    getModule(name) {
        return this.modules[name];
    }

    // Refresh all modules (for debugging)
    async refreshAll() {
        this.isInitialized = false;
        this.modules = {};
        await this.init();
    }
}

// Create and export singleton instance
const App = new DashboardApp();
export default App;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.init());
} else {
    App.init();
}

// Make App available globally for debugging
window.DashboardApp = App;