// === theme.js — Alternância de tema claro/escuro ===
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var root = document.documentElement;
        var body = document.body;
        var isAuthenticatedPage = body.classList.contains('is-authenticated');
        var themeToggleButton = document.getElementById('appThemeToggle');
        var themeToggleIcon = document.getElementById('appThemeToggleIcon');
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
            if (!themeToggleButton || !themeToggleIcon) return;
            var isDarkTheme = themeName === 'dark';
            themeToggleButton.classList.toggle('is-dark', isDarkTheme);
            themeToggleButton.setAttribute('aria-pressed', isDarkTheme ? 'true' : 'false');
            themeToggleButton.setAttribute('title', isDarkTheme ? 'Ativar modo claro' : 'Ativar modo escuro');
            themeToggleButton.setAttribute('aria-label', isDarkTheme ? 'Ativar modo claro' : 'Ativar modo escuro');
            themeToggleIcon.classList.remove('fa-moon', 'fa-sun');
            themeToggleIcon.classList.add(isDarkTheme ? 'fa-moon' : 'fa-sun');
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

        if (isAuthenticatedPage && themeToggleButton) {
            themeToggleButton.addEventListener('click', function () {
                var currentTheme = normalizeTheme(root.getAttribute('data-theme'));
                var nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
                applyTheme(nextTheme, true);
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
