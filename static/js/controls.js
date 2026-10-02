// Custom form controls, on every page: dropdown menus, date and time pickers,
// suggestion lists, file drop zones and slider fill.
//
// Each control sits on top of the real form element, which keeps its value,
// its events and its place in the form. Saving code, validation and form posts
// never see a difference: a choice made here sets the element's value and fires
// the same input/change events a person would.
//
//   <select>                                  opens a styled menu, with a search box
//                                             once it has more than SEARCH_AT choices
//   <input type="date|time|datetime-local">   becomes a button that opens a calendar
//                                             and a clock
//   <input list="…">                          shows its <datalist> as a styled list
//   <input type="file">                       (visible ones) becomes a drop zone
//   <input type="range">                      gets a filled track (--fill)
//   [data-animated-list="<items>"]            a scrolling list whose items ease in
//                                             and whose edges fade while it scrolls
//                                             (data-animated-list-rows="N": N items tall)
//
// Every drop zone, including the editors' own and any [data-drop] card, takes
// dragged or pasted files through one shared handler (see "Dropping and pasting").
//
// Options can carry data-image (a picture) or data-icon (a Lucide icon name),
// shown next to their label in the menu, and data-tag (a short note, like a
// price) shown muted at the right. Put data-native on an element, or on
// a wrapper, to keep the browser's own control.

