// Guided tour: walks a member through the real site, one spotlighted element at a time.
//
// Start it with any [data-tour-start] button (Member Hub, the written guide). The
// value names one chapter; empty runs every chapter. Steps come from
// GET /api/guide/tour (api/guide.py TOURS), and each step names the page it lives on,
// so the tour moves from page to page. Where it is in the run is kept in
// sessionStorage for this tab; finishing a chapter's steps ticks that chapter off on
// the account, like "Mark as done" in the written guide.
//
// Keys: → or Enter next, ← back, Esc ends the tour.

(function () {
    'use strict';

    const script = document.currentScript;
    const TOUR_URL = script && script.dataset.tourUrl;
    const STEP_URL = script && script.dataset.stepUrl;
    const STATE_KEY = 'mepham-tour';
    if (!TOUR_URL) return;

    const store = {
        get() {
            try { return JSON.parse(sessionStorage.getItem(STATE_KEY)); } catch (e) { return null; }
        },
        set(value) {
            try { sessionStorage.setItem(STATE_KEY, JSON.stringify(value)); } catch (e) { /* blocked storage */ }
        },
        clear() {
            try { sessionStorage.removeItem(STATE_KEY); } catch (e) { /* blocked storage */ }
        },
    };

    let state = null;      // {steps: [...], i, hub}
    let ui = null;         // the layer's elements, built once
    let current = null;    // the element spotlighted now
    let frame = 0;

    function reducedMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches
            || document.documentElement.dataset.motion === 'reduce';
    }

    function onThisPage(step) {
        try { return new RegExp(step.match).test(location.pathname); } catch (e) { return false; }
    }

    function visible(el) {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
    }

    function findTarget(step) {
        if (!step.target) return null;
        let found = [];
        try { found = [...document.querySelectorAll(step.target)]; } catch (e) { return null; }
        return found.find(visible) || null;
    }

    // --- Starting, moving, ending ------------------------------------------------------

    function start(chapterKey) {
        fetch(TOUR_URL, { credentials: 'same-origin' })
            .then(r => (r.ok ? r.json() : Promise.reject(new Error('Could not load the tour.'))))
            .then(data => {
                const chapters = data.chapters.filter(c => !chapterKey || c.key === chapterKey);
                const steps = [];
                chapters.forEach((c, ci) => c.steps.forEach((s, si) => steps.push(Object.assign({}, s, {
                    chapter: c.key, chapterTitle: c.title, chapterNo: ci + 1, chapters: chapters.length,
                    no: si + 1, of: c.steps.length, chapterEnd: si === c.steps.length - 1,
                }))));
                if (!steps.length) return;
                state = { steps, i: 0, hub: data.hub };
                go(0, 1);
            })
            .catch(() => toast('Could not load the tour. Try again in a moment.'));
    }

    // dir: +1 going forward, -1 going back (an optional step that isn't here is skipped that way).
    function go(i, dir) {
        if (i < 0) return;
        if (i >= state.steps.length) return finish();
        state.i = i;
        state.dir = dir;
        store.set(state);
        const step = state.steps[i];
        if (!onThisPage(step)) {
            hide();
            location.href = step.url;
            return;
        }
        show(step);
    }

    function next() {
        const step = state.steps[state.i];
        if (step.chapterEnd) markDone(step.chapter);
        go(state.i + 1, 1);
    }

    function back() {
        go(state.i - 1, -1);
    }

    function end() {
        store.clear();
        state = null;
        setNav(false);
        hide();
        toast('Tour ended. Restart it any time from the Member Hub.');
    }

    function finish() {
        const hub = state.hub;
        store.clear();
        state = null;
        setNav(false);
        build();
        current = null;
        ui.spot.hidden = true;
        ui.shade.hidden = false;
        ui.pop.classList.add('tour-pop--center');
        ui.meta.textContent = 'Tour complete';
        ui.title.textContent = 'That\'s the tour!';
        ui.text.textContent = 'You know where everything lives now. The tour and the written guide stay in the Member Hub whenever you need them.';
        ui.bar.style.setProperty('--tour-done', '1');
        ui.back.hidden = true;
        ui.next.textContent = 'Back to the Member Hub';
        ui.next.onclick = () => { hide(); if (location.pathname !== new URL(hub, location.href).pathname) location.href = hub; };
        open();
    }

    function markDone(key) {
        if (!STEP_URL) return;
        fetch(STEP_URL, {
            method: 'POST', credentials: 'same-origin', keepalive: true,
            headers: jsonHeaders(), body: JSON.stringify({ key, done: true }),
        }).catch(() => { /* the written guide still has Mark as done */ });
    }

    // --- The side menu -----------------------------------------------------------------

    function setNav(wantOpen) {
        const toggle = document.querySelector('.menu-toggle');
        if (!toggle) return false;
        const isOpen = toggle.getAttribute('aria-expanded') === 'true';
        if (isOpen === wantOpen) return false;
        toggle.click();
        return true;
    }

    // --- Drawing a step ----------------------------------------------------------------

    function build() {
        if (ui) return;
        const layer = document.createElement('div');
        layer.className = 'tour';
        layer.hidden = true;
        layer.innerHTML = `
            <div class="tour-shade" hidden></div>
            <div class="tour-spot" hidden></div>
            <div class="tour-pop" role="dialog" aria-modal="false" aria-labelledby="tour-title" aria-describedby="tour-text" tabindex="-1">
                <div class="tour-bar" aria-hidden="true"><span></span></div>
                <div class="tour-head">
                    <p class="tour-meta" id="tour-meta"></p>
                    <button type="button" class="tour-close" aria-label="End the tour" data-tour-end>&times;</button>
                </div>
                <h2 class="tour-title" id="tour-title"></h2>
                <p class="tour-text" id="tour-text"></p>
                <div class="tour-actions">
                    <span class="tour-count" aria-hidden="true"></span>
                    <button type="button" class="tour-btn tour-btn--ghost" data-tour-back>Back</button>
                    <button type="button" class="tour-btn" data-tour-next>Next</button>
                </div>
            </div>`;
        document.body.appendChild(layer);
        ui = {
            layer,
            shade: layer.querySelector('.tour-shade'),
            spot: layer.querySelector('.tour-spot'),
            pop: layer.querySelector('.tour-pop'),
            bar: layer.querySelector('.tour-bar'),
            meta: layer.querySelector('.tour-meta'),
            title: layer.querySelector('.tour-title'),
            text: layer.querySelector('.tour-text'),
            count: layer.querySelector('.tour-count'),
            back: layer.querySelector('[data-tour-back]'),
            next: layer.querySelector('[data-tour-next]'),
        };
        layer.querySelector('[data-tour-end]').addEventListener('click', end);
    }

    function open() {
        ui.layer.hidden = false;
        document.documentElement.classList.add('tour-on');
        requestAnimationFrame(() => {
            place();
            ui.next.focus({ preventScroll: true });
        });
    }

    function hide() {
        if (!ui) return;
        ui.layer.hidden = true;
        ui.pop.classList.remove('tour-pop--center');
        document.documentElement.classList.remove('tour-on');
        current = null;
    }

    function show(step) {
        build();
        const waitForNav = setNav(step.nav);
        // The menu slides in; measure once it has landed.
        setTimeout(() => draw(step), waitForNav ? (reducedMotion() ? 60 : 420) : 0);
    }

    function draw(step) {
        const el = findTarget(step);
        if (!el && step.optional) {
            const to = state.i + (state.dir || 1);
            if (step.chapterEnd && state.dir !== -1) markDone(step.chapter);
            return to < 0 ? go(state.i + 1, 1) : go(to, state.dir || 1);
        }

        current = el;
        const last = state.i === state.steps.length - 1;
        ui.meta.textContent = step.chapters > 1
            ? `Chapter ${step.chapterNo} of ${step.chapters} · ${step.chapterTitle}`
            : step.chapterTitle;
        ui.title.textContent = step.title;
        ui.text.innerHTML = step.text;  // trusted copy from api/guide.py
        ui.count.textContent = `${step.no} / ${step.of}`;
        ui.bar.style.setProperty('--tour-done', String((state.i + 1) / state.steps.length));
        ui.back.hidden = false;
        ui.back.disabled = state.i === 0;
        ui.back.onclick = back;
        ui.next.textContent = last ? 'Finish' : step.chapterEnd ? 'Next chapter' : 'Next';
        ui.next.onclick = next;
        ui.pop.classList.toggle('tour-pop--center', !el);
        ui.spot.hidden = !el;
        ui.shade.hidden = Boolean(el);

        if (el && !el.closest('#mySidenav')) {
            el.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
        }
        open();
    }

    // Keep the spotlight and the card on the element while the page scrolls or resizes.
    function place() {
        if (!ui || ui.layer.hidden) return;
        const pop = ui.pop;
        if (!current) {
            pop.style.left = pop.style.top = '';
            return;
        }
        const pad = 8;
        const r = current.getBoundingClientRect();
        const vw = document.documentElement.clientWidth;
        const vh = window.innerHeight;
        Object.assign(ui.spot.style, {
            left: `${r.left - pad}px`, top: `${r.top - pad}px`,
            width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
        });

        // Phones: the card docks to the bottom of the screen (tour.css).
        if (vw <= 600) {
            pop.style.left = pop.style.top = '';
            return;
        }
        const gap = 16;
        const pw = pop.offsetWidth;
        const ph = pop.offsetHeight;
        let top;
        let left;
        if (r.bottom + gap + ph <= vh) {
            top = r.bottom + gap;
        } else if (r.top - gap - ph >= 0) {
            top = r.top - gap - ph;
        } else if (r.right + gap + pw <= vw) {
            // Tall elements (the side menu, a long card): sit beside them.
            left = r.right + gap;
            top = Math.min(Math.max(gap, r.top), vh - ph - gap);
        } else if (r.left - gap - pw >= 0) {
            left = r.left - gap - pw;
            top = Math.min(Math.max(gap, r.top), vh - ph - gap);
        } else {
            top = vh - ph - gap;
        }
        if (left === undefined) left = Math.min(Math.max(gap, r.left), vw - pw - gap);
        pop.style.left = `${left}px`;
        pop.style.top = `${Math.max(gap, top)}px`;
    }

    function schedule() {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(place);
    }

    window.addEventListener('scroll', schedule, { passive: true, capture: true });
    window.addEventListener('resize', schedule);
    // Smooth scrolling (and images loading above) can still be moving things; settle once it stops.
    window.addEventListener('scrollend', schedule);

    document.addEventListener('keydown', e => {
        if (!state || !ui || ui.layer.hidden) return;
        if (e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
        if (e.key === 'Escape') { e.preventDefault(); end(); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
        else if (e.key === 'ArrowLeft' && state.i > 0) { e.preventDefault(); back(); }
    });

    // --- Paused tour: the member wandered to another page ------------------------------

    function pausedPill() {
        const pill = document.createElement('div');
        pill.className = 'tour-pill';
        pill.setAttribute('role', 'region');
        pill.setAttribute('aria-label', 'Guided tour');
        pill.innerHTML = `<span><b>Tour paused</b></span>
            <button type="button" class="tour-btn" data-tour-resume>Continue</button>
            <button type="button" class="tour-btn tour-btn--ghost" data-tour-stop>End</button>`;
        document.body.appendChild(pill);
        pill.querySelector('[data-tour-resume]').addEventListener('click', () => go(state.i, 1));
        pill.querySelector('[data-tour-stop]').addEventListener('click', () => { pill.remove(); end(); });
    }

    // --- Small note at the bottom of the screen ----------------------------------------

    function toast(message) {
        const note = document.createElement('div');
        note.className = 'tour-toast';
        note.setAttribute('role', 'status');
        note.textContent = message;
        document.body.appendChild(note);
        setTimeout(() => note.remove(), 4000);
    }

    // --- Wiring ------------------------------------------------------------------------

    document.addEventListener('click', e => {
        const btn = e.target.closest('[data-tour-start]');
        if (!btn) return;
        e.preventDefault();
        document.querySelector('.tour-pill')?.remove();
        start(btn.dataset.tourStart || '');
    });

    state = store.get();
    if (state && Array.isArray(state.steps) && state.steps[state.i]) {
        if (onThisPage(state.steps[state.i])) {
            // Give the page's own scripts (carousels, the team editor) a moment to lay out.
            window.addEventListener('load', () => show(state.steps[state.i]), { once: true });
            if (document.readyState === 'complete') show(state.steps[state.i]);
        } else {
            pausedPill();
        }
    } else {
        state = null;
    }
})();
