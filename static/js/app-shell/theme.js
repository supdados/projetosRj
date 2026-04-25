// === theme.js — Alternância de tema claro/escuro ===
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var root = document.documentElement;
        var body = document.body;
        var isAuthenticatedPage = body.classList.contains('is-authenticated');
        var themeToggleInput = document.getElementById('appThemeToggle');
        var themeColorMeta = document.querySelector('meta[name="theme-color"]');
        var themeStorageKey = 'projetosrj.theme';
        var themeColorByMode = { light: '#005A92', dark: '#273447' };
        var darkMediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

        function normalizeTheme(themeName) {
            return themeName === 'dark' ? 'dark' : 'light';
        }

        function readStoredTheme() {
            try {
                var storedTheme = window.localStorage.getItem(themeStorageKey);
                return storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : null;
            } catch (error) {
                return null;
            }
        }

        var storedThemeOverride = readStoredTheme();

        function updateThemeColor(themeName) {
            if (!themeColorMeta) return;
            themeColorMeta.setAttribute('content', themeColorByMode[themeName] || themeColorByMode.light);
        }

        function updateThemeToggle(themeName) {
            if (!themeToggleInput) return;
            var isDarkTheme = themeName === 'dark';
            themeToggleInput.checked = isDarkTheme;
            themeToggleInput.setAttribute('aria-label', isDarkTheme ? 'Ativar modo claro' : 'Ativar modo escuro');
            var label = themeToggleInput.closest('.app-theme-switch');
            if (label) label.setAttribute('title', isDarkTheme ? 'Ativar modo claro' : 'Ativar modo escuro');
        }

        function applyTheme(themeName, persistChoice) {
            var normalizedTheme = normalizeTheme(themeName);
            root.setAttribute('data-theme', normalizedTheme);
            root.setAttribute('data-bs-theme', normalizedTheme);
            updateThemeColor(normalizedTheme);
            updateThemeToggle(normalizedTheme);

            if (!persistChoice) return;

            try {
                window.localStorage.setItem(themeStorageKey, normalizedTheme);
                storedThemeOverride = normalizedTheme;
            } catch (error) {
                /* noop */
            }
        }

        function resolveInitialTheme() {
            var attrTheme = root.getAttribute('data-theme');
            if (attrTheme === 'light' || attrTheme === 'dark') return attrTheme;
            if (storedThemeOverride) return storedThemeOverride;
            return darkMediaQuery && darkMediaQuery.matches ? 'dark' : 'light';
        }

        applyTheme(resolveInitialTheme(), false);

        if (isAuthenticatedPage && themeToggleInput) {
            themeToggleInput.addEventListener('change', function () {
                applyTheme(themeToggleInput.checked ? 'dark' : 'light', true);
            });
        }

        if (darkMediaQuery) {
            var onSystemThemeChange = function (event) {
                if (storedThemeOverride) return;
                applyTheme(event.matches ? 'dark' : 'light', false);
            };

            if (typeof darkMediaQuery.addEventListener === 'function') {
                darkMediaQuery.addEventListener('change', onSystemThemeChange);
            } else if (typeof darkMediaQuery.addListener === 'function') {
                darkMediaQuery.addListener(onSystemThemeChange);
            }
        }
    });
})();
