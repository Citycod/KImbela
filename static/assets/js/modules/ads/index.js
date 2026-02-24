// ========================================
// SPONSORED ADS SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';

class AdSystem {
    constructor() {
        // Configuration - Updated timing
        this.config = {
            adInterval: 40000, // 70 seconds between ads (adjustable between 60-90s)
            rotationInterval: 60000, // 90 seconds between different ads
            modalDisplayTime: 10000, // 10 seconds for modal display
            maxRetries: 3,
            retryDelay: 2000,
            initialDelay: 3000, // Wait 3 seconds before showing first ad
            randomizeInterval: true // Add randomness to intervals
        };

        // DOM elements cache
        this.elements = {
            native: null,
            floating: null,
            modal: null,
            modalContent: null,
            nativeElements: {},
            floatingElements: {},
            modalElements: {}
        };

        // State management
        this.state = {
            activeAds: [],
            displayedIndices: [],
            currentAdIndex: 0,
            rotationTimer: null,
            modalTimer: null,
            intervalTimer: null,
            adQueue: [],
            nextAdTime: null,
            initialized: false,
            retryCount: 0,
            csrfToken: config.getCsrfToken(),
            isShowingAd: false
        };
    }

    // Initialize ad system
    async init() {

        try {
            // Cache DOM elements
            this.cacheElements();

            // Show containers if they exist
            this.showContainers();

            // Load ads but don't display immediately
            await this.loadAds();

            // Wait initial delay before showing first ad
            setTimeout(() => {
                this.startAdCycle();
            }, this.config.initialDelay);

            this.state.initialized = true;
            return this;

        } catch (error) {
            this.showErrorState('Initialization failed');
            throw error;
        }
    }

    // Start the ad display cycle
    startAdCycle() {
        if (this.state.activeAds.length === 0) {
            this.showNoAdsMessage();
            return;
        }


        // Clear any existing timers
        this.clearAllTimers();

        // Schedule first ad
        this.scheduleNextAd();
    }

    // Schedule next ad display
    scheduleNextAd() {
        // Clear existing timer
        if (this.state.intervalTimer) {
            clearTimeout(this.state.intervalTimer);
            this.state.intervalTimer = null;
        }

        // Calculate next interval (with optional randomness)
        let interval = this.config.adInterval;
        if (this.config.randomizeInterval) {
            // Add ±10 seconds randomness
            interval += (Math.random() * 20000 - 10000);
            interval = Math.max(60000, Math.min(90000, interval)); // Keep between 60-90s
        }


        // Set timer for next ad
        this.state.intervalTimer = setTimeout(() => {
            this.displayNextAd();
        }, interval);

        // Store next ad time
        this.state.nextAdTime = Date.now() + interval;
    }

    // Display the next ad
    displayNextAd() {
        if (this.state.activeAds.length === 0 || this.state.isShowingAd) {
            this.scheduleNextAd();
            return;
        }

        this.state.isShowingAd = true;

        // Get random ad
        const ad = this.getNextAd();
        if (!ad) {
            this.state.isShowingAd = false;
            this.scheduleNextAd();
            return;
        }


        // Update all ad displays
        this.updateNativeAd(ad);
        this.updateFloatingAd(ad);
        this.showAdModal(ad);

        // Track impression
        this.trackAdImpression(ad.id);

        // Hide the ad after modal display time
        setTimeout(() => {
            this.state.isShowingAd = false;
            // Schedule next ad
            this.scheduleNextAd();
        }, this.config.modalDisplayTime + 3000); // Add 3 seconds buffer
    }

