// ========================================
// FILE UPLOAD HANDLING & MEDIA PREVIEW
// ========================================

import { config } from '../app/config.js';
import Toast from '../core/toast.js';
import Loader from '../core/loader.js';

class FileUpload {
    constructor() {
        this.csrfToken = config.getCsrfToken();
    }

    init() {
        // Setup event listeners for file input
        const mediaInput = document.getElementById('mediaInput');
        if (mediaInput) {
            mediaInput.addEventListener('change', (e) => this.handleFileSelection(e.target));
        }
    }

    handleFileSelection(input) {
        const preview = document.getElementById('mediaPreview');
        const uploadProgressContainer = document.getElementById('uploadProgressContainer');
        const uploadProgressBar = document.getElementById('uploadProgressBar');
        const uploadPercentage = document.getElementById('uploadPercentage');
        const uploadStatus = document.getElementById('uploadStatus');
        const uploadSpeed = document.getElementById('uploadSpeed');

        if (!input || !input.files || !input.files[0]) return;

        const file = input.files[0];

        // Clear previous preview
        if (preview) preview.innerHTML = '';

        // Validate file size (100MB limit)
        const maxSize = 100 * 1024 * 1024; // 100MB
        if (file.size > maxSize) {
            Toast.show(`File is too large! Maximum size is ${maxSize/(1024*1024)}MB`, 'danger');
            input.value = '';
            return;
        }

        // Show preview immediately
        this.showFilePreview(file, preview);

        // Show upload progress container
        if (uploadProgressContainer) {
            uploadProgressContainer.classList.remove('hidden');
            if (uploadProgressBar) uploadProgressBar.style.width = '0%';
            if (uploadPercentage) uploadPercentage.textContent = '0%';
            if (uploadStatus) uploadStatus.textContent = 'Ready to upload';
            if (uploadSpeed) uploadSpeed.textContent = '-';
        }
    }

