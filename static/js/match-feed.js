/* ============================================
   MATCH FEED (achievements page)
   One season of RobotEvents matches, rankings and skills for every robot
   team, via /api/matches so the API key stays server-side.
   ============================================ */
(function initMatchFeed() {
    const root = document.getElementById('match-feed');
    if (!root) return;
    const seasonEl = document.getElementById('match-feed-season');
    const teamUrl = root.dataset.teamUrl || '';
    // On a team page: one team and the season that page shows. The section
    // stays hidden until there is something to show.
    const section = root.closest('[data-match-section]');
    const params = new URLSearchParams();
    if (root.dataset.team) params.set('team', root.dataset.team);
    if (root.dataset.season) params.set('season', root.dataset.season);
    const feedUrl = `/api/matches${params.toString() ? `?${params}` : ''}`;

    const MATCHES_SHOWN = 6;
    const REFRESH_MS = 300000;

    let feed = null;
    let activeTeam = '';
    const openEvents = new Set();
    const expandedEvents = new Set();
    let firstRender = true;

    const monthFmt = new Intl.DateTimeFormat(undefined, { month: 'short' });
    const yearFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });

    function esc(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function icon(name) {
        return `<i data-lucide="${name}" aria-hidden="true"></i>`;
    }

    function parseDate(value) {
        const date = value ? new Date(value) : null;
        return date && !isNaN(date) ? date : null;
    }

    function num(value, fallback = '—') {
        return value == null || value === '' ? fallback : esc(value);
    }

    function record(r) {
        return `${r.wins}-${r.losses}-${r.ties}`;
    }

    function showStatus(message) {
        root.innerHTML = `<p class="mf-status" role="status">${esc(message)}</p>`;
    }

    function teamLink(team) {
        if (!team.page || !teamUrl || root.dataset.team) return `<span class="mf-team-number">${esc(team.number)}</span>`;
        return `<a class="mf-team-number" href="${esc(teamUrl.replace('TEAM', encodeURIComponent(team.page)))}">${esc(team.number)}</a>`;
    }

    /* --- Team summary cards --- */

    function skillBar(label, iconName, value, max) {
        const pct = max ? Math.round((100 * value) / max) : 0;
        return `
            <div class="mf-skill">
                <span class="mf-skill-label">${icon(iconName)}${label}</span>
                <span class="mf-skill-track"><span class="mf-skill-fill" data-pct="${pct}"></span></span>
                <b>${esc(value)}</b>
            </div>`;
    }

    function teamCard(team, maxSkill) {
        const skills = team.skills;
        const rate = team.win_rate == null ? 0 : team.win_rate;
        return `
            <article class="mf-team${activeTeam && activeTeam !== team.number ? ' is-dimmed' : ''}">
                <header class="mf-team-head">
                    <div>
                        ${teamLink(team)}
                        ${team.name ? `<span class="mf-team-name">${esc(team.name)}</span>` : ''}
                    </div>
                    <a class="mf-team-re" href="${esc(team.profile_url)}" target="_blank" rel="noopener"
                        aria-label="${esc(team.number)} on RobotEvents">${icon('external-link')}</a>
                </header>

                <div class="mf-record" aria-label="Record ${team.wins} wins, ${team.losses} losses, ${team.ties} ties">
                    <span class="is-win"><b>${team.wins}</b>W</span>
                    <span class="is-loss"><b>${team.losses}</b>L</span>
                    <span class="is-tie"><b>${team.ties}</b>T</span>
                </div>
                <div class="mf-winrate">
                    <span class="mf-winrate-track"><span class="mf-winrate-fill" data-pct="${rate}"></span></span>
                    <span>${team.win_rate == null ? 'No results yet' : `${team.win_rate}% win rate`}</span>
                </div>

                <dl class="mf-stats">
                    <div><dt>Best rank</dt><dd>${team.best_rank ? `#${esc(team.best_rank)}` : '—'}</dd></div>
                    <div><dt>High score</dt><dd>${num(team.high_score)}</dd></div>
                    <div><dt>Avg score</dt><dd>${num(team.average_score)}</dd></div>
                    <div><dt>Events</dt><dd>${num(team.events)}</dd></div>
                </dl>

                <div class="mf-skills">
                    <p class="mf-skills-title">
                        <span>${icon('zap')}Skills</span>
                        ${skills ? `<span class="mf-skills-best">Best <b>${esc(skills.best_combined)}</b>${skills.best_rank ? ` · #${esc(skills.best_rank)} at an event` : ''}</span>` : ''}
                    </p>
                    ${skills
                        ? skillBar('Driver', 'gamepad-2', skills.best_driver, maxSkill)
                          + skillBar('Auton', 'cpu', skills.best_programming, maxSkill)
                        : '<p class="mf-empty">No skills runs this season.</p>'}
                </div>
            </article>`;
    }

    /* --- Filter chips --- */

    function filterChips() {
        if (feed.teams.length < 2) return '';
        const chip = (value, label) => `
            <button type="button" class="mf-chip" data-team="${esc(value)}" aria-pressed="${activeTeam === value}">${esc(label)}</button>`;
        return `
            <div class="mf-filter" role="group" aria-label="Show matches for">
                ${chip('', 'All teams')}
                ${feed.teams.map(t => chip(t.number, t.number)).join('')}
            </div>`;
    }

    /* --- Events and matches --- */

    function involves(match, number) {
        return match.ours.some(side => side.number === number);
    }

    function allianceTeams(side) {
        return side.teams.map(t => {
            const cls = ['mf-ally'];
            if (t.ours) cls.push('is-ours');
            if (t.sitting) cls.push('is-sitting');
            const team = feed.teams.find(x => x.number === t.number);
            if (t.ours && team && team.page && teamUrl && !root.dataset.team) {
                return `<a class="${cls.join(' ')}" href="${esc(teamUrl.replace('TEAM', encodeURIComponent(team.page)))}">${esc(t.number)}</a>`;
            }
            return `<span class="${cls.join(' ')}"${t.sitting ? ' title="Sat out"' : ''}>${esc(t.number)}</span>`;
        }).join('');
    }

    function resultFor(match) {
        const sides = activeTeam ? match.ours.filter(s => s.number === activeTeam) : match.ours;
        const results = [...new Set(sides.map(s => s.result).filter(Boolean))];
        // Two of our teams on opposite alliances: no single result to show.
        return results.length === 1 ? results[0] : null;
    }

    function matchRow(match) {
        const result = resultFor(match);
        const time = parseDate(match.time);
        const label = { win: 'W', loss: 'L', tie: 'T' }[result];
        const score = s => (match.played ? esc(s.score) : '–');
        const cls = ['mf-match'];
        if (result) cls.push(`is-${result}`);
        if (!match.played) cls.push('is-upcoming');
        if (match.elimination) cls.push('is-elim');
        return `
            <li class="${cls.join(' ')}">
                <div class="mf-match-meta">
                    <span class="mf-match-name">${esc(match.name)}</span>
                    ${match.elimination ? `<span class="mf-tag">${esc(match.round)}</span>` : ''}
                    <span class="mf-match-when">
                        ${time ? `${icon('clock')}<time datetime="${esc(match.time)}">${esc(timeFmt.format(time))}</time>` : ''}
                        ${match.field ? `<span>${icon('map-pin')}${esc(match.field)}</span>` : ''}
                    </span>
                </div>
                <div class="mf-board">
                    <div class="mf-side is-red${match.winner === 'red' ? ' is-winner' : ''}">
                        <span class="mf-allies">${allianceTeams(match.red)}</span>
                        <b class="mf-score">${score(match.red)}</b>
                    </div>
                    <span class="mf-vs" aria-hidden="true">vs</span>
                    <div class="mf-side is-blue${match.winner === 'blue' ? ' is-winner' : ''}">
                        <b class="mf-score">${score(match.blue)}</b>
                        <span class="mf-allies">${allianceTeams(match.blue)}</span>
                    </div>
                </div>
                <span class="mf-result"${result ? ` aria-label="${esc(result)}"` : ''}>${match.played ? (label || '·') : icon('hourglass')}</span>
            </li>`;
    }

    function eventTeamRows(event) {
        const rows = Object.entries(event.teams)
            .filter(([number]) => !activeTeam || number === activeTeam)
            .map(([number, t]) => {
                const r = t.ranking || {};
                const s = t.skills;
                return `
                    <tr>
                        <th scope="row">${esc(number)}</th>
                        <td>${r.rank ? `#${esc(r.rank)}` : '—'}</td>
                        <td>${record(t)}</td>
                        <td>${r.wp != null ? `${esc(r.wp)} / ${esc(r.ap)} / ${esc(r.sp)}` : '—'}</td>
                        <td>${num(t.average_score)}</td>
                        <td>${num(t.high_score)}</td>
                        <td>${s ? esc(s.driver) : '—'}</td>
                        <td>${s ? esc(s.programming) : '—'}</td>
                        <td>${s ? `<b>${esc(s.combined)}</b>${s.rank ? ` <span class="mf-muted">#${esc(s.rank)}</span>` : ''}` : '—'}</td>
                    </tr>`;
            }).join('');
        return `
            <div class="mf-table-wrap">
                <table class="mf-table">
                    <thead>
                        <tr>
                            <th scope="col">Team</th>
                            <th scope="col">Rank</th>
                            <th scope="col">W-L-T</th>
                            <th scope="col"><abbr title="Win points / autonomous points / strength of schedule">WP / AP / SP</abbr></th>
                            <th scope="col">Avg</th>
                            <th scope="col">High</th>
                            <th scope="col">Driver</th>
                            <th scope="col">Auton</th>
                            <th scope="col">Skills</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
    }

    function eventBadges(event) {
        return Object.entries(event.teams)
            .filter(([number]) => !activeTeam || number === activeTeam)
            .map(([number, t]) => {
                const rank = t.ranking && t.ranking.rank;
                return `<span class="mf-badge"><b>${esc(number)}</b>${rank ? `#${esc(rank)} · ` : ''}${record(t)}</span>`;
            }).join('');
    }

    function eventBlock(event) {
        const matches = activeTeam ? event.matches.filter(m => involves(m, activeTeam)) : event.matches;
        if (!matches.length) return '';
        const start = parseDate(event.start);
        const key = String(event.id);
        const open = openEvents.has(key);
        const expanded = expandedEvents.has(key);
        const shown = expanded ? matches : matches.slice(0, MATCHES_SHOWN);
        const wins = matches.filter(m => resultFor(m) === 'win').length;
        const played = matches.filter(m => resultFor(m)).length;
        return `
            <details class="mf-event" data-event="${esc(key)}"${open ? ' open' : ''}>
                <summary class="mf-event-head">
                    <span class="mf-date">${start ? `<span>${esc(monthFmt.format(start))}</span><b>${start.getDate()}</b>` : icon('calendar')}</span>
                    <span class="mf-event-title">
                        <span class="mf-event-name">${esc(event.name)}</span>
                        <span class="mf-event-sub">
                            ${start ? esc(yearFmt.format(start)) : ''}
                            · ${matches.length} match${matches.length === 1 ? '' : 'es'}
                            ${played ? ` · ${wins} won` : ''}
                        </span>
                        <span class="mf-badges">${eventBadges(event)}</span>
                    </span>
                    <span class="mf-chevron">${icon('chevron-down')}</span>
                </summary>
                <div class="mf-event-body">
                    ${eventTeamRows(event)}
                    <ol class="mf-matches">${shown.map(matchRow).join('')}</ol>
                    ${matches.length > MATCHES_SHOWN
                        ? `<button type="button" class="mf-more" data-more="${esc(key)}" aria-expanded="${expanded}">
                               ${expanded ? `Show fewer ${icon('chevron-up')}` : `Show all ${matches.length} matches ${icon('chevron-down')}`}
                           </button>`
                        : ''}
                </div>
            </details>`;
    }

    /* --- Render --- */

    function render() {
        if (firstRender && feed.events.length) {
            openEvents.add(String(feed.events[0].id));
            firstRender = false;
        }
        const maxSkill = Math.max(1, ...feed.teams.map(t => (t.skills ? Math.max(t.skills.best_driver, t.skills.best_programming) : 0)));
        root.innerHTML = `
            <div class="mf-teams">${feed.teams.map(t => teamCard(t, maxSkill)).join('')}</div>
            ${filterChips()}
            <div class="mf-events">${feed.events.map(eventBlock).join('') || '<p class="mf-status">No matches for this team.</p>'}</div>`;
        // Widths go through the CSSOM so the page needs no inline style attributes.
        root.querySelectorAll('[data-pct]').forEach(el => {
            el.style.width = `${Math.max(0, Math.min(100, Number(el.dataset.pct) || 0))}%`;
        });
        if (typeof refreshLucideIcons === 'function') refreshLucideIcons();
    }

    root.addEventListener('click', e => {
        const chip = e.target.closest('.mf-chip');
        if (chip) {
            activeTeam = chip.dataset.team;
            render();
            return;
        }
        const more = e.target.closest('.mf-more');
        if (more) {
            const key = more.dataset.more;
            if (expandedEvents.has(key)) expandedEvents.delete(key);
            else expandedEvents.add(key);
            render();
        }
    });

    // Remember which events are open so a filter change or refresh keeps them.
    root.addEventListener('toggle', e => {
        const details = e.target.closest && e.target.closest('.mf-event');
        if (!details) return;
        if (details.open) openEvents.add(details.dataset.event);
        else openEvents.delete(details.dataset.event);
    }, true);

    async function load() {
        let data;
        try {
            const response = await fetch(feedUrl);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            data = await response.json();
        } catch (error) {
            console.error('Match feed error:', error);
            if (!feed && !section) showStatus('Match results are unavailable right now.');
            return;
        }
        if (!data.events || !data.events.length) {
            if (!feed && !section) showStatus('No recent matches found.');
            return;
        }
        feed = data;
        if (section) section.hidden = false;
        if (seasonEl && data.season) {
            seasonEl.textContent = `${data.season.label} season${data.season.game ? ` · ${data.season.game}` : ''}`;
            seasonEl.hidden = false;
        }
        if (activeTeam && !feed.teams.some(t => t.number === activeTeam)) activeTeam = '';
        render();
    }

    load();
    setInterval(load, REFRESH_MS);
})();
