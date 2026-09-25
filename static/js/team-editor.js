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

    function saveField(input) {
        if (input.value === input.dataset.saved) return;
        const memberCard = input.closest('[data-member-id]');
        const request = memberCard
            ? post(`/member/${memberCard.dataset.memberId}`, { field: input.dataset.memberField, value: input.value })
            : post('/field', { field: input.dataset.autosave, value: input.value });
        track(input, request)
            .then(data => {
                // The server may tidy the value (upper-cases team numbers, trims spaces).
                if (typeof data.value === 'string') input.value = data.value;
                input.dataset.saved = input.value;
                if (input.dataset.memberField === 'name') {
                    const initials = memberCard.querySelector('.member-initials');
                    if (initials) initials.textContent = toInitials(input.value);
                }
            })
            .catch(() => { input.value = input.dataset.saved; });
    }

    function toInitials(name) {
        const parts = name.trim().split(/\s+/).filter(Boolean);
        if (!parts.length) return '?';
        return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
    }

    const FIELD = '[data-autosave], [data-member-field]';

    root.querySelectorAll(FIELD).forEach(input => { input.dataset.saved = input.value; });

    root.addEventListener('change', e => {
        if (e.target.matches(FIELD)) saveField(e.target);
    });

    root.addEventListener('keydown', e => {
        if (!e.target.matches(FIELD) || e.target.tagName === 'SELECT') return;
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

    // --- Uploads (click to browse or drop a file) -------------------------------------------------------

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
    root.addEventListener('dragover', e => {
        const zone = e.target.closest('[data-upload]');
        if (!zone) return;
        e.preventDefault();
        zone.classList.add('is-over');
    });
    root.addEventListener('dragleave', e => {
        const zone = e.target.closest('[data-upload]');
        if (zone && !zone.contains(e.relatedTarget)) zone.classList.remove('is-over');
    });
    root.addEventListener('drop', e => {
        const zone = e.target.closest('[data-upload]');
        if (!zone) return;
        e.preventDefault();
        zone.classList.remove('is-over');
        upload(zone, e.dataTransfer.files[0]);
    });

    // --- Roster: add and remove (editors and admins) -------------------------------------------------------

    const addForm = document.getElementById('addMemberForm');
    addForm?.addEventListener('submit', e => {
        e.preventDefault();
        const input = addForm.querySelector('input');
        const name = input.value.trim();
        if (!name) return;
        track(addForm, post('/member', { name })).then(data => {
            const card = document.getElementById('tpl-member').content.firstElementChild.cloneNode(true);
            card.dataset.memberId = data.member.member_id;
            card.querySelector('.member-initials').textContent = toInitials(name);
            const nameInput = card.querySelector('[data-member-field="name"]');
            nameInput.value = name;
            card.querySelector('[data-member-field="role"]').value = data.member.role;
            card.querySelectorAll(FIELD).forEach(field => { field.dataset.saved = field.value; });
            document.getElementById('rosterEmpty')?.remove();
            document.getElementById('memberGrid').append(card);
            refreshLucideIcons();
            input.value = '';
            card.querySelector('[data-member-field="role"]').focus();
        }).catch(() => {});
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

    // --- Leaving with saves in flight -------------------------------------------------------

    window.addEventListener('beforeunload', e => {
        if (inFlight > 0 || listTimers.size > 0) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    setStatus();
})();