    showFilePreview(file, previewContainer) {
        if (!file || !previewContainer) return;

        const isVideo = file.type.startsWith('video/');
        const isImage = file.type.startsWith('image/');
        const fileSize = this.formatFileSize(file.size);

        let previewHTML = '';

        if (isImage) {
            const reader = new FileReader();
            reader.onload = function(e) {
                previewContainer.innerHTML = `
                    <div class="file-preview relative rounded-xl overflow-hidden border border-gray-200">
                        <img src="${e.target.result}" alt="Preview" class="w-full h-48 object-cover">
                        <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                            <div class="text-white text-sm">
                                <div class="font-medium">${file.name}</div>
                                <div class="text-xs opacity-80">${fileSize} • ${file.type}</div>
                            </div>
                        </div>
                        <button type="button" onclick="removeFilePreview()" class="absolute top-2 right-2 w-8 h-8 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                            <i class="bi bi-x text-sm"></i>
                        </button>
                    </div>
                `;
            };
            reader.readAsDataURL(file);
        } else if (isVideo) {
            const url = URL.createObjectURL(file);
            previewContainer.innerHTML = `
                <div class="file-preview relative rounded-xl overflow-hidden border border-gray-200">
                    <video controls class="w-full h-48 object-cover bg-black">
                        <source src="${url}" type="${file.type}">
                    </video>
                    <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                        <div class="text-white text-sm">
                            <div class="font-medium">${file.name}</div>
                            <div class="text-xs opacity-80">${fileSize} • ${file.type}</div>
                            <div id="videoUploadProgress" class="mt-1">
                                <div class="w-full bg-gray-700 rounded-full h-1">
                                    <div id="videoProgressBar" class="h-1 bg-blue-500 rounded-full" style="width: 0%"></div>
                                </div>
                                <div class="flex justify-between text-xs mt-1">
                                    <span id="videoProgressText">0%</span>
                                    <span id="videoTimeRemaining">-</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    <button type="button" onclick="removeFilePreview()" class="absolute top-2 right-2 w-8 h-8 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                        <i class="bi bi-x text-sm"></i>
                    </button>
                </div>
            `;

            // Simulate video upload progress
            this.simulateVideoUploadProgress();
        } else {
            previewContainer.innerHTML = `
                <div class="file-preview bg-gray-100 rounded-xl p-4 border border-gray-200">
                    <div class="flex items-center">
                        <div class="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-3">
                            <i class="bi bi-file-earmark text-blue-600 text-xl"></i>
                        </div>
                        <div>
                            <div class="font-medium truncate">${file.name}</div>
                            <div class="text-sm text-gray-500">${fileSize} • ${file.type}</div>
                        </div>
                        <button type="button" onclick="removeFilePreview()" class="ml-auto w-8 h-8 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors">
                            <i class="bi bi-x text-sm"></i>
                        </button>
                    </div>
                </div>
            `;
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    simulateVideoUploadProgress() {
        const videoProgressBar = document.getElementById('videoProgressBar');
        const videoProgressText = document.getElementById('videoProgressText');
        const videoTimeRemaining = document.getElementById('videoTimeRemaining');
        const uploadProgressBar = document.getElementById('uploadProgressBar');
        const uploadPercentage = document.getElementById('uploadPercentage');
        const uploadStatus = document.getElementById('uploadStatus');
        const uploadSpeed = document.getElementById('uploadSpeed');

        if (!videoProgressBar) return;

        let progress = 0;
        const interval = setInterval(() => {
            progress += Math.random() * 10;
            if (progress > 100) progress = 100;

            // Update both progress bars
            if (videoProgressBar) videoProgressBar.style.width = progress + '%';
            if (videoProgressText) videoProgressText.textContent = Math.round(progress) + '%';
            if (uploadProgressBar) uploadProgressBar.style.width = progress + '%';
            if (uploadPercentage) uploadPercentage.textContent = Math.round(progress) + '%';

            // Update status and speed
            if (uploadStatus) {
                if (progress < 100) {
                    uploadStatus.textContent = 'Uploading...';
                } else {
                    uploadStatus.textContent = 'Upload complete!';
                }
            }

            // Simulate upload speed
            if (uploadSpeed && progress < 100) {
                const speeds = ['500 KB/s', '1.2 MB/s', '800 KB/s', '2.1 MB/s', '1.5 MB/s'];
                const randomSpeed = speeds[Math.floor(Math.random() * speeds.length)];
                uploadSpeed.textContent = randomSpeed;
            }

            // Simulate time remaining
            if (videoTimeRemaining && progress < 100) {
                const times = ['30s remaining', '1m remaining', '45s remaining', '2m remaining'];
                const randomTime = times[Math.floor(Math.random() * times.length)];
                videoTimeRemaining.textContent = randomTime;
            }

            if (progress >= 100) {
                clearInterval(interval);
                if (uploadStatus) uploadStatus.textContent = 'Processing video...';
                setTimeout(() => {
                    if (uploadStatus) uploadStatus.textContent = 'Ready to post!';
                    if (uploadSpeed) uploadSpeed.textContent = 'Complete';
                    if (videoTimeRemaining) videoTimeRemaining.textContent = 'Ready';
                }, 1500);
            }
        }, 300);
    }

    removeFilePreview() {
        const previewContainer = document.getElementById('mediaPreview');
        const fileInput = document.getElementById('mediaInput');
        const uploadProgressContainer = document.getElementById('uploadProgressContainer');

        if (previewContainer) {
            previewContainer.innerHTML = '';
        }

        if (fileInput) {
            fileInput.value = '';
        }

        if (uploadProgressContainer) {
            uploadProgressContainer.classList.add('hidden');
        }

        Toast.show('File removed', 'info');
    }

    previewMedia(input) {
        const preview = document.getElementById('mediaPreview') || document.getElementById('editMediaPreview');
        if (!preview) return;

        preview.innerHTML = '';
        const file = input.files[0];
        if (!file) return;

        preview.innerHTML = `
            <div class="flex items-center justify-center p-3 bg-gray-50 rounded-xl">
                <span class="tiny-loader sm"></span>
                <span class="ml-2 text-gray-600 text-xs">Preparing...</span>
            </div>
        `;

        setTimeout(() => {
            const url = URL.createObjectURL(file);
            const isVideo = file.type.startsWith('video/');
            const el = isVideo ? document.createElement('video') : document.createElement('img');

            el.src = url;
            if (isVideo) el.controls = true;
            el.className = 'w-full h-48 rounded-lg object-cover border border-gray-200';

            preview.innerHTML = '';
            preview.appendChild(el);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'mt-2 px-3 py-1.5 bg-red-100 text-red-600 text-xs rounded-lg hover:bg-red-200 transition-colors flex items-center';
            removeBtn.innerHTML = '<i class="bi bi-trash mr-1"></i> Remove';
            removeBtn.onclick = () => {
                preview.innerHTML = '';
                input.value = '';
            };

            preview.appendChild(removeBtn);
        }, 300);
    }

    async uploadWithProgress(form, submitBtn) {
        const formData = new FormData(form);
        const postContent = formData.get('post_content');
        const mediaFile = formData.get('media');

        if (!postContent && !mediaFile) {
            Toast.show('Please add some content or media to your post', 'warning');
            return false;
        }

        const xhr = new XMLHttpRequest();

        // Show progress UI
        this.showUploadProgress(mediaFile);

        return new Promise((resolve, reject) => {
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    this.updateProgress(percentComplete, e.loaded, e.total);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            Toast.show('Post created successfully!', 'success');
                            setTimeout(() => location.reload(), 1500);
                            resolve(true);
                        } else {
                            Toast.show(response.error || 'Failed to create post', 'danger');
                            reject(new Error(response.error));
                        }
                    } catch (e) {
                        // If response is HTML (regular form submit), reload page
                        Toast.show('Post created!', 'success');
                        setTimeout(() => location.reload(), 1000);
                        resolve(true);
                    }
                } else {
                    Toast.show('Upload failed. Please try again.', 'danger');
                    reject(new Error('Upload failed'));
                }
                this.hideUploadProgress();
            });

