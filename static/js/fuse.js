// Fuse buttons: a destructive click lights a fuse instead of opening a "Are you
// sure?" box. The button turns into Undo while a ring burns down its rim; the
// action only runs once the fuse burns out. Undo (or Escape) puts everything
// back as it was, and nothing was ever sent.
//
// A vanilla port of React Bits' <FuseButton> (commitOn "fuseEnd", settle
// "reset", outline fuse, pause on hover).
//
//   Fuse.arm(button, {
//       label: 'Deleting Kickoff',        // short; becomes "Undo: <label>"
//       detail: 'It leaves the homepage', // optional, only announced when lit
//       run: () => ...,                   // the action, once the fuse ends
//       form,                             // or: a form to post when it ends
//       window: 5000,                     // ms the fuse burns
//   });
//
// The button keeps its size and place; its content is swapped for an Undo face
// while lit, so page code that delegates clicks never sees the Undo press.
//
// Leaving the page while a fuse burns runs the action straight away: forms go
// by sendBeacon, and run() is called with Fuse.leaving set so fetch helpers can
// pass keepalive and the request outlives the page.

(function () {
    'use strict';

    const SVG = 'http://www.w3.org/2000/svg';
    const WINDOW = 5000;
    const FADE = 200;
    const armed = new Map();
    let status;

    const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function announce(text) {
        if (!status) {
            status = Object.assign(document.createElement('span'), { className: 'fuse-status' });
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
            document.body.append(status);
        }
        status.textContent = '';
        // A fresh node each time, or the same text twice in a row is not read.
        requestAnimationFrame(() => { status.textContent = text; });
    }

    // Lucide "undo-2", drawn here so a lit fuse never waits on the icon script.
    function undoIcon() {
        const svg = document.createElementNS(SVG, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('class', 'fuse-undo-icon');
        svg.setAttribute('aria-hidden', 'true');
        ['M9 14 4 9l5-5', 'M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11'].forEach(d => {
            const path = document.createElementNS(SVG, 'path');
            path.setAttribute('d', d);
            svg.append(path);
        });
        return svg;
    }

    function rim() {
        const svg = document.createElementNS(SVG, 'svg');
        svg.setAttribute('class', 'fuse-rim');
        svg.setAttribute('aria-hidden', 'true');
        const rect = document.createElementNS(SVG, 'rect');
        rect.setAttribute('pathLength', '1');
        svg.append(rect);
        return { svg, rect };
    }

    // Icon-only buttons get an icon-only Undo; buttons with words say "Undo".
    const hasText = button => Array.from(button.childNodes)
        .some(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());

    function arm(button, opts) {
        if (armed.has(button)) return;
        const keyboard = button.matches(':focus-visible');
        const css = getComputedStyle(button);
        const state = {
            opts,
            label: button.getAttribute('aria-label'),
            title: button.getAttribute('title'),
            position: button.style.position,
            hoverPause: false,
            leftOnce: false,
        };

        // Idle face: the button's own content, hidden in place so the size holds.
        const idle = Object.assign(document.createElement('span'), { className: 'fuse-face fuse-face--idle' });
        idle.append(...button.childNodes);
        const undo = Object.assign(document.createElement('span'), { className: 'fuse-face fuse-face--undo' });
        undo.append(undoIcon());
        if (hasText(idle)) undo.append(document.createTextNode('Undo'));
        const { svg, rect } = rim();
        button.append(idle, undo, svg);

        if (css.position === 'static') button.style.position = 'relative';
        button.style.setProperty('--fuse-radius', css.borderTopLeftRadius);
        button.style.setProperty('--fuse-inset', `-${css.borderTopWidth}`);
        button.classList.add('is-fuse-armed');
        if (keyboard || reduced()) button.classList.add('is-fuse-instant');
        button.setAttribute('aria-label', `Undo: ${opts.label || state.label || button.textContent.trim()}`);
        button.setAttribute('aria-keyshortcuts', 'Escape');
        button.title = 'Undo';

        state.anim = rect.animate([{ strokeDashoffset: 0 }, { strokeDashoffset: -1 }], {
            duration: opts.window || WINDOW, easing: 'linear', fill: 'forwards',
        });
        state.anim.onfinish = () => finish(button);
        state.nodes = { idle, undo, svg };
        armed.set(button, state);
        sync(button);
        announce([opts.label, opts.detail, 'Press Undo or Escape to take it back.']
            .filter(Boolean).map(part => part.replace(/\.$/, '')).join('. '));
    }

    function disarm(button, { fade = false } = {}) {
        const state = armed.get(button);
        if (!state) return null;
        armed.delete(button);
        state.anim.onfinish = null;
        state.anim.cancel();
        const { idle, undo, svg } = state.nodes;
        button.prepend(...idle.childNodes);
        idle.remove();
        undo.remove();
        svg.remove();
        button.classList.remove('is-fuse-armed', 'is-fuse-instant');
        button.style.position = state.position;
        button.style.removeProperty('--fuse-radius');
        button.style.removeProperty('--fuse-inset');
        button.removeAttribute('aria-keyshortcuts');
        if (state.label === null) button.removeAttribute('aria-label');
        else button.setAttribute('aria-label', state.label);
        if (state.title === null) button.removeAttribute('title');
        else button.title = state.title;
        if (fade && !reduced()) {
            button.animate([{ opacity: 0.2, filter: 'blur(2px)' }, { opacity: 1, filter: 'blur(0)' }],
                { duration: FADE, easing: 'ease' });
        }
        return state;
    }

    function commit(state, button) {
        const { run, form } = state.opts;
        if (form && Fuse.leaving) {
            navigator.sendBeacon(form.action, new FormData(form));
            return;
        }
        if (form) {
            form.dispatchEvent(new CustomEvent('fuse:commit', { bubbles: true }));
            form.submit();
            return;
        }
        run?.(button);
    }

    function finish(button) {
        const state = disarm(button);
        if (state) commit(state, button);
    }

    function undo(button) {
        const state = disarm(button, { fade: true });
        if (!state) return;
        state.opts.onUndo?.();
        announce('Undone.');
        button.focus({ preventScroll: true });
    }

    // Paused while the tab is hidden, or while a mouse that has left once comes
    // back to hover (the first hover is the click that lit it).
    function sync(button) {
        const state = armed.get(button);
        if (!state) return;
        const hold = state.hoverPause || document.hidden;
        if (hold && state.anim.playState === 'running') state.anim.pause();
        else if (!hold && state.anim.playState === 'paused') state.anim.play();
    }

    const armedFrom = target => {
        const button = target instanceof Element && target.closest('.is-fuse-armed');
        return button && armed.has(button) ? button : null;
    };

    // Capture phase: page code delegating clicks on the same button never runs.
    document.addEventListener('click', e => {
        const button = armedFrom(e.target);
        if (!button) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        undo(button);
    }, true);

    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        const button = armedFrom(e.target);
        if (!button) return;
        e.preventDefault();
        e.stopPropagation();
        undo(button);
    }, true);

    document.addEventListener('pointerover', e => {
        if (e.pointerType !== 'mouse') return;
        const button = armedFrom(e.target);
        const state = button && armed.get(button);
        if (!state || !state.leftOnce || state.hoverPause) return;
        state.hoverPause = true;
        sync(button);
    });

    document.addEventListener('pointerout', e => {
        if (e.pointerType !== 'mouse') return;
        const button = armedFrom(e.target);
        if (!button || button.contains(e.relatedTarget)) return;
        const state = armed.get(button);
        state.leftOnce = true;
        state.hoverPause = false;
        sync(button);
    });

    document.addEventListener('visibilitychange', () => armed.forEach((_, button) => sync(button)));

    window.addEventListener('pagehide', () => {
        if (!armed.size) return;
        Fuse.leaving = true;
        Array.from(armed.keys()).forEach(finish);
        Fuse.leaving = false;
    });

    const Fuse = {
        arm,
        undo,
        leaving: false,
        isArmed: button => armed.has(button),
    };
    window.Fuse = Fuse;
})();
