/**
 * MACROS INTERACTION ENGINE
 * Pamamahala sa password visibility toggle (show/hide password) para sa field macro
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('Macros script loaded successfully.');

    // Pamamahala sa lahat ng password eye toggle buttons sa buong app
    const toggleButtons = document.querySelectorAll('[data-password-toggle]');

    toggleButtons.forEach(button => {
        button.addEventListener('click', function () {
            const inputWrapper = button.parentElement;
            const passwordInput = inputWrapper.querySelector('input');

            if (!passwordInput) return;

            const eyeOpen = button.querySelector('[data-eye-open]');
            const eyeClosed = button.querySelector('[data-eye-closed]');

            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                button.setAttribute('aria-label', 'Hide password');
                button.setAttribute('aria-pressed', 'true');
                if (eyeOpen) eyeOpen.classList.add('hidden');
                if (eyeClosed) eyeClosed.classList.remove('hidden');
            } else {
                passwordInput.type = 'password';
                button.setAttribute('aria-label', 'Show password');
                button.setAttribute('aria-pressed', 'false');
                if (eyeOpen) eyeOpen.classList.remove('hidden');
                if (eyeClosed) eyeClosed.classList.add('hidden');
            }
        });
    });
});