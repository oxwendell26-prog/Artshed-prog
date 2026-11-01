/**
 * EDIT PROFILE INTERACTION ENGINE
 * Pamamahala sa Cropper.js image cropping, cover photo/avatar upload, at fullscreen view modals
 */

let cropper = null;
let currentType = '';
let uploadCroppedImageUrl = '';

document.addEventListener('DOMContentLoaded', function () {
    console.log('Profile script loaded successfully.');
});

function initProfileCropper(uploadUrl) {
    uploadCroppedImageUrl = uploadUrl;
}

function openCropper(type) {
    currentType = type;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpg,image/jpeg,image/png,image/webp';

    input.onchange = e => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = event => {
                document.getElementById('imageToCrop').src = event.target.result;
                document.getElementById('cropperModal').style.display = 'flex';

                if (cropper) cropper.destroy();

                const image = document.getElementById('imageToCrop');
                cropper = new Cropper(image, {
                    aspectRatio: type === 'cover' ? 16 / 9 : 1,
                    viewMode: 1,
                });
            };
            reader.readAsDataURL(file);
        }
    };
    input.click();
}

function closeCropper() {
    document.getElementById('cropperModal').style.display = 'none';
    if (cropper) {
        cropper.destroy();
        cropper = null;
    }
}

function openFullscreen(src) {
    if (!src) return;
    document.getElementById('fullscreenImg').src = src;
    document.getElementById('fullscreenModal').style.display = 'flex';
}

function closeFullscreen() {
    document.getElementById('fullscreenModal').style.display = 'none';
}

// Bind crop & upload action
document.addEventListener('DOMContentLoaded', function () {
    const cropBtn = document.getElementById('cropAndUploadBtn');
    if (cropBtn) {
        cropBtn.onclick = function () {
            if (!cropper) return;

            cropper.getCroppedCanvas().toBlob(blob => {
                const formData = new FormData();
                formData.append('file', blob, 'cropped.jpg');
                formData.append('type', currentType);
                formData.append('csrf_token', window.profileCsrfToken || '');

                fetch(window.uploadCroppedImageEndpoint || '', {
                    method: 'POST',
                    body: formData
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            location.reload();
                        } else {
                            alert('Error uploading image.');
                        }
                    })
                    .catch(err => {
                        console.error('Error:', err);
                        alert('Error uploading image.');
                    });
            }, 'image/jpeg');
        };
    }
});