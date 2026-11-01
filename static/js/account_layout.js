/**
 * ACCOUNT LAYOUT INTERACTION ENGINE
 * Pamamahala sa mga interactive na kaganapan para sa layout ng account
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Hanapin ang sidebar navigation container at ang aktibong link
    const navContainer = document.querySelector('.account-nav');
    const activeLink = document.querySelector('.account-nav-link.active');

    // 2. Awtomatikong i-scroll ang horizontal navigation papunta sa aktibong item kapag naka-mobile view
    if (navContainer && activeLink && window.innerWidth < 1024) {
        // Kukunin ang posisyon ng active link para ma-gitna ito sa scroll area
        const containerWidth = navContainer.offsetWidth;
        const linkOffsetLeft = activeLink.offsetLeft;
        const linkWidth = activeLink.offsetWidth;

        // I-scroll ang navigation patungo sa eksaktong kinaroroonan ng aktibong button
        navContainer.scrollTo({
            left: linkOffsetLeft - (containerWidth / 2) + (linkWidth / 2),
            behavior: 'smooth' // Mabilis at swabeng pag-scroll
        });
    }
});