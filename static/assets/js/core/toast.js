// ========================================
// TOAST NOTIFICATIONS
// ========================================

class Toast {
    static show(message, type = 'info', duration = 3000) {
        // Remove existing toasts to prevent stacking
        const existingToasts = document.querySelectorAll('.toast-notification');
        existingToasts.forEach(toast => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        });

        const toast = document.createElement('div');
        toast.className = `toast-notification fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-strong text-white animate-fade-in ${
            type === 'success' ? 'bg-green-500' :
            type === 'danger' ? 'bg-red-500' :
            type === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'
        }`;
        toast.textContent = message;
        toast.setAttribute('role', 'alert');
        document.body.appendChild(toast);

        // Auto-remove after duration
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-10px)';
            setTimeout(() => toast.remove(), 300);
        }, duration);

        return toast;
    }

    static success(message) {
        return this.show(message, 'success');
    }

    static error(message) {
        return this.show(message, 'danger');
    }

    static warning(message) {
        return this.show(message, 'warning');
    }

    static info(message) {
        return this.show(message, 'info');
    }
}

export default Toast;