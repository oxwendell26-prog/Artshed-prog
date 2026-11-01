/**
 * ORDER STATUS INTERACTION ENGINE
 * Pamamahala sa pagkopya ng order status link, live preview ng payment proof,
 * at pagtiyak sa confirmation bago i-release ang escrow payment.
 */

document.addEventListener("DOMContentLoaded", function () {
    console.log('Order Status script loaded successfully.');

    // 1. Copy Link to Clipboard
    const copyBtn = document.getElementById("copy-link");
    if (copyBtn) {
        copyBtn.addEventListener("click", function () {
            const input = document.getElementById("order-link");
            if (!input) return;

            input.select();
            const setCopied = () => {
                copyBtn.textContent = "Copied!";
                setTimeout(() => {
                    copyBtn.textContent = "Copy link";
                }, 2000);
            };

            if (navigator.clipboard) {
                navigator.clipboard.writeText(input.value).then(setCopied, function () {
                    document.execCommand("copy");
                    setCopied();
                });
            } else {
                document.execCommand("copy");
                setCopied();
            }
        });
    }

    // 2. Live File Preview para sa Uploading Payment Proof
    const fileInput = document.getElementById("payment_proof");
    const previewContainer = document.getElementById("proof-preview-container");
    const previewImg = document.getElementById("proof-preview-img");

    if (fileInput && previewContainer && previewImg) {
        fileInput.addEventListener("change", function () {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    previewImg.setAttribute("src", e.target.result);
                    previewContainer.classList.remove("hidden");
                };
                reader.readAsDataURL(file);
            } else {
                previewContainer.classList.add("hidden");
                previewImg.setAttribute("src", "");
            }
        });
    }

    // 3. Confirmation Dialog bago kumpirmahin ang pagtanggap ng artwork (Escrow Release)
    const confirmForm = document.getElementById("confirm-received-form");
    if (confirmForm) {
        confirmForm.addEventListener("submit", function (e) {
            const isConfirmed = confirm(
                "Are you sure you have received and inspected the artwork?\n\nOnce confirmed, the escrow funds will be permanently released to the artist."
            );
            if (!isConfirmed) {
                e.preventDefault();
            }
        });
    }
});