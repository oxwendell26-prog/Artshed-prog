/**
 * ARTIST DASHBOARD PROFILE INTERACTION ENGINE
 * Pamamahala sa image viewer lightbox at post feed modals
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('Artist Dashboard script loaded successfully.');
});

function openImageViewer(src) {
    if (!src) return;
    document.getElementById('fullSizeImage').src = src;
    document.getElementById('imageViewerModal').classList.remove('hidden');
}

function closeImageViewer() {
    document.getElementById('imageViewerModal').classList.add('hidden');
}