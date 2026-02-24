//// ========================================
//// PROFILE SYSTEM - FULLY FIXED VERSION
//// ========================================
//
//import { config } from '../../app/config.js';
//import Toast from '../../core/toast.js';
//import TimeUtils from '../../core/time-utils.js';
//import FriendSystem from '../friends/index.js';
//
//class ProfileSystem {
//    constructor() {
//        this.defaultAvatar = config.getDefaultAvatar();
//        this.isModalOpen = false;
//        this.currentUserId = null;
//        this.lastClickTime = 0; // For simple debounce
//    }
//
//    async openProfileModal(userId, fromFriendRequestNotification = false) {
//        // Simple debounce - prevent rapid double clicks
//        const now = Date.now();
//        if (now - this.lastClickTime < 500) {
//            return;
//        }
//        this.lastClickTime = now;
//
//        // If a DIFFERENT profile is currently loading/open, block to avoid overlap
//        if (this.isModalOpen && this.currentUserId !== userId) {
//            Toast.show('Please wait for the current profile to finish loading.', 'info');
//            return;
//        }
//
//        // Allow retry on same profile (e.g., after error)
//        this.isModalOpen = true;
//        this.currentUserId = userId;
//
//        const modalBody = document.getElementById('profileModalBody');
//        const profileActions = document.getElementById('profileActions');
//        const profileModal = document.getElementById('profileModal');
//
//        if (!modalBody || !profileActions || !profileModal) {
//            
//            this.resetState();
//            return;
//        }
//
//        // Show modal immediately with loading state
//        profileModal.classList.remove('hidden');
//        document.body.style.overflow = 'hidden';
//
//        // Ensure only one backdrop
//        const existingBackdrop = document.getElementById('profileModalBackdrop');
//        if (existingBackdrop) existingBackdrop.remove();
//
//        const backdrop = document.createElement('div');
//        backdrop.className = 'modal-backdrop fixed inset-0 bg-black bg-opacity-50 z-40';
//        backdrop.id = 'profileModalBackdrop';
//        document.body.appendChild(backdrop);
//
//        // Loading state
//        modalBody.innerHTML = `
//            <div class="flex flex-col items-center justify-center p-8 min-h-[400px]">
//                <div class="relative mb-4">
//                    <div class="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
//                    <div class="absolute inset-0 flex items-center justify-center">
//                        <i class="bi bi-person-circle text-blue-600 text-xl"></i>
//                    </div>
//                </div>
//                <div class="text-gray-500 mt-3">Loading profile...</div>
//            </div>
//        `;
//
//        profileActions.innerHTML = `
//            <button class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
//                    onclick="window.ProfileSystem.closeProfileModal()">
//                Cancel
//            </button>
//        `;
//
//        // Fetch profile data
//        try {
//            const response = await fetch(`/get_user_profile/${userId}`);
//            if (!response.ok) {
//                throw new Error(`Failed to load profile: ${response.status}`);
//            }
//            const data = await response.json();
//            if (data.error) {
//                throw new Error(data.error);
//            }
//
//            this.displayProfileModal(data, userId, fromFriendRequestNotification);
//        } catch (error) {
//            
//            modalBody.innerHTML = `
//                <div class="text-center p-8 text-red-500 min-h-[400px] flex flex-col items-center justify-center">
//                    <i class="bi bi-exclamation-triangle text-4xl mb-4"></i>
//                    <p class="text-lg font-medium mb-2">Failed to load profile</p>
//                    <p class="text-sm text-gray-600 mb-4">${error.message || 'Unknown error'}</p>
//                    <div class="flex space-x-2">
//                        <button onclick="window.ProfileSystem.openProfileModal(${userId})"
//                                class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
//                            Try Again
//                        </button>
//                        <button onclick="window.ProfileSystem.closeProfileModal()"
//                                class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors">
//                            Close
//                        </button>
//                    </div>
//                </div>
//            `;
//            Toast.show('Failed to load profile: ' + (error.message || 'Try again'), 'danger');
//        } finally {
//            // Only reset if we're still on the same user (prevents race conditions)
//            if (this.currentUserId === userId) {
//                this.isModalOpen = false;
//            }
//        }
//    }
//
//    async displayProfileModal(data, userId, fromFriendRequestNotification = false) {
//        const modalBody = document.getElementById('profileModalBody');
//        const profileActions = document.getElementById('profileActions');
//
//        if (!modalBody || !profileActions) {
//            this.closeProfileModal();
//            return;
//        }
//
//        try {
//            // Safely parse data with defaults
//            const userData = {
//                first_name: data.first_name || 'User',
//                last_name: data.last_name || '',
//                profile_pic: data.profile_pic || this.defaultAvatar,
//                cover_pic: data.cover_pic || 'https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg',
//                bio: data.bio || '',
//                email: data.email || '',
//                phone_number: data.phone_number || '',
//                gender: data.gender || '',
//                dob: data.dob || '',
//                religion: data.religion || '',
//                marital_status: data.marital_status || '',
//                city: data.city || '',
//                state: data.state || '',
//                country: data.country || '',
//                interests: data.interests || ''
//            };
//
//            // Format DOB and age
//            const dobFormatted = userData.dob
//                ? new Date(userData.dob).toLocaleDateString('en-US', {
//                      year: 'numeric',
//                      month: 'long',
//                      day: 'numeric'
//                  })
//                : 'Not specified';
//
//            const age = userData.dob ? TimeUtils.calculateAge(userData.dob) : '';
//
//            // Render profile content
//            modalBody.innerHTML = `
//                <div class="profile-modal-content">
//                    <div class="profile-header relative">
//                        <div class="cover-photo-container h-48 overflow-hidden rounded-t-2xl">
//                            <img src="${userData.cover_pic}"
//                                 alt="Cover"
//                                 class="cover-photo w-full h-full object-cover"
//                                 onerror="this.src='https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg'">
//                        </div>
//                        <div class="profile-info-container text-center relative -mt-16 pb-6 px-6">
//                            <div class="profile-avatar-container inline-block">
//                                <img src="${userData.profile_pic}"
//                                     alt="${userData.first_name}"
//                                     class="profile-avatar w-32 h-32 rounded-full border-4 border-white object-cover shadow-strong"
//                                     onerror="this.src='${this.defaultAvatar}'">
//                            </div>
//                            <div class="profile-text-content mt-4">
//                                <h3 class="profile-name text-2xl font-bold">${userData.first_name} ${userData.last_name}</h3>
//                                <div class="profile-details flex flex-wrap justify-center gap-2 mt-2">
//                                    ${userData.marital_status ? `
//                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
//                                            <i class="bi bi-heart-fill text-red-500 text-xs"></i>
//                                            ${userData.marital_status}
//                                        </span>` : ''}
//                                    ${userData.city && userData.country ? `
//                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
//                                            <i class="bi bi-geo-alt-fill text-blue-500 text-xs"></i>
//                                            ${userData.city}, ${userData.country}
//                                        </span>` : ''}
//                                    ${age ? `
//                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
//                                            <i class="bi bi-balloon-fill text-purple-500 text-xs"></i>
//                                            ${age}
//                                        </span>` : ''}
//                                    ${userData.religion ? `
//                                        <span class="inline-flex items-center gap-1 bg-gray-100 px-3 py-1.5 rounded-full text-sm">
//                                            <i class="bi bi-star-fill text-yellow-500 text-xs"></i>
//                                            ${userData.religion}
//                                        </span>` : ''}
//                                </div>
//                                ${userData.bio ? `
//                                    <div class="profile-bio mt-4 max-w-2xl mx-auto">
//                                        <p class="bio-text text-gray-700 text-sm leading-relaxed">${userData.bio}</p>
//                                    </div>` : ''}
//                            </div>
//                        </div>
//                    </div>
//
//                    <div class="profile-details-section mt-6 px-6 pb-6">
//                        <div class="grid md:grid-cols-2 gap-6">
//                            <div class="detail-card bg-gray-50 rounded-2xl p-6">
//                                <h6 class="detail-card-title font-semibold text-lg mb-4 flex items-center">
//                                    <i class="bi bi-person-badge-fill mr-2 text-blue-500"></i>Personal Info
//                                </h6>
//                                <div class="detail-list space-y-3">
//                                    ${userData.email ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Email:</span><span class="detail-value text-sm">${userData.email}</span></div>` : ''}
//                                    ${userData.phone_number ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Phone:</span><span class="detail-value text-sm">${userData.phone_number}</span></div>` : ''}
//                                    ${userData.gender ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Gender:</span><span class="detail-value text-sm">${userData.gender}</span></div>` : ''}
//                                    ${userData.dob ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Birth:</span><span class="detail-value text-sm">${dobFormatted}</span></div>` : ''}
//                                    ${userData.religion ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Religion:</span><span class="detail-value text-sm">${userData.religion}</span></div>` : ''}
//                                </div>
//                            </div>
//                            <div class="detail-card bg-gray-50 rounded-2xl p-6">
//                                <h6 class="detail-card-title font-semibold text-lg mb-4 flex items-center">
//                                    <i class="bi bi-geo-fill mr-2 text-green-500"></i>Location & Interests
//                                </h6>
//                                <div class="detail-list space-y-3">
//                                    ${userData.city ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">City:</span><span class="detail-value text-sm">${userData.city}</span></div>` : ''}
//                                    ${userData.state ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">State:</span><span class="detail-value text-sm">${userData.state}</span></div>` : ''}
//                                    ${userData.country ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Country:</span><span class="detail-value text-sm">${userData.country}</span></div>` : ''}
//                                    ${userData.interests ? `<div class="detail-row flex items-start"><span class="detail-label font-medium text-gray-600 min-w-24">Interests:</span><span class="detail-value text-sm">${userData.interests}</span></div>` : ''}
//                                </div>
//                            </div>
//                        </div>
//                    </div>
//                </div>
//            `;
//
//            // Base buttons: View Full Profile + Close
//            let actionsHTML = `
//                <button class="btn-view-full-profile flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl font-medium hover:from-purple-700 hover:to-pink-700 transition-all duration-300 shadow-lg hover:shadow-xl transform hover:-translate-y-1"
//                        onclick="window.location.href='/profile/${userId}'">
//                    <i class="bi bi-person-bounding-box"></i>
//                    View Full Profile
//                </button>
//                <button class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
//                        onclick="window.ProfileSystem.closeProfileModal()">
//                    Close
//                </button>
//            `;
//
//            // Special case: from friend request notification
//            if (fromFriendRequestNotification) {
//                actionsHTML = `
//                    <div class="flex space-x-2">
//                        <button class="px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors"
//                                onclick="FriendSystem.acceptFriendRequest(${userId}, this)">
//                            <i class="bi bi-check-lg mr-1"></i> Accept
//                        </button>
//                        <button class="px-4 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors"
//                                onclick="FriendSystem.declineFriendRequest(${userId}, this)">
//                            <i class="bi bi-x-lg mr-1"></i> Decline
//                        </button>
//                    </div>
//                    ${actionsHTML}
//                `;
//                profileActions.innerHTML = `
//                    <div class="flex flex-wrap gap-3 justify-center items-center">
//                        ${actionsHTML}
//                    </div>
//                `;
//                return;
//            }
//
//            // Normal case: fetch friend status and add appropriate buttons
//            try {
//                const friendStatusHTML = await this.updateProfileActions(userId);
//
//                // Prepend friend action buttons before View Full Profile & Close
//                profileActions.innerHTML = `
//                    <div class="flex flex-wrap gap-3 justify-center items-center">
//                        ${friendStatusHTML ? friendStatusHTML : ''}
//                        ${actionsHTML}
//                    </div>
//                `;
//            } catch (err) {
//                
//                // Fallback: just show base buttons
//                profileActions.innerHTML = `
//                    <div class="flex flex-wrap gap-3 justify-center items-center">
//                        ${actionsHTML}
//                    </div>
//                `;
//            }
//
//        } catch (error) {
//            
//            modalBody.innerHTML = `
//                <div class="text-center p-8 text-red-500 min-h-[400px] flex flex-col items-center justify-center">
//                    <i class="bi bi-exclamation-triangle text-5xl mb-4"></i>
//                    <p class="text-xl font-medium">Error displaying profile</p>
//                    <p class="text-sm mt-2 text-gray-600">${error.message || 'Unknown error'}</p>
//                    <button class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
//                            onclick="window.ProfileSystem.openProfileModal(${userId})">
//                        Try Again
//                    </button>
//                </div>
//            `;
//        }
//    }
//
//    async updateProfileActions(userId) {
//        try {
//            const response = await fetch(`/check_friend_status/${userId}`);
//            if (!response.ok) return null;
//
//            const data = await response.json();
//
//            switch (data.status) {
//                case 'friends':
//                    return `
//                        <button class="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
//                                onclick="handleMessageButtonClick(${userId})">
//                            <i class="bi bi-chat-dots mr-1"></i> Message
//                        </button>
//                        <button class="px-4 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors"
//                                onclick="BlockSystem.block(${userId})">
//                            <i class="bi bi-slash-circle mr-1"></i> Block
//                        </button>
//                    `;
//
//                case 'request_sent':
//                    return `
//                        <button class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
//                                onclick="FriendSystem.cancelRequest(${userId}, this)">
//                            <i class="bi bi-clock-history mr-1"></i> Cancel Request
//                        </button>
//                    `;
//
//                case 'request_received':
//                    return `
//                        <div class="flex space-x-2">
//                            <button class="px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors"
//                                    onclick="FriendSystem.acceptFriendRequest(${userId}, this)">
//                                <i class="bi bi-check-lg mr-1"></i> Accept
//                            </button>
//                            <button class="px-4 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors"
//                                    onclick="FriendSystem.declineFriendRequest(${userId}, this)">
//                                <i class="bi bi-x-lg mr-1"></i> Decline
//                            </button>
//                        </div>
//                    `;
//
//                default:
//                    return `
//                        <button class="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-lg font-medium hover:from-blue-600 hover:to-purple-700 transition-all"
//                                onclick="FriendSystem.add(${userId}, this)">
//                            <i class="bi bi-person-plus mr-1"></i> Connect
//                        </button>
//                    `;
//            }
//        } catch (error) {
//            
//            return null;
//        }
//    }
//
//    closeProfileModal() {
//        const profileModal = document.getElementById('profileModal');
//        if (profileModal) {
//            profileModal.classList.add('hidden');
//        }
//
//        const backdrop = document.getElementById('profileModalBackdrop');
//        if (backdrop) {
//            backdrop.remove();
//        }
//
//        document.body.style.overflow = '';
//        this.resetState();
//    }
//
//    resetState() {
//        this.isModalOpen = false;
//        this.currentUserId = null;
//    }
//}
//
//// Export singleton instance
//const profileSystem = new ProfileSystem();
//export default profileSystem;
//
//// Make available globally for onclick handlers
//window.ProfileSystem = profileSystem;
//window.openProfileModal = (userId, fromFriendRequestNotification = false) =>
//    profileSystem.openProfileModal(userId, fromFriendRequestNotification);