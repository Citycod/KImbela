// ========================================
// SEARCH SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';
import Modal from '../../core/modal.js';

class SearchSystem {
    constructor() {
        this.defaultAvatar = config.getDefaultAvatar();
        this.searchTimeout = null;
    }

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    highlightMatch(text, query) {
        if (!query || !query.trim()) return text;
        const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedQuery})`, 'gi');
        return text.replace(regex, '<span class="bg-yellow-200 px-1 rounded">$1</span>');
    }

    async perform(query) {
        if (!query.trim()) {
            this.hideResults();
            return;
        }

        this.showLoading();

        try {
            const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            this.displayResults(data, query);
        } catch (error) {
            console.error('Error performing search:', error);
            this.showError();
        }
    }

    displayResults(results, query) {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = '';

        if (!results.users?.length && !results.posts?.length) {
            this.showNoResults();
            return;
        }

        let html = '';

        if (results.users?.length > 0) {
            results.users.forEach(user => {
                const name = this.highlightMatch(`${user.first_name} ${user.last_name}`, query);
                html += `
                    <div class="search-result-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors" onclick="openProfileModal(${user.id})">
                        <div class="search-result-user flex items-center space-x-3">
                            <img src="${user.profile_pic || this.defaultAvatar}" class="search-result-avatar w-10 h-10 rounded-full object-cover">
                            <div class="search-result-info">
                                <div class="search-result-name font-medium">${name}</div>
                                <div class="search-result-type text-xs text-gray-500">User</div>
                            </div>
                        </div>
                    </div>
                `;
            });
        }

        if (results.posts?.length > 0) {
            results.posts.forEach(post => {
                const content = this.highlightMatch(post.content.substring(0, 100), query);
                html += `
                    <div class="search-result-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors" onclick="SearchSystem.viewPost(${post.id})">
                        <div class="search-result-post">
                            <div class="search-result-content text-sm">${content}${post.content.length > 100 ? '...' : ''}</div>
                            <div class="search-result-author text-xs text-gray-500 mt-1">By ${post.author_first_name} ${post.author_last_name}</div>
                            <div class="search-result-type text-xs text-gray-500">Post</div>
                        </div>
                    </div>
                `;
            });
        }

        searchResultsBody.innerHTML = html;
        this.showResults();
    }

    showLoading() {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = `
            <div class="search-loading text-center p-6">
                <div class="flex flex-col items-center justify-center">
                    <span class="tiny-loader md mb-3"></span>
                    <div class="text-gray-500 text-sm">Searching...</div>
                </div>
            </div>
        `;
        this.showResults();
    }

    showNoResults() {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = `
            <div class="no-results text-center p-6 text-gray-500">
                <i class="bi bi-search text-3xl mb-2"></i>
                <p>No results</p>
            </div>
        `;
        this.showResults();
    }

    showError() {
        const searchResultsBody = document.getElementById('searchResultsBody');
        if (!searchResultsBody) return;

        searchResultsBody.innerHTML = `
            <div class="no-results text-center p-6 text-red-500">
                <i class="bi bi-exclamation-triangle text-3xl mb-2"></i>
                <p>Search failed</p>
            </div>
        `;
        this.showResults();
    }

    showResults() {
        const searchResults = document.getElementById('searchResults');
        if (searchResults) searchResults.classList.remove('hidden');
    }

    hideResults() {
        const searchResults = document.getElementById('searchResults');
        if (searchResults) searchResults.classList.add('hidden');
    }

    async viewPost(postId) {
        this.hideResults();

        const searchInput = document.getElementById('globalSearch');
        if (searchInput) searchInput.value = '';

        const el = document.querySelector(`[data-post-id="${postId}"]`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('highlight-animation');
            setTimeout(() => el.classList.remove('highlight-animation'), 2000);
        } else {
            try {
                const response = await fetch(`/get_post/${postId}`);
                if (!response.ok) throw new Error('Network error');

                const post = await response.json();
                if (post.error) throw new Error(post.error);

                this.displayPostModal(post);
            } catch (error) {
                console.error('Error viewing post:', error);
                Toast.show('Post not found', 'danger');
            }
        }
    }

    displayPostModal(post) {
        const body = document.getElementById('commentModalBody');
        if (!body) return;

        body.innerHTML = `
            <div class="post-card bg-white rounded-2xl shadow-soft overflow-hidden">
                <div class="p-4 flex justify-between items-start">
                    <div class="flex items-start space-x-3">
                        <img src="${post.author_profile_pic || this.defaultAvatar}" class="w-10 h-10 rounded-full object-cover">
                        <div>
                            <div class="font-semibold">${post.author_first_name || ''} ${post.author_last_name || ''}</div>
                            <div class="text-sm text-gray-500">${new Date(post.created_at).toLocaleString()}</div>
                        </div>
                    </div>
                </div>
                <div class="px-4 pb-3">
                    <p class="post-text">${post.content || ''}</p>
                    ${post.image ? `<div class="post-media mt-3"><img src="${post.image}" alt="Post" class="w-full rounded-2xl max-h-96 object-cover"></div>` : ''}
                    ${post.video ? `<div class="post-media mt-3"><video controls class="w-full rounded-2xl max-h-96"><source src="${post.video}"></video></div>` : ''}
                </div>
            </div>
        `;
        Modal.open('commentModal');
    }

    init() {
        const searchInput = document.getElementById('globalSearch');
        const searchResults = document.getElementById('searchResults');
        const searchResultsBody = document.getElementById('searchResultsBody');

        if (!searchInput || !searchResults || !searchResultsBody) return;

        const debouncedSearch = this.debounce((query) => {
            this.perform(query);
        }, 300);

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            if (query.length >= 2) {
                debouncedSearch(query);
            } else {
                this.hideResults();
            }
        });

        searchInput.addEventListener('focus', (e) => {
            const query = e.target.value.trim();
            if (query.length >= 2) {
                this.perform(query);
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchResults.contains(e.target) && e.target !== searchInput) {
                this.hideResults();
            }
        });
    }
}

// Export singleton instance
const searchSystem = new SearchSystem();
export default searchSystem;

// Make available globally
window.SearchSystem = searchSystem;