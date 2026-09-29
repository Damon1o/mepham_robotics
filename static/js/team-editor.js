// Team editor: every field saves itself.
//
// Text fields save when they lose focus (or on Enter), lists save shortly
// after the last keystroke, and files upload the moment they are picked or
// dropped. The server enforces who may change what; this file only mirrors it.

(function () {
    const root = document.getElementById('teamEditor');
    if (!root) return;

    const API = root.dataset.api;
    const status = document.getElementById('saveStatus');
    const listTimers = new Map();
    let inFlight = 0;
    let failed = false;

    // --- Status line -------------------------------------------------------------

    function setStatus() {
        if (inFlight > 0) {
            status.textContent = 'Saving…';
            status.dataset.state = 'saving';
        } else if (failed) {
            status.textContent = 'Some changes did not save';
            status.dataset.state = 'error';
        } else {
            status.textContent = 'All changes saved';
            status.dataset.state = 'saved';
        }
    }

    function mark(node, state) {
        node.classList.remove('is-saving', 'is-saved', 'is-error');
        if (state) node.classList.add(`is-${state}`);
    }

    // Wrap one save so the page-wide status line and the field's own tick agree.
    function track(node, promise) {
        inFlight++;
        failed = false;
        mark(node, 'saving');
        setStatus();
        return promise
            .then(data => {
                mark(node, 'saved');
                return data;
            })
            .catch(err => {
                failed = true;
                mark(node, 'error');
                showToast(err.message, 'error');
                throw err;
            })
            .finally(() => {
                inFlight--;
                setStatus();
            });
    }

    async function send(url, options) {
        let response;
        try {
            response = await fetch(url, Object.assign({ credentials: 'same-origin' }, options));
        } catch (err) {
            throw new Error('Could not reach the server. Check your connection.');
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `Save failed (${response.status}).`);
        return data;
    }

    function post(path, body, method = 'POST') {
        return send(API + path, { method, headers: jsonHeaders(), body: JSON.stringify(body) });
    }

    // --- Single fields -------------------------------------------------------------

    // A radio group (segmented control) saves as one field; its saved value lives on the group.
    // A checkbox (switch) saves true/false.
    const currentValue = input => (input.type === 'checkbox' ? String(input.checked) : input.value);

    function savedValue(input) {
        return input.type === 'radio' ? input.closest('[role="radiogroup"]').dataset.saved : input.dataset.saved;
    }

    function setSaved(input) {
        if (input.type === 'radio') input.closest('[role="radiogroup"]').dataset.saved = input.value;
        else input.dataset.saved = currentValue(input);
    }

    function revert(input) {
        if (input.type === 'checkbox') {
            input.checked = input.dataset.saved === 'true';
            return;
        }
        if (input.type !== 'radio') {
            input.value = input.dataset.saved;
            return;
        }
        const group = input.closest('[role="radiogroup"]');
        group.querySelectorAll('input').forEach(radio => { radio.checked = radio.value === group.dataset.saved; });
    }

    function saveField(input) {
        if (currentValue(input) === savedValue(input)) return;
        const memberCard = input.closest('[data-member-id]');
        const value = input.type === 'checkbox' ? input.checked : input.value;
        const request = memberCard
            ? post(`/member/${memberCard.dataset.memberId}`, { field: input.dataset.memberField, value })
            : post('/field', { field: input.dataset.autosave, value });
        const target = input.type === 'radio' ? input.closest('[role="radiogroup"]') : input;
        track(target, request)
            .then(data => {
                // The server may tidy the value (upper-cases team numbers, trims spaces).
                if (typeof data.value === 'string' && input.type !== 'radio') input.value = data.value;
                setSaved(input);
                if (input.dataset.memberField === 'name') {
                    const initials = memberCard.querySelector('.member-initials');
                    if (initials) initials.textContent = toInitials(input.value);
                    if (memberCard.hasAttribute('data-drop')) memberCard.dataset.dropLabel = photoLabel(input.value);
                }
            })
            .catch(() => revert(input));
    }

    // Shown over a roster row while a photo is dragged onto it.
    const photoLabel = name => (name.trim() ? `Set as ${name.trim()}’s photo` : 'Set as their photo');

    function toInitials(name) {
        const parts = name.trim().split(/\s+/).filter(Boolean);
        if (!parts.length) return '?';
        return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
    }

    const FIELD = '[data-autosave], [data-member-field]';

    root.querySelectorAll(FIELD).forEach(input => {
        if (input.type !== 'radio') input.dataset.saved = currentValue(input);
        else if (input.checked) setSaved(input);
    });

    root.addEventListener('change', e => {
        if (e.target.matches(FIELD)) saveField(e.target);
    });

    root.addEventListener('keydown', e => {
        if (!e.target.matches(FIELD) || e.target.tagName === 'SELECT' || e.target.type === 'radio') return;
        if (e.key === 'Enter') {
            e.preventDefault();
            e.target.blur();
        } else if (e.key === 'Escape') {
            e.target.value = e.target.dataset.saved;
            e.target.blur();
        }
    });

    // --- Lists (goals, journey) -------------------------------------------------------------

    function collect(list) {
        return Array.from(list.querySelectorAll('.row-item')).map(row => {
            const item = {};
            row.querySelectorAll('[data-key]').forEach(input => {
                item[input.dataset.key] = input.type === 'range' ? Number(input.value) : input.value;
            });
            return item;
        });
    }

    function saveList(list) {
        clearTimeout(listTimers.get(list));
        listTimers.delete(list);
        track(list, post(`/list/${list.dataset.list}`, { items: collect(list) })).catch(() => {});
    }

    function scheduleList(list, delay = 800) {
        clearTimeout(listTimers.get(list));
        listTimers.set(list, setTimeout(() => saveList(list), delay));
    }

    root.addEventListener('input', e => {
        const list = e.target.closest('[data-list]');
        if (!list) return;
        if (e.target.type === 'range') {
            e.target.nextElementSibling.textContent = `${e.target.value}%`;
        }
        scheduleList(list);
    });

    root.addEventListener('click', e => {
        const add = e.target.closest('[data-action="add-row"]');
        if (add) {
            const kind = add.dataset.listTarget;
            const list = root.querySelector(`[data-list="${kind}"]`);
            const row = document.getElementById(`tpl-${kind}`).content.firstElementChild.cloneNode(true);
            list.append(row);
            refreshLucideIcons();
            row.querySelector('input[type="text"]').focus();
            return;
        }
        const remove = e.target.closest('[data-action="remove-row"]');
        if (remove) {
            const list = remove.closest('[data-list]');
            remove.closest('.row-item').remove();
            saveList(list);
        }
    });

    // --- Uploads (click to browse, drop or paste a file) ---------------------------------------------------
    // controls.js does the dropping and pasting and hands the file to the zone's input, so
    // every upload arrives here as a change event.

    function upload(zone, file) {
        if (!file) return;
        const form = new FormData();
        form.append(zone.dataset.upload, file);
        const card = zone.closest('[data-member-id]');
        if (card) form.append('member_id', card.dataset.memberId);

        const preview = zone.querySelector('.drop-zone-preview');
        const filename = zone.querySelector('.drop-zone-filename');
        if (preview && file.type.startsWith('image/')) {
            preview.src = URL.createObjectURL(file);
            preview.hidden = false;
            zone.querySelector('.member-initials')?.remove();
        }
        if (filename) filename.textContent = `Uploading ${file.name}…`;

        track(zone, send(`${API}/image`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken() }, body: form }))
            .then(data => {
                if (preview && file.type.startsWith('image/')) preview.src = data.url;
                if (filename) filename.textContent = file.name;
                removeButtonFor(zone)?.removeAttribute('hidden');
            })
            .catch(() => {
                if (filename) filename.textContent = 'Upload failed. Try again.';
            });
    }

    // Delegated, so cards added later work too.
    root.addEventListener('change', e => {
        const zone = e.target.type === 'file' && e.target.closest('[data-upload]');
        if (zone) upload(zone, e.target.files[0]);
    });

    // --- Removing an image, the CAD model, or a member's photo ------------------------------------------

    function removeButtonFor(zone) {
        const kind = zone.dataset.upload;
        const scope = zone.closest('[data-member-id]') || zone.closest('.image-field') || root;
        return scope.querySelector(`[data-action="remove-image"][data-kind="${kind}"]`);
    }

    root.addEventListener('click', e => {
        const button = e.target.closest('[data-action="remove-image"]');
        if (!button) return;
        const card = button.closest('[data-member-id]');
        const kind = button.dataset.kind;
        const zone = (card || button.closest('.image-field')).querySelector(`[data-upload="${kind}"]`);
        const body = { kind };
        if (card) body.member_id = card.dataset.memberId;
        track(zone, post('/image', body, 'DELETE')).then(() => {
            button.hidden = true;
            const preview = zone.querySelector('.drop-zone-preview');
            if (preview) {
                preview.hidden = true;
                preview.removeAttribute('src');
            }
            const filename = zone.querySelector('.drop-zone-filename');
            if (filename) filename.textContent = 'Drop an .stl or browse';
            if (card && !zone.querySelector('.member-initials')) {
                const name = card.querySelector('[data-member-field="name"]')?.value || '';
                zone.prepend(Object.assign(document.createElement('span'), {
                    className: 'member-initials', textContent: toInitials(name),
                }));
            }
            showToast('Removed.', 'success');
        }).catch(() => {});
    });

    // --- Roster: add and remove (editors and admins) -------------------------------------------------------

    const addForm = document.getElementById('addMemberForm');
    const grid = document.getElementById('memberGrid');

    // Add one person; resolves with their new roster row.
    function addMember(name, holder) {
        return track(holder, post('/member', { name })).then(data => {
            const card = document.getElementById('tpl-member').content.firstElementChild.cloneNode(true);
            card.dataset.memberId = data.member.member_id;
            card.dataset.dropLabel = photoLabel(name);
            card.querySelector('.member-initials').textContent = toInitials(name);
            card.querySelector('[data-member-field="name"]').value = name;
            card.querySelector('[data-member-field="role"]').value = data.member.role;
            card.querySelectorAll(FIELD).forEach(field => { field.dataset.saved = field.value; });
            document.getElementById('rosterEmpty')?.remove();
            grid.append(card);
            refreshLucideIcons();
            return card;
        });
    }

    addForm?.addEventListener('submit', e => {
        e.preventDefault();
        const input = addForm.querySelector('input');
        const name = input.value.trim();
        if (!name) return;
        addMember(name, addForm).then(card => {
            input.value = '';
            card.querySelector('[data-member-field="role"]').focus();
        }).catch(() => {});
    });

    // --- Dropping files on the roster as a whole (editors and admins) ---------------------------------------
    // Headshots go to the people they are named after ("alice-smith.jpg", "Alice.png"), and a
    // .csv or .txt of names adds everyone on it after a quick check. One photo dropped on a
    // row goes to that row's own photo input instead.

    const tidy = text => text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ').trim();
    const nameOf = card => (card.querySelector('[data-member-field="name"]')?.value
        || card.querySelector('.member-name')?.textContent || '');
    const isNameList = file => /\.(csv|txt)$/i.test(file.name) || /^text\//.test(file.type);

    // The one person a file name points at: every part of their name in it beats some of it.
    // Null when no one fits, or when two people fit equally well.
    function personFor(file, people) {
        const words = tidy(file.name.replace(/\.[^.]+$/, '')).split(' ').filter(word => word.length > 1);
        const joined = words.join('');
        let best = null;
        let bestScore = 0;
        let tied = false;
        people.forEach(person => {
            const parts = person.name.split(' ').filter(Boolean);
            let score = parts.filter(part => words.includes(part)).length;
            // "alicesmith.jpg" names Alice Smith too; a one-word name has to be a whole word.
            const whole = parts.length > 1 && joined.includes(parts.join(''));
            if (parts.length && (score === parts.length || whole)) score = 100 + parts.length;
            if (score > bestScore) {
                best = person;
                bestScore = score;
                tied = false;
            } else if (score && score === bestScore) {
                tied = true;
            }
        });
        return tied ? null : best;
    }

    function matchPhotos(photos) {
        const people = Array.from(grid.querySelectorAll('.member-card'))
            .filter(card => card.querySelector('[data-upload="member_photo"]'))
            .map(card => ({ card, name: tidy(nameOf(card)) }))
            .filter(person => person.name);
        const used = new Set();
        const missed = [];
        photos.forEach(file => {
            const person = personFor(file, people);
            if (!person || used.has(person.card)) {
                missed.push(file.name);
                return;
            }
            used.add(person.card);
            upload(person.card.querySelector('[data-upload="member_photo"]'), file);
        });
        // One toast shows at a time, so say it all in one.
        const matched = used.size === 1 ? 'Matched 1 photo to a name. '
            : used.size ? `Matched ${used.size} photos to names. ` : '';
        if (!missed.length) showToast(matched.trim(), 'success');
        else showToast(`${matched}No one on the roster matches ${missed.join(', ')}. Name photos after people, `
            + 'or drop one straight onto a row.', 'error');
    }

    // One name per line; for a spreadsheet export, the "Name" column (or First + Last).
    function cellsOf(line) {
        const cells = [];
        let cell = '';
        let quoted = false;
        for (let i = 0; i < line.length; i++) {
            const ch = line[i];
            if (quoted && ch === '"' && line[i + 1] === '"') {
                cell += '"';
                i++;
            } else if (ch === '"') {
                quoted = !quoted;
            } else if (!quoted && (ch === ',' || ch === '\t' || ch === ';')) {
                cells.push(cell.trim());
                cell = '';
            } else {
                cell += ch;
            }
        }
        cells.push(cell.trim());
        return cells;
    }

    // A spreadsheet cell of "Reyes, Sam" is Sam Reyes.
    function firstLast(name) {
        const parts = name.split(',').map(part => part.trim());
        return parts.length === 2 && parts[0] && parts[1] ? `${parts[1]} ${parts[0]}` : name;
    }

    function namesIn(text, spreadsheet) {
        const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
        // A plain list can put several names on a line: "Dana Kim, Evan Lopez".
        if (!spreadsheet) return lines.flatMap(line => line.split(/[,;\t]/));
        const head = cellsOf(lines[0] || '').map(cell => cell.toLowerCase());
        const nameCol = head.findIndex(cell => /^(full )?name$|^student( name)?$|^member( name)?$/.test(cell));
        const first = head.findIndex(cell => /^first( ?name)?$/.test(cell));
        const last = head.findIndex(cell => /^(last|sur)( ?name)?$/.test(cell));
        const byParts = nameCol < 0 && first >= 0 && last >= 0;
        const rows = nameCol >= 0 || byParts ? lines.slice(1) : lines;
        return rows.map(line => {
            const cells = cellsOf(line);
            return byParts ? `${cells[first] || ''} ${cells[last] || ''}` : firstLast(cells[Math.max(nameCol, 0)] || '');
        });
    }

    const MAX_IMPORT = 60;

    async function importNames(file) {
        const text = await file.text();
        const taken = new Set(Array.from(grid.querySelectorAll('.member-card')).map(card => tidy(nameOf(card))));
        const seen = new Set();
        let already = 0;
        const names = namesIn(text, /\.csv$/i.test(file.name) || file.type === 'text/csv')
            .map(name => name.replace(/\s+/g, ' ').trim().slice(0, 100))
            .filter(name => {
                const key = tidy(name);
                if (!key || seen.has(key)) return false;
                seen.add(key);
                if (taken.has(key)) {
                    already++;
                    return false;
                }
                return true;
            });
        if (!names.length) {
            showToast(already ? `Everyone in ${file.name} is already on the roster.` : `No names found in ${file.name}.`, 'info');
            return;
        }
        showImport(file.name, names.slice(0, MAX_IMPORT), already, names.length - MAX_IMPORT);
    }

    // A check before adding anyone: the names, with Add and Cancel, just above the add form.
    function showImport(fileName, names, already, over) {
        document.getElementById('rosterImport')?.remove();
        const make = (tag, className, text) => Object.assign(document.createElement(tag), { className, textContent: text || '' });
        const box = make('div', 'roster-import');
        box.id = 'rosterImport';
        box.setAttribute('role', 'group');
        box.setAttribute('aria-label', `Names from ${fileName}`);
        const title = make('p', 'roster-import-title');
        title.append(make('strong', '', `Add ${names.length} ${names.length === 1 ? 'person' : 'people'} from ${fileName}?`));
        const notes = [];
        if (already) notes.push(`${already} already on the roster`);
        if (over > 0) notes.push(`${over} more left out (${MAX_IMPORT} at a time)`);
        if (notes.length) title.append(` ${notes.join('; ')}.`);
        const list = make('ul', 'roster-import-names');
        names.forEach(name => list.append(make('li', '', name)));
        const actions = make('div', 'roster-import-actions');
        const add = make('button', 'admin-btn admin-btn-small', names.length === 1 ? 'Add' : `Add all ${names.length}`);
        const cancel = make('button', 'admin-btn admin-btn-secondary admin-btn-small', 'Cancel');
        add.type = 'button';
        cancel.type = 'button';
        actions.append(add, cancel);
        box.append(title, list, actions);
        addForm.before(box);
        box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        add.focus({ preventScroll: true });

        cancel.addEventListener('click', () => box.remove());
        add.addEventListener('click', async () => {
            add.disabled = true;
            cancel.disabled = true;
            let added = 0;
            for (const name of names) {
                add.textContent = `Adding ${added + 1} of ${names.length}…`;
                try {
                    await addMember(name, box);
                    added++;
                } catch (err) {
                    break;
                }
            }
            box.remove();
            if (added) showToast(`Added ${added} ${added === 1 ? 'person' : 'people'} to the roster.`, 'success');
        });
    }

    grid?.addEventListener('ctl:files', e => {
        if (e.target !== grid) return;
        e.preventDefault();
        const files = e.detail.files;
        const list = files.find(isNameList);
        if (list) importNames(list).catch(() => showToast(`Could not read ${list.name}.`, 'error'));
        const photos = files.filter(file => !isNameList(file));
        if (photos.length) matchPhotos(photos);
    });

    // Removing asks twice in place ("Remove?") instead of a modal.
    root.addEventListener('click', e => {
        const button = e.target.closest('[data-action="remove-member"]');
        if (!button) return;
        const card = button.closest('[data-member-id]');
        if (!button.classList.contains('is-confirming')) {
            button.classList.add('is-confirming');
            button.dataset.label = button.getAttribute('aria-label');
            button.setAttribute('aria-label', 'Click again to remove');
            button.title = 'Click again to remove';
            setTimeout(() => {
                button.classList.remove('is-confirming');
                button.setAttribute('aria-label', button.dataset.label);
                button.removeAttribute('title');
            }, 3000);
            return;
        }
        track(card, post(`/member/${card.dataset.memberId}`, {}, 'DELETE'))
            .then(() => card.remove())
            .catch(() => {});
    });

    // --- "Other roles" suggestions -------------------------------------------------------
    // A datalist only matches the whole value, so for a comma list we rebuild it with what
    // is already typed as the prefix: "Driver, " suggests "Driver, Captain", "Driver, Scout"...

    const extraRoles = document.getElementById('dl-extra-roles');
    const ROLE_CHOICES = extraRoles ? extraRoles.dataset.roles.split('|') : [];

    function suggestRoles(input) {
        const typed = input.value.split(',').map(s => s.trim());
        const done = typed.slice(0, -1).filter(Boolean);
        const prefix = done.length ? `${done.join(', ')}, ` : '';
        const taken = new Set(done.map(s => s.toLowerCase()));
        taken.add((input.closest('[data-member-id]')?.querySelector('[data-member-field="role"]')?.value || '').toLowerCase());
        extraRoles.replaceChildren(...ROLE_CHOICES
            .filter(role => !taken.has(role.toLowerCase()))
            .map(role => Object.assign(document.createElement('option'), { value: prefix + role })));
    }

    root.addEventListener('focusin', e => {
        if (extraRoles && e.target.matches('[data-suggest-roles]')) suggestRoles(e.target);
    });
    root.addEventListener('input', e => {
        if (extraRoles && e.target.matches('[data-suggest-roles]') && /,\s*$|^$/.test(e.target.value)) suggestRoles(e.target);
    });

    // --- Roster count and section nav -------------------------------------------------------

    function updateRosterCount() {
        const count = root.querySelector('#h-roster .section-count');
        if (count) count.textContent = root.querySelectorAll('#memberGrid .member-card').length;
    }
    new MutationObserver(updateRosterCount).observe(document.getElementById('memberGrid'), { childList: true });

    const navLinks = Array.from(root.querySelectorAll('.settings-nav a'));
    if ('IntersectionObserver' in window && navLinks.length) {
        const observer = new IntersectionObserver(entries => {
            entries.filter(entry => entry.isIntersecting).forEach(entry => {
                navLinks.forEach(link => {
                    const current = link.getAttribute('href') === `#${entry.target.id}`;
                    link.classList.toggle('is-current', current);
                    if (current) link.setAttribute('aria-current', 'true');
                    else link.removeAttribute('aria-current');
                });
            });
        }, { rootMargin: '-20% 0px -70% 0px' });
        root.querySelectorAll('.settings-section').forEach(section => observer.observe(section));
    }

    // --- Leaving with saves in flight -------------------------------------------------------

    window.addEventListener('beforeunload', e => {
        if (inFlight > 0 || listTimers.size > 0) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    setStatus();
})();
