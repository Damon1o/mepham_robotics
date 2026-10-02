// Swipe rows: drag a list row sideways to uncover a drawer of actions. Drag far
// enough (or flick) and the outermost action leaps across the whole row and
// runs, the way Mail deletes a message.
//
// A vanilla port of React Bits' <SwipeRow> (motion springs replaced by a small
// spring solver below). One change for this site: an action with `fuse` does not
// fold the row straight away. The leapt block becomes a Fuse Undo button
// (fuse.js); the row folds and onCommit runs only once the fuse burns out, and
// Undo slides the row back.
//
//   SwipeRow.attach(rowElement, {
//       actions: [                                  // outermost first
//           { id: 'delete', label: 'Delete', icon: 'trash-2', fuse: 'Deleting this message' },
//           { id: 'archive', label: 'Archive', icon: 'archive', hidden: () => isArchived },
//       ],
//       onAction: (action, row) => ...,             // any button press
//       onCommit: (action, row) => ...,             // full swipe or a folding action, once shut
//       fold: item,                                 // what folds shut (default: the row)
//       label: 'Message from Ana',                  // accessible name
//       direction, actionWidth, snapBounce, resistance, collapseMs, commitAt, fullSwipe, haptic,
//   });
//
// The first action is the full-swipe one and always folds the row; others fold
// only with `dismiss`. `hidden` is asked each time the drawer opens. The row is
// wrapped in place, so it keeps its own markup and listeners. If the commit
// fails, call row.reset() to unfold it. Colours come from --sr-* properties.

