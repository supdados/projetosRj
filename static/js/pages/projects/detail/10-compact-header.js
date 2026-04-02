(function () {
    const page = window.ProjectDetailPage;
    if (!page || typeof page.registerInit !== 'function') {
        return;
    }

    page.registerInit('compactHeader', function initCompactHeader(currentPage) {
        const refs = currentPage.refs;
        const shared = currentPage.shared;

        let compactHeaderObserver = null;
        let compactHeaderFallbackRaf = null;
        let compactHeaderPageReadyObserver = null;
        let compactHeaderTopnavResizeObserver = null;
        let compactHeaderTrackingStarted = false;
        let compactHeaderUsesFallback = false;
        let compactHeaderFallbackBound = false;

        function syncCompactHeaderOffset() {
            const compactTop = shared.getTopNavOffset();
            document.documentElement.style.setProperty('--project-compact-top', `${compactTop}px`);
            return compactTop;
        }

        function canUseCompactHeader() {
            if (!refs.projectMainHeader || !refs.projectCompactHeader || !refs.projectHeaderSentinel) {
                return false;
            }
            if (window.innerWidth <= 991.98) {
                return false;
            }
            if (refs.projectCompactHeader.classList.contains('is-hidden-by-edit')) {
                return false;
            }
            return true;
        }

        function forceCompactHeaderHidden() {
            if (!refs.projectCompactHeader) {
                return;
            }
            refs.projectCompactHeader.classList.remove('is-visible');
            refs.projectCompactHeader.setAttribute('aria-hidden', 'true');
        }

        function setCompactHeaderVisible(shouldShow) {
            if (!refs.projectCompactHeader) {
                return;
            }
            const visible = Boolean(shouldShow && canUseCompactHeader());
            refs.projectCompactHeader.classList.toggle('is-visible', visible);
            refs.projectCompactHeader.setAttribute('aria-hidden', visible ? 'false' : 'true');
        }

        function applyCompactHeaderVisibilityBySentinelState(sentinelIsIntersecting, compactTop) {
            if (typeof compactTop !== 'number') {
                syncCompactHeaderOffset();
            }
            setCompactHeaderVisible(!sentinelIsIntersecting);
        }

        function updateCompactHeaderBySentinelFallback() {
            if (!refs.projectHeaderSentinel) {
                setCompactHeaderVisible(false);
                return;
            }
            const compactTop = syncCompactHeaderOffset();
            const sentinelRect = refs.projectHeaderSentinel.getBoundingClientRect();
            const sentinelIsIntersecting = sentinelRect.bottom > compactTop && sentinelRect.top < window.innerHeight;
            applyCompactHeaderVisibilityBySentinelState(sentinelIsIntersecting, compactTop);
        }

        function requestFallbackUpdate() {
            if (compactHeaderFallbackRaf) {
                return;
            }
            compactHeaderFallbackRaf = window.requestAnimationFrame(function () {
                compactHeaderFallbackRaf = null;
                updateCompactHeaderBySentinelFallback();
            });
        }

        function bindFallbackScrollListener() {
            if (compactHeaderFallbackBound) {
                return;
            }
            window.addEventListener('scroll', requestFallbackUpdate, { passive: true });
            compactHeaderFallbackBound = true;
        }

        function unbindFallbackScrollListener() {
            if (!compactHeaderFallbackBound) {
                return;
            }
            window.removeEventListener('scroll', requestFallbackUpdate);
            compactHeaderFallbackBound = false;
        }

        function createIntersectionObserverTracking() {
            if (!('IntersectionObserver' in window) || !refs.projectHeaderSentinel) {
                return false;
            }
            const compactTop = syncCompactHeaderOffset();
            compactHeaderObserver = new IntersectionObserver(
                function (entries) {
                    const entry = entries && entries[0];
                    if (!entry) {
                        return;
                    }
                    const offset = syncCompactHeaderOffset();
                    applyCompactHeaderVisibilityBySentinelState(entry.isIntersecting, offset);
                },
                {
                    root: null,
                    threshold: 0,
                    rootMargin: `-${compactTop}px 0px 0px 0px`,
                }
            );
            compactHeaderObserver.observe(refs.projectHeaderSentinel);
            return true;
        }

        function destroyCompactHeaderTracking() {
            if (compactHeaderObserver) {
                compactHeaderObserver.disconnect();
                compactHeaderObserver = null;
            }
            unbindFallbackScrollListener();
            if (compactHeaderFallbackRaf) {
                window.cancelAnimationFrame(compactHeaderFallbackRaf);
                compactHeaderFallbackRaf = null;
            }
            if (compactHeaderTopnavResizeObserver) {
                compactHeaderTopnavResizeObserver.disconnect();
                compactHeaderTopnavResizeObserver = null;
            }
        }

        function refreshCompactHeaderTracking() {
            if (!compactHeaderTrackingStarted) {
                return;
            }
            destroyCompactHeaderTracking();
            compactHeaderUsesFallback = !createIntersectionObserverTracking();
            if (compactHeaderUsesFallback) {
                bindFallbackScrollListener();
                requestFallbackUpdate();
                return;
            }
            updateCompactHeaderBySentinelFallback();
        }

        function onViewportChanged() {
            if (!compactHeaderTrackingStarted) {
                return;
            }
            refreshCompactHeaderTracking();
        }

        function startCompactHeaderTracking() {
            if (compactHeaderTrackingStarted) {
                return;
            }
            compactHeaderTrackingStarted = true;
            setCompactHeaderVisible(false);
            refreshCompactHeaderTracking();
            window.addEventListener('resize', onViewportChanged);
            window.addEventListener('orientationchange', onViewportChanged);

            if ('ResizeObserver' in window) {
                const topNav = document.querySelector('.app-topnav');
                if (topNav) {
                    compactHeaderTopnavResizeObserver = new ResizeObserver(function () {
                        onViewportChanged();
                    });
                    compactHeaderTopnavResizeObserver.observe(topNav);
                }
            }
        }

        function waitForPageReadyAndStartCompactHeader() {
            forceCompactHeaderHidden();
            if (document.body.classList.contains('page-ready')) {
                window.requestAnimationFrame(function () {
                    window.requestAnimationFrame(function () {
                        startCompactHeaderTracking();
                    });
                });
                return;
            }

            compactHeaderPageReadyObserver = new MutationObserver(function () {
                if (!document.body.classList.contains('page-ready')) {
                    return;
                }
                if (compactHeaderPageReadyObserver) {
                    compactHeaderPageReadyObserver.disconnect();
                    compactHeaderPageReadyObserver = null;
                }
                window.requestAnimationFrame(function () {
                    window.requestAnimationFrame(function () {
                        startCompactHeaderTracking();
                    });
                });
            });
            compactHeaderPageReadyObserver.observe(document.body, {
                attributes: true,
                attributeFilter: ['class'],
            });
        }

        shared.setCompactHeaderVisible = setCompactHeaderVisible;
        waitForPageReadyAndStartCompactHeader();

        window.addEventListener('pageshow', function (event) {
            if (!compactHeaderTrackingStarted) {
                return;
            }
            if (event.persisted) {
                forceCompactHeaderHidden();
                refreshCompactHeaderTracking();
            }
        });
    });
})();