            xhr.addEventListener('error', () => {
                Toast.show('Network error. Please check your connection.', 'danger');
                this.hideUploadProgress();
                reject(new Error('Network error'));
            });

            xhr.open('POST', form.action);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        });
    }

    showUploadProgress(file) {
        const progressContainer = document.getElementById('uploadProgressContainer');
        const fileName = document.getElementById('uploadFileName');

        if (progressContainer) {
            progressContainer.classList.remove('hidden');
        }

        if (fileName && file) {
            fileName.textContent = file.name;
        }

        // Show video processing details if it's a video
        const videoDetails = document.getElementById('videoUploadDetails');
        if (videoDetails && file && file.type.startsWith('video/')) {
            videoDetails.classList.remove('hidden');
        }
    }

    updateProgress(percent, loaded, total) {
        const progressBar = document.getElementById('uploadProgressBar');
        const percentage = document.getElementById('uploadPercentage');
        const status = document.getElementById('uploadStatus');
        const speed = document.getElementById('uploadSpeed');
        const timeRemaining = document.getElementById('uploadTimeRemaining');

        if (progressBar) {
            progressBar.style.width = percent + '%';
        }

        if (percentage) {
            percentage.textContent = Math.round(percent) + '%';
        }

        if (status) {
            if (percent < 100) {
                status.textContent = 'Uploading...';
            } else {
                status.textContent = 'Processing...';
            }
        }

        // Calculate upload speed
        if (speed) {
            const uploadSpeed = this.calculateSpeed(loaded, total, percent);
            speed.textContent = uploadSpeed;
        }

        // Calculate time remaining
        if (timeRemaining && percent < 100) {
            const remaining = this.calculateTimeRemaining(loaded, total, percent);
            timeRemaining.textContent = remaining;
        }

        // Update video processing progress if needed
        if (percent >= 100) {
            this.simulateVideoProcessing();
        }
    }

    calculateSpeed(loaded, total, percent) {
        // Simulate speed calculation
        const speeds = ['500 KB/s', '750 KB/s', '1.2 MB/s', '850 KB/s', '2.1 MB/s', '1.5 MB/s'];
        return speeds[Math.floor(Math.random() * speeds.length)];
    }

    calculateTimeRemaining(loaded, total, percent) {
        if (percent === 0) return 'Calculating...';

        const remainingBytes = total - loaded;
        const bytesPerPercent = loaded / percent;
        const remainingPercent = 100 - percent;
        const remainingBytes2 = bytesPerPercent * remainingPercent;

        // Estimate time (very rough estimate)
        const secondsRemaining = Math.round(remainingBytes2 / (1024 * 500)); // Assume 500KB/s

        if (secondsRemaining < 60) {
            return `${secondsRemaining}s remaining`;
        } else {
            const minutes = Math.floor(secondsRemaining / 60);
            const seconds = secondsRemaining % 60;
            return `${minutes}m ${seconds}s remaining`;
        }
    }

    simulateVideoProcessing() {
        const videoBar = document.getElementById('videoProcessingBar');
        const videoStatus = document.getElementById('videoProcessingStatus');

        if (!videoBar || !videoStatus) return;

        let progress = 0;
        const interval = setInterval(() => {
            progress += 2;
            if (progress > 100) progress = 100;

            videoBar.style.width = progress + '%';

            if (progress < 30) videoStatus.textContent = 'Analyzing...';
            else if (progress < 60) videoStatus.textContent = 'Encoding...';
            else if (progress < 90) videoStatus.textContent = 'Optimizing...';
            else videoStatus.textContent = 'Finalizing...';

            if (progress >= 100) {
                clearInterval(interval);
                videoStatus.textContent = 'Complete!';
                videoStatus.className = 'text-green-600 font-medium';
            }
        }, 100);
    }

    hideUploadProgress() {
        const progressContainer = document.getElementById('uploadProgressContainer');
        if (progressContainer) {
            setTimeout(() => {
                progressContainer.classList.add('hidden');
            }, 2000);
        }
    }

    cancelUpload() {
        // In a real implementation, you would abort the XHR request
        const progressContainer = document.getElementById('uploadProgressContainer');
        const preview = document.getElementById('mediaPreview');
        const fileInput = document.getElementById('mediaInput');

        if (progressContainer) progressContainer.classList.add('hidden');
        if (preview) preview.innerHTML = '';
        if (fileInput) fileInput.value = '';

        Toast.show('Upload cancelled', 'info');
    }

    validateAndOpenFilePicker() {
        const fileInput = document.getElementById('mediaInput');
        if (fileInput) {
            fileInput.click();
        }
    }
}

// Export singleton instance
const fileUpload = new FileUpload();
export default fileUpload;

// Initialize file upload
export function initFileUpload() {
    fileUpload.init();
}

// Make available globally for HTML onclick
window.previewMedia = (input) => fileUpload.previewMedia(input);
window.removeFilePreview = () => fileUpload.removeFilePreview();
window.cancelUpload = () => fileUpload.cancelUpload();
window.validateAndOpenFilePicker = () => fileUpload.validateAndOpenFilePicker();