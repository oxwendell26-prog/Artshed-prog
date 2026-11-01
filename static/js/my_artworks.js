/**
 * MY ARTWORKS GALLERY INTERACTION ENGINE
 * Pamamahala sa mga interaksyon at modal para sa gallery ng mga sining ng artist
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('My Artworks Gallery script loaded successfully.');
});

function openAddArtworkModal() {
    const modal = document.getElementById('addArtworkModal');
    if (modal) modal.classList.remove('hidden');
}

function closeAddArtworkModal() {
    const modal = document.getElementById('addArtworkModal');
    if (modal) modal.classList.add('hidden');
}