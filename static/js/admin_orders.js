/**
 * ADMIN ORDERS MANAGEMENT INTERACTION ENGINE
 * Pamamahala sa mga interaksyon, verification confirmation, 
 * at dynamic updates para sa listahan ng orders sa admin panel.
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('Admin Orders Management script loaded successfully.');

    // 1. Confirmation para sa Payment Verification & Escrow Lock
    const verifyForms = document.querySelectorAll('.admin-verify-payment-form');
    verifyForms.forEach(form => {
        form.addEventListener('submit', function (e) {
            const confirmed = confirm(
                "Verify this payment proof?\n\nThis will lock the funds in Escrow and notify the artist to ship the artwork."
            );
            if (!confirmed) {
                e.preventDefault();
            }
        });
    });

    // 2. Quick Search/Filter sa Admin Orders Table (kung marami ang orders)
    const searchInput = document.getElementById('admin-orders-search');
    const tableRows = document.querySelectorAll('.admin-orders-tbody .admin-orders-tr');

    if (searchInput && tableRows.length > 0) {
        searchInput.addEventListener('input', function () {
            const term = this.value.toLowerCase().trim();

            tableRows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(term)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }
});