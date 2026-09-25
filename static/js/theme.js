/*
 * Theme bootstrap.
 *
 * Loaded synchronously in <head> so the saved theme is on <html> before the
 * first paint — a deferred script would let a light flash through on dark.
 * The rest of the site's CSS keys off [data-theme="dark"].
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'mepham-theme';
    // Light is the default for every visitor; dark and 'follow my device'
    // are opt-in from the footer toggle, which cycles in this order.
    var MODES = ['light', 'dark', 'system'];
    var DEFAULT_MODE = 'light';

    function stored() {
        try {
            var value = localStorage.getItem(STORAGE_KEY);
            return MODES.indexOf(value) === -1 ? DEFAULT_MODE : value;
        } catch (err) {
            // Private mode or blocked storage: fall back to the default.
            return DEFAULT_MODE;
        }
    }

    function prefersDark() {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    function resolve(mode) {
        return mode === 'system' ? (prefersDark() ? 'dark' : 'light') : mode;
    }

    function apply(mode) {
        document.documentElement.setAttribute('data-theme', resolve(mode));
        document.documentElement.setAttribute('data-theme-mode', mode);
    }

    window.MephamTheme = {
        MODES: MODES,
        get: stored,
        resolve: resolve,
        apply: apply,
        set: function (mode) {
            if (MODES.indexOf(mode) === -1) {
                mode = DEFAULT_MODE;
            }
            try {
                localStorage.setItem(STORAGE_KEY, mode);
            } catch (err) {
                /* storage unavailable — the choice just won't persist */
            }
            apply(mode);
            return mode;
        },
        next: function () {
            return MODES[(MODES.indexOf(stored()) + 1) % MODES.length];
        }
    };

    apply(stored());

    // Follow the OS while the user is on "system".
    if (window.matchMedia) {
        var query = window.matchMedia('(prefers-color-scheme: dark)');
        var onChange = function () {
            if (stored() === 'system') {
                apply('system');
            }
        };
        if (query.addEventListener) {
            query.addEventListener('change', onChange);
        } else if (query.addListener) {
            query.addListener(onChange);
        }
    }
})();
