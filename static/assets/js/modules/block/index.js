// ========================================
// BLOCK SYSTEM
// ========================================

import { config } from '../../app/config.js';
import Toast from '../../core/toast.js';
import Loader from '../../core/loader.js';
import Modal from '../../core/modal.js';

class BlockSystem {
    constructor() {
        this.csrfToken = config.getCsrfToken();
    }

    async block(userId) {
        if (!confirm("Block this user? They won't see your posts or be able to contact you.")) return;

        const button = event?.target;
        if (button) Loader.quick(button, 'show');

        try {
            const response = await fetch(`/block_user/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                Toast.show('User blocked successfully!', 'success');
                Modal.close('profileModal');
                setTimeout(() => location.reload(), 1500);
            } else {
                Toast.show(data.error || 'Error blocking user', 'danger');
            }
        } catch (error) {
            console.error('Error blocking user:', error);
            Toast.show('Error blocking user. Please try again.', 'danger');
        } finally {
            if (button) Loader.quick(button, 'hide');
        }
    }

    async unblock(userId) {
        if (!confirm("Unblock this user? They will be able to see your posts again.")) return;

        const button = event?.target;
        if (button) Loader.quick(button, 'show');

        try {
            const response = await fetch(`/unblock_user/${userId}`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) throw new Error('Network error');

            const data = await response.json();
            if (data.success) {
                Toast.show('User unblocked!', 'success');
                Modal.close('profileModal');
            } else {
                Toast.show(data.error || 'Failed to unblock', 'danger');
            }
        } catch (error) {
            console.error('Error unblocking user:', error);
            Toast.show('Error unblocking user', 'danger');
        } finally {
            if (button) Loader.quick(button, 'hide');
        }
    }
}

// Export singleton instance
const blockSystem = new BlockSystem();
export default blockSystem;

// Make available globally
window.BlockSystem = blockSystem;