// The voyage (homepage club numbers): the mascot's ship crosses a sea chart as the page
// scrolls, and each number is hoisted and counted up as the ship sails under it.
//
// This script only measures how far the pinned section has been scrolled and writes it
// to two custom properties on the section: --p (0 to 1, how far the ship has sailed) and
// --lean (degrees, from the scroll speed). pages/index.css draws everything from those.
//
// With motion reduced (device setting or My Account), or without position: sticky, it
// does nothing and the section stays a plain row of numbers above a still sea.
(function () {
    'use strict';

    var root = document.querySelector('[data-voyage]');
    if (!root) return;

    var reduced = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
        || document.documentElement.getAttribute('data-motion') === 'reduce';
    var sticky = window.CSS && CSS.supports && CSS.supports('position', 'sticky');
    if (reduced || !sticky) return;

    var stage = root.querySelector('.voyage-stage');
    var sea = root.querySelector('.voyage-sea');
    var ship = root.querySelector('.voyage-ship');
    var stops = Array.prototype.slice.call(root.querySelectorAll('[data-voyage-stop]'));
    if (!stage || !sea || !ship) return;

    var COUNT_MS = 900;
    var LANDED_AT = 0.97;

    function clamp(value, low, high) {
        return Math.min(high, Math.max(low, value));
    }

    // --- The numbers -----------------------------------------------------------------
    // Each starts at 0 and counts up when reached. Screen readers get the real value from
    // a hidden copy, so they never hear a number mid-count.
    var counters = stops.map(function (stop) {
        var el = stop.querySelector('.stat-number');
        if (!el) return null;
        var text = el.textContent.trim();
        var digits = text.replace(/[^0-9]/g, '');
        if (!digits) return null;
        var spoken = document.createElement('span');
        spoken.className = 'visually-hidden';
        spoken.textContent = text;
        el.parentNode.insertBefore(spoken, el);
        el.setAttribute('aria-hidden', 'true');
        return { el: el, text: text, target: parseInt(digits, 10), suffix: text.replace(/^[0-9,\s]+/, '') };
    });

    function countUp(counter) {
        if (!counter) return;
        var started = performance.now();
        (function step(now) {
            var t = clamp((now - started) / COUNT_MS, 0, 1);
            var eased = 1 - Math.pow(1 - t, 4);
            counter.el.textContent = t < 1 ? Math.floor(counter.target * eased) + counter.suffix : counter.text;
            if (t < 1) requestAnimationFrame(step);
        })(started);
    }

    function reach(index) {
        var stop = stops[index];
        if (stop.classList.contains('is-reached')) return;
        stop.classList.add('is-reached');
        countUp(counters[index]);
    }

    // --- Where things are --------------------------------------------------------------
    var span = 0;          // how many pixels of scroll the crossing lasts; 0 = not pinned
    var marks = [];        // the --p at which the ship is under each number

    function measure() {
        span = root.offsetHeight - stage.offsetHeight;

        // The ship's centre runs from 3% + half its width, over 82% of the sea less its
        // width (the same sums as .voyage-ship in index.css).
        var seaBox = sea.getBoundingClientRect();
        var shipWidth = ship.offsetWidth;
        var start = seaBox.left + seaBox.width * 0.03 + shipWidth / 2;
        var travel = seaBox.width * 0.82 - shipWidth;
        marks = stops.map(function (stop) {
            var box = stop.getBoundingClientRect();
            return travel > 0 ? clamp((box.left + box.width / 2 - start) / travel, 0.06, 0.94) : 0;
        });
        // Stacked numbers (the 2 x 2 block on phones) share a column, so they take turns.
        var inOrder = marks.every(function (mark, i) { return i === 0 || mark > marks[i - 1] + 0.05; });
        if (!inOrder) {
            marks = stops.map(function (_, i) { return (i + 0.5) / stops.length; });
        }
    }

    function progress() {
        if (span <= 8) return 1;                       // not pinned: the voyage is over
        return clamp(-root.getBoundingClientRect().top / span, 0, 1);
    }

    // --- The frame loop ----------------------------------------------------------------
    // Runs only while something is still moving: the scroll, or the ship easing after it.
    var shown = 0;
    var lean = 0;
    var frame = 0;

    function draw() {
        frame = 0;
        var target = progress();
        var step = (target - shown) * 0.22;
        if (Math.abs(target - shown) < 0.0006) {
            step = target - shown;
        }
        shown += step;
        // Nose down when sailing ahead, up when blown back.
        lean += (clamp(step * 420, -6, 6) - lean) * 0.16;
        if (Math.abs(lean) < 0.03) lean = 0;

        root.style.setProperty('--p', shown.toFixed(4));
        root.style.setProperty('--lean', lean.toFixed(2));
        for (var i = 0; i < stops.length; i++) {
            if (shown >= marks[i]) reach(i);
        }
        root.classList.toggle('is-landed', shown >= LANDED_AT);

        if (shown !== target || lean !== 0) {
            frame = requestAnimationFrame(draw);
        }
    }

    function wake() {
        if (!frame) frame = requestAnimationFrame(draw);
    }

    root.classList.add('is-live');
    measure();
    if (span > 8) {
        counters.forEach(function (counter) {
            if (counter) counter.el.textContent = '0' + counter.suffix;
        });
        shown = progress();
    } else {
        shown = 1;
    }
    draw();

    window.addEventListener('scroll', wake, { passive: true });
    window.addEventListener('resize', function () {
        measure();
        wake();
    });
    window.addEventListener('load', function () {
        measure();
        wake();
    });
})();
