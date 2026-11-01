/**
 * ADMIN LAYOUT INTERACTION ENGINE
 * Pamamahala sa interaksyon at horizontal scrolling ng admin sidebar sa mobile view
 */

document.addEventListener('DOMContentLoaded', function () {
    const layoutGrid = document.querySelector('.admin-layout-grid');
    const sidebarToggle = document.getElementById('admin-sidebar-toggle');
    const sidebar = document.getElementById('admin-sidebar');
    const toggleLabel = sidebarToggle && sidebarToggle.querySelector('.admin-sidebar-toggle-label');

    if (layoutGrid && sidebarToggle && sidebar && toggleLabel) {
        sidebarToggle.addEventListener('click', function () {
            const isExpanded = sidebarToggle.getAttribute('aria-expanded') === 'true';
            const shouldExpand = !isExpanded;

            layoutGrid.classList.toggle('sidebar-hidden', !shouldExpand);
            sidebarToggle.setAttribute('aria-expanded', String(shouldExpand));
            sidebar.setAttribute('aria-hidden', String(!shouldExpand));
            toggleLabel.textContent = shouldExpand ? 'Hide admin menu' : 'Show admin menu';
        });
    }

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