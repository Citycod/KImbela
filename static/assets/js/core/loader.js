// ========================================
// LOADER UTILITIES
// ========================================

class Loader {
    static show(element, options = {}) {
        if (!element) return null;

        const config = {
            type: 'tiny',
            size: 'sm',
            color: 'primary',
            position: 'append',
            text: '',
            preserveText: false,
            ...options
        };

        const originalContent = element.innerHTML;
        let loaderHTML = '';

        switch (config.type) {
            case 'dots':
                loaderHTML = '<span class="dots-loader"><span></span><span></span><span></span></span>';
                break;
            case 'bar':
                loaderHTML = '<span class="bar-loader"></span>';
                break;
            case 'pulse':
                loaderHTML = '<span class="pulse-loader"></span>';
                break;
            default:
                loaderHTML = `<span class="tiny-loader ${config.size}"></span>`;
        }

        if (config.text) {
            loaderHTML = `<span class="btn-loader">${loaderHTML}<span class="text-sm ml-1">${config.text}</span></span>`;
        } else if (config.preserveText) {
            const originalText = element.textContent.trim();
            loaderHTML = `<span class="btn-loader">${loaderHTML}<span class="text-sm ml-1">${originalText}</span></span>`;
        }

        element.dataset.originalContent = originalContent;
        element.dataset.loading = 'true';

        switch (config.position) {
            case 'prepend':
                element.innerHTML = loaderHTML + originalContent;
                break;
            case 'replace':
                element.innerHTML = loaderHTML;
                break;
            case 'inline':
                element.innerHTML = `<span class="inline-flex items-center gap-1">${loaderHTML}${originalContent}</span>`;
                break;
            default:
                element.innerHTML = originalContent + loaderHTML;
        }

        element.disabled = true;
        return element;
    }

    static hide(element) {
        if (!element) return null;

        if (element.dataset.loading === 'true') {
            element.innerHTML = element.dataset.originalContent || '';
            element.disabled = false;
            delete element.dataset.loading;
            delete element.dataset.originalContent;
        }
        return element;
    }

    static showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return null;

        const loader = document.createElement('div');
        loader.className = 'modal-loader';
        loader.innerHTML = '<span class="tiny-loader md"></span>';
        modal.appendChild(loader);
        return loader;
    }

    static hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        const loader = modal.querySelector('.modal-loader');
        if (loader) loader.remove();
    }

    static quick(button, action = 'show') {
        if (!button) return;

        if (action === 'show') {
            const originalText = button.innerHTML;
            button.dataset.originalText = originalText;
            button.innerHTML = `<span class="inline-flex items-center gap-1"><span class="tiny-loader xs white"></span>${button.textContent.trim()}</span>`;
            button.disabled = true;
        } else {
            if (button.dataset.originalText) {
                button.innerHTML = button.dataset.originalText;
                delete button.dataset.originalText;
            }
            button.disabled = false;
        }
    }
}

export default Loader;