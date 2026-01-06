// ========================================
// DROPDOWN MANAGEMENT
// ========================================

import { config } from '../app/config.js';
import Groups from '../modules/groups/index.js';

class Dropdown {
    static init() {
        document.addEventListener('click', (e) => {
            // Close all dropdowns if clicking outside
            if (!e.target.closest('.dropdown')) {
                document.querySelectorAll('.dropdown-menu').forEach(menu => {
                    menu.classList.add('hidden');
                });
            }

            // Handle dropdown toggle
            const dropdownToggle = e.target.closest('[data-bs-toggle="dropdown"]');
            if (dropdownToggle) {
                e.preventDefault();
                const dropdown = dropdownToggle.closest('.dropdown');
                const menu = dropdown.querySelector('.dropdown-menu');

                if (menu) {
                    // Close other dropdowns
                    document.querySelectorAll('.dropdown-menu').forEach(otherMenu => {
                        if (otherMenu !== menu) {
                            otherMenu.classList.add('hidden');
                        }
                    });

                    // Toggle current dropdown
                    menu.classList.toggle('hidden');

                    // Load groups if needed
                    if (menu.id.includes('groupsDropdownMenu')) {
                        if (!menu.classList.contains('hidden')) {
                            Groups.load();
                        }
                    }
                }
            }
        });

        // Handle comment dropdowns
        this.initCommentDropdowns();
    }

    static initCommentDropdowns() {
        document.addEventListener('click', e => {
            if (!e.target.closest('.dropdown')) {
                document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.add('hidden'));
            }
            if (e.target.closest('.dropdown button')) {
                const menu = e.target.closest('.dropdown').querySelector('.dropdown-menu');
                menu.classList.toggle('hidden');
            }
        });
    }

    static show(menuElement) {
        if (menuElement) {
            menuElement.classList.remove('hidden');
        }
    }

    static hide(menuElement) {
        if (menuElement) {
            menuElement.classList.add('hidden');
        }
    }

    static toggle(menuElement) {
        if (menuElement) {
            menuElement.classList.toggle('hidden');
        }
    }
}

export default Dropdown;