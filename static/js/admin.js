// Admin dashboard behaviour.
//
// Every control is wired through the delegated listeners at the bottom of
// this file (data-action, data-confirm-delete, data-preview-target, ...).
// There are no inline on*= handlers anywhere, so /admin runs under the same
// no-inline-script Content-Security-Policy as the rest of the site.

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

function field(labelText, control) {
    const label = el('label', { for: control.id, text: labelText });
    return el('div', { className: 'form-group' }, [label, control]);
}

function scrollToCard(id, offset = 50) {
    const card = document.getElementById(id);
    if (card) window.scrollTo({ top: card.offsetTop - offset, behavior: 'smooth' });
}

// --- Unsaved-change tracking --------------------------------------------------

const DIRTY_FORMS = ['event_form', 'team_form', 'sponsor_form', 'userForm'];

function resetEventForm() {
    const form = document.getElementById('event_form');
    form.reset();
    markClean(form);
    form.querySelector('input[type="text"]')?.focus();
}

function resetTeamForm() {
    const form = document.getElementById('team_form');
    form.reset();
    markClean(form);
    form.querySelector('input[type="text"]')?.focus();
}

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

// --- Sponsors -------------------------------------------------------------------

function editSponsor(button) {
    const form = document.getElementById('sponsor_form');
    document.getElementById('sponsor_form_title').innerText = 'Edit Sponsor';
    document.getElementById('sponsor_id').value = button.dataset.id;
    form.querySelector('[name="name"]').value = button.dataset.name;
    form.querySelector('[name="website"]').value = button.dataset.website;
    // Level is a segmented control (radios); fall back to the first tier for unknown values.
    const levels = Array.from(form.querySelectorAll('[name="level"]'));
    (levels.find(radio => radio.value === button.dataset.level) || levels[0]).checked = true;
    markClean(form);
    scrollToCard('sponsor_form_card');
}

function resetSponsorForm() {
    const form = document.getElementById('sponsor_form');
    document.getElementById('sponsor_form_title').innerText = 'Add New Sponsor';
    document.getElementById('sponsor_id').value = '';
    form.reset();
    document.getElementById('sponsorLogoPreview')?.replaceChildren();
    markClean(form);
}

// --- Users ----------------------------------------------------------------------

function editUser(button) {
    const user = button.dataset;
    const form = document.getElementById('userForm');
    document.getElementById('user_form_title').innerText = 'Edit account: ' + user.username;
    document.getElementById('userFormDetails').open = true;
    form.action = user.updateUrl;
    form.dataset.mode = 'edit';
    form.reset();
    document.getElementById('username').value = user.username;
    document.getElementById('email').value = user.email || '';
    document.getElementById('role').value = user.role || 'member';
    const password = document.getElementById('password');
    password.required = false;
    password.placeholder = 'Leave blank to keep current password';
    document.getElementById('password_hint').innerText = 'Optional - enter a new password (8+ characters) to reset it';
    document.getElementById('user_submit').innerText = 'Save Changes';
    markClean(form);
    scrollToCard('user_form_title', 100);
    document.getElementById('username').focus({ preventScroll: true });
}

function resetUserForm() {
    const form = document.getElementById('userForm');
    document.getElementById('user_form_title').innerText = 'Add someone manually';
    form.action = form.dataset.defaultAction;
    delete form.dataset.mode;
    form.reset();
    const password = document.getElementById('password');
    password.required = true;
    password.placeholder = 'Enter secure password';
    document.getElementById('password_hint').innerText = 'Minimum 8 characters';
    document.getElementById('user_submit').innerText = 'Create User';
    markClean(form);
}

