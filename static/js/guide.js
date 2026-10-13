// New member guide (/guide): tick chapters off, keep the progress bar, chapter list,
// and "pick up where you left off" link in step, and
// light up the chapter being read in the list.
//
// Finished chapters are saved to the account (POST /api/guide/step), so progress
// follows a member to any device. The page arrives with it drawn.

(function () {
    'use strict';

    const guide = document.querySelector('[data-guide]');
    if (!guide) return;

    const chapters = [...guide.querySelectorAll('[data-chapter]')];
    const total = chapters.length;
    const status = guide.querySelector('[data-guide-status]');
    let done = new Set(chapters.filter(ch => ch.classList.contains('is-done')).map(ch => ch.dataset.chapter));

    function post(body) {
        return fetch(guide.dataset.stepUrl, {
            method: 'POST', credentials: 'same-origin', keepalive: true,
            headers: jsonHeaders(), body: JSON.stringify(body),
        }).then(r => r.json().then(data => {
            if (!r.ok) throw new Error(data.error || 'Could not save that.');
            return data;
        }));
    }

    function paint() {
        chapters.forEach(ch => {
            const key = ch.dataset.chapter;
            const on = done.has(key);
            ch.classList.toggle('is-done', on);
            ch.querySelector('[data-guide-toggle]').setAttribute('aria-pressed', String(on));
            const link = guide.querySelector(`[data-toc="${key}"]`);
            link.classList.toggle('is-done', on);
            link.querySelector('[data-toc-state]').textContent = on ? '(done)' : '';
        });

        guide.querySelector('[data-guide-count]').textContent = done.size;
        guide.querySelector('[data-guide-bar]').value = done.size;

        const next = chapters.find(ch => !done.has(ch.dataset.chapter));
        const resume = guide.querySelector('[data-guide-resume]');
        resume.hidden = !next;
        if (next) {
            resume.href = `#${next.id}`;
            resume.querySelector('span').textContent = done.size ? 'Pick up where you left off' : 'Start reading';
        }

        guide.querySelector('[data-guide-finish]').classList.toggle('is-complete', done.size === total);
    }

    guide.addEventListener('click', e => {
        const btn = e.target.closest('[data-guide-toggle]');
        if (!btn) return;
        const key = btn.dataset.guideToggle;
        const on = !done.has(key);
        const before = new Set(done);
        on ? done.add(key) : done.delete(key);
        paint();
        status.textContent = '';
        post({ key, done: on })
            .then(data => {
                // The account's list is the truth; keep only chapters on this page.
                const saved = new Set(data.done || []);
                done = new Set(chapters.map(ch => ch.dataset.chapter).filter(k => saved.has(k)));
                paint();
                if (on && done.size === total) {
                    guide.querySelector('[data-guide-finish]').scrollIntoView({ behavior: smooth(), block: 'center' });
                }
            })
            .catch(err => {
                done = before;
                paint();
                status.textContent = err.message || 'Could not save that. Try again.';
            });
    });

    function smooth() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches
            || document.documentElement.dataset.motion === 'reduce' ? 'auto' : 'smooth';
    }

    // --- The chapter being read, lit up in the list ------------------------------------

    if ('IntersectionObserver' in window) {
        const links = new Map(chapters.map(ch => [ch.id, guide.querySelector(`[data-toc="${ch.dataset.chapter}"]`)]));
        const seen = new Map();
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => seen.set(entry.target.id, entry.isIntersecting));
            const current = chapters.find(ch => seen.get(ch.id));
            links.forEach((link, id) => {
                const on = current && id === current.id;
                link.classList.toggle('is-current', Boolean(on));
                if (on) link.setAttribute('aria-current', 'step');
                else link.removeAttribute('aria-current');
            });
        }, { rootMargin: '-35% 0px -55% 0px' });
        chapters.forEach(ch => observer.observe(ch));
    }
})();
