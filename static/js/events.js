// Events page (/events): type filter, flipping months without a reload, the day
// view under the month grid, the "Next up" countdown, copying the feed link, and
// closing "Add to calendar" menus.
//
// The page is complete without this file: the grid, the list and every link are
// server-rendered. The chosen filter is remembered in this browser only.

(function () {
    'use strict';

    const FILTER_KEY = 'events-filter';
    const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)');
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

    // The chosen type, kept across month changes (the chips are redrawn with the month).
    let currentKind = 'all';

    function hasChip(kind) {
        return kind === 'all' || page.querySelector(`.ev-chip[data-filter="${CSS.escape(kind)}"]`) !== null;
    }

    function initFilters() {
        // Delegated on the page: the chips are replaced when the month changes.
        page.addEventListener('click', e => {
            const chip = e.target.closest('.ev-chip');
            if (!chip) return;
            const kind = chip.classList.contains('is-on') && chip.dataset.filter !== 'all' ? 'all' : chip.dataset.filter;
            currentKind = kind;
            applyFilter(kind);
            try { localStorage.setItem(FILTER_KEY, kind); } catch (err) { /* storage blocked */ }
        });
        let saved = 'all';
        try { saved = localStorage.getItem(FILTER_KEY) || 'all'; } catch (err) { /* storage blocked */ }
        if (saved !== 'all' && hasChip(saved)) {
            currentKind = saved;
            applyFilter(saved);
        }
    }

    // --- Month navigation ---------------------------------------------------------------

    // Previous, next and Today fetch the month in the background and swap the
    // calendar in place: no reload, no jump to the top. The address bar follows
    // (?month=), so Back, Forward and shared links land on the same month. The
    // links still work as plain links without this script or when a fetch fails.
    const months = new Map();
    let navToken = 0;
    const live = document.createElement('p');
    live.className = 'visually-hidden';
    live.setAttribute('aria-live', 'polite');
    page.append(live);

    function monthUrl(href) {
        const url = new URL(href, location.href);
        url.hash = '';
        return url.href;
    }

    function fetchMonth(href) {
        const key = monthUrl(href);
        if (!months.has(key)) {
            const request = fetch(key, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
                .then(r => {
                    if (!r.ok) throw new Error(`HTTP ${r.status}`);
                    return r.text();
                })
                .then(html => new DOMParser().parseFromString(html, 'text/html'));
            request.catch(() => months.delete(key));
            months.set(key, request);
        }
        return months.get(key);
    }

    function prefetchNeighbours() {
        page.querySelectorAll('.ev-cal-nav a').forEach(a => { fetchMonth(a.href).catch(() => {}); });
    }

    // Swap one part of the page for its copy in the fetched page, adding or removing it.
    // Cloned, so the cached page keeps its copy for the next visit to that month.
    function swap(selector, doc, before) {
        const old = page.querySelector(selector);
        const fresh = doc.querySelector(selector)?.cloneNode(true);
        if (old && fresh) old.replaceWith(fresh);
        else if (old) old.remove();
        else if (fresh) page.querySelector(before).before(fresh);
        return fresh;
    }

    function showMonth(href, { push, direction, focusLabel }) {
        const token = ++navToken;
        page.querySelector('.ev-cal').classList.add('is-loading');
        return fetchMonth(href).then(doc => {
            if (token !== navToken) return;  // a later click won
            if (!doc.querySelector('.ev-cal')) throw new Error('No calendar in the response');
            swap('.ev-filters', doc, '.ev-main');
            const cal = swap('.ev-cal', doc, '.ev-list');
            if (direction && !REDUCED.matches) cal.querySelector('.ev-days').classList.add(`is-entering-${direction}`);
            window.lucide?.createIcons();
            if (!hasChip(currentKind)) currentKind = 'all';
            applyFilter(currentKind);
            if (push) history.pushState({ evMonth: true }, '', monthUrl(href));
            live.textContent = cal.querySelector('#ev-cal-title')?.textContent.replace(/\s+/g, ' ').trim() || '';
            if (focusLabel) {
                const nav = cal.querySelector('.ev-cal-nav');
                (nav.querySelector(`[aria-label="${focusLabel}"]`) || nav.querySelector('a'))?.focus({ preventScroll: true });
            }
            prefetchNeighbours();
        }).catch(() => {
            if (token === navToken) location.href = href;
        });
    }

    function initMonthNav() {
        if (!page.querySelector('.ev-cal-nav') || !window.fetch || !window.DOMParser) return;
        page.addEventListener('click', e => {
            const link = e.target.closest('.ev-cal-nav a');
            if (!link || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            e.preventDefault();
            const label = link.getAttribute('aria-label') || '';
            const direction = /previous/i.test(label) ? 'prev' : /next/i.test(label) ? 'next' : '';
            showMonth(link.href, { push: true, direction, focusLabel: label || null });
        });
        window.addEventListener('popstate', () => {
            showMonth(location.href, { push: false, direction: '' });
        });
        // Seed the cache with this page and fetch the months either side.
        history.replaceState({ evMonth: true }, '', location.href);
        months.set(monthUrl(location.href), Promise.resolve(document.cloneNode(true)));
        prefetchNeighbours();
    }

    // --- Day view -----------------------------------------------------------------------

    function initDayView() {
        // Delegated on the page: the grid is replaced when the month changes.
        page.addEventListener('click', e => {
            const button = e.target.closest('.ev-days [data-day]');
            if (!button) return;
            const grid = button.closest('.ev-days');
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
    initMonthNav();
    initDayView();
    initCountdown();
    initCopy();
    initMenus();
})();