function copyResetLink() {
    const input = document.getElementById('reset_link_output');
    if (!input) return;
    input.select();
    const finish = (ok) => Admin.notify(ok ? 'Reset link copied' : 'Copy failed - select and copy manually', ok ? 'success' : 'error');
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

// --- Loading overlay, delete confirmation, search -----------------------------------

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

function confirmDelete(form, type) {
    Dialog.confirm({
        title: `Delete ${type}`,
        message: `Are you sure you want to delete this ${type}? This action cannot be undone.`,
        confirmLabel: 'Delete',
    }).then(confirmed => {
        if (!confirmed) return;
        lockSubmit(form);
        showLoading();
        form.submit();
    });
}

// Search only the tab the admin is looking at; matches in hidden tabs used to
// hide every card on the current tab and leave it blank.
function searchAdminContent() {
    const term = document.getElementById('adminSearch').value.trim().toLowerCase();
    const panel = document.querySelector('.admin-panel:not([hidden])');
    if (!panel) return;
    const cards = Array.from(panel.querySelectorAll('.admin-card'));
    let shown = 0;
    cards.forEach(card => {
        const match = !term || card.textContent.toLowerCase().includes(term);
        card.classList.toggle('is-hidden', !match);
        if (match) shown++;
    });
    let empty = panel.querySelector('.admin-search-empty');
    if (!shown && term) {
        if (!empty) {
            empty = el('p', { className: 'admin-search-empty', role: 'status' });
            panel.append(empty);
        }
        empty.textContent = `Nothing on this tab matches "${term}".`;
    } else if (empty) {
        empty.remove();
    }
}

// --- Notifications and list filters ---------------------------------------------------

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
        stack.append(toast);
        setTimeout(dismiss, action ? 9000 : 5000);
    },

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

// --- Image previews -----------------------------------------------------------------

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
        preview.replaceChildren(el('img', { src: e.target.result, alt: 'Preview', className: 'member-photo-thumb' }));
        preview.classList.add('is-visible');
    };
    reader.readAsDataURL(file);
}

// --- User form validation -------------------------------------------------------------

document.getElementById('userForm')?.addEventListener('submit', function (e) {
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm_password').value;
    const editing = this.dataset.mode === 'edit';

    if (editing && !password && !confirmPassword) return;

    if (password !== confirmPassword) {
        e.preventDefault();
        Admin.notify('Passwords do not match!', 'error');
        return;
    }

    if (password.length < 8) {
        e.preventDefault();
        Admin.notify('Password must be at least 8 characters long', 'error');
    }
});

// --- Help -------------------------------------------------------------------------------

function showHelp() {
    Dialog.alert({
        title: 'Admin Dashboard Help',
        html: `
            <p><strong>Saving:</strong> Numbers, event fields, roles and team pages save the moment you change them. A green tick means it worked; a red mark means it did not, and the old value comes back.</p>
            <p><strong>People:</strong> Approve sign-ups at the top of the People tab. Drag cards between team columns, or use each card's <em>Move to</em> menu. Every move has an Undo.</p>
            <p><strong>Teams:</strong> Click a team to open its editor. Anyone on a team's roster can edit that team's page, too.</p>
            <p><strong>Tabs:</strong> Each tab's link is shareable. The search box filters the tab you are on.</p>
            <p><strong>Need more help?</strong> Contact the system administrator.</p>
        `,
        confirmLabel: 'Got it!',
    });
}

// --- Dialog ---------------------------------------------------------------------------------

const Dialog = (function () {
    let dialogEl, titleEl, messageEl, confirmBtn, cancelBtn, lastFocused, resolvePromise;

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
        if (lastFocused) lastFocused.focus();
        if (resolvePromise) {
            const resolve = resolvePromise;
            resolvePromise = null;
            resolve(result);
        }
    }

    // `message` is plain text. `html` is for the static help copy only; nothing
    // user-supplied may be passed through it.
    function open({ title, message, html, confirmLabel, cancelLabel, showCancel }) {
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
        titleEl.textContent = title || '';
        if (html) messageEl.innerHTML = html;
        else messageEl.textContent = message || '';
        confirmBtn.textContent = confirmLabel;
        cancelBtn.textContent = cancelLabel || 'Cancel';
        cancelBtn.hidden = !showCancel;
        dialogEl.hidden = false;
        confirmBtn.focus();
        return new Promise(resolve => {
            resolvePromise = resolve;
        });
    }

    function confirmDialog({ title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel' } = {}) {
        return open({ title, message, confirmLabel, cancelLabel, showCancel: true });
    }

    function alertDialog({ title, message, html, confirmLabel = 'OK' } = {}) {
        return open({ title, message, html, confirmLabel, showCancel: false });
    }

    return { confirm: confirmDialog, alert: alertDialog };
})();

