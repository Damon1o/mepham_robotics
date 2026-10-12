// Achievements page: season chips over the competition log, and a Share button on
// each award. Without this file every season is listed and the buttons stay hidden.

(function () {
    'use strict';

    // --- Season filter ------------------------------------------------------------------

    function initSeasons() {
        const bar = document.querySelector('.ach-season-filter');
        if (!bar) return;
        const seasons = document.querySelectorAll('.ach-season[data-season]');
        bar.hidden = false;
        bar.addEventListener('click', e => {
            const chip = e.target.closest('[data-season]');
            if (!chip) return;
            const pick = chip.dataset.season;
            bar.querySelectorAll('[data-season]').forEach(c => {
                const on = c === chip;
                c.classList.toggle('is-on', on);
                c.setAttribute('aria-pressed', String(on));
            });
            seasons.forEach(s => { s.hidden = pick !== 'all' && s.dataset.season !== pick; });
        });
    }

    // --- Share an award -----------------------------------------------------------------

    // The phone's share sheet where there is one; otherwise copy a link to the award.
    function initShare() {
        const canShare = typeof navigator.share === 'function';
        if (!canShare && !navigator.clipboard) return;
        document.querySelectorAll('.ach-share').forEach(b => { b.hidden = false; });
        const live = document.createElement('p');
        live.className = 'visually-hidden';
        live.setAttribute('aria-live', 'polite');
        document.body.append(live);
        document.addEventListener('click', e => {
            const button = e.target.closest('.ach-share');
            if (!button) return;
            const url = new URL(location.href);
            url.hash = button.dataset.share;
            const label = button.querySelector('span');
            if (canShare) {
                navigator.share({ title: document.title, text: button.dataset.shareText, url: url.href })
                    .catch(() => { /* closed the sheet */ });
                return;
            }
            navigator.clipboard.writeText(url.href).then(() => {
                label.textContent = 'Link copied';
                live.textContent = 'Link to the award copied.';
                setTimeout(() => { label.textContent = 'Share'; }, 2000);
            }).catch(() => { /* permission denied */ });
        });
    }

    initSeasons();
    initShare();
})();
