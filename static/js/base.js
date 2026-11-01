/**
 * BASE / GLOBAL INTERACTION ENGINE
 * Pamamahala sa scroll progress, page entry animations, history navigation, at password toggles
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Suriin kung Naka-enable ang Reduced Motion sa Operating System ng User
    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // 2. IntersectionObserver para sa Smooth Page Entrance Animations
    var pageSections = document.querySelectorAll("[data-page-enter]");
    if (!reducedMotion && "IntersectionObserver" in window) {
        var pageObserver = new IntersectionObserver(
            function (entries, observer) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("is-visible");
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.08 }
        );
        pageSections.forEach(function (section) {
            section.classList.add("page-enter");
            pageObserver.observe(section);
        });
    } else {
        pageSections.forEach(function (section) {
            section.classList.add("page-enter", "is-visible");
        });
    }

    // 3. Scroll Progress Indicator at Back-to-Top Button Handler
    var backToTop = document.getElementById("back-to-top");
    var scrollProgress = document.getElementById("scroll-progress");
    var scrollUpdatePending = false;

    window.addEventListener(
        "scroll",
        function () {
            if (scrollUpdatePending) return;
            scrollUpdatePending = true;
            window.requestAnimationFrame(function () {
                var scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
                var scrollPercent = scrollableHeight > 0 ? window.scrollY / scrollableHeight : 0;

                if (scrollProgress) {
                    scrollProgress.style.transform = "scaleX(" + Math.min(1, Math.max(0, scrollPercent)) + ")";
                }
                if (backToTop) {
                    backToTop.classList.toggle("hidden", window.scrollY < 420);
                }
                scrollUpdatePending = false;
            });
        },
        { passive: true }
    );

    if (backToTop) {
        backToTop.addEventListener("click", function () {
            window.scrollTo({
                top: 0,
                behavior: reducedMotion ? "auto" : "smooth"
            });
        });
    }

    // 4. Browser History Back / Forward Navigation Buttons
    var historyBack = document.querySelector("[data-history-back]");
    var historyForward = document.querySelector("[data-history-forward]");

    if (historyBack) {
        historyBack.disabled = window.history.length < 2;
        historyBack.addEventListener("click", function () {
            window.history.back();
        });
    }

    if (historyForward) {
        historyForward.addEventListener("click", function () {
            window.history.forward();
        });
    }

    // I-trigger ang paunang scroll event para maayos ang progress bar sa pag-load
    window.dispatchEvent(new Event("scroll"));

    // 5. Password Field Toggle (Show / Hide Password) Functionality
    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-password-toggle]");
        if (!btn) return;

        var input = btn.parentElement.querySelector("input");
        if (!input) return;

        var show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.setAttribute("aria-pressed", show ? "true" : "false");
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");

        var eyeOpen = btn.querySelector("[data-eye-open]");
        var eyeClosed = btn.querySelector("[data-eye-closed]");

        if (eyeOpen) eyeOpen.classList.toggle("hidden", show);
        if (eyeClosed) eyeClosed.classList.toggle("hidden", !show);
    });
});