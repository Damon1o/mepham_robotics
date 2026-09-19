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
        if (!panel && !band && !results) return;

        const url = panel && panel.dataset.liveUrl;
        if (!url) {
            [panel, band, results].forEach(drop);
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
                    [panel, band, results].forEach(drop);
                    return;
                }
                fillSkills(panel, data);
                fillScoreboard(band, data);
                fillResults(results, data, photosByEvent);
            })
            .catch(function () {
                // An unreachable endpoint must leave no empty frames behind.
                [panel, band, results].forEach(drop);
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadLiveData);
    } else {
        loadLiveData();
    }
})();
