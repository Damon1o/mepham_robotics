// Events page (/events): type filter, the day view under the month grid, the
// "Next up" countdown, copying the feed link, and closing "Add to calendar" menus.
//
// The page is complete without this file: the grid, the list and every link are
// server-rendered. The chosen filter is remembered in this browser only.

(function () {
    'use strict';

    const FILTER_KEY = 'events-filter';
    const page = document.querySelector('.ev');
    if (!page) return;

    // --- Filter chips -------------------------------------------------------------------

    function applyFilter(kind) {
        const all = kind === 'all';
        page.querySelectorAll('.ev-chip').forEach(chip => {
            const on = chip.dataset.filter === kind;
            chip.classList.toggle('is-on', on);
            chip.setAttribute('aria-pressed', String(on));
        });
        page.querySelectorAll('.ev-list [data-kind], .ev-cal [data-kind]').forEach(el => {
            const kinds = el.dataset.kind.split(' ');
            el.hidden = !all && !kinds.includes(kind);
        });
        page.querySelectorAll('.ev-day.has-items').forEach(day => {
            day.classList.toggle('is-muted', !all && !day.dataset.kinds.split(' ').includes(kind));
        });
        let any = false;
        page.querySelectorAll('[data-month]').forEach(month => {
            const shown = month.querySelector('.ev-item:not([hidden])') !== null;
            month.hidden = !shown;
            any = any || shown;
        });
        const empty = page.querySelector('.ev-empty--filtered');
        if (empty) empty.hidden = any;
    }

    function initFilters() {
        const chips = [...page.querySelectorAll('.ev-chip')];
        if (!chips.length) return;
        page.querySelector('.ev-filters').addEventListener('click', e => {
            const chip = e.target.closest('.ev-chip');
            if (!chip) return;
            const kind = chip.classList.contains('is-on') && chip.dataset.filter !== 'all' ? 'all' : chip.dataset.filter;
            applyFilter(kind);
            try { localStorage.setItem(FILTER_KEY, kind); } catch (err) { /* storage blocked */ }
        });
        let saved = 'all';
        try { saved = localStorage.getItem(FILTER_KEY) || 'all'; } catch (err) { /* storage blocked */ }
        if (saved !== 'all' && chips.some(c => c.dataset.filter === saved)) applyFilter(saved);
    }

    // --- Day view -----------------------------------------------------------------------

    function initDayView() {
        const grid = page.querySelector('.ev-days');
        if (!grid) return;
        grid.addEventListener('click', e => {
            const button = e.target.closest('[data-day]');
            if (!button) return;
            const open = button.getAttribute('aria-expanded') !== 'true';
            grid.querySelectorAll('[data-day]').forEach(b => {
                b.setAttribute('aria-expanded', 'false');
                b.closest('.ev-day').classList.remove('is-selected');
            });
            page.querySelectorAll('[data-day-panel]').forEach(p => { p.hidden = true; });
            if (!open) return;
            button.setAttribute('aria-expanded', 'true');
            button.closest('.ev-day').classList.add('is-selected');
            const panel = page.querySelector(`[data-day-panel="${button.dataset.day}"]`);
            if (panel) {
                panel.hidden = false;
                panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        });
    }

    // --- Countdown ----------------------------------------------------------------------

    // Seconds come from the server, so a visitor in another time zone still counts
    // down to the club's start time.
    function initCountdown() {
        const box = page.querySelector('[data-ev-seconds]');
        if (!box) return;
        const end = Date.now() + Number(box.dataset.evSeconds) * 1000;
        const units = {};
        box.querySelectorAll('[data-unit]').forEach(el => { units[el.dataset.unit] = el; });
        function tick() {
            const left = Math.max(0, Math.round((end - Date.now()) / 1000));
            if (left === 0) {
                const live = document.createElement('p');
                live.className = 'ev-live';
                live.textContent = 'Happening now';
                box.replaceWith(live);
                return;
            }
            units.days.textContent = Math.floor(left / 86400);
            units.hours.textContent = Math.floor(left / 3600) % 24;
            units.minutes.textContent = Math.floor(left / 60) % 60;
            units.seconds.textContent = left % 60;
            setTimeout(tick, 1000 - (Date.now() % 1000));
        }
        tick();
    }

    // --- Copy the feed link -------------------------------------------------------------

    function initCopy() {
        page.addEventListener('click', e => {
            const button = e.target.closest('[data-copy]');
            if (!button || !navigator.clipboard) return;
            const label = button.querySelector('span');
            navigator.clipboard.writeText(button.dataset.copy).then(() => {
                const before = label.textContent;
                label.textContent = 'Copied!';
                setTimeout(() => { label.textContent = before; }, 2000);
            }).catch(() => { /* permission denied: the link is still on the Subscribe button */ });
        });
    }

    // --- "Add to calendar" menus --------------------------------------------------------

    function initMenus() {
        const menus = () => page.querySelectorAll('.ev-add[open]');
        page.addEventListener('toggle', e => {
            if (!e.target.matches('.ev-add') || !e.target.open) return;
            menus().forEach(m => { if (m !== e.target) m.open = false; });
        }, true);
        document.addEventListener('click', e => {
            menus().forEach(m => { if (!m.contains(e.target)) m.open = false; });
        });
        document.addEventListener('keydown', e => {
            if (e.key !== 'Escape') return;
            menus().forEach(m => {
                m.open = false;
                m.querySelector('summary').focus();
            });
        });
    }

    initFilters();
    initDayView();
    initCountdown();
    initCopy();
    initMenus();
})();
