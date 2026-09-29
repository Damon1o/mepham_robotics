// Admin dashboard behaviour.
//
// Every control is wired through delegated listeners (data-action,
// data-confirm-delete, data-preview-target, ...). There are no inline on*=
// handlers anywhere, so /admin runs under the same no-inline-script
// Content-Security-Policy as the rest of the site.
//
// Sections, in order: DOM helpers, notifications, dialog, JSON calls, tabs and
// search, forms (sponsor/account editors), autosave (numbers, awards, events),
// homepage number modes, awards, events, teams, dropped files (team banners,
// sponsor logos), people (approvals, roles, roster), messages and newsletter,
// activity, help, and the delegated wiring.

// --- DOM helpers --------------------------------------------------------------

// Build an element from a tag, a map of attributes/properties, and children.
// Values are always assigned as properties or attributes, never parsed as
// HTML, so stored team/member names cannot inject markup.
function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([key, value]) => {
        if (value === undefined || value === null || value === false) return;
        if (key === 'className') node.className = value;
        else if (key === 'text') node.textContent = value;
        else if (key === 'value') node.value = value;
        else if (key === 'dataset') Object.assign(node.dataset, value);
        else if (value === true) node.setAttribute(key, '');
        else node.setAttribute(key, value);
    });
    [].concat(children).forEach(child => {
        if (child) node.append(child);
    });
    return node;
}