    // Get next ad to display
    getNextAd() {
        if (this.state.activeAds.length === 0) return null;

        // Reset if all ads have been shown
        if (this.state.displayedIndices.length >= this.state.activeAds.length) {
            this.state.displayedIndices = [];
        }

        // Get available indices (not shown recently)
        const availableIndices = [];
        for (let i = 0; i < this.state.activeAds.length; i++) {
            if (!this.state.displayedIndices.includes(i)) {
                availableIndices.push(i);
            }
        }

        // If no new ads, use random from all
        const useIndices = availableIndices.length > 0 ? availableIndices :
                          Array.from({length: this.state.activeAds.length}, (_, i) => i);

        // Pick random
        const randomIndex = Math.floor(Math.random() * useIndices.length);
        const selectedIndex = useIndices[randomIndex];

        // Track displayed ad
        this.state.displayedIndices.push(selectedIndex);
        this.state.currentAdIndex = selectedIndex;

        return this.state.activeAds[selectedIndex];
    }

    // Cache DOM elements for better performance
    cacheElements() {
        // Main containers
        this.elements.native = document.getElementById('nativeAd');
        this.elements.floating = document.getElementById('floatingAdContent');
        this.elements.modal = document.getElementById('adModal');

        if (this.elements.modal) {
            this.elements.modalContent = this.elements.modal.querySelector('.ad-modal-content');
        }

        // Native ad elements
        this.elements.nativeElements = {
            advertiser: document.getElementById('nativeAdAdvertiser'),
            title: document.getElementById('nativeAdTitle'),
            description: document.getElementById('nativeAdDescription'),
            image: document.getElementById('nativeAdImage'),
            link: document.getElementById('nativeAdLink'),
            cta: document.getElementById('nativeAdCTA')
        };

        // Floating ad elements
        this.elements.floatingElements = {
            title: document.getElementById('floatingAdTitle'),
            desc: document.getElementById('floatingAdDesc'),
            link: document.getElementById('floatingAdLink')
        };

        // Modal elements
        this.elements.modalElements = {
            image: document.getElementById('adModalImage'),
            title: document.getElementById('adModalTitle'),
            description: document.getElementById('adModalDescription'),
            link: document.getElementById('adModalLink'),
            cta: document.getElementById('adModalCTA')
        };
    }

    // Show/hide containers
    showContainers() {
        if (this.elements.native) {
            this.elements.native.classList.remove('hidden');
        }

        if (this.elements.floating) {
            this.elements.floating.classList.remove('hidden');
        }
    }

    hideContainers() {
        if (this.elements.native) {
            this.elements.native.classList.add('hidden');
        }

        if (this.elements.floating) {
            this.elements.floating.classList.add('hidden');
        }
    }