// --- Tabs --------------------------------------------------------------------------------------

const AdminTabs = (function () {
    const DEFAULT_TAB = 'stats';

    function tabs() {
        return Array.from(document.querySelectorAll('.admin-tabs [role="tab"]'));
    }

    function panels() {
        return Array.from(document.querySelectorAll('.admin-panel'));
    }

    function currentTab() {
        const hash = location.hash.replace('#', '');
        const valid = tabs().some(t => t.dataset.tab === hash);
        return valid ? hash : DEFAULT_TAB;
    }

    function show(name) {
        tabs().forEach(tab => {
            const active = tab.dataset.tab === name;
            tab.setAttribute('aria-selected', active ? 'true' : 'false');
            tab.tabIndex = active ? 0 : -1;
        });
        panels().forEach(panel => {
            panel.hidden = panel.dataset.panel !== name;
        });
        const search = document.getElementById('adminSearch');
        if (search && search.value) searchAdminContent();
    }

    function go(name) {
        if (location.hash === '#' + name) {
            show(name);
        } else {
            location.hash = name;
        }
    }

    function onHashChange() {
        show(currentTab());
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
            tab.addEventListener('click', function (e) {
                e.preventDefault();
                go(tab.dataset.tab);
            });
        });
        document.querySelector('.admin-tabs')?.addEventListener('keydown', onKeydown);
        window.addEventListener('hashchange', onHashChange);
        show(currentTab());
    }

    return { init, go };
})();

// --- Delegated wiring ------------------------------------------------------------------------------

// Quick-action links: switch tab and start a blank form, asking first if the
// admin has unsaved edits in it.
const QUICK_ADD = {
    events: ['event_form', resetEventForm],
    teams: ['team_form', resetTeamForm],
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
    const trigger = e.target.closest('[data-action]');
    if (!trigger) return;
    const action = trigger.dataset.action;

    if (action === 'quick-add') {
        e.preventDefault();
        const [formId, reset] = QUICK_ADD[trigger.dataset.tab];
        guarded(formId, () => {
            AdminTabs.go(trigger.dataset.tab);
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
        AdminTabs.go(trigger.dataset.tab);
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
    }
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
    if (target.dataset.previewTarget) {
        previewImage(target, target.dataset.previewTarget);
    }
    if (target.form && DIRTY_FORMS.includes(target.form.id)) target.form.dataset.dirty = '1';

    if (target.matches('[data-role-user-id]')) Roles.change(target);
    if (target.matches('.roster-move')) Roster.moveFromSelect(target);
});

document.addEventListener('submit', function (e) {
    const form = e.target;
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

// --- Page setup ---------------------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    AdminTabs.init();
    initMessagesPanel();
    Autosave.init();
    TeamAwards.init();
    Roster.init();
    Admin.attachListFilter('#events_filter', '#panel-events .event-item');
    Admin.attachListFilter('#awards_filter', '#panel-awards .award-item');
    Admin.attachListFilter('#teams_filter', '#panel-teams .data-list > .data-item');
    Admin.attachListFilter('#sponsors_filter', '#panel-sponsors .data-list > .data-item');

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

    document.querySelectorAll('#toast-stack .status-msg').forEach(toast => {
        setTimeout(() => {
            toast.classList.add('is-leaving');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        }, 5000);
    });
});

// --- Contact messages panel ---------------------------------------------------------------------------

function initMessagesPanel() {
    const panel = document.getElementById('panel-messages');
    if (!panel) return;

    const items = Array.from(panel.querySelectorAll('.message-item'));
    const filters = panel.querySelectorAll('.message-filter');

    filters.forEach(button => {
        button.addEventListener('click', () => {
            filters.forEach(b => {
                b.classList.toggle('active', b === button);
                b.setAttribute('aria-pressed', String(b === button));
            });
            const wanted = button.dataset.status;
            items.forEach(item => {
                item.hidden = Boolean(wanted) && item.dataset.status !== wanted;
            });
        });
    });

    panel.querySelectorAll('.message-toggle').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const body = document.getElementById(toggle.getAttribute('aria-controls'));
            if (!body) return;
            const open = body.hidden;
            body.hidden = !open;
            toggle.setAttribute('aria-expanded', String(open));
        });
    });
}