(function () {
    'use strict';

    const SEARCH_AT = 10;
    const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)');
    const SVG_NS = 'http://www.w3.org/2000/svg';
    let uid = 0;
    const nextId = prefix => `ctl-${prefix}-${++uid}`;

    // --- Helpers ----------------------------------------------------------------------

    // Values are set as attributes or text, never parsed as HTML.
    function h(tag, props = {}, children = []) {
        const node = document.createElement(tag);
        Object.entries(props).forEach(([key, value]) => {
            if (value === undefined || value === null || value === false) return;
            if (key === 'className') node.className = value;
            else if (key === 'text') node.textContent = value;
            else node.setAttribute(key, value === true ? '' : value);
        });
        [].concat(children).forEach(child => {
            if (child !== null && child !== undefined && child !== false) node.append(child);
        });
        return node;
    }

    // Drawn here rather than with Lucide, so they are there before Lucide loads.
    const PATHS = {
        check: ['M20 6 9 17l-5-5'],
        left: ['m15 18-6-6 6-6'],
        right: ['m9 18 6-6-6-6'],
        calendar: ['M8 2v4', 'M16 2v4', 'M3 10h18', 'M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z'],
        clock: ['M12 6v6l4 2', 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z'],
        search: ['m21 21-4.3-4.3', 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z'],
        upload: ['M12 3v12', 'm17 8-5-5-5 5', 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'],
    };

    function icon(name, className = 'ctl-icon') {
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('class', className);
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        PATHS[name].forEach(d => {
            const path = document.createElementNS(SVG_NS, 'path');
            path.setAttribute('d', d);
            svg.append(path);
        });
        return svg;
    }

    function fire(node, ...types) {
        types.forEach(type => node.dispatchEvent(new Event(type, { bubbles: true })));
    }

    const keepsNative = node => Boolean(node.closest('[data-native]'));

    // The visible text of an element's label, without the text of any control inside it.
    function labelOf(node) {
        if (node.getAttribute('aria-label')) return node.getAttribute('aria-label');
        const label = node.labels && node.labels[0];
        if (label) {
            const copy = label.cloneNode(true);
            copy.querySelectorAll('select, input, textarea, button, .visually-hidden').forEach(child => child.remove());
            const text = copy.textContent.replace(/\s+/g, ' ').trim();
            if (text) return text;
        }
        return node.getAttribute('title') || node.getAttribute('placeholder') || '';
    }

    // Keep scrolling inside a list instead of moving the page.
    function reveal(list, node, center = false) {
        const top = node.offsetTop;
        const bottom = top + node.offsetHeight;
        if (center) list.scrollTop = top - (list.clientHeight - node.offsetHeight) / 2;
        else if (top < list.scrollTop) list.scrollTop = top - 4;
        else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
    }

    // Assigning .value from code must redraw the control that shows it.
    const inputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

    function watchValue(input, onSet) {
        Object.defineProperty(input, 'value', {
            configurable: true,
            get() { return inputValue.get.call(this); },
            set(next) {
                inputValue.set.call(this, next);
                onSet();
            },
        });
    }

    // --- Popover layer -----------------------------------------------------------------------
    // One popover at a time, fixed to the viewport beside its anchor. On a narrow
    // screen it docks to the bottom edge as a sheet.

    const Popover = (function () {
        let current = null;

        function place() {
            if (!current) return;
            const { pop, anchor, matchWidth } = current;
            if (!anchor.isConnected || !anchor.getClientRects().length) {
                close('gone');
                return;
            }
            const sheet = window.innerWidth < 560;
            pop.classList.toggle('is-sheet', sheet);
            if (sheet) {
                pop.style.removeProperty('top');
                pop.style.removeProperty('left');
                pop.style.removeProperty('min-width');
                pop.style.setProperty('--pop-max', `${Math.round(window.innerHeight * 0.8)}px`);
                return;
            }
            const rect = anchor.getBoundingClientRect();
            const margin = 8;
            if (matchWidth) pop.style.minWidth = `${Math.round(rect.width)}px`;
            const below = window.innerHeight - rect.bottom - margin - 4;
            const above = rect.top - margin - 4;
            pop.style.setProperty('--pop-max', `${Math.round(Math.max(below, above, 160))}px`);
            const height = pop.offsetHeight;
            const width = pop.offsetWidth;
            const under = height <= below || below >= above;
            const top = under ? rect.bottom + 4 : rect.top - height - 4;
            const left = Math.min(rect.left, window.innerWidth - width - margin);
            pop.style.top = `${Math.round(Math.max(margin, top))}px`;
            pop.style.left = `${Math.round(Math.max(margin, left))}px`;
            // It grows out of the corner it shares with its anchor.
            pop.style.transformOrigin = `${under ? 'top' : 'bottom'} ${left < rect.left - 1 ? 'right' : 'left'}`;
        }

        // Follow the anchor while open: pages animate, toasts push content, lists grow.
        function follow() {
            if (!current) return;
            const r = current.anchor.getBoundingClientRect();
            const key = `${r.top}|${r.left}|${r.width}|${r.height}`;
            if (key !== current.key) {
                current.key = key;
                place();
            }
            if (current) current.frame = requestAnimationFrame(follow);
        }

        function open(pop, anchor, { onClose = null, matchWidth = false } = {}) {
            close('replaced');
            current = { pop, anchor, onClose, matchWidth, key: '', frame: 0 };
            pop.classList.add('ctl-pop');
            document.body.append(pop);
            follow();
            requestAnimationFrame(() => pop.classList.add('is-open'));
        }

        // `reason` tells the owner why: outside, escape, choose, done, toggle, tab, gone, replaced.
        function close(reason) {
            if (!current) return;
            const { pop, onClose, frame } = current;
            const hadFocus = pop.contains(document.activeElement);
            cancelAnimationFrame(frame);
            current = null;
            // Dismissed, it shrinks back into its corner; a choice closes it at once.
            if ((reason === 'outside' || reason === 'toggle') && pop.classList.contains('is-open') && !REDUCED.matches) {
                pop.classList.remove('is-open');
                pop.classList.add('is-leaving');
                setTimeout(() => pop.remove(), 140);
            } else {
                pop.remove();
            }
            if (onClose) onClose(reason, hadFocus);
        }

        document.addEventListener('pointerdown', e => {
            if (!current || current.pop.contains(e.target) || current.anchor.contains(e.target)) return;
            close('outside');
        }, true);
        window.addEventListener('resize', place);
        window.addEventListener('scroll', e => {
            if (current && !current.pop.contains(e.target)) place();
        }, true);

        return { open, close, place, isOpenFor: anchor => Boolean(current && current.anchor === anchor) };
    })();

    // Tab stays inside a popover that holds focus (the date picker); Escape leaves it.
    function trapFocus(pop, onEscape) {
        pop.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                onEscape();
                return;
            }
            if (e.key !== 'Tab') return;
            const stops = Array.from(pop.querySelectorAll('button:not([disabled]), input, [tabindex="0"]'))
                .filter(node => node.getClientRects().length && !node.closest('[hidden]'));
            if (!stops.length) return;
            const first = stops[0];
            const last = stops[stops.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        });
    }

    // --- Dropdowns -----------------------------------------------------------------------------
    // The <select> stays on the page, styled, and keeps focus; only its list is ours.

    const Dropdown = (function () {
        const seen = new WeakSet();
        const tints = new WeakMap();
        let state = null;

        // A disabled option with no value ("Move to…") is a prompt, not a choice.
        const choices = select => Array.from(select.options).filter(o => !o.hidden && !(o.disabled && o.value === ''));
        const enabled = () => state.items.filter(item => !item.node.hidden && !item.option.disabled);

        function build(select) {
            const list = h('div', { className: 'cs-list cs-glide', role: 'listbox', id: nextId('list'), 'aria-label': labelOf(select) || null });
            // One highlight that glides between rows instead of each row lighting up.
            const pill = h('span', { className: 'cs-pill', 'aria-hidden': 'true' });
            list.append(pill);
            const items = [];
            let group = null;
            choices(select).forEach(option => {
                const parent = option.parentElement;
                const inGroup = parent && parent.tagName === 'OPTGROUP' ? parent : null;
                if (inGroup && inGroup !== group) list.append(h('div', { className: 'cs-group', role: 'presentation', text: inGroup.label }));
                group = inGroup;
                const node = h('div', {
                    className: 'cs-option', role: 'option', id: nextId('opt'),
                    'aria-selected': String(option.selected), 'aria-disabled': option.disabled ? 'true' : null,
                }, [
                    option.dataset.image
                        ? h('img', { className: 'cs-thumb', src: option.dataset.image, alt: '', width: '24', height: '24' })
                        : option.dataset.icon ? h('i', { className: 'cs-lucide', 'data-lucide': option.dataset.icon, 'aria-hidden': 'true' }) : null,
                    h('span', { className: 'cs-label', text: option.label || option.textContent }),
                    option.dataset.tag ? h('span', { className: 'cs-tag', text: option.dataset.tag }) : null,
                    icon('check', 'ctl-icon cs-check'),
                ]);
                items.push({ option, node });
                list.append(node);
            });

            const pop = h('div', { className: 'cs-menu' });
            let search = null;
            if (items.length > SEARCH_AT) {
                search = h('input', {
                    type: 'text', className: 'cs-search', placeholder: 'Search…', autocomplete: 'off', spellcheck: 'false',
                    role: 'combobox', 'aria-expanded': 'true', 'aria-controls': list.id, 'aria-autocomplete': 'list',
                    'aria-label': `Search ${labelOf(select) || 'the choices'}`,
                });
                pop.append(h('div', { className: 'cs-search-wrap' }, [icon('search'), search]));
            }
            const empty = h('p', { className: 'cs-empty', text: 'Nothing matches.', hidden: true });
            pop.append(list, empty);

            const itemAt = target => {
                const node = target.closest && target.closest('.cs-option');
                return node ? items.find(item => item.node === node) : null;
            };
            // A mouse can press, drag along the rows and let go on one to pick it,
            // starting in the list or on the select itself. Taps pick on click, so
            // a finger can still scroll a long list.
            list.addEventListener('pointerdown', e => {
                e.preventDefault();
                if (state && e.pointerType !== 'touch') state.pressed = true;
            });
            list.addEventListener('pointerup', e => {
                if (state && state.pressed && e.pointerType !== 'touch') choose(itemAt(e.target), true);
            });
            list.addEventListener('click', e => {
                if (state) choose(itemAt(e.target), true);
            });
            list.addEventListener('pointermove', e => {
                const item = itemAt(e.target);
                if (item && !item.option.disabled && state && state.active !== item) activate(item, false, true);
            });
            if (search) {
                search.addEventListener('input', () => filter(search.value));
                search.addEventListener('keydown', e => onKey(e, select, true));
            }
            return { pop, list, pill, items, search, empty };
        }

        // The pointer glides the pill to its row; keys and opening jump it there.
        function glide(item, smooth) {
            const { pill } = state;
            if (!item || item.node.hidden) {
                pill.classList.remove('is-on');
                return;
            }
            const jump = !smooth || !pill.classList.contains('is-on') || REDUCED.matches;
            if (jump) pill.classList.add('is-instant');
            pill.style.transform = `translateY(${item.node.offsetTop}px)`;
            pill.style.height = `${item.node.offsetHeight}px`;
            if (jump) {
                void pill.offsetHeight;
                pill.classList.remove('is-instant');
            }
            pill.classList.add('is-on');
        }

        function activate(item, scroll = true, smooth = false) {
            if (state.active) state.active.node.classList.remove('is-active');
            state.active = item || null;
            glide(item, smooth);
            const owner = state.search || state.select;
            if (!item) {
                owner.removeAttribute('aria-activedescendant');
                return;
            }
            item.node.classList.add('is-active');
            owner.setAttribute('aria-activedescendant', item.node.id);
            if (scroll) reveal(state.list, item.node);
        }

        function move(step) {
            const pool = enabled();
            if (!pool.length) return;
            let i = pool.indexOf(state.active);
            if (i === -1) i = step > 0 ? -1 : pool.length;
            activate(pool[Math.max(0, Math.min(pool.length - 1, i + step))]);
        }

        function edge(last) {
            const pool = enabled();
            if (pool.length) activate(pool[last ? pool.length - 1 : 0]);
        }

        function typeahead(char) {
            const now = Date.now();
            state.typed = now - state.typedAt < 700 ? state.typed + char.toLowerCase() : char.toLowerCase();
            state.typedAt = now;
            const pool = enabled();
            const start = state.typed.length === 1 ? pool.indexOf(state.active) + 1 : 0;
            const ordered = pool.slice(start).concat(pool.slice(0, start));
            const hit = ordered.find(item => item.node.textContent.trim().toLowerCase().startsWith(state.typed));
            if (hit) activate(hit);
        }

        function filter(term) {
            const needle = term.trim().toLowerCase();
            let shown = 0;
            state.items.forEach(item => {
                const hit = !needle || item.node.textContent.toLowerCase().includes(needle);
                item.node.hidden = !hit;
                if (hit) shown++;
            });
            state.list.querySelectorAll('.cs-group').forEach(heading => {
                let next = heading.nextElementSibling;
                let any = false;
                while (next && !next.classList.contains('cs-group')) {
                    if (!next.hidden) {
                        any = true;
                        break;
                    }
                    next = next.nextElementSibling;
                }
                heading.hidden = !any;
            });
            state.empty.hidden = shown > 0;
            activate(enabled()[0] || null);
            Popover.place();
        }

        function open(select) {
            if (select.disabled || (state && state.select === select)) return;
            Popover.close('replaced');
            const built = build(select);
            state = Object.assign({ select, active: null, typed: '', typedAt: 0 }, built);
            select.setAttribute('aria-expanded', 'true');
            select.setAttribute('aria-controls', built.list.id);
            Popover.open(built.pop, select, { matchWidth: true, onClose: (reason, hadFocus) => closed(select, reason, hadFocus) });
            if (window.lucide && built.pop.querySelector('[data-lucide]')) window.lucide.createIcons();
            const selected = built.items.find(item => item.option.selected && !item.option.disabled);
            activate(selected || enabled()[0] || null, false);
            if (state.active) reveal(built.list, state.active.node, true);
            if (built.search) built.search.focus({ preventScroll: true });
        }

        function closed(select, reason, hadFocus) {
            select.setAttribute('aria-expanded', 'false');
            select.removeAttribute('aria-controls');
            select.removeAttribute('aria-activedescendant');
            state = null;
            if (hadFocus && reason !== 'outside') select.focus({ preventScroll: true });
        }

        function choose(item, byPointer = false) {
            if (!item || item.option.disabled) return;
            const { select } = state;
            Popover.close('choose');
            select.focus({ preventScroll: true });
            if (!item.option.selected) {
                item.option.selected = true;
                fire(select, 'input', 'change');
                // The new label settles in out of a soft blur.
                if (byPointer && !REDUCED.matches) {
                    select.classList.remove('cs-swap');
                    void select.offsetWidth;
                    select.classList.add('cs-swap');
                }
            }
        }

        function onKey(e, select, fromSearch) {
            const isOpen = Boolean(state && state.select === select);
            if (!isOpen) {
                // Enter is left alone: it still confirms dialogs and submits forms.
                if (['ArrowDown', 'ArrowUp', ' ', 'F4'].includes(e.key) && !e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    open(select);
                }
                return;
            }
            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    move(1);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    if (e.altKey) Popover.close('escape');
                    else move(-1);
                    break;
                case 'PageDown':
                case 'PageUp':
                    e.preventDefault();
                    move(e.key === 'PageDown' ? 8 : -8);
                    break;
                case 'Home':
                case 'End':
                    if (!fromSearch) {
                        e.preventDefault();
                        edge(e.key === 'End');
                    }
                    break;
                case 'Enter':
                    e.preventDefault();
                    e.stopPropagation();
                    choose(state.active);
                    break;
                case ' ':
                    if (!fromSearch) {
                        e.preventDefault();
                        choose(state.active);
                    }
                    break;
                case 'Escape':
                    e.preventDefault();
                    e.stopPropagation();
                    Popover.close('escape');
                    break;
                case 'Tab':
                    Popover.close('tab');
                    break;
                default:
                    if (!fromSearch && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                        e.preventDefault();
                        typeahead(e.key);
                    }
            }
        }

        // The chevron is drawn in the select's own text colour, so it suits every theme and badge.
        function tint(select) {
            const color = getComputedStyle(select).color;
            if (!color || tints.get(select) === color) return;
            tints.set(select, color);
            const chevron = d => `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'><path d='${d}' fill='none' stroke='${color}' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/></svg>`)}")`;
            select.style.setProperty('--cs-chevron', chevron('M1.5 1.75 6 6.25l4.5-4.5'));
            select.style.setProperty('--cs-chevron-open', chevron('M1.5 6.25 6 1.75l4.5 4.5'));
            select.style.setProperty('--cs-ink', color);
        }

        document.addEventListener('pointerup', () => {
            if (state) state.pressed = false;
        });

        function enhance(select) {
            if (seen.has(select) || select.multiple || select.size > 1 || keepsNative(select)) return;
            seen.add(select);
            select.classList.add('cs-select');
            select.setAttribute('aria-expanded', 'false');
            select.addEventListener('mousedown', e => {
                if (e.button !== 0 || select.disabled) return;
                e.preventDefault();
                if (Popover.isOpenFor(select)) {
                    Popover.close('toggle');
                    return;
                }
                select.focus({ preventScroll: true });
                open(select);
                if (state) state.pressed = true;
            });
            select.addEventListener('keydown', e => onKey(e, select, false));
            select.addEventListener('animationend', e => {
                if (e.animationName === 'cs-swap') select.classList.remove('cs-swap');
            });

            // A tap opens our list too; a swipe that starts on the select still scrolls the page.
            let start = null;
            select.addEventListener('touchstart', e => {
                start = { x: e.touches[0].clientX, y: e.touches[0].clientY };
            }, { passive: true });
            select.addEventListener('touchend', e => {
                if (!start || select.disabled) return;
                const touch = e.changedTouches[0];
                const moved = Math.abs(touch.clientX - start.x) > 10 || Math.abs(touch.clientY - start.y) > 10;
                start = null;
                if (moved) return;
                e.preventDefault();
                if (Popover.isOpenFor(select)) Popover.close('toggle');
                else open(select);
            });
            tint(select);
        }

        return { enhance, tint, owns: select => seen.has(select) };
    })();

    // --- Date and time pickers ----------------------------------------------------------------
    // The input is hidden but still holds the value in the browser's format
    // (2026-10-04, 09:30, 2026-10-04T09:30), so the server reads it as before.

    const DatePicker = (function () {
        const triggers = new WeakMap();
        const LOCALE = 'en-US';
        const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
        const MONTHS = Array.from({ length: 12 }, (_, i) => new Date(2000, i, 1).toLocaleString(LOCALE, { month: 'short' }));
        const DEFAULT_TIME = { h: 9, min: 0 };
        const pad = n => String(n).padStart(2, '0');
        const ymd = p => `${p.y}-${pad(p.m)}-${pad(p.d)}`;
        const hm = t => `${pad(t.h)}:${pad(t.min)}`;
        const toParts = date => ({ y: date.getFullYear(), m: date.getMonth() + 1, d: date.getDate() });
        const toDate = p => new Date(p.y, p.m - 1, p.d);
        const same = (a, b) => Boolean(a && b && a.y === b.y && a.m === b.m && a.d === b.d);
        const today = () => toParts(new Date());
        const addDays = (p, n) => toParts(new Date(p.y, p.m - 1, p.d + n));
        let current = null;

        function addMonths(p, n) {
            const first = new Date(p.y, p.m - 1 + n, 1);
            const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
            return { y: first.getFullYear(), m: first.getMonth() + 1, d: Math.min(p.d, last) };
        }

        function parse(kind, value) {
            let match;
            if (kind === 'time') {
                match = /^(\d{2}):(\d{2})/.exec(value || '');
                return { date: null, time: match ? { h: Number(match[1]), min: Number(match[2]) } : null };
            }
            match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(value || '');
            if (!match) return { date: null, time: null };
            const date = { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
            const time = match[4] !== undefined ? { h: Number(match[4]), min: Number(match[5]) } : null;
            return { date, time };
        }

        function formatTime(t) {
            return new Date(2000, 0, 1, t.h, t.min).toLocaleTimeString(LOCALE, { hour: 'numeric', minute: '2-digit' });
        }

        function format(kind, date, time) {
            const day = date && toDate(date).toLocaleDateString(LOCALE, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
            if (kind === 'date') return day || '';
            if (kind === 'time') return time ? formatTime(time) : '';
            return date ? `${day} · ${formatTime(time || DEFAULT_TIME)}` : '';
        }

        function placeholder(kind) {
            return kind === 'time' ? 'Pick a time' : kind === 'date' ? 'Pick a date' : 'Pick a date and time';
        }

        function bounds(input) {
            const min = parse('date', input.min).date;
            const max = parse('date', input.max).date;
            return p => (min && toDate(p) < toDate(min)) || (max && toDate(p) > toDate(max));
        }

        function minuteStep(input) {
            const seconds = Number(input.step);
            return seconds >= 60 && seconds % 60 === 0 && seconds <= 3600 ? seconds / 60 : 5;
        }

        // Classes, disabled and hidden follow the input, so saving ticks and layout rules still apply.
        function sync(input) {
            const trigger = triggers.get(input);
            if (!trigger) return;
            const { date, time } = parse(input.type, input.value);
            const text = format(input.type, date, time);
            trigger.className = ['dp-trigger', ...Array.from(input.classList).filter(c => c !== 'ctl-native'),
                text ? '' : 'is-empty'].filter(Boolean).join(' ');
            trigger.querySelector('.dp-text').textContent = text || input.placeholder || placeholder(input.type);
            trigger.disabled = input.disabled;
            trigger.hidden = input.hidden;
            trigger.setAttribute('aria-label', `${labelOf(input) || placeholder(input.type)}: ${text || 'not set'}`);
        }

        function enhance(input) {
            if (triggers.has(input) || keepsNative(input)) return;
            const trigger = h('button', { type: 'button', 'aria-haspopup': 'dialog', 'aria-expanded': 'false' }, [
                icon(input.type === 'time' ? 'clock' : 'calendar'),
                h('span', { className: 'dp-text' }),
            ]);
            triggers.set(input, trigger);
            input.after(trigger);
            input.classList.add('ctl-native');
            input.tabIndex = -1;
            input.setAttribute('aria-hidden', 'true');
            watchValue(input, () => sync(input));
            sync(input);

            // A label's click focuses the hidden input; send it on to the button.
            input.addEventListener('focus', () => trigger.focus());
            input.addEventListener('invalid', e => {
                e.preventDefault();
                trigger.classList.add('is-invalid');
                trigger.focus();
                if (!Popover.isOpenFor(trigger)) open(input);
            });
            trigger.addEventListener('click', () => {
                if (Popover.isOpenFor(trigger)) Popover.close('toggle');
                else open(input);
            });
            trigger.addEventListener('keydown', e => {
                if (e.key === 'ArrowDown' && !Popover.isOpenFor(trigger)) {
                    e.preventDefault();
                    open(input);
                }
            });
        }

        // --- The popover ---

        function open(input) {
            if (input.disabled) return;
            Popover.close('replaced');
            const kind = input.type;
            const trigger = triggers.get(input);
            const { date, time } = parse(kind, input.value);
            const focusDay = date || today();
            current = {
                input, kind, date, time, focusDay,
                view: { y: focusDay.y, m: focusDay.m }, mode: 'days',
                isOff: bounds(input), step: minuteStep(input),
            };
            const pop = h('div', {
                className: `dp-pop dp-pop--${kind === 'datetime-local' ? 'datetime' : kind}`,
                role: 'dialog', 'aria-label': labelOf(input) || placeholder(kind),
            });
            const body = h('div', { className: 'dp-body' });
            if (kind !== 'time') body.append(buildCalendar());
            if (kind !== 'date') body.append(buildClock());
            pop.append(body, buildFooter());
            trapFocus(pop, () => Popover.close('escape'));
            trigger.setAttribute('aria-expanded', 'true');
            trigger.classList.remove('is-invalid');
            Popover.open(pop, trigger, { onClose: (reason, hadFocus) => closed(input, reason, hadFocus) });
            requestAnimationFrame(() => {
                const target = kind === 'time'
                    ? pop.querySelector('.dp-col .is-selected') || pop.querySelector('.dp-cell')
                    : pop.querySelector('.dp-day[tabindex="0"]');
                if (target) target.focus({ preventScroll: true });
                revealClock();
            });
        }

        function closed(input, reason, hadFocus) {
            const state = current;
            current = null;
            const trigger = triggers.get(input);
            trigger.setAttribute('aria-expanded', 'false');
            if (reason !== 'escape' && reason !== 'replaced' && reason !== 'gone') commit(state);
            if (hadFocus && reason !== 'outside') trigger.focus({ preventScroll: true });
        }

        function commit(state) {
            const { input, kind } = state;
            let { date, time } = state;
            if (kind === 'datetime-local' && time && !date) date = today();
            let value = '';
            if (kind === 'date') value = date ? ymd(date) : '';
            else if (kind === 'time') value = time ? hm(time) : '';
            else value = date ? `${ymd(date)}T${hm(time || DEFAULT_TIME)}` : '';
            if (value === input.value) return;
            input.value = value;
            fire(input, 'input', 'change');
        }

        // --- Calendar ---

        function buildCalendar() {
            const prev = h('button', { type: 'button', className: 'dp-nav', 'aria-label': 'Previous month' }, icon('left'));
            const next = h('button', { type: 'button', className: 'dp-nav', 'aria-label': 'Next month' }, icon('right'));
            const title = h('button', { type: 'button', className: 'dp-title', 'aria-live': 'polite' });
            const week = h('div', { className: 'dp-week', 'aria-hidden': 'true' }, WEEKDAYS.map(day => h('span', { text: day })));
            const grid = h('div', { className: 'dp-grid', role: 'grid' });
            const months = h('div', { className: 'dp-months', hidden: true });
            current.cal = { prev, next, title, week, grid, months };

            prev.addEventListener('click', () => step(-1));
            next.addEventListener('click', () => step(1));
            title.addEventListener('click', () => {
                current.mode = current.mode === 'days' ? 'months' : 'days';
                draw();
                (current.mode === 'months' ? months.querySelector('.is-selected, button') : grid.querySelector('[tabindex="0"]'))?.focus();
            });
            grid.addEventListener('click', e => {
                const day = e.target.closest('.dp-day');
                if (day && !day.disabled) pick(parse('date', day.dataset.date).date);
            });
            grid.addEventListener('keydown', onGridKey);
            months.addEventListener('click', e => {
                const month = e.target.closest('[data-month]');
                if (!month) return;
                current.view.m = Number(month.dataset.month);
                current.focusDay = addMonths({ y: current.view.y, m: current.view.m, d: 1 }, 0);
                current.mode = 'days';
                draw();
                grid.querySelector('[tabindex="0"]')?.focus();
            });
            draw();
            return h('div', { className: 'dp-cal' }, [h('div', { className: 'dp-head' }, [prev, title, next]), week, grid, months]);
        }

        // In the month view the arrows step a year; in the day view, a month.
        function step(n) {
            if (current.mode === 'months') current.view.y += n;
            else {
                const moved = addMonths({ y: current.view.y, m: current.view.m, d: 1 }, n);
                current.view = { y: moved.y, m: moved.m };
                current.focusDay = addMonths(current.focusDay, n);
            }
            draw();
        }

        function draw() {
            const { cal, view, mode } = current;
            const days = mode === 'days';
            cal.title.textContent = days
                ? new Date(view.y, view.m - 1, 1).toLocaleDateString(LOCALE, { month: 'long', year: 'numeric' })
                : String(view.y);
            cal.title.setAttribute('aria-label', days ? `${cal.title.textContent}, choose a month` : `${view.y}, back to days`);
            cal.prev.setAttribute('aria-label', days ? 'Previous month' : 'Previous year');
            cal.next.setAttribute('aria-label', days ? 'Next month' : 'Next year');
            cal.week.hidden = !days;
            cal.grid.hidden = !days;
            cal.months.hidden = days;
            if (days) drawDays();
            else drawMonths();
        }

        function drawDays() {
            const { cal, view, date, isOff } = current;
            const now = today();
            const lead = new Date(view.y, view.m - 1, 1).getDay();
            let focus = current.focusDay;
            if (focus.y !== view.y || focus.m !== view.m) focus = { y: view.y, m: view.m, d: 1 };
            const rows = [];
            for (let w = 0; w < 6; w++) {
                const row = h('div', { className: 'dp-row', role: 'row' });
                for (let d = 0; d < 7; d++) {
                    const parts = addDays({ y: view.y, m: view.m, d: 1 }, w * 7 + d - lead);
                    const button = h('button', {
                        type: 'button', className: 'dp-day', role: 'gridcell', tabindex: same(parts, focus) ? '0' : '-1',
                        'data-date': ymd(parts), text: String(parts.d),
                        'aria-label': toDate(parts).toLocaleDateString(LOCALE, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }),
                    });
                    if (parts.m !== view.m) button.classList.add('is-outside');
                    if (same(parts, now)) {
                        button.classList.add('is-today');
                        button.setAttribute('aria-current', 'date');
                    }
                    if (same(parts, date)) {
                        button.classList.add('is-selected');
                        button.setAttribute('aria-selected', 'true');
                    }
                    if (isOff(parts)) button.disabled = true;
                    row.append(button);
                }
                rows.push(row);
            }
            cal.grid.replaceChildren(...rows);
        }

        function drawMonths() {
            const { cal, view, date } = current;
            cal.months.replaceChildren(...MONTHS.map((name, i) => {
                const chosen = date && date.y === view.y && date.m === i + 1;
                return h('button', {
                    type: 'button', className: `dp-month${chosen ? ' is-selected' : ''}`, 'data-month': String(i + 1),
                    text: name, 'aria-pressed': String(Boolean(chosen)),
                });
            }));
        }

        function focusDay(parts) {
            current.focusDay = parts;
            if (parts.y !== current.view.y || parts.m !== current.view.m) {
                current.view = { y: parts.y, m: parts.m };
                draw();
            } else {
                current.cal.grid.querySelectorAll('[tabindex="0"]').forEach(node => node.setAttribute('tabindex', '-1'));
            }
            const target = current.cal.grid.querySelector(`[data-date="${ymd(parts)}"]`);
            if (target) {
                target.setAttribute('tabindex', '0');
                target.focus();
            }
        }

        function onGridKey(e) {
            const day = e.target.closest('.dp-day');
            if (!day) return;
            const at = parse('date', day.dataset.date).date;
            const weekday = toDate(at).getDay();
            const moves = {
                ArrowLeft: () => addDays(at, -1),
                ArrowRight: () => addDays(at, 1),
                ArrowUp: () => addDays(at, -7),
                ArrowDown: () => addDays(at, 7),
                Home: () => addDays(at, -weekday),
                End: () => addDays(at, 6 - weekday),
                PageUp: () => addMonths(at, e.shiftKey ? -12 : -1),
                PageDown: () => addMonths(at, e.shiftKey ? 12 : 1),
            };
            if (moves[e.key]) {
                e.preventDefault();
                focusDay(moves[e.key]());
            }
        }

        function pick(parts) {
            current.date = parts;
            current.focusDay = parts;
            if (current.kind === 'date') {
                Popover.close('done');
                return;
            }
            if (!current.time) current.time = { ...DEFAULT_TIME };
            if (parts.m !== current.view.m || parts.y !== current.view.y) current.view = { y: parts.y, m: parts.m };
            draw();
            current.cal.grid.querySelector(`[data-date="${ymd(parts)}"]`)?.focus();
            drawClock();
        }

        // --- Clock ---

        function column(name, cells) {
            const col = h('div', { className: 'dp-col', role: 'listbox', 'aria-label': name },
                cells.map(cell => h('button', {
                    type: 'button', className: 'dp-cell', role: 'option', 'data-part': cell.part, 'data-value': String(cell.value),
                    text: cell.text, 'aria-selected': 'false',
                })));
            col.addEventListener('keydown', e => {
                const cell = e.target.closest('.dp-cell');
                if (!cell) return;
                let target = null;
                if (e.key === 'ArrowDown') target = cell.nextElementSibling;
                else if (e.key === 'ArrowUp') target = cell.previousElementSibling;
                else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                    const cols = Array.from(current.clock.querySelectorAll('.dp-col'));
                    const next = cols[cols.indexOf(col) + (e.key === 'ArrowRight' ? 1 : -1)];
                    target = next && (next.querySelector('.is-selected') || next.querySelector('.dp-cell'));
                } else return;
                e.preventDefault();
                if (target) {
                    target.focus();
                    reveal(target.parentElement, target);
                }
            });
            return col;
        }

        function buildClock() {
            const minutes = [];
            for (let m = 0; m < 60; m += current.step) minutes.push(m);
            if (current.time && !minutes.includes(current.time.min)) {
                minutes.push(current.time.min);
                minutes.sort((a, b) => a - b);
            }
            const clock = h('div', { className: 'dp-clock' }, [
                column('Hour', [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map(n => ({ part: 'hour', value: n, text: String(n) }))),
                column('Minute', minutes.map(n => ({ part: 'min', value: n, text: pad(n) }))),
                column('AM or PM', [{ part: 'pm', value: 0, text: 'AM' }, { part: 'pm', value: 1, text: 'PM' }]),
            ]);
            clock.addEventListener('click', e => {
                const cell = e.target.closest('.dp-cell');
                if (!cell) return;
                const t = current.time || { ...DEFAULT_TIME };
                const value = Number(cell.dataset.value);
                let hour = t.h;
                if (cell.dataset.part === 'hour') hour = (value % 12) + (t.h >= 12 ? 12 : 0);
                if (cell.dataset.part === 'pm') hour = (t.h % 12) + (value ? 12 : 0);
                current.time = { h: hour, min: cell.dataset.part === 'min' ? value : t.min };
                drawClock();
                cell.focus();
            });
            current.clock = clock;
            drawClock();
            return clock;
        }

        function drawClock() {
            if (current.clock) {
                const t = current.time;
                current.clock.querySelectorAll('.dp-cell').forEach(cell => {
                    const value = Number(cell.dataset.value);
                    const on = Boolean(t) && (cell.dataset.part === 'hour' ? value === (t.h % 12 || 12)
                        : cell.dataset.part === 'min' ? value === t.min : value === (t.h >= 12 ? 1 : 0));
                    cell.classList.toggle('is-selected', on);
                    cell.setAttribute('aria-selected', String(on));
                });
            }
            if (current.summary) {
                current.summary.textContent = format(current.kind, current.date || (current.time ? today() : null), current.time)
                    || 'Nothing picked yet';
            }
        }

        function revealClock() {
            if (!current || !current.clock) return;
            current.clock.querySelectorAll('.dp-col').forEach(col => {
                const chosen = col.querySelector('.is-selected');
                if (chosen) reveal(col, chosen, true);
            });
        }

        // --- Footer: shortcuts and Done ---

        function buildFooter() {
            const { kind, input } = current;
            const button = (text, className, run) => {
                const node = h('button', { type: 'button', className, text });
                node.addEventListener('click', run);
                return node;
            };
            const tools = [];
            if (kind !== 'time') {
                tools.push(button('Today', 'dp-link', () => {
                    const now = today();
                    current.view = { y: now.y, m: now.m };
                    current.mode = 'days';
                    pick(now);
                }));
            } else {
                tools.push(button('Now', 'dp-link', () => {
                    const now = new Date();
                    const min = Math.min(55, Math.round(now.getMinutes() / current.step) * current.step);
                    current.time = { h: now.getHours(), min };
                    drawClock();
                    revealClock();
                }));
            }
            if (!input.required) {
                tools.push(button('Clear', 'dp-link', () => {
                    current.date = null;
                    current.time = null;
                    Popover.close('done');
                }));
            }
            const foot = h('div', { className: 'dp-foot' }, [h('div', { className: 'dp-tools' }, tools)]);
            if (kind !== 'date') {
                current.summary = h('span', { className: 'dp-summary', 'aria-live': 'polite' });
                foot.append(current.summary, button('Done', 'dp-done', () => Popover.close('done')));
                drawClock();
            }
            return foot;
        }

        return { enhance, sync, owns: input => triggers.has(input), triggerFor: input => triggers.get(input) };
    })();

    // --- Suggestions (datalist) ---------------------------------------------------------------
    // The native list only matches from the start in some browsers and cannot be styled.
    // This one matches anywhere in the text and highlights the match.

    const Suggest = (function () {
        const seen = new WeakSet();
        let state = null;
        let picking = false;

        function enhance(input) {
            const listId = input.getAttribute('list');
            if (!listId || seen.has(input) || keepsNative(input)) return;
            seen.add(input);
            input.removeAttribute('list');
            input.dataset.suggest = listId;
            input.setAttribute('autocomplete', 'off');
            input.setAttribute('role', 'combobox');
            input.setAttribute('aria-autocomplete', 'list');
            input.setAttribute('aria-expanded', 'false');
        }

        function marked(text, needle) {
            const at = needle ? text.toLowerCase().indexOf(needle) : -1;
            if (at < 0) return [text];
            return [text.slice(0, at), h('mark', { text: text.slice(at, at + needle.length) }), text.slice(at + needle.length)];
        }

        function show(input) {
            const datalist = document.getElementById(input.dataset.suggest);
            if (!datalist) return;
            const typed = input.value.trim();
            const needle = typed.toLowerCase();
            const seenValues = new Set();
            const matches = Array.from(datalist.options)
                .map(option => ({ value: option.value, label: option.label && option.label !== option.value ? option.label : '' }))
                .filter(option => {
                    if (!option.value || seenValues.has(option.value) || option.value === input.value) return false;
                    seenValues.add(option.value);
                    return !needle || option.value.toLowerCase().includes(needle) || option.label.toLowerCase().includes(needle);
                })
                .slice(0, 60);
            if (!matches.length) {
                if (state && state.input === input) Popover.close('empty');
                return;
            }
            if (!state || state.input !== input) {
                Popover.close('replaced');
                const list = h('div', { className: 'cs-list', role: 'listbox', id: nextId('suggest'), 'aria-label': 'Suggestions' });
                const pop = h('div', { className: 'cs-menu sg-menu' }, [list]);
                list.addEventListener('pointerdown', e => e.preventDefault());
                list.addEventListener('click', e => {
                    const node = e.target.closest('.cs-option');
                    if (node && state) pick(state.items.find(item => item.node === node));
                });
                state = { input, list, items: [], active: null };
                input.setAttribute('aria-expanded', 'true');
                input.setAttribute('aria-controls', list.id);
                Popover.open(pop, input, { matchWidth: true, onClose: () => closed(input) });
            }
            state.items = matches.map(match => ({
                value: match.value,
                node: h('div', { className: 'cs-option', role: 'option', id: nextId('sg'), 'aria-selected': 'false' }, [
                    h('span', { className: 'cs-label' }, marked(match.value, needle)),
                    match.label ? h('span', { className: 'sg-note' }, marked(match.label, needle)) : null,
                ]),
            }));
            state.list.replaceChildren(...state.items.map(item => item.node));
            state.active = null;
            input.removeAttribute('aria-activedescendant');
            Popover.place();
        }

        function closed(input) {
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            input.removeAttribute('aria-controls');
            state = null;
        }

        function activate(item) {
            if (state.active) state.active.node.classList.remove('is-active');
            state.active = item;
            item.node.classList.add('is-active');
            state.input.setAttribute('aria-activedescendant', item.node.id);
            reveal(state.list, item.node);
        }

        function move(step) {
            const { items, active } = state;
            let i = items.indexOf(active);
            if (i === -1) i = step > 0 ? -1 : items.length;
            activate(items[Math.max(0, Math.min(items.length - 1, i + step))]);
        }

        function pick(item) {
            if (!item) return;
            const { input } = state;
            Popover.close('choose');
            picking = true;
            input.value = item.value;
            fire(input, 'input', 'change');
            picking = false;
        }

        const isSuggest = node => node instanceof HTMLInputElement && Boolean(node.dataset.suggest);

        document.addEventListener('input', e => {
            if (!picking && isSuggest(e.target) && document.activeElement === e.target) show(e.target);
        });
        document.addEventListener('click', e => {
            if (isSuggest(e.target) && !Popover.isOpenFor(e.target)) show(e.target);
        });
        document.addEventListener('focusout', e => {
            if (state && e.target === state.input) Popover.close('blur');
        });
        // Capture, so a chosen suggestion wins over page shortcuts on Enter and Escape.
        document.addEventListener('keydown', e => {
            if (!isSuggest(e.target)) return;
            const open = Boolean(state && state.input === e.target);
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (!open) show(e.target);
                else move(e.key === 'ArrowDown' ? 1 : -1);
            } else if (open && e.key === 'Enter' && state.active) {
                e.preventDefault();
                e.stopPropagation();
                pick(state.active);
            } else if (open && e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                Popover.close('escape');
            } else if (open && e.key === 'Tab') {
                Popover.close('tab');
            }
        }, true);

        return { enhance };
    })();

    // --- File inputs ------------------------------------------------------------------------------
    // Only visible ones; the editors already draw their own drop zones around hidden inputs.
    // Dropping and pasting are handled for every zone at once, further down.

    const FileDrop = (function () {
        const zones = new WeakMap();
        const inputs = new WeakMap();

        function sync(input) {
            const zone = zones.get(input);
            if (!zone) return;
            const count = input.files ? input.files.length : 0;
            zone.querySelector('.fd-name').textContent = count > 1 ? `${count} files` : count ? input.files[0].name : '';
            zone.classList.toggle('has-file', count > 0);
            zone.disabled = input.disabled;
            zone.hidden = input.hidden;
        }

        function enhance(input) {
            if (zones.has(input) || keepsNative(input) || input.classList.contains('visually-hidden')
                || input.closest('.drop-zone, [data-upload]')) return;
            const zone = h('button', { type: 'button', className: 'file-drop', 'aria-label': `${labelOf(input) || 'File'}: choose a file` }, [
                icon('upload'),
                h('span', { className: 'fd-text' }, [h('strong', { text: 'Choose a file' }), ' or drop it here']),
                h('span', { className: 'fd-name' }),
            ]);
            zones.set(input, zone);
            inputs.set(zone, input);
            input.after(zone);
            input.classList.add('ctl-native');
            input.tabIndex = -1;
            zone.addEventListener('click', () => input.click());
            input.addEventListener('change', () => sync(input));
            sync(input);
        }

        return {
            enhance, sync,
            owns: input => zones.has(input),
            zoneFor: input => zones.get(input),
            inputOf: zone => inputs.get(zone),
        };
    })();

    // --- Dropping and pasting files -------------------------------------------------------------------
    // Every drop zone on the page takes files dragged onto it, or pasted (Ctrl+V) while it has
    // the keyboard focus or the pointer:
    //   .drop-zone, .file-drop   an upload box around (or beside) a file input
    //   [data-drop]              a bigger target, like a whole card or row. It feeds the file input
    //                            inside it or the one named by data-drop-input; with
    //                            data-drop="event" it only fires ctl:files (below).
    // Files are checked against the input's accept list (or data-drop-accept). A zone takes one
    // file unless its input is multiple or it has data-drop-multiple; several files over a
    // one-file zone go to the nearest zone around it that takes several.
    //
    // The zone first gets a bubbling, cancelable ctl:files event with detail.files. Page code
    // can preventDefault() it to handle the files itself; otherwise they are put on the input,
    // which fires input and change as if a person had picked them.
    //
    // While files are over the page, html.ctl-dragging lights up every zone. The one under the
    // pointer gets .is-over and shows its data-drop-label (data-drop-label-many for several
    // files, {n} being the count). A drop that misses every zone is refused, so the browser
    // never replaces the page, and its unsaved edits, with the file.

    (function drops() {
        const ZONE = '.drop-zone, .file-drop, [data-drop]';
        const IDLE_MS = 1200;
        const status = h('div', { className: 'visually-hidden', role: 'status', 'aria-live': 'polite' });
        let dragging = false;
        let over = null;
        let hovered = null;
        let idle = 0;
        let note = null;
        let noteTimer = 0;

        const hasFiles = e => Boolean(e.dataTransfer) && Array.from(e.dataTransfer.types || []).includes('Files');
        const elementOf = node => (node && node.nodeType === 1 ? node : node && node.parentElement) || null;
        const outerZone = zone => zone.parentElement && zone.parentElement.closest(ZONE);

        function inputFor(zone) {
            if (zone.dataset.drop === 'event') return null;
            if (zone.dataset.dropInput) return document.getElementById(zone.dataset.dropInput);
            return FileDrop.inputOf(zone) || zone.querySelector('input[type="file"]');
        }

        function usable(zone) {
            if (!zone.isConnected || zone.hidden || zone.disabled || keepsNative(zone)) return false;
            if (zone.dataset.drop === 'event') return true;
            const input = inputFor(zone);
            return Boolean(input) && !input.disabled;
        }

        const takesMany = zone => zone.hasAttribute('data-drop-multiple') || Boolean(inputFor(zone)?.multiple);
        const acceptOf = zone => zone.dataset.dropAccept || inputFor(zone)?.accept || '';

        // The zone a drop on `node` belongs to, for `count` files.
        function zoneFor(node, count = 1) {
            let zone = elementOf(node)?.closest(ZONE) || null;
            while (zone && !usable(zone)) zone = outerZone(zone);
            if (!zone || count < 2 || takesMany(zone)) return zone;
            let outer = outerZone(zone);
            while (outer && !(usable(outer) && takesMany(outer))) outer = outerZone(outer);
            return outer || zone;
        }

        function rulesOf(accept) {
            return accept.split(',').map(rule => rule.trim().toLowerCase()).filter(Boolean);
        }

        function accepts(file, accept) {
            const rules = rulesOf(accept);
            if (!rules.length) return true;
            const type = (file.type || '').toLowerCase();
            const name = file.name.toLowerCase();
            return rules.some(rule => {
                if (rule.startsWith('.')) return name.endsWith(rule);
                if (rule.endsWith('/*')) return type.startsWith(rule.slice(0, -1));
                return type === rule;
            });
        }

        const NAMES = { jpeg: 'JPG', 'svg+xml': 'SVG', webp: 'WebP', plain: '.txt', csv: '.csv' };
        const orList = items => (items.length < 2 ? items.join('')
            : `${items.slice(0, -1).join(', ')} or ${items[items.length - 1]}`);

        // "Only PNG, JPG or WebP images go here." from an accept list.
        function describe(accept) {
            const rules = rulesOf(accept);
            if (rules.includes('image/*') && rules.length === 1) return 'Only images go here.';
            const images = rules.filter(rule => rule.startsWith('image/'));
            const kinds = [...new Set(rules.map(rule => {
                const sub = rule.startsWith('.') ? rule : rule.split('/')[1];
                return NAMES[sub] || (sub.startsWith('.') ? sub : sub.toUpperCase());
            }))];
            return `Only ${orList(kinds)} ${images.length === rules.length ? 'images' : 'files'} go here.`;
        }

        // A short message beside the zone, also read out by screen readers.
        function tell(zone, message) {
            status.textContent = message;
            note?.remove();
            note = h('div', { className: 'drop-note', text: message });
            document.body.append(note);
            const rect = zone.getBoundingClientRect();
            const room = window.innerHeight - rect.bottom;
            note.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - note.offsetWidth - 8))}px`;
            note.style.top = `${room > note.offsetHeight + 14 ? rect.bottom + 6 : Math.max(8, rect.top - note.offsetHeight - 6)}px`;
            clearTimeout(noteTimer);
            const shown = note;
            noteTimer = setTimeout(() => {
                shown.classList.add('is-leaving');
                setTimeout(() => shown.remove(), 250);
            }, 3600);
        }

        function deliver(zone, files) {
            const input = inputFor(zone);
            const accept = acceptOf(zone);
            const fits = files.filter(file => accepts(file, accept));
            if (!fits.length) {
                tell(zone, describe(accept));
                return;
            }
            const chosen = takesMany(zone) ? fits : fits.slice(0, 1);
            const event = new CustomEvent('ctl:files', { bubbles: true, cancelable: true, detail: { files: chosen, input } });
            if (zone.dispatchEvent(event) && input) {
                const transfer = new DataTransfer();
                chosen.forEach(file => transfer.items.add(file));
                input.files = transfer.files;
                fire(input, 'input', 'change');
            }
            const skipped = files.length - chosen.length;
            if (skipped && fits.length > chosen.length) tell(zone, `One file at a time here, so only ${chosen[0].name} was used.`);
            else if (skipped) tell(zone, `Skipped ${skipped} file${skipped === 1 ? '' : 's'}. ${describe(accept)}`);
        }

        // --- Highlighting ----------------------------------------------------------------

        function point(zone, count, y) {
            if (over && over !== zone) {
                over.classList.remove('is-over');
                over.removeAttribute('data-drop-now');
                over.style.removeProperty('--drop-y');
            }
            over = zone;
            if (!zone) return;
            // dragover repeats many times a second; only touch the DOM when something changes.
            if (!zone.classList.contains('is-over')) zone.classList.add('is-over');
            const template = (count > 1 && zone.dataset.dropLabelMany) || zone.dataset.dropLabel || '';
            const label = template.replace('{n}', count);
            if (label && zone.dataset.dropNow !== label) zone.dataset.dropNow = label;
            else if (!label) zone.removeAttribute('data-drop-now');
            // On a tall zone the label sits level with the pointer, so it is always in view.
            const rect = zone.getBoundingClientRect();
            if (label && rect.height > 120) {
                zone.style.setProperty('--drop-y', `${Math.round(Math.max(28, Math.min(rect.height - 28, y - rect.top)))}px`);
            }
        }

        function stop() {
            dragging = false;
            clearTimeout(idle);
            document.documentElement.classList.remove('ctl-dragging');
            point(null);
        }

        // Browsers do not always say how many files are coming until the drop.
        function countOf(e) {
            const items = e.dataTransfer.items;
            const count = items ? Array.from(items).filter(item => item.kind === 'file').length : 0;
            return count || 1;
        }

        function onDrag(e) {
            if (!hasFiles(e) || !document.querySelector(ZONE)) return;
            e.preventDefault();
            if (!dragging) {
                dragging = true;
                document.documentElement.classList.add('ctl-dragging');
            }
            // dragover repeats while the pointer is on the page; silence means it left.
            clearTimeout(idle);
            idle = setTimeout(stop, IDLE_MS);
            const count = countOf(e);
            const zone = zoneFor(e.target, count);
            point(zone, count, e.clientY);
            e.dataTransfer.dropEffect = zone ? 'copy' : 'none';
        }

        document.addEventListener('dragenter', onDrag);
        document.addEventListener('dragover', onDrag);
        document.addEventListener('dragleave', e => {
            if (!dragging || e.relatedTarget) return;
            const { clientX: x, clientY: y } = e;
            if (x <= 0 || y <= 0 || x >= window.innerWidth || y >= window.innerHeight) stop();
        });
        document.addEventListener('drop', e => {
            if (!dragging || !hasFiles(e)) return;
            e.preventDefault();
            const files = Array.from(e.dataTransfer.files || []);
            const zone = zoneFor(e.target, files.length);
            stop();
            if (zone && files.length) deliver(zone, files);
        });
        document.addEventListener('dragend', stop);

        // --- Pasting --------------------------------------------------------------------------

        document.addEventListener('mouseover', e => {
            hovered = e.target;
        }, { passive: true });

        document.addEventListener('paste', e => {
            const data = e.clipboardData;
            const files = Array.from((data && data.files) || []);
            if (!files.length) return;
            const focused = document.activeElement;
            // Text copied with a picture (from a web page, say) is meant for the text field.
            if (focused && focused.matches('input:not([type="file"]), textarea, [contenteditable]')
                && Array.from(data.types).includes('text/plain')) return;
            const zone = (focused && focused !== document.body && zoneFor(focused, files.length))
                || zoneFor(hovered, files.length);
            if (!zone) return;
            e.preventDefault();
            deliver(zone, files);
        });

        document.body.append(status);
    })();

    // --- Sliders --------------------------------------------------------------------------------------

    function paintRange(input) {
        const min = Number(input.min || 0);
        const max = Number(input.max || 100);
        const pct = max > min ? ((Number(input.value) - min) / (max - min)) * 100 : 0;
        input.style.setProperty('--fill', `${Math.max(0, Math.min(100, pct))}%`);
    }

    document.addEventListener('input', e => {
        if (e.target instanceof HTMLInputElement && e.target.type === 'range') paintRange(e.target);
    });

    // --- Animated lists ---------------------------------------------------------------------------------
    // data-animated-list="<item selector>" on a scrolling box: items ease in once half of them
    // is in view, and the edges fade while there is more to scroll (controls.css, section 10).

    const AnimatedList = (function () {
        const still = window.matchMedia('(prefers-reduced-motion: reduce)');
        const seen = new WeakSet();

        function fades(list) {
            const { scrollTop, scrollHeight, clientHeight } = list;
            const bottom = scrollHeight <= clientHeight ? 0 : Math.min((scrollHeight - scrollTop - clientHeight) / 50, 1);
            list.style.setProperty('--fade-top', Math.min(scrollTop / 50, 1).toFixed(2));
            list.style.setProperty('--fade-bottom', bottom.toFixed(2));
        }

        // data-animated-list-rows="N": the box is exactly N items tall, however tall they are.
        function fit(list, selector) {
            const rows = Number(list.dataset.animatedListRows);
            if (!rows) return;
            const items = list.querySelectorAll(selector);
            const last = items[rows - 1];
            if (items.length <= rows || !last) {
                list.style.removeProperty('max-height');
                return;
            }
            if (!last.offsetHeight) return; // hidden (a closed tab); measured again once shown
            const style = getComputedStyle(list);
            const px = name => parseFloat(style[name]) || 0;
            // offsetTop counts from inside the border (the box is positioned, see controls.css).
            const bottom = last.offsetTop + last.offsetHeight;
            const height = style.boxSizing === 'border-box'
                ? bottom + px('paddingBottom') + px('borderTopWidth') + px('borderBottomWidth')
                : bottom - px('paddingTop');
            list.style.maxHeight = `${Math.ceil(height)}px`;
        }

        function enhance(list) {
            if (seen.has(list)) return;
            seen.add(list);
            const selector = list.dataset.animatedList || ':scope > *';
            const update = () => {
                fit(list, selector);
                fades(list);
            };
            const inView = 'IntersectionObserver' in window && !still.matches && new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    // An item moved to another list reports here once more; only its own list counts.
                    if (list.contains(entry.target)) entry.target.classList.toggle('is-in', entry.intersectionRatio >= 0.5);
                });
            }, { root: list, threshold: [0, 0.5] });
            // The box and, when it counts rows, its items: a closed tab opening or a card growing changes the fit.
            const resized = 'ResizeObserver' in window && new ResizeObserver(update);
            if (resized) resized.observe(list);
            const watch = () => list.querySelectorAll(selector).forEach(item => {
                item.classList.add('ctl-animated-item');
                if (inView) inView.observe(item);
                if (resized && list.dataset.animatedListRows) resized.observe(item);
            });
            if (inView) list.classList.add('is-animated');
            watch();
            new MutationObserver(records => {
                if (inView) records.forEach(record => record.removedNodes.forEach(node => {
                    if (node.nodeType === 1 && !list.contains(node)) inView.unobserve(node);
                }));
                watch();
                update();
            }).observe(list, { childList: true, subtree: true });
            list.addEventListener('scroll', () => fades(list), { passive: true });
            update();
        }

        return { enhance };
    })();

    // --- Wiring -------------------------------------------------------------------------------------------

    const TARGETS = 'select, input[type="date"], input[type="time"], input[type="datetime-local"], input[list], input[type="file"], input[type="range"]';

    function enhance(node) {
        if (node.tagName === 'SELECT') Dropdown.enhance(node);
        else if (['date', 'time', 'datetime-local'].includes(node.type)) DatePicker.enhance(node);
        else if (node.type === 'file') FileDrop.enhance(node);
        else if (node.type === 'range') paintRange(node);
        else if (node.hasAttribute('list')) Suggest.enhance(node);
    }

    function enhanceWithin(root) {
        if (root.nodeType !== 1) return;
        if (root.matches(TARGETS)) enhance(root);
        root.querySelectorAll(TARGETS).forEach(enhance);
        if (root.matches('[data-animated-list]')) AnimatedList.enhance(root);
        root.querySelectorAll('[data-animated-list]').forEach(AnimatedList.enhance);
    }

    // A control removed on its own leaves its button behind; take that too.
    function cleanUp(root) {
        if (root.nodeType !== 1) return;
        const inputs = root.matches('input') ? [root] : Array.from(root.querySelectorAll('input.ctl-native'));
        inputs.forEach(input => {
            const companion = DatePicker.triggerFor(input) || FileDrop.zoneFor(input);
            if (companion && companion.isConnected && !input.isConnected) companion.remove();
        });
    }

    function syncAttributes(node) {
        if (DatePicker.owns(node)) DatePicker.sync(node);
        else if (FileDrop.owns(node)) FileDrop.sync(node);
        else if (Dropdown.owns(node)) Dropdown.tint(node);
    }

    enhanceWithin(document.body);

    new MutationObserver(records => {
        records.forEach(record => {
            if (record.type === 'childList') {
                record.addedNodes.forEach(enhanceWithin);
                record.removedNodes.forEach(cleanUp);
            } else {
                syncAttributes(record.target);
            }
        });
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'disabled', 'hidden'] });

    // The chevrons follow the text colour, which changes with the theme.
    new MutationObserver(() => document.querySelectorAll('select.cs-select').forEach(Dropdown.tint))
        .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // form.reset() restores values without an input event; redraw once it has.
    document.addEventListener('reset', e => {
        setTimeout(() => e.target.querySelectorAll('input.ctl-native').forEach(syncAttributes), 0);
    }, true);
})();
