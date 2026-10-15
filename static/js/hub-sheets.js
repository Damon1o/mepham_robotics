// Member Hub (/resources): meeting sign-in/sign-out, event sign-ups and sign-up sheets.
// Editors can fill in any of them for anyone, past days and past events included.
//
// Both sections are server-rendered. Every action posts and gets the section back
// as HTML, which replaces the old one, so the page never drifts from what was saved.
// Removing a person or a sheet lights a fuse (Fuse.arm) instead of asking first.

(function () {
    'use strict';

    const attendance = document.querySelector('[data-attendance]');
    const signups = document.querySelector('[data-sheets]');

    function send(url, body, method = 'POST') {
        return fetch(url, {
            method, credentials: 'same-origin', keepalive: Boolean(window.Fuse && Fuse.leaving),
            headers: jsonHeaders(), body: body === undefined ? undefined : JSON.stringify(body),
        }).then(r => r.json().catch(() => ({})).then(data => {
            if (!r.ok) throw new Error(data.error || 'Could not save that.');
            return data;
        }));
    }

    function swap(section, data) {
        section.dispatchEvent(new CustomEvent('hub:swap'));
        section.innerHTML = data.html;
        refreshLucideIcons();
        section.dispatchEvent(new CustomEvent('hub:swapped'));
    }

    function busy(button, on) {
        if (!button) return;
        button.disabled = on;
        button.classList.toggle('is-busy', on);
    }

    function act(section, button, request) {
        busy(button, true);
        return request
            .then(data => swap(section, data))
            .catch(err => {
                busy(button, false);
                showToast(err.message, 'error');
            });
    }

    // --- Meeting sign-in ----------------------------------------------------------------

    if (attendance) {
        const day = () => attendance.querySelector('[data-roll-day]')?.dataset.rollDay;
        const roll = (button, body) => act(attendance, button,
            send('/api/hub/attendance/sheet', Object.assign({ day: day() }, body)));
        const openDay = value => act(attendance, null,
            send(`/api/hub/attendance/sheet?day=${encodeURIComponent(value)}`, undefined, 'GET'));

        attendance.addEventListener('click', e => {
            const own = e.target.closest('[data-attend]');
            if (own) {
                act(attendance, own, send('/api/hub/attendance', { action: own.dataset.attend }));
                return;
            }
            const edit = e.target.closest('[data-roll-edit]');
            if (edit) {
                const box = edit.closest('[data-roll-row]').querySelector('[data-roll-set]');
                box.hidden = !box.hidden;
                edit.setAttribute('aria-expanded', String(!box.hidden));
                if (!box.hidden) box.elements.in_time.focus();
                return;
            }
            const button = e.target.closest('[data-roll]');
            if (!button) return;
            if (button.dataset.roll === 'remove') {
                Fuse.arm(button, {
                    label: `Taking ${button.dataset.name} off the sheet`,
                    run: () => roll(null, { action: 'remove', user_id: button.dataset.user }),
                });
            } else {
                roll(button, { action: button.dataset.roll, user_id: button.dataset.user });
            }
        });

        attendance.addEventListener('change', e => {
            if (e.target.matches('[data-roll-pick]')) openDay(e.target.value);
            else if (e.target.matches('[data-roll-date]') && e.target.value && e.target.value !== day()) {
                openDay(e.target.value);
            }
        });

        attendance.addEventListener('submit', e => {
            const f = e.target;
            const submit = f.querySelector('[type="submit"]');
            const times = { in_time: f.elements.in_time?.value || '', out_time: f.elements.out_time?.value || '' };
            if (f.matches('[data-roll-add]') && f.elements.user_id) {
                e.preventDefault();
                if (f.elements.user_id.value) roll(submit, Object.assign({ action: 'in', user_id: f.elements.user_id.value }, times));
            } else if (f.matches('[data-roll-bulk]')) {
                e.preventDefault();
                const ids = [...f.querySelectorAll('[name="user_ids"]:checked')].map(box => box.value);
                if (!ids.length) return showToast('Check at least one member.', 'error');
                roll(submit, Object.assign({ action: 'in', user_ids: ids }, times));
            } else if (f.matches('[data-roll-set]')) {
                e.preventDefault();
                roll(submit, Object.assign({ action: 'set', user_id: f.dataset.user }, times));
            }
        });
    }

    // --- Event sign-ups -----------------------------------------------------------------

    const hubEvents = document.querySelector('[data-hub-events]');
    if (hubEvents) {
        const signup = (card, button, body) => act(hubEvents, button,
            send(`/api/hub/events/${card.dataset.event}`, body));

        hubEvents.addEventListener('click', e => {
            const card = e.target.closest('[data-event]');
            if (!card) return;
            const toggle = e.target.closest('[data-event-toggle]');
            if (toggle) {
                signup(card, toggle, { on: toggle.getAttribute('aria-pressed') !== 'true' });
                return;
            }
            const remove = e.target.closest('[data-event-remove]');
            if (remove) {
                Fuse.arm(remove, {
                    label: `Taking ${remove.dataset.name} off`,
                    run: () => signup(card, null, { on: false, user_id: remove.dataset.eventRemove }),
                });
            }
        });

        hubEvents.addEventListener('submit', e => {
            if (!e.target.matches('[data-event-add]')) return;
            e.preventDefault();
            const userId = e.target.elements.user_id.value;
            if (userId) signup(e.target.closest('[data-event]'), e.target.querySelector('[type="submit"]'),
                { on: true, user_id: userId });
        });

        // The upcoming events turn one card at a time. A redraw keeps the card that was showing
        // and whether turning was paused.
        let ring = carousel(hubEvents.querySelector('[data-carousel]'));
        hubEvents.addEventListener('hub:swap', () => ring && ring.stop());
        hubEvents.addEventListener('hub:swapped', () => {
            const was = ring;
            ring = carousel(hubEvents.querySelector('[data-carousel]'), was && was.state());
        });
    }

    // A row of cards that snaps one to the middle and moves on by itself every few seconds.
    // It holds still while the pointer or focus is on it, while the tab is hidden, when the
    // visitor pauses it, and always under reduced motion.
    function carousel(root, from) {
        if (!root) return null;
        const track = root.querySelector('[data-carousel-track]');
        const cards = Array.from(track.children);
        const dots = Array.from(root.querySelectorAll('[data-carousel-go]'));
        const play = root.querySelector('[data-carousel-play]');
        const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const EVERY = 6000;
        let index = Math.max(0, cards.findIndex(c => from && c.dataset.event === from.event));
        let held = Boolean(from && from.held) || still;
        let hovering = false;
        let timer = null;
        let frame = 0;
        let aim = null;  // the card a turn is gliding to; scrolling passes others on the way

        function mark() {
            cards.forEach((card, i) => card.classList.toggle('is-current', i === index));
            dots.forEach((dot, i) => dot.setAttribute('aria-current', i === index ? 'true' : 'false'));
            if (play) play.setAttribute('aria-pressed', held ? 'true' : 'false');
            root.classList.toggle('is-held', held);
        }

        function go(i, smooth = true) {
            index = (i + cards.length) % cards.length;
            aim = smooth && !still ? index : null;
            const card = cards[index];
            track.scrollTo({
                left: card.offsetLeft - (track.clientWidth - card.offsetWidth) / 2,
                behavior: smooth && !still ? 'smooth' : 'auto',
            });
            mark();
        }

        function restart() {
            clearInterval(timer);
            timer = null;
            // Focus on a card (signing up, adding someone) holds it; focus on the arrows doesn't.
            const active = document.activeElement;
            const focused = root.contains(active) && !active.closest('.hub-carousel-nav');
            if (cards.length < 2 || held || hovering || focused || document.hidden) return;
            timer = setInterval(() => go(index + 1), EVERY);
        }

        // A swipe or a scroll by hand: the card nearest the middle becomes the current one.
        function settle() {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
                const middle = track.scrollLeft + track.clientWidth / 2;
                let best = index;
                let gap = Infinity;
                cards.forEach((card, i) => {
                    const d = Math.abs(card.offsetLeft + card.offsetWidth / 2 - middle);
                    if (d < gap) { gap = d; best = i; }
                });
                if (aim !== null) {
                    if (best === aim) aim = null;
                    return;
                }
                if (best !== index) { index = best; mark(); }
            });
        }

        const onClick = e => {
            // A card peeking in at the side comes to the middle before anything on it works.
            const card = e.target.closest('[data-event]');
            if (card && !card.classList.contains('is-current')) {
                e.preventDefault();
                go(cards.indexOf(card));
                restart();
                return;
            }
            const step = e.target.closest('[data-carousel-step]');
            const dot = e.target.closest('[data-carousel-go]');
            if (step) go(index + Number(step.dataset.carouselStep));
            else if (dot) go(Number(dot.dataset.carouselGo));
            else if (e.target.closest('[data-carousel-play]')) { held = !held; mark(); }
            else return;
            restart();
        };
        const onKey = e => {
            if (e.target.closest('input, select, textarea, [contenteditable]')) return;
            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                e.preventDefault();
                go(index + (e.key === 'ArrowRight' ? 1 : -1));
            }
        };
        const enter = () => { hovering = true; restart(); };
        const leave = () => { hovering = false; restart(); };
        const focusOut = () => setTimeout(restart);

        root.addEventListener('click', onClick);
        root.addEventListener('keydown', onKey);
        root.addEventListener('pointerenter', enter);
        root.addEventListener('pointerleave', leave);
        root.addEventListener('focusin', e => {
            const card = e.target.closest('[data-event]');
            if (card && card !== cards[index]) go(cards.indexOf(card));
            restart();
        });
        root.addEventListener('focusout', focusOut);
        track.addEventListener('scroll', settle, { passive: true });
        // A hand on the track takes over from a turn still gliding.
        ['pointerdown', 'wheel', 'touchstart'].forEach(type =>
            track.addEventListener(type, () => { aim = null; }, { passive: true }));
        document.addEventListener('visibilitychange', restart);
        // Cards change width with the page; keep the current one in the middle.
        const resized = 'ResizeObserver' in window && new ResizeObserver(() => go(index, false));
        if (resized) resized.observe(track);

        root.classList.add('is-ready');
        go(index, false);
        restart();

        return {
            state: () => ({ event: cards[index] && cards[index].dataset.event, held: held && !still }),
            stop() {
                clearInterval(timer);
                cancelAnimationFrame(frame);
                document.removeEventListener('visibilitychange', restart);
                if (resized) resized.disconnect();
            },
        };
    }

    // --- Sign-up sheets -----------------------------------------------------------------

    if (!signups) return;
    let editing = null;  // the sheet id being edited, or null for a new sheet

    const form = () => signups.querySelector('[data-sheet-form]');

    function setValue(input, value) {
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function addRole(rows, role = {}) {
        const row = form().querySelector('[data-role-template]').content.firstElementChild.cloneNode(true);
        rows.append(row);
        ['key', 'name', 'slots', 'prompt'].forEach(name => {
            if (role[name] !== undefined) setValue(row.querySelector(`[name="${name}"]`), role[name]);
        });
        refreshLucideIcons();
        return row;
    }

    // A new sheet starts as a bake sale on the next Saturday morning.
    function nextSaturday() {
        const d = new Date();
        d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7 || 7));
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00`;
    }

    function openForm(sheet) {
        const f = form();
        editing = sheet ? sheet.id : null;
        const data = sheet ? sheet.data : {
            title: 'Bake sale', date: nextSaturday(), location: '', details: '',
            roles: JSON.parse(f.querySelector('[data-bake-sale-roles]').textContent),
        };
        f.querySelector('[data-sheet-form-title]').textContent = sheet ? `Edit ${data.title}` : 'New sign-up sheet';
        ['title', 'date', 'location', 'details'].forEach(name => setValue(f.elements[name], data[name] || ''));
        const rows = f.querySelector('[data-role-rows]');
        rows.replaceChildren();
        data.roles.forEach(role => addRole(rows, role));
        f.querySelector('[data-sheet-error]').hidden = true;
        f.hidden = false;
        f.scrollIntoView({ behavior: 'smooth', block: 'start' });
        f.elements.title.focus({ preventScroll: true });
    }

    function readForm(f) {
        return {
            title: f.elements.title.value, date: f.elements.date.value,
            location: f.elements.location.value, details: f.elements.details.value,
            roles: [...f.querySelectorAll('[data-role-row]')].map(row => ({
                key: row.querySelector('[name="key"]').value,
                name: row.querySelector('[name="name"]').value,
                slots: Number(row.querySelector('[name="slots"]').value),
                prompt: row.querySelector('[name="prompt"]').value,
            })),
        };
    }

    signups.addEventListener('click', e => {
        const target = e.target;
        if (target.closest('[data-sheet-new]')) return openForm(null);
        if (target.closest('[data-sheet-cancel]')) {
            form().hidden = true;
            return;
        }
        if (target.closest('[data-role-add]')) {
            addRole(form().querySelector('[data-role-rows]')).querySelector('[name="name"]').focus();
            return;
        }
        const removeRole = target.closest('[data-role-remove]');
        if (removeRole) return removeRole.closest('[data-role-row]').remove();

        const card = target.closest('[data-sheet]');
        if (!card) return;
        const edit = target.closest('[data-sheet-edit]');
        if (edit) return openForm({ id: card.dataset.sheet, data: JSON.parse(edit.dataset.sheetEdit) });

        const del = target.closest('[data-sheet-delete]');
        if (del) {
            Fuse.arm(del, {
                label: `Deleting ${del.dataset.name}`,
                detail: 'Everyone signed up comes off it too',
                run: () => act(signups, null, send(`/api/hub/sheets/${card.dataset.sheet}`, undefined, 'DELETE')),
            });
            return;
        }
        const role = target.closest('[data-role]')?.dataset.role;
        const off = target.closest('[data-signup-off]');
        if (off) {
            act(signups, off, send(`/api/hub/sheets/${card.dataset.sheet}/signup`, { role, on: false }));
            return;
        }
        const other = target.closest('[data-signup-remove]');
        if (other) {
            Fuse.arm(other, {
                label: `Taking ${other.dataset.name} off`,
                run: () => act(signups, null, send(`/api/hub/sheets/${card.dataset.sheet}/signup`,
                    { role, on: false, user_id: other.dataset.signupRemove })),
            });
        }
    });

    signups.addEventListener('submit', e => {
        const f = e.target;
        e.preventDefault();
        if (f.matches('[data-signup-add]')) {
            const card = f.closest('[data-sheet]');
            if (!f.elements.user_id.value) return;
            act(signups, f.querySelector('[type="submit"]'), send(`/api/hub/sheets/${card.dataset.sheet}/signup`, {
                role: f.closest('[data-role]').dataset.role, on: true,
                user_id: f.elements.user_id.value, note: f.elements.note.value,
            }));
            return;
        }
        if (f.matches('[data-signup-on]')) {
            const card = f.closest('[data-sheet]');
            act(signups, f.querySelector('[type="submit"]'), send(`/api/hub/sheets/${card.dataset.sheet}/signup`,
                { role: f.closest('[data-role]').dataset.role, on: true, note: f.elements.note?.value || '' }));
            return;
        }
        if (!f.matches('[data-sheet-form]')) return;
        const button = f.querySelector('[type="submit"]');
        const error = f.querySelector('[data-sheet-error]');
        busy(button, true);
        send(editing ? `/api/hub/sheets/${editing}` : '/api/hub/sheets', readForm(f))
            .then(data => swap(signups, data))
            .catch(err => {
                busy(button, false);
                error.textContent = err.message;
                error.hidden = false;
            });
    });
})();
