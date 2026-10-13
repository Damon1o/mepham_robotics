// Member pages (/people/<id>, templates/person.html): sharing and printing, the
// "Verified on RobotEvents" panel, and, for the member, the in-place editors.
//
// "Edit page" puts an Edit button on each part of the page; Edit swaps that part for
// its form, filled from the JSON seed the server put in the page. Saving posts one
// section to /api/people/<id>/profile and reloads, so what shows is always what the
// server stored. Photos upload one at a time as they are picked or dropped, and a
// delete lights a Fuse with Undo rather than asking "Are you sure?".

(function () {
    const page = document.querySelector('[data-person-page]');
    if (!page) return;

    const icons = () => window.refreshLucideIcons && window.refreshLucideIcons();
    const STORE_KEY = 'pf-after-save';

    // --- Status line ------------------------------------------------------------------

    const status = page.querySelector('[data-page-status]');
    let statusTimer = 0;
    function say(text, isError = false) {
        if (!status) return;
        status.textContent = text;
        status.classList.toggle('is-error', isError);
        status.hidden = false;
        clearTimeout(statusTimer);
        statusTimer = setTimeout(() => { status.hidden = true; }, isError ? 8000 : 4000);
    }

    function flash(button, text) {
        const label = button.querySelector('span');
        if (!label) return;
        const before = label.textContent;
        label.textContent = text;
        setTimeout(() => { label.textContent = before; }, 2000);
    }

    async function copy(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            return false;
        }
    }

    // --- Share, print, QR ---------------------------------------------------------------

    page.querySelectorAll('[data-copy-link]').forEach(button => {
        button.addEventListener('click', async () => {
            flash(button, await copy(button.dataset.copyLink) ? 'Link copied' : 'Copy from the address bar');
        });
    });

    page.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));

    const qrBox = page.querySelector('[data-qr]');
    if (qrBox && typeof qrcode === 'function') {
        const qr = qrcode(0, 'M');
        qr.addData(qrBox.dataset.qr);
        qr.make();
        // Built from the page's own address only, so it is safe to insert.
        qrBox.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 1, scalable: true });
    }

    // --- Verified on RobotEvents --------------------------------------------------------

    const verified = page.querySelector('[data-verified-url]');
    if (verified) {
        fetch(verified.dataset.verifiedUrl, { credentials: 'same-origin' })
            .then(resp => (resp.status === 200 ? resp.json() : null))
            .then(data => {
                if (!data || !data.seasons || !data.seasons.length) return;
                const list = verified.querySelector('[data-verified-list]');
                data.seasons.forEach(season => {
                    const item = document.createElement('li');
                    const head = document.createElement('p');
                    head.className = 'pf-verified-season';
                    head.append(`${season.season} · ${season.team} `);
                    const link = document.createElement('a');
                    link.href = season.url;
                    link.target = '_blank';
                    link.rel = 'noopener';
                    link.textContent = 'See on RobotEvents';
                    head.append(link);
                    const awards = document.createElement('ul');
                    awards.className = 'pf-verified-awards';
                    season.awards.forEach(award => {
                        const row = document.createElement('li');
                        const title = document.createElement('b');
                        title.textContent = award.title;
                        row.append(title);
                        if (award.event) {
                            const where = document.createElement('span');
                            where.textContent = award.event;
                            row.append(where);
                        }
                        awards.append(row);
                    });
                    item.append(head, awards);
                    list.append(item);
                });
                verified.hidden = false;
            })
            .catch(() => {});  // the panel just stays hidden
    }

    // Everything below is for the member (and admins) only.
    const api = page.dataset.profileApi;
    const seedEl = page.querySelector('[data-editor-seed]');
    if (!api || !seedEl) return;
    const seed = JSON.parse(seedEl.textContent);
    const profile = seed.profile;

    // --- Character counters -------------------------------------------------------------

    function wireCounter(field) {
        const counter = field.querySelector('[data-counter]');
        const input = field.querySelector('input, textarea');
        if (!counter || !input) return;
        const limit = Number(input.maxLength) || 0;
        const update = () => {
            const n = input.value.length;
            counter.querySelector('[data-count]').textContent = n;
            counter.classList.toggle('is-near', limit && n >= limit * 0.9 && n < limit);
            counter.classList.toggle('is-full', limit && n >= limit);
        };
        input.addEventListener('input', update);
        update();
        return update;
    }

    page.querySelectorAll('.pf-field').forEach(wireCounter);

    // --- Saving -------------------------------------------------------------------------

    async function send(section, data) {
        const resp = await fetch(api, {
            method: 'POST', credentials: 'same-origin', headers: jsonHeaders(),
            body: JSON.stringify({ section, data }),
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body.error || 'That did not save. Try again in a moment.');
        return body;
    }

    function reloadAt(section, message) {
        try { sessionStorage.setItem(STORE_KEY, JSON.stringify({ section, message })); } catch (err) { /* fine */ }
        window.location.hash = section;
        window.location.reload();
    }

    function showError(form, message) {
        const box = form.querySelector('[data-editor-error]');
        if (box) {
            box.textContent = message;
            box.hidden = false;
        } else {
            say(message, true);
        }
    }

    function busy(form, on) {
        form.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = on; });
    }

    // --- Edit mode and opening a section ------------------------------------------------

    const toggle = page.querySelector('[data-edit-toggle]');
    const visibilityBadge = page.querySelector('[data-visibility-toggle]');
    function setEditing(on) {
        page.classList.toggle('is-editing', on);
        if (visibilityBadge) {
            visibilityBadge.disabled = !on;
            visibilityBadge.title = on ? 'Click to change who can see this page'
                : 'Click Edit page, then click here to change who can see it';
        }
        if (!toggle) return;
        toggle.setAttribute('aria-pressed', String(on));
        toggle.querySelector('[data-edit-label]').textContent = on ? 'Done editing' : 'Edit page';
        if (!on) page.querySelectorAll('[data-editor]:not([data-always-open])').forEach(close);
    }
    toggle?.addEventListener('click', () => setEditing(!page.classList.contains('is-editing')));

    // The toolbar badge flips who can see the page, saved on its own so About me is untouched.
    visibilityBadge?.addEventListener('click', async () => {
        if (visibilityBadge.getAttribute('aria-busy') === 'true') return;
        const next = profile.visibility === 'public' ? 'members' : 'public';
        visibilityBadge.setAttribute('aria-busy', 'true');
        try {
            await send('visibility', { visibility: next });
            profile.visibility = next;
            visibilityBadge.classList.toggle('pf-visibility--public', next === 'public');
            visibilityBadge.classList.toggle('pf-visibility--members', next !== 'public');
            say(next === 'public' ? 'Your page is public: anyone with the link can see it.'
                : 'Your page is for signed-in members only.');
        } catch (err) {
            say(err.message, true);
        } finally {
            visibilityBadge.removeAttribute('aria-busy');
        }
    });

    const fillers = {};

    function open(section) {
        const form = page.querySelector(`[data-editor="${section}"]`);
        const view = page.querySelector(`[data-view="${section}"]`);
        if (!form) return;
        fillers[section]?.(form);
        form.querySelector('[data-editor-error]')?.setAttribute('hidden', '');
        form.hidden = false;
        if (view) view.hidden = true;
        page.querySelector(`[data-edit-section="${section}"]`)?.setAttribute('aria-expanded', 'true');
        icons();
        form.querySelector('input:not([type="hidden"]):not([type="file"]), textarea')?.focus({ preventScroll: true });
    }

    function close(form) {
        const section = form.dataset.editor;
        form.hidden = true;
        const view = page.querySelector(`[data-view="${section}"]`);
        if (view) view.hidden = false;
        page.querySelector(`[data-edit-section="${section}"]`)?.setAttribute('aria-expanded', 'false');
    }

    page.querySelectorAll('[data-edit-section]').forEach(button => {
        button.addEventListener('click', () => {
            const form = page.querySelector(`[data-editor="${button.dataset.editSection}"]`);
            if (form && !form.hidden) close(form);
            else open(button.dataset.editSection);
        });
    });

    page.querySelectorAll('[data-edit-cancel]').forEach(button => {
        button.addEventListener('click', () => close(button.closest('[data-editor]')));
    });

    // --- Repeating rows (honors, links, photos) -----------------------------------------

    function rowFrom(kind, values) {
        const template = page.querySelector(`[data-row-template="${kind}"]`);
        const row = template.content.firstElementChild.cloneNode(true);
        row.querySelectorAll('[name]').forEach(input => {
            const value = values[input.name];
            if (input.type === 'checkbox') input.checked = Boolean(value);
            else if (value !== undefined && value !== null && value !== 0) input.value = value;
        });
        row.querySelectorAll('.pf-field').forEach(wireCounter);
        return row;
    }

    function syncMoves(list) {
        const rows = [...list.children];
        rows.forEach((row, i) => {
            const up = row.querySelector('[data-row-move="-1"]');
            const down = row.querySelector('[data-row-move="1"]');
            if (up) up.disabled = i === 0;
            if (down) down.disabled = i === rows.length - 1;
        });
    }

    function fillRows(form, kind, items) {
        const list = form.querySelector(`[data-rows="${kind}"]`);
        list.replaceChildren(...items.map(item => rowFrom(kind, item)));
        syncMoves(list);
        return list;
    }

    page.addEventListener('click', event => {
        const move = event.target.closest('[data-row-move]');
        if (move) {
            const row = move.closest('[data-row]');
            const list = row.parentElement;
            const step = Number(move.dataset.rowMove);
            const other = step < 0 ? row.previousElementSibling : row.nextElementSibling;
            if (other) {
                if (step < 0) list.insertBefore(row, other);
                else list.insertBefore(other, row);
                syncMoves(list);
                move.focus();
            }
            return;
        }
        const remove = event.target.closest('[data-row-remove]');
        if (remove) {
            // Nothing is sent until Save, and Cancel brings the row back.
            const row = remove.closest('[data-row]');
            const list = row.parentElement;
            const next = row.nextElementSibling || row.previousElementSibling;
            row.remove();
            syncMoves(list);
            (next?.querySelector('input') || list.closest('form').querySelector('[data-row-add]'))?.focus();
            return;
        }
        const add = event.target.closest('[data-row-add]');
        if (add) {
            const kind = add.dataset.rowAdd;
            const list = add.closest('form').querySelector(`[data-rows="${kind}"]`);
            const row = rowFrom(kind, {});
            list.append(row);
            syncMoves(list);
            icons();
            row.querySelector('input')?.focus();
        }
    });

    function collect(list) {
        return [...list.children].map(row => {
            const values = {};
            row.querySelectorAll('[name]').forEach(input => {
                values[input.name] = input.type === 'checkbox' ? input.checked : input.value;
            });
            return values;
        });
    }

    // --- About me (with skill chips) ----------------------------------------------------

    function chipBox(form) {
        const box = form.querySelector('[data-chips]');
        const list = box.querySelector('[data-chip-list]');
        const input = box.querySelector('[data-chip-input]');
        const most = Number(box.dataset.chipsMax) || 12;
        const values = () => [...list.children].map(chip => chip.dataset.value);

        function add(text) {
            const value = text.trim().replace(/\s+/g, ' ');
            if (!value || values().some(v => v.toLowerCase() === value.toLowerCase())) return;
            if (values().length >= most) {
                showError(form, `Up to ${most} skills.`);
                return;
            }
            const chip = document.createElement('li');
            chip.className = 'pf-chip';
            chip.dataset.value = value;
            chip.append(value);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.setAttribute('aria-label', `Remove ${value}`);
            remove.innerHTML = '<i data-lucide="x" aria-hidden="true"></i>';
            remove.addEventListener('click', () => { chip.remove(); input.focus(); });
            chip.append(remove);
            list.append(chip);
            icons();
        }

        if (!box.dataset.wired) {
            box.dataset.wired = '1';
            input.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ',') {
                    event.preventDefault();
                    add(input.value);
                    input.value = '';
                } else if (event.key === 'Backspace' && !input.value && list.lastElementChild) {
                    list.lastElementChild.remove();
                }
            });
            // Picking a suggestion from the list adds it straight away.
            input.addEventListener('change', () => {
                if (input.value) { add(input.value); input.value = ''; }
            });
        }
        return { set: items => { list.replaceChildren(); items.forEach(add); }, values, flush: () => { add(input.value); input.value = ''; } };
    }

    fillers.about = form => {
        form.elements.headline.value = profile.headline || '';
        form.elements.grad_year.value = profile.grad_year || '';
        form.elements.bio.value = profile.bio || '';
        form.querySelectorAll('input[name="visibility"]').forEach(radio => {
            radio.checked = radio.value === profile.visibility;
        });
        chipBox(form).set(profile.skills || []);
        form.querySelectorAll('.pf-field').forEach(field => field.querySelector('input, textarea')?.dispatchEvent(new Event('input')));
    };

    const collectors = {
        about: form => {
            const chips = chipBox(form);
            chips.flush();
            return {
                headline: form.elements.headline.value, grad_year: form.elements.grad_year.value,
                bio: form.elements.bio.value, skills: chips.values(),
                visibility: (form.querySelector('input[name="visibility"]:checked') || {}).value || 'members',
            };
        },
        honors: form => ({ honors: collect(form.querySelector('[data-rows="honors"]')) }),
        links: form => ({ links: collect(form.querySelector('[data-rows="links"]')).filter(l => l.url.trim()) }),
        photos: form => ({
            photos: [...form.querySelector('[data-rows="photos"]').children].map(row => ({
                path: row.dataset.path, caption: row.querySelector('[name="caption"]').value,
            })),
        }),
        activity: form => ({ position: form.elements.position.value, activity: form.elements.activity.value }),
    };

    fillers.honors = form => fillRows(form, 'honors', profile.honors.length ? profile.honors : [{}]);
    fillers.links = form => fillRows(form, 'links', profile.links.length ? profile.links : [{}]);

    // --- Photos ---------------------------------------------------------------------------

    const photosApi = page.dataset.photosApi;

    function photoRow(photo) {
        const row = rowFrom('photos', photo);
        row.dataset.path = photo.path;
        row.querySelector('[data-photo-thumb]').src = photo.src;
        return row;
    }

    fillers.photos = form => {
        const list = form.querySelector('[data-rows="photos"]');
        list.replaceChildren(...profile.photos.map(photoRow));
        syncMoves(list);
    };

    const photoForm = page.querySelector('[data-editor="photos"]');
    if (photoForm) {
        const input = photoForm.querySelector('[data-photo-input]');
        const drop = photoForm.querySelector('.pf-drop');
        const list = photoForm.querySelector('[data-rows="photos"]');
        let uploaded = false;

        input.addEventListener('change', async () => {
            const files = [...input.files];
            input.value = '';
            if (!files.length) return;
            drop.classList.add('is-busy');
            for (const file of files) {
                const body = new FormData();
                body.append('photo', file);
                try {
                    const resp = await fetch(photosApi, {
                        method: 'POST', credentials: 'same-origin', body,
                        headers: { 'X-CSRF-Token': csrfToken() },
                    });
                    const data = await resp.json().catch(() => ({}));
                    if (!resp.ok) throw new Error(data.error || `${file.name} did not upload.`);
                    profile.photos.push(data.photo);
                    list.append(photoRow(data.photo));
                    uploaded = true;
                } catch (err) {
                    showError(photoForm, err.message);
                    break;
                }
            }
            syncMoves(list);
            icons();
            drop.classList.remove('is-busy');
            if (uploaded) say('Photo added. Add captions, then save, or just close: it is already on your page.');
        });

        list.addEventListener('click', event => {
            const button = event.target.closest('[data-photo-delete]');
            if (!button) return;
            const row = button.closest('[data-row]');
            const run = () => fetch(photosApi, {
                method: 'DELETE', credentials: 'same-origin', headers: jsonHeaders(),
                body: JSON.stringify({ path: row.dataset.path }), keepalive: Boolean(window.Fuse && Fuse.leaving),
            }).then(resp => {
                if (!resp.ok) throw new Error('That photo could not be deleted.');
                profile.photos = profile.photos.filter(p => p.path !== row.dataset.path);
                row.remove();
                syncMoves(list);
                uploaded = true;
            }).catch(err => showError(photoForm, err.message));
            if (window.Fuse) Fuse.arm(button, { label: 'Deleting photo', detail: 'It leaves your page', run });
            else run();
        });

        // Uploads and deletes are saved already, so Cancel shows them by reloading.
        photoForm.querySelector('[data-edit-cancel]').addEventListener('click', () => {
            if (uploaded) reloadAt('photos', '');
        });
    }

    // --- Submitting -------------------------------------------------------------------------

    page.querySelectorAll('form[data-editor]').forEach(form => {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const section = form.dataset.editor;
            form.querySelector('[data-editor-error]')?.setAttribute('hidden', '');
            busy(form, true);
            try {
                await send(section, collectors[section](form));
                if (section === 'activity') {
                    busy(form, false);
                    say('Saved your Common App lines.');
                    return;
                }
                reloadAt(section, 'Saved. This is how your page looks now.');
            } catch (err) {
                busy(form, false);
                showError(form, err.message);
            }
        });
    });

    // --- College-app kit --------------------------------------------------------------------

    const kit = page.querySelector('[data-editor="activity"]');
    if (kit) {
        kit.querySelector('[data-copy-activity]').addEventListener('click', async event => {
            const text = `${kit.elements.position.value}\n${kit.elements.activity.value}`;
            flash(event.currentTarget, await copy(text) ? 'Copied' : 'Select and copy them');
        });
        kit.querySelector('[data-activity-draft]').addEventListener('click', () => {
            kit.elements.position.value = kit.dataset.draftPosition;
            kit.elements.activity.value = kit.dataset.draftActivity;
            kit.querySelectorAll('input, textarea').forEach(el => el.dispatchEvent(new Event('input')));
        });
    }

    // --- After a save: stay in edit mode, say so ---------------------------------------------

    try {
        const after = JSON.parse(sessionStorage.getItem(STORE_KEY) || 'null');
        sessionStorage.removeItem(STORE_KEY);
        if (after) {
            setEditing(true);
            if (after.message) say(after.message);
            document.getElementById(after.section)?.scrollIntoView({ block: 'start' });
        }
    } catch (err) { /* storage blocked: nothing to restore */ }
})();