// --- JSON calls ----------------------------------------------------------------------------------------

// POST JSON to the admin API. Resolves with the parsed body, rejects with an
// Error whose message is the server's user-facing text.
async function api(url, body = {}) {
    let response;
    try {
        response = await fetch(url, {
            method: 'POST',
            headers: jsonHeaders(),
            credentials: 'same-origin',
            body: JSON.stringify(body),
        });
    } catch (err) {
        throw new Error('Could not reach the server. Check your connection.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Save failed (${response.status}).`);
    return data;
}

// --- Autosave: stat steppers, award steppers, inline event fields --------------------------------------

const AUTOSAVE_FIELDS = '[data-stat-field], [data-award-id], [data-event-field]';

const Autosave = (function () {
    const timers = new Map();
    let inFlight = 0;

    function mark(input, state) {
        const holder = input.closest('.stepper, .event-inline');
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
        const row = input.closest('[data-event-id]');
        return api(`/admin/api/events/${row.dataset.eventId}`, { field: input.dataset.eventField, value: input.value });
    }

    function save(input) {
        if (input.value === input.dataset.saved) return;
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
            if (!button) return;
            const input = button.parentElement.querySelector('input');
            input.value = String(Math.max(0, (parseInt(input.value, 10) || 0) + Number(button.dataset.step)));
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

        // Enter commits an inline event field; Escape puts the saved value back.
        document.addEventListener('keydown', e => {
            if (!e.target.matches('[data-event-field]')) return;
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

// --- Team awards: pick a team chip, edit its counts with steppers --------------------------------------

const TeamAwards = (function () {
    let awards = [];

    function stepperFor(award) {
        const input = el('input', {
            id: `team-award-${award._id}`, type: 'number', min: '0', inputmode: 'numeric',
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

    function show(teamNumber) {
        document.querySelectorAll('[data-team-awards]').forEach(chip => {
            chip.setAttribute('aria-pressed', String(chip.dataset.teamAwards === teamNumber));
        });
        const rows = awards.filter(a => String(a.team_number) === teamNumber);
        document.getElementById('team_awards_list').replaceChildren(...(rows.length
            ? rows.map(a => el('div', { className: 'data-item award-item' }, [
                el('span', { className: 'award-name', text: a.title }),
                stepperFor(a),
            ]))
            : [el('p', { className: 'list-empty', text: 'This team has no award categories yet.' })]));
        document.getElementById('no_team_msg').hidden = true;
    }

    function init() {
        const data = document.getElementById('team_awards_data');
        if (!data) return;
        awards = JSON.parse(data.textContent);
        document.querySelectorAll('[data-team-awards]').forEach(chip => {
            chip.addEventListener('click', () => show(chip.dataset.teamAwards));
        });
    }

    // Keep the local copy current so switching teams and back shows the saved counts.
    function remember(id, count) {
        const award = awards.find(a => a._id === id);
        if (award) award.count = count;
    }

    return { init, remember };
})();

// --- Sign-up approvals and inline roles ------------------------------------------------------------------

const Approvals = {
    approve(item) {
        const role = item.querySelector('[data-approve-role]').value;
        const teamId = item.querySelector('[data-approve-team]').value;
        const name = item.querySelector('strong').textContent;
        item.classList.add('is-busy');
        api(`/admin/api/users/${item.dataset.userId}/approve`, { role, team_id: teamId || null })
            .then(() => {
                Admin.notify(`${name} approved${teamId ? ' and added to the roster' : ''}. Refreshing…`, 'success');
                // The board and the account list are both server-rendered; reload rather than patch both.
                setTimeout(() => location.reload(), 1200);
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

// --- Roster board: drag and drop, Move-to menu, Undo -------------------------------------------------------
//
// Team columns hold roster cards (data-member-id, plus data-user-id when the
// person has a login). The Unassigned column holds accounts (data-user-id
// only). Only people with a login can go to Unassigned; removing someone
// without one is a team-editor job, where it gets a confirmation.

const Roster = (function () {
    let dragged = null;

    const columns = () => Array.from(document.querySelectorAll('.roster-col'));
    const columnFor = teamId => columns().find(col => (col.dataset.teamId || null) === (teamId || null));
    const teamOf = card => card.closest('.roster-col').dataset.teamId || null;
    const labelOf = col => col.querySelector('.roster-col-head strong').textContent;
    const canGo = (card, teamId) => Boolean(teamId) || Boolean(card.dataset.userId);

    function recount() {
        columns().forEach(col => {
            col.querySelector('.roster-count').textContent = col.querySelectorAll('.roster-card').length;
        });
    }

    // Rebuild a card's Move-to menu for the column it now sits in.
    function refreshMenu(card) {
        const here = teamOf(card);
        const options = [el('option', { value: '', text: 'Move to…', selected: true, disabled: true })];
        columns().forEach(col => {
            const id = col.dataset.teamId || null;
            if (id === here || !canGo(card, id)) return;
            options.push(el('option', { value: id || 'none', text: labelOf(col) }));
        });
        card.querySelector('.roster-move').replaceChildren(...options);
    }

    function place(card, teamId) {
        columnFor(teamId).querySelector('.roster-drop').append(card);
        refreshMenu(card);
        recount();
    }

    function move(card, toTeamId, undoable = true) {
        const from = teamOf(card);
        const to = toTeamId || null;
        if (to === from || !canGo(card, to) || !columnFor(to)) return;

        const body = { to_team_id: to };
        if (card.dataset.memberId) body.member_id = card.dataset.memberId;
        else body.user_id = card.dataset.userId;

        place(card, to);
        card.classList.add('is-busy');
        api('/admin/api/roster/move', body)
            .then(data => {
                card.classList.remove('is-busy');
                if (to) card.dataset.memberId = data.member.member_id;
                else delete card.dataset.memberId;
                Admin.notify(`${card.dataset.name} moved to ${labelOf(columnFor(to))}.`, 'success',
                    undoable ? { label: 'Undo', run: () => move(card, from, false) } : null);
            })
            .catch(err => {
                card.classList.remove('is-busy');
                place(card, from);
                Admin.notify(err.message, 'error');
            });
    }

    function moveFromSelect(select) {
        const value = select.value;
        select.value = '';
        move(select.closest('.roster-card'), value === 'none' ? null : value);
    }

    function clearHover() {
        document.querySelectorAll('.roster-col.is-over').forEach(col => col.classList.remove('is-over'));
    }

    function init() {
        const board = document.getElementById('rosterBoard');
        if (!board) return;

        board.addEventListener('dragstart', e => {
            dragged = e.target.closest('.roster-card');
            if (!dragged) return;
            e.dataTransfer.effectAllowed = 'move';
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

    return { init, moveFromSelect };
})();