    // Load ads from server with retry logic
    async loadAds() {
        if (this.state.retryCount >= this.config.maxRetries) {
            this.showErrorState('Failed to load ads after multiple attempts');
            return;
        }

        try {

            const response = await fetch('/api/ads/sponsored', {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Cache-Control': 'no-cache'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success && data.ads && Array.isArray(data.ads) && data.ads.length > 0) {
                this.state.activeAds = data.ads;
                this.state.displayedIndices = [];
                this.state.retryCount = 0;


            } else {
                this.showNoAdsMessage();
            }

        } catch (error) {
            this.state.retryCount++;

            // Retry with exponential backoff
            setTimeout(() => {
                this.loadAds();
            }, this.config.retryDelay * Math.pow(2, this.state.retryCount - 1));

            this.showErrorState('Temporarily unavailable');
        }
    }

    // Update native ad
    updateNativeAd(ad) {
        if (!this.elements.native || !ad) return;

        const { nativeElements } = this.elements;

        // Helper to safely update element
        const updateElement = (element, value, fallback = '') => {
            if (element) {
                element.textContent = value || fallback;
            }
        };

        updateElement(nativeElements.advertiser, ad.advertiser_name, 'Sponsored Partner');
        updateElement(nativeElements.title, ad.title, 'Special Offer');
        updateElement(nativeElements.description, ad.description, 'Check out this amazing offer!');
        updateElement(nativeElements.cta, ad.cta_text, 'Learn More');

        // Update image
        if (nativeElements.image) {
            const imageUrl = ad.image_url || 'https://via.placeholder.com/400x200/3B82F6/FFFFFF?text=Sponsored+Ad';
            nativeElements.image.src = imageUrl;
            nativeElements.image.alt = ad.title || 'Sponsored Advertisement';
            nativeElements.image.onerror = () => {
                nativeElements.image.src = 'https://via.placeholder.com/400x200/3B82F6/FFFFFF?text=Sponsored+Ad';
            };
        }

        // Update link
        if (nativeElements.link) {
            nativeElements.link.href = ad.cta_url || '#';
            nativeElements.link.target = '_blank';
            nativeElements.link.onclick = (e) => {
                this.trackAdClick(ad.id);
                return true;
            };
        }

        // Ensure container is visible
        this.elements.native.classList.remove('hidden');
    }

    // Update floating ad
    updateFloatingAd(ad) {
        if (!this.elements.floating || !ad) return;

        const { floatingElements } = this.elements;

        if (floatingElements.title) {
            floatingElements.title.textContent = (ad.title || 'Special Offer!').substring(0, 30);
        }

        if (floatingElements.desc) {
            floatingElements.desc.textContent = (ad.description || 'Amazing deals available').substring(0, 40);
        }

        if (floatingElements.link) {
            floatingElements.link.href = ad.cta_url || '#';
            floatingElements.link.onclick = (e) => {
                this.trackAdClick(ad.id);
                return true;
            };
        }
    }

    // Show ad modal
    showAdModal(ad) {
        if (!this.elements.modal || !ad) return;

        const { modalElements } = this.elements;

        // Update modal content
        if (modalElements.image) {
            const imageUrl = ad.image_url || 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Sponsored+Ad';
            modalElements.image.src = imageUrl;
            modalElements.image.alt = ad.title || 'Sponsored Advertisement';
            modalElements.image.onerror = () => {
                modalElements.image.src = 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Sponsored+Ad';
            };
        }

        if (modalElements.title) {
            modalElements.title.textContent = ad.title || 'Special Offer';
        }

        if (modalElements.description) {
            modalElements.description.textContent = ad.description || 'Check out this amazing offer!';
        }

        if (modalElements.link) {
            modalElements.link.href = ad.cta_url || '#';
            modalElements.link.target = '_blank';
            modalElements.link.onclick = () => this.trackAdClick(ad.id);
        }

        if (modalElements.cta) {
            modalElements.cta.textContent = ad.cta_text || 'Learn More';
        }

        // Show modal with animation
        this.elements.modal.classList.remove('hidden');
        setTimeout(() => {
            if (this.elements.modalContent) {
                this.elements.modalContent.classList.remove('scale-95', 'opacity-0');
                this.elements.modalContent.classList.add('scale-100', 'opacity-100');
            }
        }, 50);

        // Clear any existing timer
        if (this.state.modalTimer) {
            clearTimeout(this.state.modalTimer);
        }

        // Auto-hide after configured time
        this.state.modalTimer = setTimeout(() => {
            this.closeAdModal();
        }, this.config.modalDisplayTime);
    }

    // Close ad modal
    closeAdModal() {
        if (!this.elements.modal) return;

        if (this.elements.modalContent) {
            this.elements.modalContent.classList.remove('scale-100', 'opacity-100');
            this.elements.modalContent.classList.add('scale-95', 'opacity-0');
        }

        setTimeout(() => {
            this.elements.modal.classList.add('hidden');
        }, 300);
    }

    // User not interested
    async adNotInterested() {
        const currentAd = this.state.activeAds[this.state.currentAdIndex];
        if (currentAd) {

            try {
                await fetch(`/api/ads/${currentAd.id}/not_interested`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-Token': this.state.csrfToken,
                        'Content-Type': 'application/json'
                    }
                });
            } catch (error) {
            }
        }

        this.closeAdModal();

