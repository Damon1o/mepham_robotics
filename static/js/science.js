/* /science/: Interactions between Subatomic Particles, a Coulomb's law lab.
   Two clusters of protons, neutrons and electrons sit on a 0-100 pm track.
   The page shows the force between them, works the math out step by step,
   graphs force against distance, and ticks off the guided steps as the
   visitor discovers each idea. Also rotates the donate ads in the side rails. */
(function () {
    'use strict';

    var K = 8.9875517923e9;   // Coulomb constant, N·m²/C²
    var E = 1.602176634e-19;  // elementary charge, C
    var MIN_PM = 4, MAX_PM = 96, MIN_GAP = 10, MAX_COUNT = 8;
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var root = document.querySelector('[data-sci]');
    if (root) lab(root);
    document.querySelectorAll('[data-sci-ad]').forEach(rotateAd);

    function lab(root) {
        var $ = function (sel) { return root.querySelector(sel); };
        var track = $('[data-track]');
        var START = {
            1: { protons: 1, neutrons: 0, electrons: 0, pos: 22 },
            2: { protons: 1, neutrons: 0, electrons: 0, pos: 78 }
        };
        var PRESETS = {
            pp: [{ protons: 1 }, { protons: 1 }],
            pe: [{ protons: 1 }, { electrons: 1 }],
            he: [{ protons: 2, neutrons: 2 }, { electrons: 1 }],
            atom: [{ protons: 1, electrons: 1 }, { protons: 1 }],
            ions: [{ protons: 6, neutrons: 6 }, { electrons: 6 }]
        };
        var state = clone(START);
        var pinned = null;
        var found = {};

        buildRuler($('[data-ruler]'));

        // --- Physics -------------------------------------------------------
        function charge(g) { return g.protons - g.electrons; }
        function distance() { return state[2].pos - state[1].pos; }
        function force(q1, q2, rPm) {
            var r = rPm * 1e-12;
            return K * Math.abs(q1 * E * q2 * E) / (r * r);
        }

        // --- Formatting ----------------------------------------------------
        function sci(n, digits) {
            if (n === 0) return '0';
            if (!isFinite(n)) return '—';
            var exp = Math.floor(Math.log10(Math.abs(n)));
            var mant = n / Math.pow(10, exp);
            var m = mant.toFixed(digits === undefined ? 2 : digits);
            if (Math.abs(parseFloat(m)) >= 10) { exp += 1; m = (mant / 10).toFixed(digits === undefined ? 2 : digits); }
            return m.replace('-', '−') + ' × 10<sup>' + String(exp).replace('-', '−') + '</sup>';
        }
        function signed(q) { return q > 0 ? '+' + q : (q < 0 ? '−' + Math.abs(q) : '0'); }

        // --- Drawing the clusters ------------------------------------------
        function drawCluster(idx) {
            var g = state[idx];
            var nucleus = $('[data-nucleus="' + idx + '"]');
            var atom = $('[data-atom="' + idx + '"]');
            var parts = [];
            var i;
            for (i = 0; i < g.protons; i++) parts.push('p');
            for (i = 0; i < g.neutrons; i++) parts.push('n');
            // Alternate protons and neutrons so the nucleus looks mixed.
            parts.sort(function (a, b) { return (a.charCodeAt(0) * 7 + 3) % 5 - (b.charCodeAt(0) * 3 + 1) % 5; });
            nucleus.innerHTML = parts.map(function (kind, k) {
                var r = 4.2 * Math.sqrt(k + (parts.length > 1 ? 1 : 0));
                var t = k * 137.508 * Math.PI / 180;
                return '<span class="sci-nucleon sci-' + kind + '" data-x="' + (r * Math.cos(t)).toFixed(1) +
                    '" data-y="' + (r * Math.sin(t)).toFixed(1) + '"></span>';
            }).join('');
            nucleus.querySelectorAll('.sci-nucleon').forEach(function (el) {
                el.style.transform = 'translate(' + el.dataset.x + 'px, ' + el.dataset.y + 'px)';
            });

            atom.querySelectorAll('.sci-orbit').forEach(function (o) { o.remove(); });
            for (i = 0; i < g.electrons; i++) {
                var orbit = document.createElement('span');
                var radius = 34 + (i % 3) * 8;
                orbit.className = 'sci-orbit';
                orbit.style.width = orbit.style.height = radius * 2 + 'px';
                orbit.style.margin = -radius + 'px 0 0 ' + -radius + 'px';
                orbit.style.animationDuration = (7 + (i % 4)) + 's';
                orbit.style.animationDelay = -(i * 0.9) + 's';
                orbit.style.animationDirection = i % 2 ? 'reverse' : 'normal';
                orbit.innerHTML = '<span class="sci-electron"></span>';
                atom.appendChild(orbit);
            }

            var q = charge(g);
            var badge = $('[data-badge="' + idx + '"]');
            badge.textContent = signed(q) + 'e';
            badge.className = 'sci-badge ' + (q > 0 ? 'is-pos' : q < 0 ? 'is-neg' : 'is-zero');
            ['protons', 'neutrons', 'electrons'].forEach(function (key) {
                $('[data-count="' + idx + ':' + key + '"]').textContent = g[key];
                $('[data-step="' + idx + ':' + key + ':-1"]').disabled = g[key] === 0;
                $('[data-step="' + idx + ':' + key + ':1"]').disabled = g[key] === MAX_COUNT;
            });
        }

        function place(idx) {
            var el = $('[data-cluster="' + idx + '"]');
            el.style.left = state[idx].pos + '%';
            el.setAttribute('aria-valuenow', Math.round(state[idx].pos));
            el.setAttribute('aria-valuetext', 'Cluster ' + (idx === 1 ? 'A' : 'B') + ' at ' +
                state[idx].pos.toFixed(1) + ' picometers');
        }

        // --- Force arrows, readouts, math, graph ---------------------------
        function update() {
            place(1); place(2);
            var q1 = charge(state[1]), q2 = charge(state[2]);
            var r = distance();
            var F = force(q1, q2, r);
            var zero = q1 === 0 || q2 === 0;
            var repel = q1 * q2 > 0;

            var link = $('[data-link]');
            link.style.left = state[1].pos + '%';
            link.style.width = r + '%';
            link.className = 'sci-link' + (zero ? '' : repel ? ' is-repel' : ' is-attract');

            $('[data-out="r"]').textContent = r.toFixed(1) + ' pm';
            $('[data-out="f"]').innerHTML = zero ? '0 N' : sci(F) + ' N';
            var rel = $('[data-out="rel"]');
            rel.textContent = zero ? 'No net charge on one cluster: no electrostatic force'
                : repel ? 'Repulsive: like charges push apart' : 'Attractive: opposite charges pull together';
            rel.className = 'sci-relation ' + (zero ? 'is-zero' : repel ? 'is-repel' : 'is-attract');

            drawArrows(F, zero, repel);
            drawRatio(F, zero);
            drawWork(q1, q2, r, F, zero, repel);
            drawGraph(q1, q2, r, zero);
            checkSteps(q1, q2, r);
        }

        function drawArrows(F, zero, repel) {
            // Arrow length follows the force on a log scale, so a 4× jump is visible
            // without the biggest forces running off the track.
            var len = zero ? 0 : 18 + 72 * Math.min(1, Math.max(0, (Math.log10(F) + 8.2) / 4.6));
            [1, 2].forEach(function (idx) {
                var arrow = $('[data-arrow="' + idx + '"]');
                var label = $('[data-flabel="' + idx + '"]');
                var pointsRight = (idx === 1) !== repel;  // A points right to attract, B points left
                arrow.style.width = len + 'px';
                arrow.style.left = 'calc(' + state[idx].pos + '% ' + (pointsRight ? '+ 8px' : '- ' + (len + 8) + 'px') + ')';
                arrow.className = 'sci-arrow sci-arrow-' + (idx === 1 ? 'a' : 'b') + (pointsRight ? ' is-right' : ' is-left') +
                    (zero ? ' is-off' : '');
                label.style.left = state[idx].pos + '%';
                label.innerHTML = zero ? '0 N' : sci(F, 1) + ' N';
                label.classList.toggle('is-off', zero);
            });
        }

        function drawRatio(F, zero) {
            var out = $('[data-out="ratio"]');
            if (!pinned) { out.textContent = 'Nothing pinned'; return; }
            if (zero || pinned.F === 0) { out.textContent = zero ? '0× (no force now)' : 'Pinned force was 0'; return; }
            var ratio = F / pinned.F;
            out.innerHTML = '×' + (ratio >= 100 ? ratio.toFixed(0) : ratio >= 10 ? ratio.toFixed(1) : ratio.toFixed(2)) +
                ' <small>' + (Math.abs(ratio - 1) < 0.005 ? 'same' : ratio > 1 ? 'stronger' : 'weaker') + '</small>';
        }

        function drawWork(q1, q2, r, F, zero, repel) {
            var a = state[1], b = state[2];
            var rows = [
                ['Net charge of A', 'q<sub>1</sub> = protons − electrons = ' + a.protons + ' − ' + a.electrons + ' = <b>' +
                    signed(q1) + 'e</b>' + (q1 ? ' = ' + sci(q1 * E) + ' C' : '')],
                ['Net charge of B', 'q<sub>2</sub> = ' + b.protons + ' − ' + b.electrons + ' = <b>' + signed(q2) + 'e</b>' +
                    (q2 ? ' = ' + sci(q2 * E) + ' C' : '')],
                ['Distance in meters', 'r = ' + r.toFixed(1) + ' pm = ' + sci(r * 1e-12) + ' m'],
                zero
                    ? ['Plug in', 'One charge is 0, so q<sub>1</sub> · q<sub>2</sub> = 0 and <b>F = 0 N</b>']
                    : ['Plug in', 'F = (8.99 × 10<sup>9</sup>) · |' + sci(q1 * E) + ' · ' + sci(q2 * E) + '| / (' +
                        sci(r * 1e-12) + ')<sup>2</sup> = <b>' + sci(F) + ' N</b>'],
                ['Direction', zero ? 'No force, so no direction.'
                    : 'Signs are ' + (repel ? 'the same, so the clusters <b>repel</b>.' : 'opposite, so the clusters <b>attract</b>.')]
            ];
            $('[data-work]').innerHTML = rows.map(function (row) {
                return '<li><span>' + row[0] + '</span><span>' + row[1] + '</span></li>';
            }).join('');
        }

        function drawGraph(q1, q2, r, zero) {
            var X = function (pm) { return 40 + pm * 2.7; };
            var top = force(q1 || 1, q2 || 1, MIN_GAP);
            var Y = function (f) { return 150 - 140 * Math.min(1, f / top); };
            var d = '';
            for (var pm = MIN_GAP - 2; pm <= 100; pm += 1) {
                var f = zero ? 0 : force(q1, q2, pm);
                d += (d ? ' L' : 'M') + X(pm).toFixed(1) + ' ' + Y(f).toFixed(1);
            }
            $('[data-curve]').setAttribute('d', d);
            var px = X(r), py = Y(zero ? 0 : force(q1, q2, r));
            var point = $('[data-point]');
            point.setAttribute('cx', px.toFixed(1));
            point.setAttribute('cy', py.toFixed(1));
            var guide = $('[data-guide]');
            guide.setAttribute('x1', px.toFixed(1));
            guide.setAttribute('x2', px.toFixed(1));
            guide.setAttribute('y1', py.toFixed(1));
            $('[data-graph-note]').textContent = zero
                ? 'With a neutral cluster the curve is flat: zero force at every distance.'
                : 'Steep up close, nearly flat far away: that is the inverse-square law.';
        }

        // --- Guided steps ---------------------------------------------------
        var neutronTried = false;
        function checkSteps(q1, q2, r) {
            var now = force(q1, q2, r);
            var hits = {
                repel: q1 > 0 && q2 > 0,
                attract: q1 * q2 < 0,
                distance: !!pinned && pinned.q1 === q1 && pinned.q2 === q2 && q1 * q2 !== 0 &&
                    Math.abs(pinned.r / r - 2) < 0.1,
                charge: !!pinned && pinned.F > 0 && Math.abs(pinned.r - r) < 0.6 &&
                    Math.abs(Math.abs(q1 * q2) / Math.abs(pinned.q1 * pinned.q2) - 2) < 0.001,
                neutron: neutronTried && now > 0,
                neutral: [1, 2].some(function (i) {
                    var g = state[i], other = state[3 - i];
                    return g.protons > 0 && charge(g) === 0 && charge(other) !== 0;
                })
            };
            Object.keys(hits).forEach(function (task) {
                if (hits[task] && !found[task]) {
                    found[task] = true;
                    var li = root.querySelector('[data-task="' + task + '"]');
                    li.classList.add('is-found');
                    if (!reduceMotion) { li.classList.add('is-pop'); setTimeout(function () { li.classList.remove('is-pop'); }, 700); }
                }
            });
            $('[data-progress]').textContent = Object.keys(found).length;
        }

        // --- Input -----------------------------------------------------------
        root.addEventListener('click', function (ev) {
            var step = ev.target.closest('[data-step]');
            if (step) {
                var parts = step.dataset.step.split(':');
                var g = state[parts[0]];
                var next = Math.max(0, Math.min(MAX_COUNT, g[parts[1]] + Number(parts[2])));
                if (next === g[parts[1]]) return;
                g[parts[1]] = next;
                if (parts[1] === 'neutrons' && charge(g) !== 0 && charge(state[3 - parts[0]]) !== 0) neutronTried = true;
                drawCluster(Number(parts[0]));
                update();
                return;
            }
            var preset = ev.target.closest('[data-preset]');
            if (preset) {
                var key = preset.dataset.preset;
                var keep = [state[1].pos, state[2].pos];
                state = clone(START);
                if (key !== 'reset') {
                    [1, 2].forEach(function (i) {
                        state[i] = Object.assign({ protons: 0, neutrons: 0, electrons: 0 }, PRESETS[key][i - 1]);
                        state[i].pos = keep[i - 1];
                    });
                } else {
                    pinned = null;
                    $('[data-pin]').textContent = 'Pin this force';
                }
                drawCluster(1); drawCluster(2);
                update();
                return;
            }
            if (ev.target.closest('[data-pin]')) {
                var q1 = charge(state[1]), q2 = charge(state[2]);
                pinned = { q1: q1, q2: q2, r: distance(), F: force(q1, q2, distance()) };
                ev.target.closest('[data-pin]').textContent = 'Re-pin';
                update();
            }
        });

        function moveTo(idx, pm) {
            var other = state[3 - idx].pos;
            pm = idx === 1 ? Math.min(pm, other - MIN_GAP) : Math.max(pm, other + MIN_GAP);
            state[idx].pos = Math.max(MIN_PM, Math.min(MAX_PM, pm));
            update();
        }

        root.querySelectorAll('[data-cluster]').forEach(function (el) {
            var idx = Number(el.dataset.cluster);
            el.addEventListener('pointerdown', function (ev) {
                el.setPointerCapture(ev.pointerId);
                el.classList.add('is-dragging');
                ev.preventDefault();
            });
            el.addEventListener('pointermove', function (ev) {
                if (!el.hasPointerCapture(ev.pointerId)) return;
                var rect = track.getBoundingClientRect();
                moveTo(idx, (ev.clientX - rect.left) / rect.width * 100);
            });
            ['pointerup', 'pointercancel'].forEach(function (type) {
                el.addEventListener(type, function () { el.classList.remove('is-dragging'); });
            });
            el.addEventListener('keydown', function (ev) {
                var step = ev.shiftKey ? 5 : 1;
                var to = { ArrowLeft: -step, ArrowDown: -step, ArrowRight: step, ArrowUp: step }[ev.key];
                if (ev.key === 'Home') to = -100;
                if (ev.key === 'End') to = 100;
                if (to === undefined) return;
                ev.preventDefault();
                moveTo(idx, state[idx].pos + to);
            });
        });

        window.addEventListener('resize', update);
        drawCluster(1); drawCluster(2);
        update();
    }

    function buildRuler(ruler) {
        if (!ruler) return;
        for (var t = 0; t <= 100; t += 5) {
            var tick = document.createElement('span');
            tick.className = 'sci-tick' + (t % 10 === 0 ? ' is-major' : '');
            tick.style.left = t + '%';
            if (t % 10 === 0) tick.innerHTML = '<span>' + t + '</span>';
            ruler.appendChild(tick);
        }
    }

    function clone(obj) { return JSON.parse(JSON.stringify(obj)); }

    // --- Side-rail ads: rotate through the slides, pause while read ---------
    function rotateAd(ad) {
        var slides = ad.querySelectorAll('.sci-ad-slide');
        var dots = ad.querySelectorAll('.sci-ad-dots span');
        if (slides.length < 2 || reduceMotion) return;
        var at = 0, paused = false;
        ['mouseenter', 'focusin'].forEach(function (t) { ad.addEventListener(t, function () { paused = true; }); });
        ['mouseleave', 'focusout'].forEach(function (t) { ad.addEventListener(t, function () { paused = false; }); });
        setInterval(function () {
            if (paused || document.hidden) return;
            slides[at].classList.remove('is-on');
            slides[at].hidden = true;
            dots[at].classList.remove('is-on');
            at = (at + 1) % slides.length;
            slides[at].hidden = false;
            dots[at].classList.add('is-on');
            requestAnimationFrame(function () { slides[at].classList.add('is-on'); });
        }, 7000);
    }
})();
