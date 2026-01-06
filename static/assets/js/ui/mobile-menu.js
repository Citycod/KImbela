// ========================================
// MOBILE MENU FUNCTIONALITY
// ========================================

class MobileMenu {
    static init() {
        // Setup event listeners for mobile menu
        this.setupEventListeners();
    }

    static setupEventListeners() {
        // Add ESC key to close mobile menu
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const overlay = document.getElementById('mobileSidebarOverlay');
                if (overlay && (overlay.style.display === 'block' || overlay.classList.contains('block'))) {
                    this.toggle();
                }
            }
        });

        // Close mobile menu when clicking outside
        document.getElementById('mobileSidebarOverlay')?.addEventListener('click', (e) => {
            if (e.target.id === 'mobileSidebarOverlay') {
                this.toggle();
            }
        });
    }

    static toggle() {
        const overlay = document.getElementById('mobileSidebarOverlay');
        const sidebar = document.getElementById('mobileSidebar');

        if (!overlay || !sidebar) {
            console.error('Mobile menu elements not found!');
            return;
        }

        // Toggle display
        if (overlay.style.display === 'block' || overlay.classList.contains('block')) {
            overlay.style.display = 'none';
            overlay.classList.remove('block');
            sidebar.classList.remove('translate-x-0');
            sidebar.classList.add('-translate-x-full');
        } else {
            overlay.style.display = 'block';
            overlay.classList.add('block');
            sidebar.classList.remove('-translate-x-full');
            sidebar.classList.add('translate-x-0');
        }
    }
}

export default MobileMenu;

// Make available globally for HTML onclick
window.toggleMobileMenu = MobileMenu.toggle;