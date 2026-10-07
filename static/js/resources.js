// Member Hub (/resources): library search and shelf filter, per-viewer stars,
// and the drivetrain calculator.
//
// Stars and the last calculator setup live in this browser only (localStorage).
// Everything still works when storage is blocked; nothing is remembered.

(function () {
    'use strict';

    const store = {
        get(key, fallback) {
            try {
                const raw = localStorage.getItem(key);
                return raw ? JSON.parse(raw) : fallback;
            } catch (e) {
                return fallback;
            }
        },
        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
            } catch (e) { /* private window or blocked storage */ }
        },
    };

    // --- Library ----------------------------------------------------------------------

    function initLibrary() {
        const library = document.getElementById('hub-library');
        const search = document.getElementById('hub-q');
        if (!library || !search) return;

        const rows = [...library.querySelectorAll('[data-row]')];
        const boxes = [...library.querySelectorAll('[data-shelf-box]')];
        const chips = [...document.querySelectorAll('.hub-bar [data-shelf]')];
        const empty = document.getElementById('hub-empty');
        const starCount = document.querySelector('[data-star-count]');
        let stars = new Set(store.get('hub-stars', []));
        let shelf = '';

        function paintStars() {
            document.querySelectorAll('[data-star]').forEach(btn => {
                const on = stars.has(btn.dataset.star);
                btn.setAttribute('aria-pressed', String(on));
                btn.closest('[data-row]').classList.toggle('is-starred', on);
            });
            // Links an admin removed since they were starred no longer count.
            const live = new Set(rows.map(r => r.dataset.url));
            starCount.textContent = [...stars].filter(url => live.has(url)).length;
        }

        function apply() {
            const q = search.value.trim().toLowerCase();
            const words = q.split(/\s+/).filter(Boolean);
            let shown = 0;
            rows.forEach(row => {
                const inShelf = !shelf || (shelf === 'starred' ? stars.has(row.dataset.url) : row.dataset.shelf === shelf);
                const match = words.every(w => row.dataset.text.includes(w));
                row.hidden = !(inShelf && match);
                if (!row.hidden) shown++;
            });
            boxes.forEach(box => {
                box.hidden = !box.querySelector('[data-row]:not([hidden])');
            });
            library.classList.toggle('is-filtered', Boolean(q || shelf));
            empty.hidden = shown > 0;
            empty.querySelector('[data-empty-search]').hidden = !q;
            empty.querySelector('[data-empty-stars]').hidden = Boolean(q) || shelf !== 'starred';
            empty.querySelector('[data-empty-q]').textContent = search.value.trim();
        }

        chips.forEach(chip => chip.addEventListener('click', () => {
            shelf = chip.dataset.shelf;
            chips.forEach(c => {
                c.classList.toggle('is-on', c === chip);
                c.setAttribute('aria-pressed', String(c === chip));
            });
            apply();
        }));

        library.addEventListener('click', event => {
            const btn = event.target.closest('[data-star]');
            if (!btn) return;
            const url = btn.dataset.star;
            if (stars.has(url)) stars.delete(url); else stars.add(url);
            store.set('hub-stars', [...stars]);
            btn.classList.remove('is-popping');
            void btn.offsetWidth;
            btn.classList.add('is-popping');
            paintStars();
            if (shelf === 'starred') apply();
        });

        search.addEventListener('input', apply);
        search.addEventListener('keydown', event => {
            if (event.key === 'Escape' && search.value) {
                search.value = '';
                apply();
            } else if (event.key === 'Enter') {
                const first = rows.find(r => !r.hidden);
                if (first) first.querySelector('a').click();
            }
        });

        // "/" jumps to the search box, unless someone is typing somewhere already.
        document.addEventListener('keydown', event => {
            if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
            const el = document.activeElement;
            if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
            event.preventDefault();
            search.focus();
            search.select();
        });

        paintStars();
    }

    // --- Drivetrain calculator --------------------------------------------------------

    // V5 Smart Motor stall torque at the output shaft for each cartridge, in N·m.
    const STALL_TORQUE = { 100: 2.1, 200: 1.05, 600: 0.35 };
    const FIELD_INCHES = 144;
    const NEWTONS_TO_LBF = 0.224809;
    const INCH_TO_M = 0.0254;

    function initCalculator() {
        const calc = document.querySelector('[data-calc]');
        if (!calc) return;
        const form = calc.querySelector('form');
        const out = name => calc.querySelector(`[data-out="${name}"]`);
        const dot = calc.querySelector('[data-balance]');

        function read() {
            const data = new FormData(form);
            return ['rpm', 'drive', 'driven', 'wheel', 'motors'].map(k => data.get(k));
        }

        function write(values) {
            const [rpm, drive, driven, wheel, motors] = values;
            const radio = form.querySelector(`input[name="rpm"][value="${rpm}"]`);
            if (radio) radio.checked = true;
            [['drive', drive], ['driven', driven], ['wheel', wheel], ['motors', motors]].forEach(([name, value]) => {
                const select = form.elements[name];
                if ([...select.options].some(o => o.value === String(value)) && select.value !== String(value)) {
                    select.value = String(value);
                    // controls.js listens for change to redraw its custom menu.
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }

        function update() {
            const [rpmRaw, driveRaw, drivenRaw, wheelRaw, motorsRaw] = read();
            const rpm = Number(rpmRaw), wheel = Number(wheelRaw), motors = Number(motorsRaw);
            let drive = Number(driveRaw), driven = Number(drivenRaw);
            // Direct drive on either end means no gears at all.
            if (drive === 1 || driven === 1) drive = driven = 1;

            const wheelRpm = rpm * drive / driven;
            const inchesPerSecond = wheelRpm * Math.PI * wheel / 60;
            const fps = inchesPerSecond / 12;
            const wheelTorque = STALL_TORQUE[rpm] * driven / drive;
            const pushN = motors * wheelTorque / (wheel * INCH_TO_M / 2);

            out('fps').textContent = fps.toFixed(1);
            out('cross').textContent = (FIELD_INCHES / inchesPerSecond).toFixed(1);
            out('wheel').textContent = Math.round(wheelRpm);
            out('ratio').textContent = drive === 1 ? 'Direct' : `${drive}:${driven}`;
            out('push').textContent = Math.round(pushN * NEWTONS_TO_LBF);
            // 2 ft/s reads as all torque, 10 ft/s as all speed.
            const pct = Math.min(1, Math.max(0, (fps - 2) / 8));
            dot.style.setProperty('--pos', `${(pct * 100).toFixed(1)}%`);

            store.set('hub-calc', read());
        }

        calc.querySelectorAll('[data-preset]').forEach(btn => btn.addEventListener('click', () => {
            write(btn.dataset.preset.split(','));
            update();
        }));
        form.addEventListener('submit', event => event.preventDefault());
        form.addEventListener('change', update);
        form.addEventListener('input', update);

        const saved = store.get('hub-calc', null);
        if (Array.isArray(saved) && saved.length === 5) write(saved);
        update();
    }

    function init() {
        initLibrary();
        initCalculator();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
}());
