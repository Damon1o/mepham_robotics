// Alumni (/alumni): pathway chips, class and school menus, the "Open to questions"
// chip and search narrow the wall. The update form and the "Ask an alum" form send
// to the contact inbox tagged "alumni"; an Ask button on a card picks that person.

(function () {
    'use strict';

    function initWall() {
        const cards = [...document.querySelectorAll('[data-alum]')];
        if (!cards.length) return;
        const chips = [...document.querySelectorAll('[data-path-filter]')];
        const search = document.querySelector('[data-alumni-search]');
        const count = document.querySelector('[data-alumni-count]');
        const none = document.querySelector('[data-alumni-none]');
        const year = document.querySelector('[data-alumni-class]');
        const school = document.querySelector('[data-alumni-school]');
        const mentors = document.querySelector('[data-alumni-mentors]');
        let path = '';

        function apply() {
            const words = (search?.value || '').toLowerCase().split(/\s+/).filter(Boolean);
            let shown = 0;
            cards.forEach(card => {
                const match = (!path || card.dataset.path === path)
                    && (!year?.value || card.dataset.classYear === year.value)
                    && (!school?.value || card.dataset.school === school.value)
                    && (mentors?.getAttribute('aria-pressed') !== 'true' || 'mentor' in card.dataset)
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
        year?.addEventListener('change', apply);
        school?.addEventListener('change', apply);
        mentors?.addEventListener('click', () => {
            mentors.setAttribute('aria-pressed', String(mentors.getAttribute('aria-pressed') !== 'true'));
            apply();
        });
    }

    // An Ask button on a card picks that person in the form; its link then scrolls there.
    function initAskButtons() {
        const pick = document.querySelector('[data-alumni-ask] select[name="alum"]');
        if (!pick) return;
        document.addEventListener('click', e => {
            const button = e.target.closest('[data-ask]');
            if (!button) return;
            pick.value = button.dataset.ask;
            pick.dispatchEvent(new Event('change', { bubbles: true }));
            setTimeout(() => pick.form.querySelector('[name="name"]').focus({ preventScroll: true }), 0);
        });
    }

    // Both forms post to /api/contact tagged "alumni"; `compose` builds the message.
    function initForm(form, compose, sent) {
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
            const year = field('class_year')?.value.trim() || '';
            const note = field('message').value.trim();
            const missing = [[field('name'), !name], [field('email'), !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)],
                [field('class_year'), year && !/^\d{4}$/.test(year)], [field('message'), !note]]
                .filter(([input]) => input);
            missing.forEach(([input, bad]) => input.classList.toggle('has-error', Boolean(bad)));
            const first = missing.find(([, bad]) => bad);
            if (first) {
                say(first[0] === field('class_year') ? 'Class year should look like 2024.'
                    : `Fill in your name, a valid email and ${field('class_year') ? 'where you are now' : 'your question'}.`, false);
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
                        message: compose(field, year, note),
                        website: field('website').value
                    })
                });
                const data = await response.json().catch(() => ({}));
                if (response.ok) {
                    form.reset();
                    say(sent, true);
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
        initAskButtons();
        initForm(document.querySelector('[data-alumni-form]'),
            (field, year, note) => (year ? `Class of ${year}\n\n` : '') + note,
            'Thanks! We got your update and will be in touch.');
        initForm(document.querySelector('[data-alumni-ask]'),
            (field, year, note) => `Question for ${field('alum').value}:\n\n${note}`,
            'Thanks! We will pass your question on.');
    });
})();
