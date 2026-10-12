// Homepage live ticker: during a competition on the calendar, our latest scored
// matches and our next one, from /api/matches (cached on the server). The
// section stays hidden until there is something to show, and stops asking
// while the tab is in the background.

(function () {
    'use strict';

    const REFRESH_MS = 60 * 1000;
    const RECENT_SHOWN = 6;
    // A RobotEvents event counts as the one on now if a match of ours is within this window.
    const FRESH_MS = 18 * 60 * 60 * 1000;

    const box = document.querySelector('[data-live-ticker]');
    if (!box) return;
    const list = box.querySelector('[data-live-list]');
    const next = box.querySelector('[data-live-next]');
    let timer = null;

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    const when = time => (time ? new Date(time).getTime() : 0);
    const clock = time => new Date(time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

    // The newest event with a match of ours close to now; null between competitions.
    function currentEvent(feed) {
        const now = Date.now();
        return (feed.events || []).find(e => e.matches.some(m => m.ours.length && m.time
            && Math.abs(when(m.time) - now) < FRESH_MS)) || null;
    }

    function matchRow(m) {
        const side = m.ours[0];
        const li = el('li', `live-match is-${side.result || 'tbd'}`);
        li.append(el('span', 'live-match-name', m.name));
        const teams = el('span', 'live-match-teams');
        m.ours.forEach((s, i) => {
            if (i) teams.append(' ');
            const link = el('a', '', s.number);
            link.href = box.dataset.teamUrl.replace('TEAM', encodeURIComponent(s.number));
            teams.append(link);
        });
        li.append(teams);
        const ourScore = m[side.color].score;
        const theirScore = m[side.color === 'red' ? 'blue' : 'red'].score;
        li.append(el('span', 'live-match-score', `${ourScore}–${theirScore}`));
        const label = { win: 'Won', loss: 'Lost', tie: 'Tied' }[side.result] || '';
        li.append(el('span', 'live-match-result', label));
        return li;
    }

    function show(feed) {
        const event = currentEvent(feed);
        if (!event) {
            box.hidden = true;
            return;
        }
        const ours = event.matches.filter(m => m.ours.length);
        const played = ours.filter(m => m.played).sort((a, b) => when(b.time) - when(a.time));
        const upcoming = ours.filter(m => !m.played && m.time).sort((a, b) => when(a.time) - when(b.time));
        list.replaceChildren(...played.slice(0, RECENT_SHOWN).map(matchRow));
        if (upcoming.length) {
            const m = upcoming[0];
            next.textContent = `Next: ${m.name} · ${m.ours.map(s => `${s.number} (${s.color})`).join(', ')} · ${clock(m.time)}`;
        }
        next.hidden = !upcoming.length;
        box.hidden = !played.length && !upcoming.length;
    }

    function load() {
        fetch('/api/matches', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
            .then(r => (r.ok ? r.json() : null))
            .then(feed => { if (feed) show(feed); })
            .catch(() => { /* keep whatever is showing; try again next time */ });
    }

    function schedule() {
        clearInterval(timer);
        timer = document.hidden ? null : setInterval(load, REFRESH_MS);
    }

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) load();
        schedule();
    });
    load();
    schedule();
})();
