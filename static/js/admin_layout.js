/**
 * ADMIN LAYOUT INTERACTION ENGINE
 * Pamamahala sa interaksyon at horizontal scrolling ng admin sidebar sa mobile view
 */

document.addEventListener('DOMContentLoaded', function () {
    const navContainer = document.querySelector('.admin-nav');
    const activeLink = document.querySelector('.admin-nav-link.active');

    // Awtomatikong i-scroll ang navigation patungo sa kasalukuyang aktibong link sa mobile view
    if (navContainer && activeLink && window.innerWidth < 1024) {
        const containerWidth = navContainer.offsetWidth;
        const linkOffsetLeft = activeLink.offsetLeft;
        const linkWidth = activeLink.offsetWidth;

        navContainer.scrollTo({
            left: linkOffsetLeft - (containerWidth / 2) + (linkWidth / 2),
            behavior: 'smooth'
        });
    }
});