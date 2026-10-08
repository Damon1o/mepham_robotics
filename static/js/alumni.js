// Alumni (/alumni): pathway chips and search narrow the wall; the update form
// sends to the contact inbox tagged "alumni".

(function () {
    'use strict';

    function initWall() {
        const cards = [...document.querySelectorAll('[data-alum]')];
        if (!cards.length) return;
        const chips = [...document.querySelectorAll('[data-path-filter]')];
        const search = document.querySelector('[data-alumni-search]');
        const count = document.querySelector('[data-alumni-count]');
        const none = document.querySelector('[data-alumni-none]');
        let path = '';

        function apply() {
            const words = (search?.value || '').toLowerCase().split(/\s+/).filter(Boolean);
            let shown = 0;
            cards.forEach(card => {
                const match = (!path || card.dataset.path === path)
                    && words.every(w => card.dataset.search.includes(w));
                card.hidden = !match;
                if (match) shown++;
            });
            document.querySelectorAll('[data-class]').forEach(group => {
                group.hidden = !group.querySelector('[data-alum]:not([hidden])');
            });
            if (none) none.hidden = shown > 0;
            if (count) {
                count.textContent = shown === cards.length ? ''
                    : `Showing ${shown} of ${cards.length} alumni`;
            }
        }

        chips.forEach(chip => chip.addEventListener('click', () => {
            path = chip.dataset.pathFilter;
            chips.forEach(c => c.setAttribute('aria-pressed', String(c === chip)));
            apply();
        }));
        search?.addEventListener('input', apply);
    }

    function initForm() {
        const form = document.querySelector('[data-alumni-form]');
        if (!form) return;
        const status = form.querySelector('[data-alumni-status]');
        const field = name => form.querySelector(`[name="${name}"]`);

        function say(text, ok) {
            status.textContent = text;
            status.classList.toggle('is-ok', ok === true);
            status.classList.toggle('is-error', ok === false);
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = field('name').value.trim();
            const email = field('email').value.trim();
            const year = field('class_year').value.trim();
            const note = field('message').value.trim();
            const missing = [[field('name'), !name], [field('email'), !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)],
                [field('class_year'), year && !/^\d{4}$/.test(year)], [field('message'), !note]];
            missing.forEach(([input, bad]) => input.classList.toggle('has-error', Boolean(bad)));
            const first = missing.find(([, bad]) => bad);
            if (first) {
                say(first[0] === field('class_year') ? 'Class year should look like 2024.'
                    : 'Fill in your name, a valid email and where you are now.', false);
                first[0].focus();
                return;
            }

            const button = form.querySelector('button[type="submit"]');
            button.disabled = true;
            say('Sending…');
            try {
                const response = await fetch('/api/contact', {
                    method: 'POST',
                    headers: jsonHeaders(),
                    body: JSON.stringify({
                        name, email, topic: 'alumni',
                        message: (year ? `Class of ${year}\n\n` : '') + note,
                        website: field('website').value
                    })
                });
                const data = await response.json().catch(() => ({}));
                if (response.ok) {
                    form.reset();
                    say('Thanks! We got your update and will be in touch.', true);
                } else {
                    say(data.error || 'That did not send. Try again in a moment.', false);
                }
            } catch (err) {
                say('That did not send. Check your connection and try again.', false);
            } finally {
                button.disabled = false;
            }
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        initWall();
        initForm();
    });
})();
