/**
 * CONVERSATION CHAT INTERACTION ENGINE
 * Pamamahala sa mga interaksyon at auto-scroll para sa pahina ng usapan
 */

document.addEventListener('DOMContentLoaded', function () {
    console.log('Conversation Chat script loaded successfully.');

    // Opsyonal: Awtomatikong i-scroll pababa sa pinakabagong mensahe
    window.scrollTo({
        top: document.body.scrollHeight,
        behavior: 'smooth'
    });
});