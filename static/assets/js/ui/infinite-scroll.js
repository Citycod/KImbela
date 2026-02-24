// ========================================
// INFINITE SCROLL
// ========================================

import { appState } from '../app/state.js';
import Toast from '../core/toast.js';
import PostSystem from '../modules/posts/index.js';

class InfiniteScroll {
    async loadMore() {
        if (appState.isLoadingPosts || !appState.hasMorePosts || !appState.nextCursor) return;

        appState.setLoadingPosts(true);
        const loadingSpinner = document.getElementById('loading-spinner');
        const loadMoreBtn = document.getElementById('load-more-btn');

        if (loadingSpinner) loadingSpinner.classList.remove('hidden');
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');

        try {
            const response = await fetch(`/user_dashboard?cursor=${appState.nextCursor}&limit=10`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();

            if (data.success) {
                if (data.posts) {
                    const postsFeed = document.getElementById('posts-feed');
                    if (postsFeed) {
                        postsFeed.insertAdjacentHTML('beforeend', data.posts);
                        PostSystem.initInteractions();
                    }
                }

                appState.updatePagination(data.has_more, data.next_cursor);

                if (loadMoreBtn && data.has_more) {
                    loadMoreBtn.classList.remove('hidden');
                } else {
                    const endOfFeed = document.getElementById('end-of-feed');
                    if (endOfFeed) endOfFeed.classList.remove('hidden');
                }

                if (data.count > 0) {
                    Toast.show(`Loaded ${data.count} more posts`, 'success');
                }
            }
        } catch (error) {
            Toast.show('Failed to load more posts', 'danger');
            if (loadMoreBtn) loadMoreBtn.classList.remove('hidden');
        } finally {
            appState.setLoadingPosts(false);
            if (loadingSpinner) loadingSpinner.classList.add('hidden');
        }
    }

    init() {
        const loadMoreBtn = document.getElementById('load-more-btn');
        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', () => this.loadMore());
        }

        window.addEventListener('scroll', () => {
            const scrollPosition = window.innerHeight + window.scrollY;
            const threshold = document.body.offsetHeight - 500;

            if (scrollPosition >= threshold && appState.canLoadMorePosts()) {
                this.loadMore();
            }
        });
    }
}

// Export singleton instance
const infiniteScroll = new InfiniteScroll();
export default infiniteScroll;