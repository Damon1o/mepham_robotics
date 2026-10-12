// Events page (/events): type filter, flipping months without a reload, the day
// view under the month grid, zooming and maximizing the calendar, the "Next up"
// countdown, copying the feed link, and closing "Add to calendar" menus. On one
// event's page (/events/<id>) it also runs the countdown and members' RSVPs.
//
// The page is complete without this file: the grid, the list and every link are
// server-rendered. The chosen filter and zoom are remembered in this browser only.

(function () {
    'use strict';

    const FILTER_KEY = 'events-filter';
    const ZOOM_KEY = 'events-zoom';
    const ZOOM_STEPS = 4;  // 100% plus four steps to 200%; see events.css
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
            syncCalTools();
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

    // --- Zoom and maximize -------------------------------------------------------------

    // Both live on the page wrapper, not the calendar, so they survive month changes
    // (the calendar is replaced). The buttons stay hidden without this script.
    let zoom = 0;
    let maxed = false;

    function syncCalTools() {
        const tools = page.querySelector('.ev-cal-tools');
        if (!tools) return;
        tools.hidden = false;
        tools.querySelector('[data-cal-step="-1"]').disabled = zoom === 0;
        tools.querySelector('[data-cal-step="1"]').disabled = zoom === ZOOM_STEPS;
        const max = tools.querySelector('[data-cal-max]');
        max.setAttribute('aria-pressed', String(maxed));
        max.setAttribute('aria-label', maxed ? 'Restore calendar size' : 'Maximize calendar');
    }

    function setZoom(step) {
        const next = Math.min(ZOOM_STEPS, Math.max(0, step));
        if (next === zoom) return;
        // Keep the middle of what's in view in the middle as the month widens.
        const body = page.querySelector('.ev-cal-body');
        const centre = body ? (body.scrollLeft + body.clientWidth / 2) / body.scrollWidth : 0;
        zoom = next;
        if (zoom) page.dataset.calZoom = String(zoom);
        else delete page.dataset.calZoom;
        if (body) body.scrollLeft = centre * body.scrollWidth - body.clientWidth / 2;
        try { localStorage.setItem(ZOOM_KEY, String(zoom)); } catch (err) { /* storage blocked */ }
        live.textContent = `Calendar at ${100 + zoom * 25}%`;
        syncCalTools();
    }

    function setMax(on) {
        maxed = on;
        page.classList.toggle('is-cal-max', on);
        document.documentElement.classList.toggle('ev-cal-locked', on);
        syncCalTools();
        page.querySelector('[data-cal-max]')?.focus({ preventScroll: true });
        if (!on) page.querySelector('.ev-cal')?.scrollIntoView({ block: 'nearest' });
    }

    function initCalTools() {
        try { zoom = Math.min(ZOOM_STEPS, Math.max(0, parseInt(localStorage.getItem(ZOOM_KEY), 10) || 0)); } catch (err) { /* storage blocked */ }
        if (zoom) page.dataset.calZoom = String(zoom);
        syncCalTools();
        // Delegated on the page: the buttons are replaced when the month changes.
        page.addEventListener('click', e => {
            const step = e.target.closest('[data-cal-step]');
            if (step) setZoom(zoom + Number(step.dataset.calStep));
            else if (e.target.closest('[data-cal-max]')) setMax(!maxed);
        });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && maxed) setMax(false);
        });
        // Pinching a trackpad (and Ctrl + wheel) over the month zooms it, not the page.
        let pinch = 0;
        page.addEventListener('wheel', e => {
            if (!e.ctrlKey || !e.target.closest('.ev-cal-body')) return;
            e.preventDefault();
            pinch -= e.deltaY;
            if (Math.abs(pinch) < 40) return;
            setZoom(zoom + Math.sign(pinch));
            pinch = 0;
        }, { passive: false });
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

    // --- RSVP (one event's page) ------------------------------------------------------

    // Pressing your current answer again takes it back. The counts and the list of
    // who's coming are redrawn from the server's reply, so they stay in step.
    function personItem(p) {
        const li = document.createElement('li');
        li.className = 'ev-person';
        const face = document.createElement('span');
        face.className = 'ev-person-avatar' + (p.tone && p.tone !== 'gold' ? ` avatar-tone--${p.tone}` : '');
        face.setAttribute('aria-hidden', 'true');
        if (p.photo) {
            face.classList.add('has-photo');
            const img = document.createElement('img');
            img.src = p.photo;
            img.alt = '';
            face.append(img);
        } else {
            face.textContent = p.initials;
        }
        const name = document.createElement('span');
        name.className = 'ev-person-name';
        name.textContent = p.name;
        li.append(face, name);
        if (p.status === 'maybe') {
            const tag = document.createElement('span');
            tag.className = 'ev-person-tag';
            tag.textContent = 'maybe';
            li.append(tag);
        }
        return li;
    }

    function showRsvp(box, data) {
        Object.entries(data.counts).forEach(([key, n]) => {
            const el = box.querySelector(`[data-rsvp-count="${key}"]`);
            if (el) el.textContent = n;
        });
        box.querySelectorAll('[data-rsvp]').forEach(b => {
            const on = b.dataset.rsvp === data.mine;
            b.classList.toggle('is-on', on);
            b.setAttribute('aria-pressed', String(on));
        });
        const list = box.querySelector('[data-rsvp-people]');
        if (list) list.replaceChildren(...data.people.map(personItem));
        const empty = box.querySelector('[data-rsvp-empty]');
        if (empty) empty.hidden = data.people.length > 0;
    }

    function initRsvp() {
        const box = page.querySelector('.ev-rsvp');
        if (!box) return;
        const status = box.querySelector('.ev-rsvp-status');
        let busy = false;
        box.addEventListener('click', e => {
            const button = e.target.closest('[data-rsvp]');
            if (!button || busy) return;
            const answer = button.getAttribute('aria-pressed') === 'true' ? '' : button.dataset.rsvp;
            busy = true;
            box.setAttribute('aria-busy', 'true');
            fetch(box.dataset.rsvpUrl, {
                method: 'POST', credentials: 'same-origin', headers: jsonHeaders(),
                body: JSON.stringify({ status: answer }),
            }).then(r => r.json().then(data => {
                if (!r.ok) throw new Error(data.error || 'Could not save that.');
                showRsvp(box, data);
                status.textContent = answer ? `Saved: ${button.textContent.trim()}.` : 'Answer removed.';
            })).catch(err => {
                status.textContent = err.message || 'Could not save that. Try again.';
            }).finally(() => {
                busy = false;
                box.removeAttribute('aria-busy');
            });
        });
    }

    initFilters();
    initMonthNav();
    initDayView();
    initCalTools();
    initCountdown();
    initCopy();
    initMenus();
    initRsvp();
})();
