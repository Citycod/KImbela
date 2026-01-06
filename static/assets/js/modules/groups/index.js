// ========================================
// GROUPS SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';
import Loader from '../../core/loader.js';

class Groups {
    constructor() {
        this.csrfToken = config.getCsrfToken();

        // Cache to prevent multiple simultaneous loads
        this.cache = {
            groups: null,
            lastFetch: null,
            expiry: 30000 // 30 seconds
        };

        // Debounce search
        this.searchTimer = null;
    }

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
    }

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
    }

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
    }

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
    }

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
    }

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
    }

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
                    'X-CSRFToken': this.csrfToken,
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
    }

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
                    'X-CSRFToken': this.csrfToken,
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
    }

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
    }

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
    }

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
    }

    // Clear cache
    clearCache() {
        this.cache.groups = null;
        this.cache.lastFetch = null;
        console.log('🧹 Groups cache cleared');
    }

    // Refresh groups (force reload)
    refresh() {
        this.clearCache();
        this.load();
    }
}

// Export singleton instance
const groups = new Groups();
export default groups;

// Make available globally
window.Groups = groups;