function plural(n, word) {
    return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function scrollToId(id) {
    const target = document.getElementById(id);
    if (!target) return;
    if (target.tagName === 'DETAILS') target.open = true;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const focusable = target.matches('input, select, textarea, button, a[href]') ? target
        : target.querySelector('input:not([type="hidden"]), select, textarea, summary');
    focusable?.focus({ preventScroll: true });
}

// --- Notifications ----------------------------------------------------------------

const Admin = {
    // `action` ({label, run}) adds a button to the toast, e.g. Undo after a roster move.
    notify(message, category = 'info', action = null) {
        const stack = document.getElementById('toast-stack');
        if (!stack) return;

        const toast = el('div', { className: `status-msg ${category}` }, [el('span', { text: message })]);
        const dismiss = () => {
            toast.classList.add('is-leaving');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        };
        if (action) {
            const button = el('button', { type: 'button', className: 'toast-action', text: action.label });
            button.addEventListener('click', () => {
                dismiss();
                action.run();
            }, { once: true });
            toast.append(button);
        }
        toast.append(el('button', { type: 'button', className: 'toast-close', 'aria-label': 'Dismiss', text: '×' }));
        toast.lastChild.addEventListener('click', dismiss, { once: true });
        stack.append(toast);
        setTimeout(dismiss, action ? 9000 : category === 'error' ? 8000 : 5000);
    },

    // Hide list items whose text does not contain the typed term.
    attachListFilter(inputSelector, itemSelector) {
        const input = document.querySelector(inputSelector);
        if (!input) return;
        input.addEventListener('input', () => {
            const term = input.value.trim().toLowerCase();
            document.querySelectorAll(itemSelector).forEach(item => {
                item.classList.toggle('is-hidden', term !== '' && !item.textContent.toLowerCase().includes(term));
            });
        });
    },
};

// --- Dialog ---------------------------------------------------------------------------
//
// One accessible dialog shell for confirmations, alerts, and small forms.
// `message` is plain text. `html` is for the static help copy only; nothing
// user-supplied may be passed through it. `body` is a DOM node (a form field).

const Dialog = (function () {
    let dialogEl, titleEl, messageEl, confirmBtn, cancelBtn, lastFocused, resolvePromise, readValue;

    function els() {
        if (dialogEl) return;
        dialogEl = document.getElementById('admin-confirm-dialog');
        titleEl = dialogEl.querySelector('.confirmation-title');
        messageEl = dialogEl.querySelector('.confirmation-message');
        confirmBtn = dialogEl.querySelector('.confirmation-confirm');
        cancelBtn = dialogEl.querySelector('.confirmation-cancel');

        confirmBtn.addEventListener('click', () => close(true));
        cancelBtn.addEventListener('click', () => close(false));
        dialogEl.addEventListener('click', e => {
            if (e.target === dialogEl) close(false);
        });
        dialogEl.addEventListener('keydown', onKeydown);
    }

    function onKeydown(e) {
        if (dialogEl.hidden) return;
        if (e.key === 'Escape') {
            close(false);
            return;
        }
        if (e.key === 'Enter' && e.target.matches('input, select')) {
            e.preventDefault();
            close(true);
            return;
        }
        if (e.key !== 'Tab') return;
        // Skip hidden controls (the cancel button in alert mode), or the trap
        // lands on an element that cannot take focus and lets Tab escape.
        const focusable = Array.from(dialogEl.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'))
            .filter(node => !node.hidden && !node.disabled);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }

    function close(result) {
        dialogEl.hidden = true;
        document.body.classList.remove('has-dialog');
        const value = result && readValue ? readValue() : result;
        if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
        if (resolvePromise) {
            const resolve = resolvePromise;
            resolvePromise = null;
            resolve(value);
        }
    }

    function open({ title, message, html, body, confirmLabel, cancelLabel, showCancel, tone = 'danger', value }) {
        els();
        // A second request while one is open cancels the first, so its caller
        // is never left waiting on a promise that no dialog will resolve.
        if (resolvePromise) {
            const previous = resolvePromise;
            resolvePromise = null;
            previous(false);
        } else {
            lastFocused = document.activeElement;
        }
        readValue = value || null;
        titleEl.textContent = title || '';
        if (html) messageEl.innerHTML = html;
        else messageEl.textContent = message || '';
        if (body) messageEl.append(body);
        confirmBtn.textContent = confirmLabel;
        confirmBtn.className = `admin-btn confirmation-confirm admin-btn-${tone}`;
        cancelBtn.textContent = cancelLabel || 'Cancel';
        cancelBtn.hidden = !showCancel;
        dialogEl.hidden = false;
        document.body.classList.add('has-dialog');
        (body?.querySelector('input, select') || confirmBtn).focus();
        return new Promise(resolve => {
            resolvePromise = resolve;
        });
    }

    return {
        confirm: ({ title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', tone = 'danger' } = {}) =>
            open({ title, message, confirmLabel, cancelLabel, showCancel: true, tone }),
        alert: ({ title, message, html, confirmLabel = 'OK' } = {}) =>
            open({ title, message, html, confirmLabel, showCancel: false, tone: 'success' }),
        // Resolves with the field's value, or false when cancelled.
        form: ({ title, message, field, confirmLabel = 'Save' }) =>
            open({ title, message, body: field, confirmLabel, showCancel: true, tone: 'success',
                value: () => field.querySelector('input, select').value }),
    };
})();

// --- JSON calls ----------------------------------------------------------------------

// Call the admin API. Resolves with the parsed body, rejects with an Error
// whose message is the server's user-facing text.
async function api(url, body = {}, method = 'POST') {
    let response;
    try {
        response = await fetch(url, {
            method,
            headers: jsonHeaders(),
            credentials: 'same-origin',
            body: method === 'GET' ? undefined : JSON.stringify(body),
        });
    } catch (err) {
        throw new Error('Could not reach the server. Check your connection.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Save failed (${response.status}).`);
    return data;
}

// Send a form upload ({field: file or text}). Same promise shape as api().
async function uploadFile(url, fields) {
    const body = new FormData();
    Object.entries(fields).forEach(([name, value]) => body.append(name, value));
    let response;
    try {
        response = await fetch(url, {
            method: 'POST', headers: { 'X-CSRF-Token': csrfToken() }, credentials: 'same-origin', body,
        });
    } catch (err) {
        throw new Error('Could not reach the server. Check your connection.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Upload failed (${response.status}).`);
    return data;
}

// --- Loading overlay and submit locking ----------------------------------------------

function showLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.hidden = false;
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.hidden = true;
}

function lockSubmit(form) {
    form.querySelectorAll('[type="submit"]').forEach(button => {
        button.disabled = true;
    });
}

const DELETE_WARNINGS = {
    team: 'This removes this season\'s team page, its roster and photos. Award counts are kept if another season still uses the number.',
    season: 'This removes that season\'s team page and roster.',
    group: 'This removes this season\'s group page and roster. Members keep their robot teams and other groups.',
    account: 'They will no longer be able to sign in. Their roster card stays, without a login.',
    event: 'The event disappears from the homepage.',
    sponsor: 'The sponsor and its logo disappear from the Donate page.',
};

function confirmDelete(form, type) {
    const name = form.dataset.confirmName;
    Dialog.confirm({
        title: name ? `Delete ${name}?` : `Delete this ${type}?`,
        message: `${DELETE_WARNINGS[type] || ''} This cannot be undone.`.trim(),
        confirmLabel: 'Delete',
    }).then(confirmed => {
        if (!confirmed) return;
        lockSubmit(form);
        showLoading();
        form.submit();
    });
}

// --- Tabs and search -------------------------------------------------------------------

// Search only the tab the admin is looking at: rows inside its lists are
// filtered, and whole cards drop out when nothing in them matches.
function searchAdminContent() {
    const term = document.getElementById('adminSearch').value.trim().toLowerCase();
    const panel = document.querySelector('.admin-panel:not([hidden])');
    if (!panel) return;
    let shown = 0;
    panel.querySelectorAll('.admin-card, .site-tile').forEach(card => {
        const rows = card.querySelectorAll('.data-item, .roster-card, .attention-item, .activity-item, .subscriber-item');
        let match;
        if (rows.length) {
            let rowsShown = 0;
            rows.forEach(row => {
                const hit = !term || row.textContent.toLowerCase().includes(term);
                row.classList.toggle('is-search-hidden', !hit);
                if (hit) rowsShown++;
            });
            const head = card.querySelector('.admin-card-header')?.textContent.toLowerCase() || '';
            match = !term || rowsShown > 0 || head.includes(term);
        } else {
            match = !term || card.textContent.toLowerCase().includes(term);
        }
        card.classList.toggle('is-search-hidden', !match);
        if (match) shown++;
    });
    let emptyNote = panel.querySelector('.admin-search-empty');
    if (!shown && term) {
        if (!emptyNote) {
            emptyNote = el('p', { className: 'admin-search-empty', role: 'status' });
            panel.append(emptyNote);
        }
        emptyNote.textContent = `Nothing on this tab matches "${term}".`;
    } else if (emptyNote) {
        emptyNote.remove();
    }
}

const AdminTabs = (function () {
    const DEFAULT_TAB = 'overview';

    const tabs = () => Array.from(document.querySelectorAll('.admin-tabs [role="tab"]'));
    const panels = () => Array.from(document.querySelectorAll('.admin-panel'));

    function currentTab() {
        const hash = location.hash.replace('#', '');
        return tabs().some(t => t.dataset.tab === hash) ? hash : DEFAULT_TAB;
    }

    function show(name) {
        tabs().forEach(tab => {
            const active = tab.dataset.tab === name;
            tab.setAttribute('aria-selected', active ? 'true' : 'false');
            tab.tabIndex = active ? 0 : -1;
            if (active) tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        });
        panels().forEach(panel => {
            panel.hidden = panel.dataset.panel !== name;
        });
        const search = document.getElementById('adminSearch');
        if (search) {
            const label = tabs().find(t => t.dataset.tab === name)?.querySelector('span')?.textContent || 'this tab';
            search.placeholder = `Search ${label}…  ( / )`;
            if (search.value) searchAdminContent();
        }
    }

    function go(name, scrollTarget) {
        if (location.hash === '#' + name) show(name);
        else location.hash = name;
        if (scrollTarget) requestAnimationFrame(() => scrollToId(scrollTarget));
    }

    function onKeydown(e) {
        const tabEls = tabs();
        const i = tabEls.indexOf(document.activeElement);
        if (i === -1) return;
        let next = null;
        if (e.key === 'ArrowRight') next = tabEls[(i + 1) % tabEls.length];
        else if (e.key === 'ArrowLeft') next = tabEls[(i - 1 + tabEls.length) % tabEls.length];
        else if (e.key === 'Home') next = tabEls[0];
        else if (e.key === 'End') next = tabEls[tabEls.length - 1];
        if (next) {
            e.preventDefault();
            next.focus();
            go(next.dataset.tab);
        }
    }

    function init() {
        tabs().forEach(tab => {
            tab.addEventListener('click', e => {
                e.preventDefault();
                go(tab.dataset.tab);
            });
        });
        document.querySelector('.admin-tabs')?.addEventListener('keydown', onKeydown);
        window.addEventListener('hashchange', () => show(currentTab()));
        show(currentTab());
    }

    return { init, go };
})();

// --- Forms: unsaved changes, sponsors, accounts ------------------------------------------

const DIRTY_FORMS = ['event_form', 'team_form', 'sponsor_form', 'userForm'];

function markClean(form) {
    if (form) delete form.dataset.dirty;
}

function isDirty(form) {
    return Boolean(form && form.dataset.dirty);
}

// Resolve true when it is safe to throw away the form's contents.
function confirmDiscard(form) {
    if (!isDirty(form)) return Promise.resolve(true);
    return Dialog.confirm({
        title: 'Discard unsaved changes?',
        message: 'This form has changes that have not been saved. They will be lost.',
        confirmLabel: 'Discard',
    });
}

function resetSimpleForm(id) {
    return () => {
        const form = document.getElementById(id);
        form.reset();
        markClean(form);
        form.querySelector('input:not([type="hidden"])')?.focus();
    };
}

function setSponsorFormMode(editing, name = '') {
    document.querySelector('#sponsor_form_title [data-form-title]').textContent = editing ? `Edit ${name}` : 'Add a sponsor';
    document.querySelector('#sponsor_form [data-submit-label]').textContent = editing ? 'Save changes' : 'Add sponsor';
}

function editSponsor(button) {
    const form = document.getElementById('sponsor_form');
    form.reset();
    document.getElementById('sponsorLogoPreview')?.replaceChildren();
    document.getElementById('sponsor_id').value = button.dataset.id;
    form.querySelector('[name="name"]').value = button.dataset.name;
    form.querySelector('[name="website"]').value = button.dataset.website;
    // Level is a segmented control (radios); fall back to the first tier for unknown values.
    const levels = Array.from(form.querySelectorAll('[name="level"]'));
    (levels.find(radio => radio.value === button.dataset.level) || levels[0]).checked = true;
    document.getElementById('removeLogoWrap').hidden = button.dataset.hasLogo !== 'true';
    setSponsorFormMode(true, button.dataset.name);
    markClean(form);
    scrollToId('sponsor_form_card');
    form.querySelector('[name="name"]').focus({ preventScroll: true });
}

function resetSponsorForm() {
    const form = document.getElementById('sponsor_form');
    form.reset();
    document.getElementById('sponsor_id').value = '';
    document.getElementById('sponsorLogoPreview')?.replaceChildren();
    document.getElementById('removeLogoWrap').hidden = true;
    setSponsorFormMode(false);
    markClean(form);
}

function editUser(button) {
    const user = button.dataset;
    const form = document.getElementById('userForm');
    document.getElementById('user_form_title').textContent = 'Edit account: ' + user.username;
    document.getElementById('userFormDetails').open = true;
    form.action = user.updateUrl;
    form.dataset.mode = 'edit';
    form.reset();
    document.getElementById('full_name').value = user.fullName || '';
    document.getElementById('username').value = user.username;
    document.getElementById('email').value = user.email || '';
    document.getElementById('role').value = user.role || 'member';
    const password = document.getElementById('password');
    password.required = false;
    password.placeholder = 'Leave blank to keep the current password';
    document.getElementById('password_hint').textContent = 'Only fill this in to set a new password (8+ characters).';
    document.getElementById('user_submit').textContent = 'Save changes';
    markClean(form);
    scrollToId('userFormDetails');
    document.getElementById('full_name').focus({ preventScroll: true });
}

function resetUserForm() {
    const form = document.getElementById('userForm');
    document.getElementById('user_form_title').textContent = 'Add someone manually';
    form.action = form.dataset.defaultAction;
    delete form.dataset.mode;
    form.reset();
    const password = document.getElementById('password');
    password.required = true;
    password.placeholder = 'At least 8 characters';
    document.getElementById('password_hint').textContent = 'Minimum 8 characters';
    document.getElementById('user_submit').textContent = 'Create account';
    markClean(form);
}

function copyResetLink() {
    const input = document.getElementById('reset_link_output');
    if (!input) return;
    input.select();
    const finish = ok => Admin.notify(ok ? 'Reset link copied' : 'Copy failed - select and copy manually', ok ? 'success' : 'error');
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(input.value).then(() => finish(true), () => finish(false));
    } else {
        try {
            finish(document.execCommand('copy'));
        } catch (err) {
            finish(false);
        }
    }
}

function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    if (!preview) return;
    const file = input.files[0];
    if (!file) {
        preview.replaceChildren();
        preview.classList.remove('is-visible');
        return;
    }
    const reader = new FileReader();
    reader.onload = e => {
        preview.replaceChildren(el('img', { src: e.target.result, alt: 'Preview', className: 'preview-thumb' }));
        preview.classList.add('is-visible');
    };
    reader.readAsDataURL(file);
}

function validateUserForm(e) {
    const form = e.target;
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm_password').value;
    const editing = form.dataset.mode === 'edit';
    if (editing && !password && !confirmPassword) return;
    let problem = '';
    if (password !== confirmPassword) problem = 'The two passwords do not match.';
    else if (password.length < 8) problem = 'Passwords need at least 8 characters.';
    if (problem) {
        e.preventDefault();
        Admin.notify(problem, 'error');
        document.getElementById(password !== confirmPassword ? 'confirm_password' : 'password').focus();
    }
}

// --- Autosave: homepage numbers, award counts, event fields, award names ------------------

const AUTOSAVE_FIELDS = '[data-stat-field], [data-award-id], [data-event-field], .award-title-input';

const Autosave = (function () {
    const timers = new Map();
    let inFlight = 0;

    function mark(input, state) {
        const holder = input.closest('.stepper, .event-inline, .award-row');
        if (!holder) return;
        holder.classList.remove('is-saving', 'is-saved', 'is-error');
        if (state) holder.classList.add(`is-${state}`);
    }

    function request(input) {
        if (input.dataset.statField) {
            return api('/admin/api/stats', { field: input.dataset.statField, value: Number(input.value) });
        }
        if (input.dataset.awardId) {
            return api(`/admin/api/awards/${input.dataset.awardId}`, { count: Number(input.value) })
                .then(data => {
                    TeamAwards.remember(input.dataset.awardId, data.count);
                    return data;
                });
        }
        if (input.matches('.award-title-input')) {
            return Awards.saveField(input.closest('[data-category-id]'), 'title', input.value.trim());
        }
        const row = input.closest('[data-event-id]');
        return api(`/admin/api/events/${row.dataset.eventId}`, { field: input.dataset.eventField, value: input.value });
    }

    // A number field that is empty or not a whole number is not sent: clearing a
    // box to retype it used to save 0 to the homepage after a short pause.
    function invalidNumber(input) {
        if (input.type !== 'number') return '';
        const raw = input.value.trim();
        if (raw === '') return 'empty';
        const n = Number(raw);
        if (!Number.isInteger(n) || n < 0) return 'Enter a whole number.';
        if (input.max && n > Number(input.max)) return `That number can be at most ${Number(input.max).toLocaleString()}.`;
        return '';
    }

    function save(input) {
        if (input.value === input.dataset.saved || input.disabled) return;
        const problem = invalidNumber(input);
        if (problem === 'empty') return;
        if (problem) {
            mark(input, 'error');
            Admin.notify(problem, 'error');
            return;
        }
        mark(input, 'saving');
        inFlight++;
        request(input)
            .then(() => {
                input.dataset.saved = input.value;
                mark(input, 'saved');
            })
            .catch(err => {
                input.value = input.dataset.saved;
                mark(input, 'error');
                Admin.notify(err.message, 'error');
            })
            .finally(() => { inFlight--; });
    }

    // Steppers get clicked in bursts (+ + + +), so wait for a pause before saving.
    function schedule(input, delay = 600) {
        clearTimeout(timers.get(input));
        timers.set(input, setTimeout(() => {
            timers.delete(input);
            save(input);
        }, delay));
    }

    function remember(input) {
        input.dataset.saved = input.value;
    }

    function init() {
        document.querySelectorAll(AUTOSAVE_FIELDS).forEach(remember);

        document.addEventListener('click', e => {
            const button = e.target.closest('.stepper-btn');
            if (!button || button.disabled) return;
            const input = button.parentElement.querySelector('input');
            const max = input.max ? Number(input.max) : Infinity;
            input.value = String(Math.min(max, Math.max(0, (parseInt(input.value, 10) || 0) + Number(button.dataset.step))));
            schedule(input);
        });

        document.addEventListener('input', e => {
            if (e.target.matches('[data-stat-field], [data-award-id]')) schedule(e.target, 900);
        });

        document.addEventListener('change', e => {
            if (!e.target.matches(AUTOSAVE_FIELDS)) return;
            clearTimeout(timers.get(e.target));
            timers.delete(e.target);
            save(e.target);
        });

        // Enter commits an inline text field; Escape puts the saved value back.
        document.addEventListener('keydown', e => {
            if (!e.target.matches('[data-event-field], .award-title-input')) return;
            if (e.key === 'Enter') {
                e.preventDefault();
                e.target.blur();
            } else if (e.key === 'Escape') {
                e.target.value = e.target.dataset.saved;
                e.target.blur();
            }
        });
    }

    return { init, remember, pending: () => inFlight > 0 || timers.size > 0 };
})();

// --- Homepage numbers: Auto / Typed --------------------------------------------------------

const StatModes = {
    change(radio) {
        const field = radio.dataset.statMode;
        const row = radio.closest('[data-stat-row]');
        const input = row.querySelector('[data-stat-field]');
        const previous = radio.value === 'auto' ? 'manual' : 'auto';
        api('/admin/api/stats', { field, mode: radio.value })
            .then(data => {
                const auto = data.mode === 'auto';
                row.querySelectorAll('.stepper-btn, input[type="number"]').forEach(node => { node.disabled = auto; });
                row.querySelector('.stepper').classList.toggle('is-disabled', auto);
                input.value = String(data.value);
                Autosave.remember(input);
                Admin.notify(auto ? 'This number now follows the live count.' : 'This number is now typed in.', 'success');
            })
            .catch(err => {
                row.querySelector(`[data-stat-mode][value="${previous}"]`).checked = true;
                Admin.notify(err.message, 'error');
            });
    },
};

// --- Awards: club totals, categories, and each team's counts --------------------------------

const TeamAwards = (function () {
    let awards = [];

    function stepperFor(award) {
        const input = el('input', {
            id: `team-award-${award._id}`, type: 'number', min: '0', max: '999', step: '1', inputmode: 'numeric',
            value: String(award.count ?? 0), 'aria-label': `${award.title} count`,
            dataset: { awardId: award._id },
        });
        Autosave.remember(input);
        return el('div', { className: 'stepper' }, [
            el('button', { type: 'button', className: 'stepper-btn', 'aria-label': `Decrease ${award.title}`, dataset: { step: '-1' }, text: '−' }),
            input,
            el('button', { type: 'button', className: 'stepper-btn', 'aria-label': `Increase ${award.title}`, dataset: { step: '1' }, text: '+' }),
            el('span', { className: 'field-status', 'aria-hidden': 'true' }),
        ]);
    }

    function iconFor(award) {
        if (!award.icon) return el('span', { className: 'award-thumb award-thumb--none', 'aria-hidden': 'true' });
        return el('img', { className: 'award-thumb', src: `/static/assets/icons/${award.icon}`, alt: '', width: '36', height: '36' });
    }

    function render(teamNumber) {
        const rows = awards.filter(a => String(a.team_number) === teamNumber);
        document.getElementById('team_awards_list').replaceChildren(...(rows.length
            ? rows.map(a => el('div', { className: 'data-item award-item award-row award-row--team' }, [
                iconFor(a),
                el('span', { className: 'award-name', text: a.title }),
                stepperFor(a),
            ]))
            : [el('p', { className: 'list-empty', text: 'This team has no award categories yet. Add one under Club totals.' })]));
    }

    function init() {
        const data = document.getElementById('team_awards_data');
        if (data) awards = JSON.parse(data.textContent);
    }

    // Keep the local copy current so switching teams and back shows the saved counts.
    function remember(id, count) {
        const award = awards.find(a => a._id === id);
        if (award) award.count = count;
    }

    return { init, render, remember };
})();

const Awards = {
    scope(chip) {
        const team = chip.dataset.awardScope;
        document.querySelectorAll('[data-award-scope]').forEach(c => c.setAttribute('aria-selected', String(c === chip)));
        document.querySelector('[data-scope-panel=""]').hidden = Boolean(team);
        document.querySelector('[data-scope-panel="team"]').hidden = !team;
        if (team) TeamAwards.render(team);
    },

    saveField(row, field, value) {
        return api(`/admin/api/award-categories/${row.dataset.categoryId}`, { [field]: value });
    },

    // Style controls save as soon as they change (icon, border, wide, shimmer).
    styleChange(control) {
        const row = control.closest('[data-category-id]');
        const field = control.dataset.categoryField;
        const value = control.type === 'checkbox' ? (field === 'layout' ? (control.checked ? 'wide' : '') : control.checked)
            : control.value;
        Awards.saveField(row, field, value)
            .then(() => {
                if (field === 'icon') row.querySelector('.award-thumb')?.setAttribute('src', `/static/assets/icons/${value}`);
                Admin.notify('Award style saved. Team copies were updated too.', 'success');
            })
            .catch(err => Admin.notify(err.message, 'error'));
    },

    toggleStyle(button) {
        const panel = button.closest('[data-category-id]').querySelector('.award-style');
        panel.hidden = !panel.hidden;
        button.setAttribute('aria-expanded', String(!panel.hidden));
    },

    move(button) {
        const row = button.closest('[data-category-id]');
        api(`/admin/api/award-categories/${row.dataset.categoryId}/move`, { step: Number(button.dataset.step) })
            .then(() => {
                const sibling = Number(button.dataset.step) < 0 ? row.previousElementSibling : row.nextElementSibling;
                if (sibling?.matches('[data-category-id]')) {
                    if (Number(button.dataset.step) < 0) sibling.before(row);
                    else sibling.after(row);
                }
                Awards.refreshArrows();
                button.focus();
            })
            .catch(err => Admin.notify(err.message, 'error'));
    },

    refreshArrows() {
        const rows = Array.from(document.querySelectorAll('#clubAwards [data-category-id]'));
        rows.forEach((row, i) => {
            row.querySelector('[data-step="-1"]').disabled = i === 0;
            row.querySelector('[data-step="1"]').disabled = i === rows.length - 1;
        });
    },

    remove(button) {
        const row = button.closest('[data-category-id]');
        Dialog.confirm({
            title: `Delete "${button.dataset.title}"?`,
            message: 'The category and every team\'s count of it are removed from the site. This cannot be undone.',
            confirmLabel: 'Delete',
        }).then(ok => {
            if (!ok) return;
            api(`/admin/api/award-categories/${row.dataset.categoryId}`, {}, 'DELETE')
                .then(() => location.reload())
                .catch(err => Admin.notify(err.message, 'error'));
        });
    },

    add(form) {
        const title = form.querySelector('#new-award-title').value.trim();
        const iconFile = form.querySelector('#new-award-icon').value;
        if (!title) return;
        lockSubmit(form);
        api('/admin/api/award-categories', { title, icon: iconFile })
            .then(() => location.reload())
            .catch(err => {
                form.querySelectorAll('[type="submit"]').forEach(b => { b.disabled = false; });
                Admin.notify(err.message, 'error');
            });
    },
};

// --- Events -------------------------------------------------------------------------------

function prunePastEvents(button) {
    const count = Number(button.dataset.count);
    Dialog.confirm({
        title: `Delete ${plural(count, 'past event')}?`,
        message: 'They are no longer on the homepage. Delete them to keep this list short. This cannot be undone.',
        confirmLabel: 'Delete them',
    }).then(ok => {
        if (!ok) return;
        api('/admin/api/events/prune')
            .then(data => {
                document.getElementById('past-events')?.remove();
                Admin.notify(`Deleted ${plural(data.deleted, 'past event')}.`, 'success');
            })
            .catch(err => Admin.notify(err.message, 'error'));
    });
}

// --- Teams: start a new season ------------------------------------------------------------

function startNewSeason(button) {
    const { teamId, teamNumber, currentSeason, nextSeason } = button.dataset;
    const start = parseInt(nextSeason, 10) || new Date().getFullYear();
    const options = [];
    for (let y = start; y >= start - 3; y--) {
        const label = `${y}-${String((y + 1) % 100).padStart(2, '0')}`;
        if (label !== currentSeason) options.push(el('option', { value: label, text: label }));
    }
    const field = el('label', { className: 'dialog-field' }, [
        el('span', { text: 'Season' }),
        el('select', {}, options),
    ]);
    Dialog.form({
        title: `Start a new season for ${teamNumber}`,
        message: 'The nickname, tagline and roster carry over, and logins move to the new season. Specs, goals and '
            + 'the journey start empty. Last season stays on the team page under its season picker.',
        field,
        confirmLabel: 'Start season',
    }).then(season => {
        if (!season) return;
        showLoading();
        api(`/admin/api/teams/${teamId}/new-season`, { season })
            .then(data => location.assign(data.url))
            .catch(err => {
                hideLoading();
                Admin.notify(err.message, 'error');
            });
    });
}

// --- Dropped files: team banners and sponsor logos ------------------------------------------
// controls.js finds the zone under the pointer and checks the file type, then fires
// ctl:files on it; these send the file where that zone says.

const DroppedFiles = (function () {
    function busy(node, promise) {
        node.classList.add('is-uploading');
        node.setAttribute('aria-busy', 'true');
        return promise
            .catch(err => Admin.notify(err.message, 'error'))
            .finally(() => {
                node.classList.remove('is-uploading');
                node.removeAttribute('aria-busy');
            });
    }

    function teamBanner(tile, file) {
        busy(tile, uploadFile(`/api/team/${tile.dataset.teamId}/image`, { hero_image: file }).then(data => {
            let photo = tile.querySelector('.team-tile-photo');
            if (!photo) {
                photo = el('img', { className: 'team-tile-photo', alt: '' });
                tile.querySelector('.team-tile-main').append(photo);
            }
            photo.src = data.url;
            Admin.notify(`New banner photo for ${tile.dataset.teamName}.`, 'success');
        }));
    }

    function sponsorLogo(row, file) {
        const edit = row.querySelector('[data-action="edit-sponsor"]');
        busy(row, uploadFile(`/admin/api/sponsor/${row.dataset.sponsorId}/logo`, { logo: file }).then(data => {
            row.querySelector('.sponsor-thumb').replaceChildren(el('img', { src: data.url, alt: '' }));
            if (edit) edit.dataset.hasLogo = 'true';
            Admin.notify(`New logo for ${edit ? edit.dataset.name : 'the sponsor'}.`, 'success');
        }));
    }

    // "acme_corp-logo-final.png" suggests the name "Acme Corp".
    const FILLER = /^(logos?|final|transparent|icon|vector|colou?r|hi|res|hires|rgb|cmyk|white|black|dark|light|copy|v?\d+(px)?|\d+x\d*)$/i;

    function nameFromFile(fileName) {
        return fileName.replace(/\.[^.]+$/, '').split(/[\s_.-]+/)
            .filter(word => word && !FILLER.test(word))
            .map(word => (word === word.toUpperCase() ? word : word.charAt(0).toUpperCase() + word.slice(1)))
            .join(' ')
            .slice(0, 100);
    }

    // A photo dropped on a People board card: that person's photo on that team or group.
    function memberPhoto(card, file) {
        const teamId = card.closest('.roster-col')?.dataset.teamId;
        busy(card, uploadFile(`/api/team/${teamId}/image`, { member_photo: file, member_id: card.dataset.memberId })
            .then(data => {
                card.querySelector('.roster-avatar').replaceChildren(el('img', { src: data.url, alt: '' }));
                Admin.notify(`New photo for ${card.dataset.name}.`, 'success');
            }));
    }

    // A logo dropped on the list, not on a sponsor: start a new sponsor with it.
    function newSponsor(file) {
        guarded('sponsor_form', () => {
            resetSponsorForm();
            const form = document.getElementById('sponsor_form');
            const input = document.getElementById('f-logo');
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            const name = form.querySelector('[name="name"]');
            name.value = nameFromFile(file.name);
            scrollToId('sponsor_form_card');
            name.focus({ preventScroll: true });
            name.select();
        });
    }

    function onFiles(e) {
        const zone = e.target;
        const file = e.detail.files[0];
        if (!file) return;
        if (zone.matches('.team-tile')) {
            e.preventDefault();
            teamBanner(zone, file);
        } else if (zone.matches('.sponsor-row')) {
            e.preventDefault();
            sponsorLogo(zone, file);
        } else if (zone.id === 'sponsor_list_card') {
            e.preventDefault();
            newSponsor(file);
        } else if (zone.matches('.roster-card')) {
            e.preventDefault();
            memberPhoto(zone, file);
        }
    }

    return { onFiles };
})();

// --- People: approvals, roles, roster board -------------------------------------------------

const Approvals = {
    approve(item) {
        const role = item.querySelector('[data-approve-role]').value;
        const choice = item.querySelector('[data-approve-team]').value;
        const name = item.querySelector('[data-display-name]').textContent;
        const body = { role };
        if (choice.startsWith('claim:')) body.member_id = choice.slice(6);
        else body.team_id = choice || null;
        item.classList.add('is-busy');
        api(`/admin/api/users/${item.dataset.userId}/approve`, body)
            .then(() => {
                Admin.notify(`${name} approved${choice ? ' and put on the roster' : ''}. Refreshing…`, 'success');
                // The board and the account list are both server-rendered; reload rather than patch both.
                setTimeout(() => location.reload(), 1000);
            })
            .catch(err => {
                item.classList.remove('is-busy');
                Admin.notify(err.message, 'error');
            });
    },

    reject(item, username) {
        Dialog.confirm({
            title: 'Reject this request?',
            message: `${username}'s request will be deleted. They can sign up again later.`,
            confirmLabel: 'Reject',
        }).then(ok => {
            if (!ok) return;
            api(`/admin/api/users/${item.dataset.userId}/reject`)
                .then(() => {
                    item.remove();
                    Admin.notify(`Request from ${username} rejected.`, 'info');
                    if (!document.querySelector('.approval-item')) document.getElementById('approvals')?.remove();
                })
                .catch(err => Admin.notify(err.message, 'error'));
        });
    },
};

const Roles = {
    change(select) {
        const previous = select.dataset.current;
        const role = select.value;
        api(`/admin/api/users/${select.dataset.roleUserId}/role`, { role })
            .then(data => {
                select.dataset.current = role;
                select.classList.replace(previous, role);
                select.closest('.user-item').dataset.role = role;
                Admin.notify(`Role changed to ${role}.`, 'success');
                if (data.self_demoted) location.assign('/');
            })
            .catch(err => {
                select.value = previous;
                Admin.notify(err.message, 'error');
            });
    },
};

// Team and group columns hold roster cards (data-member-id, plus data-user-id
// when the person has a login). The Unassigned column holds accounts
// (data-user-id only). A person is on one robot team at most but can be in any
// number of groups, so dropping on a group adds a card and leaves the dragged
// one where it was; dropping on a team moves the person's team card. Only
// people with a login can go to Unassigned; removing someone without one is a
// team-editor job, where it gets a confirmation.
const Roster = (function () {
    let dragged = null;

    const columns = () => Array.from(document.querySelectorAll('.roster-col'));
    const columnFor = teamId => columns().find(col => (col.dataset.teamId || null) === (teamId || null));
    const teamOf = card => card.closest('.roster-col')?.dataset.teamId || null;
    const labelOf = col => col.querySelector('.roster-col-head strong').textContent;
    const isGroup = col => col?.dataset.kind === 'group';
    const cardsOf = userId => Array.from(document.querySelectorAll(`.roster-card[data-user-id="${userId}"]`))
        .filter(card => teamOf(card));

    function canGo(card, teamId) {
        const col = columnFor(teamId);
        if (!col || col === card.closest('.roster-col')) return false;
        if (!teamId) return Boolean(card.dataset.userId);
        const userId = card.dataset.userId;
        // Not into a group they are already in, nor onto the team they are already on.
        return !userId || !cardsOf(userId).some(other => other.closest('.roster-col') === col);
    }

    function recount() {
        columns().forEach(col => {
            col.querySelector('.roster-count').textContent = col.querySelectorAll('.roster-card').length;
        });
    }

    // A card on a team or group takes a dropped photo for that spot; an account in Unassigned has
    // no roster spot to hold one.
    function photoDrop(card) {
        if (card.dataset.memberId && teamOf(card)) {
            card.dataset.drop = 'event';
            card.dataset.dropAccept = 'image/png,image/jpeg,image/gif,image/webp';
            card.dataset.dropLabel = `Set as ${card.dataset.name}’s photo`;
        } else {
            ['drop', 'dropAccept', 'dropLabel'].forEach(key => delete card.dataset[key]);
        }
    }

    // Rebuild a card's Move-to menu for the column it now sits in (same shape as move_options in _people.html).
    function refreshMenu(card) {
        photoDrop(card);
        const here = card.closest('.roster-col');
        const option = col => el('option', { value: col.dataset.teamId, text: labelOf(col) });
        const targets = columns().filter(col => col.dataset.teamId && canGo(card, col.dataset.teamId));
        const teams = targets.filter(col => !isGroup(col)).map(option);
        const groups = targets.filter(isGroup).map(option);
        const options = [el('option', { value: '', text: 'Move to…', selected: true, disabled: true })];
        if (teams.length) options.push(el('optgroup', { label: 'Move to team' }, teams));
        if (groups.length) options.push(el('optgroup', { label: 'Also add to group' }, groups));
        if (here.dataset.teamId && card.dataset.userId) {
            options.push(el('option', {
                value: 'none', text: isGroup(here) ? `Remove from ${labelOf(here)}` : 'Unassigned',
            }));
        }
        card.querySelector('.roster-move').replaceChildren(...options);
    }

    // One move can change what several cards may do (a person's other cards), so redo them all.
    function refresh() {
        document.querySelectorAll('.roster-card').forEach(refreshMenu);
        recount();
    }

    function place(card, teamId) {
        columnFor(teamId).querySelector('.roster-drop').append(card);
        refresh();
    }

    // A new card for a person just added to a group (or to a team, from a group card).
    function newCard(member, like) {
        const username = like.querySelector('[data-card-meta]')?.textContent.match(/@(\S+)/)?.[1];
        const role = member.role || 'Member';
        const meta = el('small', { dataset: { cardMeta: '' } }, member.user_id
            ? [`${role}${username ? ` · @${username}` : ''}`]
            : [`${role} · `, el('span', { className: 'no-login-chip', text: 'no login' })]);
        const dataset = { memberId: member.member_id, name: member.name };
        if (member.user_id) dataset.userId = member.user_id;
        return el('li', { className: 'roster-card', draggable: 'true', dataset }, [
            like.querySelector('.roster-avatar')?.cloneNode(true)
                || el('span', { className: 'roster-avatar', 'aria-hidden': 'true' }),
            el('span', { className: 'roster-text' }, [el('strong', { text: member.name }), meta]),
            el('div', { className: 'roster-card-controls' }, [
                el('select', { className: 'roster-move', 'aria-label': `Move ${member.name} to` }),
            ]),
        ]);
    }

    // Show what the server did. Returns the card now at `to` (or the removed one), for Undo.
    function show(card, data, to) {
        if (!to) {
            // Its card is gone from the roster, so Undo puts the person back by account.
            delete card.dataset.memberId;
            if (data.unassigned) {
                place(card, null);
            } else {
                card.remove();
                refresh();
            }
            return card;
        }
        // An account card (in Unassigned, or taken off the board by an earlier move) goes itself.
        if (data.mode === 'add' && teamOf(card) && card.isConnected) {
            const added = newCard(data.member, card);
            place(added, to);
            return added;
        }
        const moved = document.querySelector(`.roster-card[data-member-id="${data.member.member_id}"]`) || card;
        moved.dataset.memberId = data.member.member_id;
        place(moved, to);
        return moved;
    }

    function move(card, toTeamId, isUndo = false) {
        const fromCol = card.closest('.roster-col');
        const to = toTeamId || null;
        if (!isUndo && !canGo(card, to)) return;

        const body = { to_team_id: to };
        if (card.dataset.memberId) body.member_id = card.dataset.memberId;
        else body.user_id = card.dataset.userId;
        if (isUndo && !to) body.remove = true;

        card.classList.add('is-busy');
        api('/admin/api/roster/move', body)
            .then(data => {
                card.classList.remove('is-busy');
                const result = show(card, data, to);
                const name = card.dataset.name;
                let message, revert;
                if (!to) {
                    message = data.unassigned ? `${name} is now unassigned.` : `${name} is off ${labelOf(fromCol)}.`;
                    revert = () => move(result, fromCol.dataset.teamId, true);
                } else if (data.mode === 'add') {
                    message = `${name} added to ${labelOf(columnFor(to))}.`;
                    revert = () => move(result, null, true);
                } else {
                    message = `${name} moved to ${labelOf(columnFor(to))}.`;
                    revert = () => move(result, data.from_team_id, true);
                }
                Admin.notify(message, 'success', isUndo ? null : { label: 'Undo', run: revert });
            })
            .catch(err => {
                card.classList.remove('is-busy');
                Admin.notify(err.message, 'error');
            });
    }

    function moveFromSelect(select) {
        const value = select.value;
        select.value = '';
        move(select.closest('.roster-card'), value === 'none' ? null : value);
    }

    // Give a no-login card an account. The account's Unassigned card goes away.
    function link(select) {
        const card = select.closest('.roster-card');
        const userId = select.value;
        const account = document.querySelector(`.roster-col--unassigned .roster-card[data-user-id="${userId}"]`);
        const accountName = select.selectedOptions[0]?.textContent || 'that account';
        select.value = '';
        api('/admin/api/roster/link', { member_id: card.dataset.memberId, user_id: userId })
            .then(() => {
                card.dataset.userId = userId;
                const username = accountName.match(/\(@([^)]+)\)/)?.[1];
                const meta = card.querySelector('[data-card-meta]');
                meta.textContent = `${meta.textContent.split(' · ')[0]}${username ? ` · @${username}` : ''}`;
                account?.remove();
                document.querySelectorAll(`.roster-link option[value="${userId}"]`).forEach(o => o.remove());
                select.remove();
                refresh();
                Admin.notify(`${card.dataset.name} is now linked to ${accountName}.`, 'success');
            })
            .catch(err => Admin.notify(err.message, 'error'));
    }

    function clearHover() {
        document.querySelectorAll('.roster-col.is-over').forEach(col => col.classList.remove('is-over'));
    }

    function init() {
        const board = document.getElementById('rosterBoard');
        if (!board) return;
        board.querySelectorAll('.roster-card').forEach(photoDrop);

        board.addEventListener('dragstart', e => {
            dragged = e.target.closest('.roster-card');
            if (!dragged) return;
            e.dataTransfer.effectAllowed = 'copyMove';
            e.dataTransfer.setData('text/plain', dragged.dataset.name || '');
            dragged.classList.add('is-dragging');
            board.classList.add('is-dragging');
        });
        board.addEventListener('dragend', () => {
            dragged?.classList.remove('is-dragging');
            board.classList.remove('is-dragging');
            clearHover();
            dragged = null;
        });
        board.addEventListener('dragover', e => {
            const col = e.target.closest('.roster-col');
            if (!col || !dragged || !canGo(dragged, col.dataset.teamId || null)) return;
            e.preventDefault();
            // Into or out of a group, the dragged card stays put and a new one is added: show a copy cursor.
            const copies = teamOf(dragged) && col.dataset.teamId && (isGroup(col) || isGroup(dragged.closest('.roster-col')));
            e.dataTransfer.dropEffect = copies ? 'copy' : 'move';
            if (!col.classList.contains('is-over')) {
                clearHover();
                col.classList.add('is-over');
            }
        });
        board.addEventListener('dragleave', e => {
            const col = e.target.closest('.roster-col');
            if (col && !col.contains(e.relatedTarget)) col.classList.remove('is-over');
        });
        board.addEventListener('drop', e => {
            const col = e.target.closest('.roster-col');
            if (!col || !dragged) return;
            e.preventDefault();
            clearHover();
            move(dragged, col.dataset.teamId || null);
        });
    }

    return { init, moveFromSelect, link };
})();

// --- Messages and the newsletter list ----------------------------------------------------------

const Messages = (function () {
    let panel, status = '';

    const items = () => Array.from(panel.querySelectorAll('.message-item'));
    const selected = () => items().filter(i => !i.hidden && !i.classList.contains('is-hidden') && i.querySelector('.message-check').checked);

    function applyFilters() {
        const term = (document.getElementById('messages_filter')?.value || '').trim().toLowerCase();
        items().forEach(item => {
            item.hidden = (Boolean(status) && item.dataset.status !== status)
                || (term !== '' && !item.textContent.toLowerCase().includes(term));
        });
        updateBulk();
    }

    function updateBulk() {
        const count = selected().length;
        const label = document.getElementById('messagesSelected');
        if (label) label.textContent = count ? `${count} selected` : '';
        panel.querySelectorAll('[data-bulk]').forEach(b => { b.disabled = !count; });
        const all = document.getElementById('messagesSelectAll');
        if (all) {
            const visible = items().filter(i => !i.hidden);
            all.checked = visible.length > 0 && visible.every(i => i.querySelector('.message-check').checked);
        }
    }

    function adjustCount(fromStatus, toStatus) {
        const bump = (s, d) => {
            const badge = panel.querySelector(`[data-count-for="${s}"]`);
            if (!badge) return;
            const n = Math.max(0, parseInt(badge.textContent, 10) + d);
            badge.textContent = `${n} ${s}`;
        };
        if (fromStatus) bump(fromStatus, -1);
        if (toStatus && toStatus !== 'deleted') bump(toStatus, 1);
        const unread = parseInt(panel.querySelector('[data-count-for="new"]')?.textContent, 10) || 0;
        const tabBadge = document.querySelector('#tab-messages .tab-badge');
        if (tabBadge) {
            tabBadge.textContent = String(unread);
            tabBadge.hidden = unread === 0;
        }
    }

    function applyStatus(item, newStatus) {
        const old = item.dataset.status;
        if (newStatus === 'deleted') {
            item.remove();
            adjustCount(old, null);
            return;
        }
        item.dataset.status = newStatus;
        const badge = item.querySelector('[data-status-badge]');
        badge.textContent = newStatus;
        badge.className = `status-badge ${newStatus}`;
        item.querySelectorAll('[data-message-action]').forEach(b => {
            const action = b.dataset.messageAction;
            b.hidden = (action === 'read' && newStatus === 'read') || (action === 'new' && newStatus === 'new')
                || (action === 'archive' && newStatus === 'archived');
        });
        if (old !== newStatus) adjustCount(old, newStatus);
    }

    function act(item, action) {
        const run = () => api(`/admin/api/messages/${item.dataset.messageId}`, { action })
            .then(data => {
                applyStatus(item, data.status);
                applyFilters();
                Admin.notify(data.status === 'deleted' ? 'Message deleted.' : `Marked ${data.status}.`, 'success');
            })
            .catch(err => Admin.notify(err.message, 'error'));
        if (action !== 'delete') return run();
        return Dialog.confirm({ title: 'Delete this message?', message: 'This cannot be undone.', confirmLabel: 'Delete' })
            .then(ok => ok && run());
    }

    function bulk(action) {
        const chosen = selected();
        if (!chosen.length) return;
        const run = () => api('/admin/api/messages/bulk', { action, ids: chosen.map(i => i.dataset.messageId) })
            .then(data => {
                chosen.forEach(item => applyStatus(item, data.status));
                applyFilters();
                Admin.notify(`${data.status === 'deleted' ? 'Deleted' : 'Updated'} ${plural(data.count, 'message')}.`, 'success');
            })
            .catch(err => Admin.notify(err.message, 'error'));
        if (action !== 'delete') return run();
        return Dialog.confirm({
            title: `Delete ${plural(chosen.length, 'message')}?`, message: 'This cannot be undone.', confirmLabel: 'Delete',
        }).then(ok => ok && run());
    }

    function toggle(button) {
        const item = button.closest('.message-item');
        const body = document.getElementById(button.getAttribute('aria-controls'));
        if (!body) return;
        const open = body.hidden;
        body.hidden = !open;
        button.setAttribute('aria-expanded', String(open));
        item.classList.toggle('is-open', open);
        // Opening a new message counts as reading it.
        if (open && item.dataset.status === 'new') {
            api(`/admin/api/messages/${item.dataset.messageId}`, { action: 'read' })
                .then(data => applyStatus(item, data.status))
                .catch(() => {});
        }
    }

    function init() {
        panel = document.getElementById('panel-messages');
        if (!panel) return;
        panel.querySelectorAll('.message-filter').forEach(button => {
            button.addEventListener('click', () => {
                panel.querySelectorAll('.message-filter').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
                status = button.dataset.status;
                applyFilters();
            });
        });
        document.getElementById('messages_filter')?.addEventListener('input', applyFilters);
        panel.addEventListener('click', e => {
            const toggleBtn = e.target.closest('.message-toggle');
            if (toggleBtn) return toggle(toggleBtn);
            const actionBtn = e.target.closest('[data-message-action]');
            if (actionBtn) return act(actionBtn.closest('.message-item'), actionBtn.dataset.messageAction);
            const bulkBtn = e.target.closest('[data-bulk]');
            if (bulkBtn) return bulk(bulkBtn.dataset.bulk);
            return undefined;
        });
        panel.addEventListener('change', e => {
            if (e.target.id === 'messagesSelectAll') {
                items().filter(i => !i.hidden).forEach(i => { i.querySelector('.message-check').checked = e.target.checked; });
            }
            if (e.target.matches('.message-check, #messagesSelectAll')) updateBulk();
        });
    }

    return { init };
})();

function removeSubscriber(button) {
    const email = button.dataset.email;
    Dialog.confirm({
        title: `Remove ${email}?`,
        message: 'They will stop getting the newsletter. They can sign up again from the footer.',
        confirmLabel: 'Remove',
    }).then(ok => {
        if (!ok) return;
        const item = button.closest('[data-subscriber-id]');
        api(`/admin/api/subscribers/${item.dataset.subscriberId}`, {}, 'DELETE')
            .then(() => {
                item.remove();
                const chip = document.querySelector('#newsletterCard .count-chip');
                if (chip) chip.textContent = String(Math.max(0, parseInt(chip.textContent, 10) - 1));
                Admin.notify(`Removed ${email}.`, 'success');
            })
            .catch(err => Admin.notify(err.message, 'error'));
    });
}

// --- Activity log: filters and paging ----------------------------------------------------------

const Activity = (function () {
    let group = '';

    function row(a) {
        const time = el('time', { datetime: a.timestamp, title: a.when, text: a.ago });
        return el('li', { className: 'activity-item' }, [
            el('span', { className: 'activity-icon', 'aria-hidden': 'true', text: a.icon }),
            el('div', { className: 'activity-content' }, [
                el('div', { className: 'activity-title', text: a.title }),
                el('div', { className: 'activity-desc', text: a.description }),
                el('div', { className: 'activity-time' }, [`${a.user} · `, time]),
            ]),
        ]);
    }

    function load(reset) {
        const list = document.getElementById('activityList');
        const more = document.getElementById('activityMore');
        const params = new URLSearchParams();
        if (group) params.set('group', group);
        if (!reset && more.dataset.before) params.set('before', more.dataset.before);
        more.disabled = true;
        fetch(`/admin/api/activity?${params}`, { credentials: 'same-origin' })
            .then(r => r.json().then(data => (r.ok ? data : Promise.reject(new Error(data.error || 'Could not load activity.')))))
            .then(data => {
                if (reset) list.replaceChildren();
                data.items.forEach(a => list.append(row(a)));
                if (reset && !data.items.length) {
                    list.append(el('li', { className: 'list-empty', text: 'Nothing here yet.' }));
                }
                more.dataset.before = data.items.length ? data.items[data.items.length - 1].timestamp : '';
                more.hidden = !data.more;
            })
            .catch(err => Admin.notify(err.message, 'error'))
            .finally(() => { more.disabled = false; });
    }

    function filter(chip) {
        group = chip.dataset.activityGroup;
        document.querySelectorAll('[data-activity-group]').forEach(c => c.setAttribute('aria-pressed', String(c === chip)));
        load(true);
    }

    function init() {
        document.getElementById('activityMore')?.addEventListener('click', () => load(false));
    }

    return { init, filter };
})();

// --- Help ----------------------------------------------------------------------------------------

function showHelp() {
    Dialog.alert({
        title: 'How the Command Center works',
        html: `
            <p><strong>Saving:</strong> numbers, event fields, roles, award names and team pages save the moment you change them. A green tick means it worked; a red mark means it did not, and the old value comes back.</p>
            <p><strong>Overview:</strong> "Needs attention" lists what is waiting on you. The homepage numbers can count themselves (Auto) or show what you type.</p>
            <p><strong>People:</strong> approve sign-ups at the top. Drag cards between teams or use <em>Move to</em>; every move has an Undo. <em>Link login</em> connects an account to a card that was added by name.</p>
            <p><strong>Teams:</strong> open a team to edit its page. <em>New season</em> copies the roster into next season.</p>
            <p><strong>Site:</strong> edit page text, photos, the announcement bar and more in the site editor.</p>
            <p><strong>Keyboard:</strong> press <kbd>/</kbd> to search the current tab, and use the arrow keys on the tab bar.</p>
        `,
        confirmLabel: 'Got it',
    });
}

// --- Delegated wiring -------------------------------------------------------------------------

// Quick-action links: switch tab and start a blank form, asking first if the
// admin has unsaved edits in it.
const QUICK_ADD = {
    events: ['event_form', resetSimpleForm('event_form')],
    teams: ['team_form', resetSimpleForm('team_form')],
    sponsors: ['sponsor_form', resetSponsorForm],
};

const RESETS = {
    'reset-sponsor': ['sponsor_form', resetSponsorForm],
    'reset-user': ['userForm', resetUserForm],
};

const EDITS = {
    'edit-sponsor': ['sponsor_form', editSponsor],
    'edit-user': ['userForm', editUser],
};

function guarded(formId, run) {
    confirmDiscard(document.getElementById(formId)).then(ok => {
        if (ok) run();
    });
}

document.addEventListener('click', function (e) {
    const scope = e.target.closest('[data-award-scope]');
    if (scope) return Awards.scope(scope);
    const group = e.target.closest('[data-activity-group]');
    if (group) return Activity.filter(group);

    const trigger = e.target.closest('[data-action]');
    if (!trigger) return undefined;
    const action = trigger.dataset.action;

    if (action === 'quick-add') {
        e.preventDefault();
        const [formId, reset] = QUICK_ADD[trigger.dataset.tab];
        guarded(formId, () => {
            AdminTabs.go(trigger.dataset.tab, formId);
            reset();
        });
    } else if (RESETS[action]) {
        const [formId, reset] = RESETS[action];
        guarded(formId, reset);
    } else if (EDITS[action]) {
        const [formId, edit] = EDITS[action];
        guarded(formId, () => edit(trigger));
    } else if (action === 'go-tab') {
        e.preventDefault();
        AdminTabs.go(trigger.dataset.tab, trigger.dataset.scroll);
    } else if (action === 'approve-user') {
        Approvals.approve(trigger.closest('[data-user-id]'));
    } else if (action === 'reject-user') {
        Approvals.reject(trigger.closest('[data-user-id]'), trigger.dataset.username);
    } else if (action === 'copy-reset-link') {
        copyResetLink();
    } else if (action === 'select-all') {
        trigger.select();
    } else if (action === 'show-help') {
        showHelp();
    } else if (action === 'award-move') {
        Awards.move(trigger);
    } else if (action === 'award-style') {
        Awards.toggleStyle(trigger);
    } else if (action === 'award-delete') {
        Awards.remove(trigger);
    } else if (action === 'prune-events') {
        prunePastEvents(trigger);
    } else if (action === 'new-season') {
        startNewSeason(trigger);
    } else if (action === 'remove-subscriber') {
        removeSubscriber(trigger);
    }
    return undefined;
});

document.addEventListener('input', function (e) {
    const target = e.target;
    if (target.id === 'adminSearch') {
        searchAdminContent();
        return;
    }
    const form = target.form;
    if (form && DIRTY_FORMS.includes(form.id)) form.dataset.dirty = '1';
});

document.addEventListener('change', function (e) {
    const target = e.target;
    if (target.dataset.previewTarget) previewImage(target, target.dataset.previewTarget);
    if (target.form && DIRTY_FORMS.includes(target.form.id)) target.form.dataset.dirty = '1';

    if (target.matches('[data-role-user-id]')) Roles.change(target);
    if (target.matches('.roster-move')) Roster.moveFromSelect(target);
    if (target.matches('.roster-link')) Roster.link(target);
    if (target.matches('[data-stat-mode]')) StatModes.change(target);
    if (target.matches('.award-style [data-category-field]')) Awards.styleChange(target);
});

document.addEventListener('ctl:files', DroppedFiles.onFiles);

document.addEventListener('submit', function (e) {
    const form = e.target;
    if (form.id === 'awardCategoryForm') {
        e.preventDefault();
        Awards.add(form);
        return;
    }
    if (form.id === 'userForm') validateUserForm(e);
    if (form.dataset.confirmDelete) {
        e.preventDefault();
        confirmDelete(form, form.dataset.confirmDelete);
        return;
    }
    if (e.defaultPrevented) {
        hideLoading();
        return;
    }
    // Block double submits: a second click on a slow multipart save used to
    // upload every file twice.
    lockSubmit(form);
    markClean(form);
    showLoading();
});

// "/" jumps to the tab search, like most dashboards.
document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || e.target.matches('input, textarea, select, [contenteditable]')) return;
    const search = document.getElementById('adminSearch');
    if (!search) return;
    e.preventDefault();
    search.focus();
    search.select();
});

// Warn before leaving the page with unsaved edits.
window.addEventListener('beforeunload', function (e) {
    const dirty = DIRTY_FORMS.some(id => isDirty(document.getElementById(id))) || Autosave.pending();
    if (dirty) {
        e.preventDefault();
        e.returnValue = '';
    }
});

// Coming back through the back/forward cache: undo the submit lock and overlay.
window.addEventListener('pageshow', function () {
    hideLoading();
    document.querySelectorAll('.admin-container [type="submit"]').forEach(button => {
        button.disabled = false;
    });
});

// --- Page setup -----------------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    AdminTabs.init();
    Messages.init();
    Autosave.init();
    TeamAwards.init();
    Roster.init();
    Activity.init();
    Admin.attachListFilter('#events_filter', '#panel-events .event-item');
    Admin.attachListFilter('#awards_filter', '#panel-awards .award-item');
    Admin.attachListFilter('#teams_filter', '#panel-teams .team-tile');
    Admin.attachListFilter('#sponsors_filter', '#panel-sponsors .sponsor-row');
    Admin.attachListFilter('#subscribers_filter', '#panel-messages .subscriber-item');

    const usersFilter = document.getElementById('users_filter');
    const usersRoleFilter = document.getElementById('users_role_filter');
    function filterUsers() {
        const term = usersFilter.value.trim().toLowerCase();
        const role = usersRoleFilter.value;
        document.querySelectorAll('#panel-users .user-item').forEach(item => {
            const matches = (!term || item.textContent.toLowerCase().includes(term))
                && (!role || item.dataset.role === role);
            item.classList.toggle('is-hidden', !matches);
        });
    }
    usersFilter?.addEventListener('input', filterUsers);
    usersRoleFilter?.addEventListener('change', filterUsers);

    // Server flash messages fade like the toasts the page makes itself.
    document.querySelectorAll('#toast-stack .status-msg').forEach(toast => {
        setTimeout(() => {
            toast.classList.add('is-leaving');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        }, 6000);
    });
});