        // Continue with next ad schedule
        this.state.isShowingAd = false;
        this.scheduleNextAd();
    }

    // Clear all timers
    clearAllTimers() {
        if (this.state.rotationTimer) {
            clearInterval(this.state.rotationTimer);
            this.state.rotationTimer = null;
        }

        if (this.state.modalTimer) {
            clearTimeout(this.state.modalTimer);
            this.state.modalTimer = null;
        }

        if (this.state.intervalTimer) {
            clearTimeout(this.state.intervalTimer);
            this.state.intervalTimer = null;
        }
    }

    // Track ad click
    async trackAdClick(adId) {

        // Analytics
        if (typeof gtag === 'function') {
            gtag('event', 'ad_click', {
                'ad_id': adId,
                'event_category': 'ads',
                'event_label': 'sponsored_ad'
            });
        }

        // Server tracking
        try {
            await fetch(`/api/ads/${adId}/click`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': this.state.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        } catch (error) {
        }
    }

    // Track ad impression
    async trackAdImpression(adId) {

        // Analytics
        if (typeof gtag === 'function') {
            gtag('event', 'ad_impression', {
                'ad_id': adId,
                'event_category': 'ads',
                'event_label': 'sponsored_ad'
            });
        }

        // Server tracking
        try {
            await fetch(`/api/ads/${adId}/impression`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': this.state.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        } catch (error) {
        }
    }

    // Show no ads message
    showNoAdsMessage() {
        if (this.elements.native) {
            this.elements.native.innerHTML = `
                <div class="p-6 text-center">
                    <i class="bi bi-megaphone text-3xl text-gray-300 mb-3"></i>
                    <p class="text-gray-500">No sponsored ads available at the moment</p>
                    <p class="text-sm text-gray-400 mt-1">Check back later for amazing offers!</p>
                </div>
            `;
        }
    }

    // Show error state
    showErrorState(message = 'Unable to load ads') {
        if (this.elements.native) {
            this.elements.native.innerHTML = `
                <div class="p-6 text-center">
                    <i class="bi bi-exclamation-triangle text-3xl text-yellow-500 mb-3"></i>
                    <p class="text-gray-500">${message}</p>
                    <button onclick="AdSystem.refresh()"
                            class="mt-3 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors">
                        Retry
                    </button>
                </div>
            `;
        }
    }

    // Toggle floating ad visibility
    toggleFloatingAd() {
        if (!this.elements.floating) return;

        const isHidden = this.elements.floating.classList.contains('hidden');

        if (isHidden) {
            this.elements.floating.classList.remove('hidden');
            setTimeout(() => {
                this.elements.floating.classList.remove('opacity-0', 'scale-95');
                this.elements.floating.classList.add('opacity-100', 'scale-100');
            }, 10);
        } else {
            this.elements.floating.classList.add('opacity-0', 'scale-95');
            setTimeout(() => {
                this.elements.floating.classList.add('hidden');
            }, 300);
        }
    }

    // Refresh system
    refresh() {

        this.clearAllTimers();
        this.state.isShowingAd = false;
        this.state.displayedIndices = [];
        this.state.retryCount = 0;

        this.loadAds().then(() => {
            setTimeout(() => {
                this.startAdCycle();
            }, 3000);
        });
    }

    // Destroy/cleanup
    destroy() {

        this.clearAllTimers();
        this.closeAdModal();
        this.hideContainers();

        this.state = {
            activeAds: [],
            displayedIndices: [],
            currentAdIndex: 0,
            rotationTimer: null,
            modalTimer: null,
            intervalTimer: null,
            adQueue: [],
            nextAdTime: null,
            initialized: false,
            retryCount: 0,
            csrfToken: this.state.csrfToken,
            isShowingAd: false
        };
    }
}

// Export singleton instance
const adSystem = new AdSystem();
export default adSystem;

// Make available globally
window.AdSystem = adSystem;