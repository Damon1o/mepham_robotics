/* Team page: live RobotEvents panels, event gallery lightbox, STL viewer.
 *
 * Nothing here runs unless its section is actually on the page, so a team with
 * no live data and no CAD model costs one no-op pass and zero network requests.
 */
(function () {
    'use strict';

    // --- helpers -----------------------------------------------------------

    function field(root, name) {
        return root ? root.querySelector('[data-field="' + name + '"]') : null;
    }

    function setText(root, name, value) {
        const el = field(root, name);
        if (el) el.textContent = value;
    }

    function drop(section) {
        if (section && section.parentNode) section.parentNode.removeChild(section);
    }

    function relativeTime(iso) {
        if (!iso) return '';
        const then = new Date(iso);
        if (isNaN(then)) return '';
        const minutes = Math.round((Date.now() - then.getTime()) / 60000);
        if (minutes < 1) return 'just now';
        if (minutes < 60) return minutes + ' min ago';
        const hours = Math.round(minutes / 60);
        if (hours < 24) return hours === 1 ? 'an hour ago' : hours + ' hours ago';
        const days = Math.round(hours / 24);
        return days === 1 ? 'yesterday' : days + ' days ago';
    }

    // Trend carries its own words; colour alone would be unreadable for some viewers.
    function trendText(trend) {
        if (!trend) return '';
        if (trend.direction === 'up') return '▲ Up ' + trend.delta;
        if (trend.direction === 'down') return '▼ Down ' + trend.delta;
        if (trend.direction === 'flat') return '— Holding';
        return 'NEW First appearance';
    }

    // --- live panels -------------------------------------------------------

    function fillSkills(panel, data) {
        if (!panel) return;
        const skills = data.skills;
        if (!skills) {
            drop(panel);
            return;
        }

        setText(panel, 'combined', skills.combined);
        setText(panel, 'driver', skills.driver);
        setText(panel, 'programming', skills.programming);
        setText(panel, 'rank', skills.rank ? '#' + skills.rank : 'Unranked');

        const trend = field(panel, 'trend');
        if (trend) {
            trend.textContent = skills.rank ? trendText(data.trend) : '';
            trend.className = 'skills-trend' + (data.trend ? ' is-' + data.trend.direction : '');
        }

        const age = relativeTime(data.fetched_at);
        setText(panel, 'updated', age ? (data.stale ? 'Last reachable ' + age : 'Updated ' + age) : '');

        const profile = field(panel, 'profile');
        if (profile && data.profile_url) profile.href = data.profile_url;

        panel.removeAttribute('hidden');
        panel.setAttribute('aria-busy', 'false');
    }

    function fillScoreboard(band, data) {
        const board = data.scoreboard;
        if (!band) return;
        if (!board || !board.competitions) {
            drop(band);
            return;
        }

        setText(band, 'competitions', board.competitions);
        setText(band, 'awards', board.awards);

        const parts = [];
        if (board.local) parts.push(board.local + ' local');
        if (board.signature) parts.push(board.signature + ' signature');
        if (board.championship) parts.push(board.championship + ' championship');
        setText(band, 'breakdown', parts.join(' · '));

        const crown = field(band, 'crown-wrap');
        if (crown) {
            if (board.triple_crowns) {
                setText(band, 'triple_crowns', board.triple_crowns);
                crown.removeAttribute('hidden');
            } else {
                crown.setAttribute('hidden', '');
            }
        }

        band.removeAttribute('hidden');
    }

    function recordLine(record) {
        if (!record) return '';
        const wins = record.wins || 0, losses = record.losses || 0, ties = record.ties || 0;
        const rank = record.rank ? ' · Rank ' + record.rank : '';
        return wins + '-' + losses + '-' + ties + rank;
    }

    function buildResultRow(event, photos) {
        const row = document.createElement('article');
        row.className = 'results-row';

        const head = document.createElement('div');
        head.className = 'results-head';

        const date = document.createElement('span');
        date.className = 'results-date';
        date.textContent = (event.start || '').slice(0, 10);

        const name = document.createElement('h3');
        name.className = 'results-name';
        name.textContent = event.name || 'Competition';

        const level = document.createElement('span');
        level.className = 'results-level';
        level.textContent = event.level || 'Event';

        head.appendChild(date);
        head.appendChild(name);
        head.appendChild(level);
        row.appendChild(head);

        const record = recordLine(event.record);
        if (record) {
            const line = document.createElement('p');
            line.className = 'results-record';
            line.textContent = record;
            row.appendChild(line);
        }

        if (event.awards && event.awards.length) {
            const list = document.createElement('ul');
            list.className = 'results-awards';
            event.awards.forEach(function (title) {
                const item = document.createElement('li');
                item.className = 'results-award';
                item.textContent = title;
                list.appendChild(item);
            });
            row.appendChild(list);
        }

        if (photos && photos.length) {
            const details = document.createElement('details');
            details.className = 'results-gallery';

            const summary = document.createElement('summary');
            summary.textContent = photos.length + ' photo' + (photos.length === 1 ? '' : 's');
            details.appendChild(summary);

            const strip = document.createElement('div');
            strip.className = 'results-strip';
            photos.forEach(function (src) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'results-thumb';

                const img = document.createElement('img');
                img.src = src;
                img.alt = event.name ? event.name + ' photo' : 'Competition photo';
                img.loading = 'lazy';

                button.appendChild(img);
                button.addEventListener('click', function () { openLightbox(src, img.alt, button); });
                strip.appendChild(button);
            });

            details.appendChild(strip);
            row.appendChild(details);
        }

        return row;
    }

    function fillResults(section, data, photosByEvent) {
        if (!section) return;
        const events = data.events || [];
        if (!events.length) {
            drop(section);
            return;
        }

        const list = field(section, 'results');
        events.forEach(function (event) {
            list.appendChild(buildResultRow(event, photosByEvent[event.name]));
        });
        section.removeAttribute('hidden');
    }

    // --- bento tiles -------------------------------------------------------

    // The Bento layout's two live tiles; each one is dropped when its data is missing
    // and the tiles around it grow into the space.
    function fillBentoTile(tile, data) {
        if (tile.dataset.bentoLive === 'skills') {
            const skills = data.skills;
            if (!skills) return drop(tile);
            setText(tile, 'combined', skills.combined);
            setText(tile, 'rank', skills.rank ? 'Rank #' + skills.rank + ' · ' + trendText(data.trend) : 'Combined score');
        } else {
            const events = (data.events || []).slice().sort(function (a, b) {
                return (b.start || '').localeCompare(a.start || '');
            });
            const latest = events[0];
            if (!latest) return drop(tile);
            setText(tile, 'event', latest.name || 'Competition');
            const parts = [recordLine(latest.record)].concat(latest.awards || []).filter(Boolean);
            setText(tile, 'record', parts.join(' · ') || shortDate(latest.start));
        }
        tile.removeAttribute('hidden');
    }

    // --- season timeline ---------------------------------------------------

    function shortDate(iso) {
        const parts = (iso || '').slice(0, 10).split('-').map(Number);
        if (parts.length !== 3 || !parts[0]) return '';
        return new Date(parts[0], parts[1] - 1, parts[2])
            .toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    function timelineItem(event) {
        const item = document.createElement('li');
        item.className = 'tl-item tl-item--event';
        item.dataset.kind = 'event';
        item.dataset.name = event.name || 'Competition';
        item.dataset.when = '';

        const dot = document.createElement('span');
        dot.className = 'tl-dot';
        dot.setAttribute('aria-hidden', 'true');

        const card = document.createElement('article');
        card.className = 'tl-card';
        const meta = document.createElement('p');
        meta.className = 'tl-meta';
        const kind = document.createElement('span');
        kind.className = 'tl-kind';
        kind.textContent = 'Competition';
        meta.appendChild(kind);
        const title = document.createElement('h3');
        title.className = 'tl-title';
        title.textContent = item.dataset.name;
        const live = document.createElement('div');
        live.className = 'tl-live';
        live.dataset.field = 'live';

        card.append(meta, title, live);
        item.append(dot, card);
        return item;
    }

    // Before the first dated entry that comes later; an undated entry goes
    // before the undated events that close the list.
    function placeInTimeline(list, item) {
        const when = item.dataset.when;
        const next = Array.from(list.children).find(function (other) {
            if (other === item) return false;
            if (!when) return !other.dataset.when && other.dataset.kind === 'event';
            return other.dataset.when ? other.dataset.when > when : other.dataset.kind === 'event';
        });
        list.insertBefore(item, next || null);
    }

    function setTimelineDate(item, iso) {
        item.dataset.when = iso;
        const meta = item.querySelector('.tl-meta');
        let date = meta.querySelector('.tl-date');
        if (!date) {
            date = document.createElement('span');
            date.className = 'tl-date';
            meta.insertBefore(date, meta.firstChild);
        }
        date.textContent = shortDate(iso);
    }

    // RobotEvents results join the stored timeline: a competition the team already
    // has a gallery for gains its record and awards; any other one is slotted in by date.
    function fillTimeline(list, data) {
        if (!list) return;
        (data.events || []).forEach(function (event) {
            const name = (event.name || '').trim().toLowerCase();
            const when = (event.start || '').slice(0, 10);
            let item = Array.from(list.children).find(function (other) {
                return other.dataset.kind === 'event' && other.dataset.name.trim().toLowerCase() === name;
            });
            if (!item) {
                item = timelineItem(event);
                if (when) setTimelineDate(item, when);
                placeInTimeline(list, item);
            } else if (!item.dataset.when && when) {
                setTimelineDate(item, when);
                placeInTimeline(list, item);
            }

            const live = field(item, 'live');
            if (!live) return;
            live.textContent = '';
            if (event.level) {
                const level = document.createElement('span');
                level.className = 'tl-level';
                level.textContent = event.level;
                live.appendChild(level);
            }
            const record = recordLine(event.record);
            if (record) {
                const line = document.createElement('span');
                line.className = 'tl-record';
                line.textContent = record;
                live.appendChild(line);
            }
            (event.awards || []).forEach(function (title) {
                const award = document.createElement('span');
                award.className = 'tl-award';
                award.textContent = title;
                live.appendChild(award);
            });
            if (live.children.length) live.removeAttribute('hidden');
            item.classList.add('tl-item--live');
        });
    }

    // Server-rendered photo buttons (the timeline's event galleries) open the lightbox too.
    function initPhotoButtons() {
        document.addEventListener('click', function (event) {
            const button = event.target.closest('[data-lightbox]');
            if (!button) return;
            const img = button.querySelector('img');
            openLightbox(button.dataset.lightbox, button.getAttribute('aria-label') || (img && img.alt), button);
        });
    }

    // --- lightbox ----------------------------------------------------------

    let lightbox = null;
    let lastFocused = null;

    function closeLightbox() {
        if (!lightbox) return;
        lightbox.setAttribute('hidden', '');
        document.body.classList.remove('has-lightbox');
        if (lastFocused) lastFocused.focus();
    }

    function ensureLightbox() {
        if (lightbox) return lightbox;

        lightbox = document.createElement('div');
        lightbox.className = 'team-lightbox';
        lightbox.setAttribute('role', 'dialog');
        lightbox.setAttribute('aria-modal', 'true');
        lightbox.setAttribute('hidden', '');
        lightbox.innerHTML =
            '<button type="button" class="team-lightbox-close" aria-label="Close photo">&times;</button>' +
            '<img class="team-lightbox-img" alt="">';

        lightbox.addEventListener('click', function (event) {
            if (event.target === lightbox) closeLightbox();
        });
        lightbox.querySelector('.team-lightbox-close').addEventListener('click', closeLightbox);
        document.addEventListener('keydown', function (event) {
            if (lightbox.hasAttribute('hidden')) return;
            if (event.key === 'Escape') closeLightbox();
            if (event.key === 'Tab') {
                // Only one control inside, so focus simply stays on it.
                event.preventDefault();
                lightbox.querySelector('.team-lightbox-close').focus();
            }
        });

        document.body.appendChild(lightbox);
        return lightbox;
    }

    function openLightbox(src, alt, trigger) {
        const box = ensureLightbox();
        const img = box.querySelector('.team-lightbox-img');
        img.src = src;
        img.alt = alt || '';
        lastFocused = trigger;
        box.removeAttribute('hidden');
        document.body.classList.add('has-lightbox');
        box.querySelector('.team-lightbox-close').focus();
    }

    // --- bootstrap ---------------------------------------------------------

    function loadLiveData() {
        const panel = document.getElementById('skills-panel');
        const band = document.getElementById('scoreboard-band');
        const results = document.getElementById('results-section');
        const tiles = Array.from(document.querySelectorAll('[data-bento-live]'));
        const live = [panel, band, results].concat(tiles);
        if (!panel && !band && !results && !tiles.length) return;

        // The skills panel carries the URL; the Bento layout has a skills tile instead.
        const source = document.querySelector('[data-live-url]');
        const url = source && source.dataset.liveUrl;
        if (!url) {
            live.forEach(drop);
            return;
        }

        let photosByEvent = {};
        const photoData = document.getElementById('team_event_photos');
        if (photoData) {
            try {
                photosByEvent = JSON.parse(photoData.textContent) || {};
            } catch (err) {
                photosByEvent = {};
            }
        }

        fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(function (resp) {
                if (resp.status !== 200) return null;
                return resp.json();
            })
            .then(function (data) {
                if (!data) {
                    live.forEach(drop);
                    return;
                }
                fillSkills(panel, data);
                fillScoreboard(band, data);
                fillResults(results, data, photosByEvent);
                fillTimeline(document.querySelector('[data-timeline]'), data);
                tiles.forEach(function (tile) { fillBentoTile(tile, data); });
            })
            .catch(function () {
                // An unreachable endpoint must leave no empty frames behind.
                live.forEach(drop);
            });
    }

    // --- STL viewer --------------------------------------------------------

    // The raw examples/jsm files import a bare "three" specifier, which a browser
    // cannot resolve without an import map. jsDelivr's /+esm builds rewrite that to
    // the same three@0.160.0/+esm URL used below, so all three share one instance.
    const THREE_VERSION = '0.160.0';
    const THREE_BASE = 'https://cdn.jsdelivr.net/npm/three@' + THREE_VERSION;

    function viewerFailed(host, message) {
        const shell = host.closest('.viewer-shell') || host;
        shell.innerHTML = '';
        const note = document.createElement('p');
        note.className = 'viewer-empty';
        note.textContent = message;
        shell.appendChild(note);
    }

    function hasWebGL() {
        try {
            const canvas = document.createElement('canvas');
            return !!(window.WebGLRenderingContext &&
                (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
        } catch (err) {
            return false;
        }
    }

    function startViewer(host) {
        const url = host.dataset.stl;
        if (!url) return;

        if (!hasWebGL()) {
            viewerFailed(host, 'Your browser cannot display the 3D model.');
            return;
        }

        Promise.all([
            import(THREE_BASE + '/+esm'),
            import(THREE_BASE + '/examples/jsm/loaders/STLLoader.js/+esm'),
            import(THREE_BASE + '/examples/jsm/controls/OrbitControls.js/+esm')
        ]).then(function (mods) {
            const THREE = mods[0];
            const STLLoader = mods[1].STLLoader;
            const OrbitControls = mods[2].OrbitControls;

            const width = host.clientWidth || 800;
            const height = host.clientHeight || 450;

            const scene = new THREE.Scene();
            scene.background = null;

            const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 5000);
            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.setSize(width, height);

            scene.add(new THREE.AmbientLight(0xffffff, 0.75));
            const key = new THREE.DirectionalLight(0xffffff, 0.9);
            key.position.set(1, 1, 1);
            scene.add(key);

            const controls = new OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            // Auto-spin is motion the viewer did not ask for.
            controls.autoRotate = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            controls.autoRotateSpeed = 1.2;

            new STLLoader().load(url, function (geometry) {
                geometry.computeBoundingBox();
                geometry.center();

                const size = geometry.boundingBox.getSize(new THREE.Vector3());
                const extent = Math.max(size.x, size.y, size.z) || 1;

                const mesh = new THREE.Mesh(geometry, new THREE.MeshPhongMaterial({
                    color: 0x944547, specular: 0x222222, shininess: 40
                }));
                mesh.rotation.x = -Math.PI / 2;
                scene.add(mesh);

                camera.position.set(0, extent * 0.8, extent * 2);
                controls.target.set(0, 0, 0);
                controls.saveState();
                controls.update();

                host.innerHTML = '';
                host.appendChild(renderer.domElement);

                const reset = document.getElementById('viewer-reset');
                if (reset) reset.addEventListener('click', function () { controls.reset(); });

                window.addEventListener('resize', function () {
                    const w = host.clientWidth || width;
                    const h = host.clientHeight || height;
                    camera.aspect = w / h;
                    camera.updateProjectionMatrix();
                    renderer.setSize(w, h);
                });

                (function animate() {
                    requestAnimationFrame(animate);
                    controls.update();
                    renderer.render(scene, camera);
                })();
            }, undefined, function () {
                viewerFailed(host, 'The 3D model could not be loaded.');
            });
        }).catch(function () {
            viewerFailed(host, 'The 3D viewer could not be loaded.');
        });
    }

    function initViewer() {
        const host = document.querySelector('#robot-viewer[data-stl]');
        if (!host) return; // No model: three.js is never fetched.

        if (!('IntersectionObserver' in window)) {
            startViewer(host);
            return;
        }

        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    observer.disconnect();
                    startViewer(host);
                }
            });
        }, { rootMargin: '200px' });
        observer.observe(host);
    }

    // --- dossier rail ------------------------------------------------------

    // The Dossier layout's fact rail sticks below the menu button. A rail taller
    // than the screen gets a negative offset instead, so it scrolls with the page
    // until its bottom edge is in view and sticks from there: nothing is cut off.
    const RAIL_TOP = 96;
    const RAIL_GAP = 16;

    function initDossierRail() {
        const rail = document.querySelector('.dossier-rail');
        if (!rail || !('ResizeObserver' in window)) return;
        function place() {
            const top = Math.min(RAIL_TOP, window.innerHeight - rail.offsetHeight - RAIL_GAP);
            rail.style.setProperty('--rail-top', top + 'px');
        }
        new ResizeObserver(place).observe(rail);
        window.addEventListener('resize', place);
    }

    // --- tabbed hub -------------------------------------------------------

    // The Tabbed Hub layout shows one panel at a time. Tabs follow the ARIA tabs
    // pattern (arrow keys, Home, End), and every tab but the first deep-links as
    // #<key>. A panel whose content goes away (Results, when RobotEvents has
    // nothing) takes its tab with it. The CAD viewer waits on an
    // IntersectionObserver, so it only loads once the Robot panel is shown.
    function initHub() {
        const hub = document.querySelector('[data-hub]');
        if (!hub) return;
        const tabs = Array.from(hub.querySelectorAll('[data-hub-tab]'));
        const panelOf = tab => document.getElementById(tab.getAttribute('aria-controls'));
        const shown = () => tabs.filter(tab => !tab.hidden);
        const byKey = key => shown().find(tab => tab.dataset.hubTab === key);

        // On a phone the tab row scrolls sideways; keep the open tab in sight.
        function centerTab(tab) {
            const bar = tab.parentElement;
            bar.scrollLeft = tab.offsetLeft - bar.offsetLeft - (bar.clientWidth - tab.offsetWidth) / 2;
        }
        // Tab widths settle once the web fonts load, so centre the open tab again then.
        window.addEventListener('load', function () {
            const open = tabs.find(tab => tab.getAttribute('aria-selected') === 'true');
            if (open) centerTab(open);
        });

        function select(key, opts) {
            const tab = byKey(key) || shown()[0];
            tabs.forEach(function (other) {
                const on = other === tab;
                other.setAttribute('aria-selected', on ? 'true' : 'false');
                other.tabIndex = on ? 0 : -1;
                const panel = panelOf(other);
                if (panel) panel.hidden = !on;
            });
            if (opts.focus) tab.focus();
            centerTab(tab);
            if (opts.hash) {
                const first = tab === shown()[0];
                history.replaceState(null, '', first ? location.pathname + location.search : '#' + tab.dataset.hubTab);
            }
            // A switch from far down a long panel lands at the top of the new one.
            if (opts.scroll && hub.getBoundingClientRect().top < 0) hub.scrollIntoView({ block: 'start' });
        }

        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                select(tab.dataset.hubTab, { hash: true, scroll: true });
            });
        });

        hub.querySelector('[role="tablist"]').addEventListener('keydown', function (event) {
            const list = shown();
            const at = list.indexOf(document.activeElement);
            if (at < 0) return;
            let next;
            if (event.key === 'ArrowRight') next = list[(at + 1) % list.length];
            else if (event.key === 'ArrowLeft') next = list[(at - 1 + list.length) % list.length];
            else if (event.key === 'Home') next = list[0];
            else if (event.key === 'End') next = list[list.length - 1];
            else return;
            event.preventDefault();
            select(next.dataset.hubTab, { hash: true, focus: true });
        });

        // Overview tiles (and any other [data-hub-open] link) open their tab.
        hub.addEventListener('click', function (event) {
            const opener = event.target.closest('[data-hub-open]');
            if (!opener || !byKey(opener.dataset.hubOpen)) return;
            event.preventDefault();
            select(opener.dataset.hubOpen, { hash: true, scroll: true, focus: true });
        });

        function fromHash(scroll) {
            const key = decodeURIComponent(location.hash.slice(1));
            if (byKey(key)) {
                select(key, {});
                if (scroll) hub.scrollIntoView({ block: 'start' });
            }
        }
        window.addEventListener('hashchange', function () { fromHash(true); });
        fromHash(true);

        tabs.forEach(function (tab) {
            const panel = panelOf(tab);
            if (!panel) return;
            new MutationObserver(function () {
                if (panel.children.length) return;
                const wasOpen = tab.getAttribute('aria-selected') === 'true';
                tab.hidden = true;
                hub.querySelectorAll('[data-hub-open="' + tab.dataset.hubTab + '"]').forEach(drop);
                if (wasOpen) select(shown()[0].dataset.hubTab, { hash: true });
            }).observe(panel, { childList: true });
        });
    }

    function boot() {
        initHub();
        initPhotoButtons();
        loadLiveData();
        initViewer();
        initDossierRail();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
