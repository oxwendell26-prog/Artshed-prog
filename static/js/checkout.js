/**
 * CHECKOUT PAGE INTERACTION ENGINE
 * Pamamahala sa mga interaksyon, validation, at double-submit prevention
 * sa checkout page para sa Escrow System.
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('Checkout script loaded successfully.');

    const checkoutForm = document.querySelector('.checkout-form');
    const submitBtn = document.querySelector('.checkout-submit-btn');

    if (checkoutForm && submitBtn) {
        checkoutForm.addEventListener('submit', function (e) {
            // Check valid phone number format (basic client-side check)
            const phoneInput = document.getElementById('phone');
            if (phoneInput) {
                const phoneVal = phoneInput.value.trim();
                const phoneRegex = /^[0-9+()\-\s]{7,20}$/;
                if (!phoneRegex.test(phoneVal)) {
                    alert('Please enter a valid phone number so we can coordinate your order.');
                    phoneInput.focus();
                    e.preventDefault();
                    return;
                }
            }

            // Iwas sa double-submission kapag napindot na ang order button
            submitBtn.disabled = true;
            submitBtn.textContent = 'Processing Escrow Order...';
        });
    }
});