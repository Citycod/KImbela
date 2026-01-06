// ========================================
// MODAL MANAGEMENT
// ========================================

import Loader from './loader.js';

class Modal {
    static open(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';

            // Add animation
            setTimeout(() => {
                const content = modal.querySelector('.modal-content, .modal-dialog');
                if (content) {
                    content.classList.remove('scale-95', 'opacity-0');
                    content.classList.add('scale-100', 'opacity-100');
                }
            }, 10);
        }
    }

    static close(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            // Add animation
            const content = modal.querySelector('.modal-content, .modal-dialog');
            if (content) {
                content.classList.remove('scale-100', 'opacity-100');
                content.classList.add('scale-95', 'opacity-0');
            }

            setTimeout(() => {
                modal.classList.add('hidden');
                modal.style.display = 'none';
                document.body.style.overflow = '';
            }, 300);
        }
    }

    static toggle(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            if (modal.classList.contains('hidden')) {
                this.open(modalId);
            } else {
                this.close(modalId);
            }
        }
    }

    static showLoading(modalId) {
        return Loader.showModal(modalId);
    }

    static hideLoading(modalId) {
        Loader.hideModal(modalId);
    }

    static closeAll() {
        document.querySelectorAll('.modal').forEach(modal => {
            if (!modal.classList.contains('hidden')) {
                this.close(modal.id);
            }
        });
    }

    static isOpen(modalId) {
        const modal = document.getElementById(modalId);
        return modal && !modal.classList.contains('hidden');
    }
}

export default Modal;