(function () {
    'use strict';

    const HYST = 10;
    const FLICK = 110;
    const DECEL = 0.998;
    const VMAX = 1500;
    const UI = { duration: 0.3, bounce: 0 };

    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    const rubber = (o, dim, c) => (o * dim * c) / (dim + c * Math.abs(o));
    const unrubber = (y, dim, c) => (y * dim) / (c * Math.max(1, dim - Math.abs(y)));
    const project = v => ((v / 1000) * DECEL) / (1 - DECEL);
    const velocityOf = hist => {
        if (hist.length < 2) return 0;
        const a = hist[0];
        const b = hist[hist.length - 1];
        return ((b[1] - a[1]) / Math.max(1, b[0] - a[0])) * 1000;
    };
    const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const easeOut = t => 1 - Math.pow(1 - t, 4);

    // An animatable number. to() runs a spring ({ duration, bounce, velocity })
    // or, with ease: true, a plain ease-out tween; it resolves when it settles
    // and never if stopped first.
    function value(onChange, rest = 0.5) {
        let v = 0;
        let frame = 0;
        const stop = () => { cancelAnimationFrame(frame); frame = 0; };
        const set = n => { stop(); v = n; onChange(); };
        function to(target, { duration = 0.3, bounce = 0, velocity = 0, ease = false } = {}) {
            stop();
            const from = v;
            const omega = (2 * Math.PI) / duration;
            const k = omega * omega;
            const c = 2 * (1 - clamp(bounce, 0, 0.95)) * omega;
            let vel = velocity;
            let last = performance.now();
            const start = last;
            return new Promise(resolve => {
                const tick = now => {
                    if (ease) {
                        const t = Math.min(1, (now - start) / (duration * 1000));
                        v = from + (target - from) * easeOut(t);
                        if (t >= 1) { frame = 0; onChange(); resolve(); return; }
                    } else {
                        let dt = Math.min(64, now - last) / 1000;
                        while (dt > 0) {
                            const h = Math.min(dt, 0.004);
                            vel += (-k * (v - target) - c * vel) * h;
                            v += vel * h;
                            dt -= h;
                        }
                        if (Math.abs(v - target) < rest && Math.abs(vel) < rest * 20) {
                            v = target;
                            frame = 0;
                            onChange();
                            resolve();
                            return;
                        }
                    }
                    last = now;
                    onChange();
                    frame = requestAnimationFrame(tick);
                };
                frame = requestAnimationFrame(tick);
            });
        }
        return { get: () => v, set, to, stop };
    }

    function node(tag, className, attrs = {}) {
        const n = document.createElement(tag);
        n.className = className;
        Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
        return n;
    }

    function glyph(action) {
        const g = node('span', 'swipe-row__glyph');
        if (action.icon) {
            const icon = node('span', 'swipe-row__icon');
            icon.append(node('i', '', { 'data-lucide': action.icon, 'aria-hidden': 'true' }));
            g.append(icon);
        }
        g.append(Object.assign(document.createElement('span'), { textContent: action.label }));
        return g;
    }

    let uid = 0;

    function attach(surface, opts = {}) {
        const actions = opts.actions || [{ id: 'delete', label: 'Delete', icon: 'trash-2' }];
        const s = (opts.direction || 'left') === 'left' ? -1 : 1;
        const A = opts.actionWidth || 76;
        const c = clamp(opts.resistance ?? 0.55, 0.05, 1);
        const commitAt = opts.commitAt ?? 0.6;
        const fullSwipe = opts.fullSwipe !== false;
        const snapBounce = opts.snapBounce ?? 0.2;
        const collapseMs = opts.collapseMs ?? 200;
        const primary = actions[0];
        const railId = `swipe-row-${++uid}-rail`;

        // Build: root > clip > [rail, surface], with the surface wrapped in place.
        const root = node('div', 'swipe-row', { role: 'group', 'aria-label': opts.label || 'List item' });
        root.dataset.direction = s < 0 ? 'left' : 'right';
        root.dataset.phase = 'idle';
        root.style.setProperty('--sr-a', `${A}px`);
        const clip = node('div', 'swipe-row__clip');
        const rail = node('div', 'swipe-row__rail', { id: railId, 'aria-hidden': 'true' });
        rail.inert = true;
        surface.before(root);
        surface.classList.add('swipe-row__surface');
        clip.append(rail, surface);
        const sr = node('span', 'swipe-row__sr', { 'aria-live': 'polite' });
        root.append(clip, sr);

        const buttons = new Map();
        actions.slice(1).forEach(a => {
            const b = node('button', 'swipe-row__action', { type: 'button' });
            b.dataset.swipeAction = a.id;
            b.append(glyph(a));
            b.addEventListener('click', e => act(a, e));
            buttons.set(a, b);
            rail.append(b);
        });
        const block = node('div', 'swipe-row__block');
        const commitBtn = node('button', 'swipe-row__action swipe-row__action--commit', { type: 'button' });
        commitBtn.dataset.swipeAction = primary.id;
        commitBtn.append(glyph(primary));
        commitBtn.addEventListener('click', e => act(primary, e));
        block.append(commitBtn);
        rail.append(block);

        const toggle = node('button', 'swipe-row__toggle', {
            type: 'button', 'aria-expanded': 'false', 'aria-controls': railId,
            'aria-keyshortcuts': s < 0 ? 'ArrowLeft' : 'ArrowRight',
        });
        surface.append(toggle);
        window.lucide?.createIcons();

        let w = root.offsetWidth || 360;
        new ResizeObserver(entries => {
            const width = entries[0]?.contentRect.width;
            if (width) { w = width; render(); }
        }).observe(root);

        let open = false;
        let phase = 'idle';
        let grip = null;
        let heading = null;
        let foldAnim = null;
        let swallowClick = false;
        let D = A;
        let n = 1;

        const x = value(render);
        const spread = value(render, 0.002);
        const landed = value(render, 0.002);

        // commitAt of a wide desktop row is a long haul; never ask for more than
        // two action widths past the drawer.
        const commitPoint = () => Math.max(Math.min(commitAt * w, D + 2 * A), D + A / 2);
        const canCommit = () => fullSwipe && commitPoint() <= w;
        const exposed = () => s * x.get();

        function render() {
            const e = exposed();
            surface.style.transform = e ? `translateX(${x.get()}px)` : '';
            rail.style.transform = `translateX(${-s * Math.max(0, D - e)}px)`;
            const shift = spread.get() * Math.max(0, e - A);
            block.style.transform = `translateX(${s * shift}px)`;
            commitBtn.style.transform = `translateX(${-s * landed.get() * (shift - (w - A) / 2)}px)`;
        }

        // Lay the drawer out again: actions can hide themselves (hidden()).
        function layout() {
            let slot = 1;
            buttons.forEach((b, a) => {
                b.hidden = Boolean(a.hidden?.());
                if (b.hidden) return;
                b.style[s < 0 ? 'right' : 'left'] = `${slot * A}px`;
                slot += 1;
            });
            n = slot;
            D = n * A;
            toggle.textContent = `${n} ${n === 1 ? 'action' : 'actions'}`;
            render();
        }
        layout();

        const map = raw => {
            if (raw < 0) return rubber(raw, w, c);
            if (raw <= D) return raw;
            if (!canCommit()) return D + rubber(raw - D, w, c);
            const C = commitPoint();
            const knee = D + (C - D) / c;
            return raw <= knee ? D + c * (raw - D) : C + rubber(raw - knee, w, c);
        };
        const inv = ex => {
            if (ex < 0) return unrubber(ex, w, c);
            if (ex <= D) return ex;
            if (!canCommit()) return D + unrubber(ex - D, w, c);
            const C = commitPoint();
            const knee = D + (C - D) / c;
            return ex <= C ? D + (ex - D) / c : knee + unrubber(ex - C, w, c);
        };

        const say = text => { sr.textContent = text; };
        function setPhase(next) {
            phase = next;
            root.dataset.phase = next;
            // The drawer is live while open, and while a leapt block waits on its fuse.
            const live = open || next === 'committing';
            rail.inert = !live;
            rail.setAttribute('aria-hidden', String(!live));
        }
        function setOpen(next) {
            if (next === open) return;
            open = next;
            root.toggleAttribute('data-open', open);
            toggle.setAttribute('aria-expanded', String(open));
            setPhase(phase);
            opts.onOpenChange?.(open);
        }

        function settle(target, v = 0) {
            heading = target;
            if (reduced()) return x.to(s * target, { duration: 0.2, ease: true });
            const flick = Math.abs(v) >= FLICK;
            return x.to(s * target, flick
                ? { duration: 0.4, bounce: snapBounce, velocity: s * clamp(v, -VMAX, VMAX) }
                : { ...UI, velocity: s * v });
        }
        function setSpread(on) {
            if ((spread.get() === 1) === on) return;
            if (reduced()) spread.set(on ? 1 : 0);
            else spread.to(on ? 1 : 0, UI);
            if (on) {
                say(`Release to ${primary.label}`);
                if (opts.haptic !== false && grip?.touch) navigator.vibrate?.(8);
            }
        }

        function fold(a) {
            setPhase('collapsing');
            const done = () => {
                opts.onCommit?.(a, row);
                a.onSelect?.(row);
            };
            const target = opts.fold || root;
            if (window.Fuse?.leaving || reduced()) { done(); return; }
            target.style.overflow = 'hidden';
            foldAnim = target.animate([
                { height: `${target.offsetHeight}px`, opacity: 1 },
                {
                    height: '0px', opacity: 0, paddingTop: '0px', paddingBottom: '0px',
                    marginTop: '0px', marginBottom: '0px', borderTopWidth: '0px', borderBottomWidth: '0px',
                },
            ], { duration: collapseMs, easing: 'cubic-bezier(0.23, 1, 0.32, 1)', fill: 'forwards' });
            foldAnim.onfinish = done;
        }

        // Fold now, or, for an action with `fuse`, once its fuse burns out.
        function afterLeap(a) {
            if (!a.fuse || !window.Fuse) { fold(a); return; }
            const button = a === primary ? commitBtn : buttons.get(a);
            Fuse.arm(button, { label: a.fuse, run: () => fold(a), onUndo: reset });
            button.focus({ preventScroll: true });
        }

        function commit(a, viaKey, v = 0) {
            const leap = a === primary;
            setPhase('committing');
            say(a.label);
            setOpen(false);
            if (viaKey || reduced()) {
                if (leap) { spread.set(1); landed.set(1); }
                if (viaKey) { x.set(s * w); afterLeap(a); }
                else x.to(s * w, { duration: 0.2, ease: true }).then(() => afterLeap(a));
                return;
            }
            if (leap) {
                if (spread.get() < 1) spread.to(1, UI);
                landed.to(1, UI);
            }
            x.to(s * w, { ...UI, velocity: s * v }).then(() => afterLeap(a));
        }

        // Back to a closed, idle row: after Undo, or when the commit failed.
        function reset() {
            if (foldAnim) {
                foldAnim.cancel();
                foldAnim = null;
                (opts.fold || root).style.overflow = '';
            }
            setOpen(false);
            setPhase('idle');
            spread.set(0);
            landed.set(0);
            settle(0);
        }

        function down(e) {
            if (phase !== 'idle' || grip || e.button !== 0 || root.closest('[inert]')) return;
            x.stop();
            heading = null;
            grip = {
                id: e.pointerId, x0: e.clientX, y0: e.clientY,
                grab: null, moved: false, hist: [], touch: e.pointerType === 'touch',
            };
            window.addEventListener('pointermove', move);
            window.addEventListener('pointerup', up);
            window.addEventListener('pointercancel', up);
        }
        function move(e) {
            const g = grip;
            if (!g || g.id !== e.pointerId) return;
            if (g.grab === null) {
                const dx = e.clientX - g.x0;
                const dy = e.clientY - g.y0;
                if (Math.abs(dx) < HYST || Math.abs(dx) < Math.abs(dy)) return;
                if (!open) layout();
                g.grab = s * (g.x0 + Math.sign(dx) * HYST) - inv(exposed());
                g.moved = true;
                root.setAttribute('data-dragging', '');
                // Captured only once it is a drag, so taps still reach the row's own buttons.
                try { surface.setPointerCapture(e.pointerId); } catch (err) { /* already released */ }
                window.getSelection()?.removeAllRanges();
            }
            const ex = map(s * e.clientX - g.grab);
            x.set(s * ex);
            g.hist.push([performance.now(), ex]);
            if (g.hist.length > 4) g.hist.shift();
            setSpread(canCommit() && ex >= commitPoint());
        }
        function up(e) {
            const g = grip;
            if (!g || g.id !== e.pointerId) return;
            grip = null;
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
            window.removeEventListener('pointercancel', up);
            root.removeAttribute('data-dragging');
            try { surface.releasePointerCapture(e.pointerId); } catch (err) { /* not captured */ }
            const ex = exposed();
            const v = velocityOf(g.hist);
            if (!g.moved) {
                if (open) { setOpen(false); settle(0); }
                return;
            }
            // The click that ends a drag is not a press on whatever lies under it.
            swallowClick = true;
            setTimeout(() => { swallowClick = false; }, 0);
            if (canCommit() && ex >= commitPoint()) { commit(primary, false, v); return; }
            const target = Math.abs(v) >= FLICK ? (v > 0 ? D : 0) : ex + project(v) > D / 2 ? D : 0;
            setSpread(false);
            setOpen(target === D);
            settle(target, v);
        }
        surface.addEventListener('pointerdown', down);
        surface.addEventListener('click', e => {
            if (!swallowClick) return;
            e.preventDefault();
            e.stopPropagation();
        }, true);

        function act(a, e) {
            if (phase !== 'idle') return;
            opts.onAction?.(a, row);
            if (a === primary || a.dismiss) { commit(a, e.detail === 0); return; }
            a.onSelect?.(row);
            if (opts.closeOnAction === false) return;
            setOpen(false);
            if (e.detail === 0) { heading = 0; x.set(0); toggle.focus(); }
            else settle(0);
        }

        function openNow() {
            layout();
            heading = D;
            x.set(s * D);
            setOpen(true);
            say(`${n} actions revealed`);
        }
        function closeNow() {
            heading = 0;
            x.set(0);
            setOpen(false);
        }
        toggle.addEventListener('keydown', e => {
            if (phase !== 'idle') return;
            const openKey = s < 0 ? 'ArrowLeft' : 'ArrowRight';
            const closeKey = s < 0 ? 'ArrowRight' : 'ArrowLeft';
            const press = e.key === 'Enter' || e.key === ' ';
            if (e.key === openKey || (press && !open)) {
                e.preventDefault();
                openNow();
            } else if (e.key === closeKey || e.key === 'Escape' || (press && open)) {
                e.preventDefault();
                closeNow();
            } else if ((e.key === 'Delete' || e.key === 'Backspace') && open && canCommit()) {
                e.preventDefault();
                commit(primary, true);
            }
        });
        toggle.addEventListener('click', e => {
            if (e.detail !== 0 || phase !== 'idle') return;
            if (open) closeNow();
            else openNow();
        });

        const row = {
            root,
            reset,
            close: () => { if (phase === 'idle' && open) { setOpen(false); settle(0); } },
            get open() { return open; },
        };
        return row;
    }

    window.SwipeRow = { attach };
})();
