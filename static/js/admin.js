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

// --- Events -------------------------------------------------------------------

function editEvent(button) {
    const form = document.getElementById('event_form');
    document.getElementById('event_form_title').innerText = 'Edit Event';
    form.action = button.dataset.updateUrl;
    form.querySelector('[name="comp_name"]').value = button.dataset.name;
    form.querySelector('[name="comp_location"]').value = button.dataset.location;
    form.querySelector('[name="comp_date"]').value = button.dataset.date;
    markClean(form);
    scrollToCard('event_form', 100);
}

function resetEventForm() {
    const form = document.getElementById('event_form');
    document.getElementById('event_form_title').innerText = 'Add New Event';
    form.action = form.dataset.defaultAction;
    form.reset();
    markClean(form);
}

// --- Teams: member and goal rows ------------------------------------------------

// Row indexes only need to be unique: the server collects every
// member_name_<n> / goal_name_<n> present and orders them by <n>, so deleting
// a row in the middle can no longer truncate the list.
let memberCount = 0;
let goalCount = 0;
const DEFAULT_MEMBER_PHOTO = 'static/assets/other/base.png';

// Stored photos are either Blob URLs or repo-relative static paths.
function photoSrc(photo) {
    return /^https?:\/\//.test(photo) ? photo : '/' + photo.replace(/^\/+/, '');
}

function removeButton(label) {
    return el('button', {
        type: 'button', className: 'remove-btn', 'aria-label': label,
        dataset: { action: 'remove-row' }, text: '×',
    });
}

function addMemberRow(data = {}) {
    const i = memberCount++;
    const photo = data.photo && !data.photo.endsWith('/base.png') ? data.photo : '';

    const name = el('input', { type: 'text', id: `member_name_${i}`, name: `member_name_${i}`, value: data.name || '', required: true });
    const role = el('input', { type: 'text', id: `member_role_${i}`, name: `member_role_${i}`, value: data.role || '', required: true });

    const account = el('select', { id: `member_user_${i}`, name: `member_user_${i}` },
        [el('option', { value: '', text: '-- No link --' })]);
    const users = JSON.parse(document.getElementById('admin_users_data').textContent);
    users.forEach(u => {
        account.append(el('option', {
            value: u._id,
            text: `${u.username} (${u.role})`,
            selected: data.user_id === u._id,
        }));
    });

    const file = el('input', {
        type: 'file', id: `member_photo_${i}`, name: `member_photo_${i}`, accept: 'image/*',
        dataset: { previewTarget: `member_preview_${i}` },
    });
    const preview = el('div', { className: 'image-preview', id: `member_preview_${i}` });
    if (photo) {
        preview.append(el('img', { src: photoSrc(photo), alt: 'Current photo', className: 'member-photo-thumb' }));
        preview.classList.add('is-visible');
    }

    const row = el('div', { className: 'dynamic-row' }, [
        removeButton('Remove member'),
        el('input', { type: 'hidden', name: `member_photo_path_${i}`, value: photo || DEFAULT_MEMBER_PHOTO }),
        field('Member Name', name),
        field('Role', role),
        field('Link User Account (Optional)', account),
        el('div', { className: 'form-group' }, [
            el('label', { for: file.id, text: `Profile Image (${photo ? 'current photo kept unless replaced' : 'default used'})` }),
            file,
            preview,
        ]),
    ]);
    document.getElementById('members_container').append(row);
    return row;
}

function addGoalRow(data = {}) {
    const i = goalCount++;
    const progress = Number.isFinite(Number(data.progress)) ? Number(data.progress) : 0;

    const name = el('input', { type: 'text', id: `goal_name_${i}`, name: `goal_name_${i}`, value: data.name || '', required: true });
    const range = el('input', {
        type: 'range', id: `goal_progress_${i}`, name: `goal_progress_${i}`,
        min: '0', max: '100', value: String(progress),
        dataset: { progressLabel: `goal_progress_label_${i}` },
    });
    const rangeLabel = el('label', { for: range.id, id: `goal_progress_label_${i}`, text: `Progress (${progress}%)` });

    const row = el('div', { className: 'dynamic-row' }, [
        removeButton('Remove goal'),
        field('Goal Name', name),
        el('div', { className: 'form-group' }, [rangeLabel, range]),
    ]);
    document.getElementById('goals_container').append(row);
    return row;
}

function editTeam(button) {
    const team = JSON.parse(button.dataset.team);
    const specs = team.specs || {};
    const form = document.getElementById('team_form');

    document.getElementById('team_form_title').innerText = 'Edit Team ' + team.team_number;
    document.getElementById('team_id').value = team._id;
    form.querySelector('[name="team_number"]').value = team.team_number || '';
    form.querySelector('[name="nickname"]').value = team.nickname || '';
    form.querySelector('[name="tagline"]').value = team.tagline || '';
    form.querySelector('[name="drive_train"]').value = specs.drive_train || '';
    form.querySelector('[name="lift_system"]').value = specs.lift_system || '';
    form.querySelector('[name="intake"]').value = specs.intake || '';
    form.querySelector('[name="auton_consistency"]').value = specs.auton_consistency || '';
    form.querySelector('[name="notebook_link"]').value = team.notebook_link || '';

    document.getElementById('members_container').replaceChildren();
    memberCount = 0;
    (team.members || []).forEach(m => addMemberRow(m));

    document.getElementById('goals_container').replaceChildren();
    goalCount = 0;
    (team.goals || []).forEach(g => addGoalRow(g));

    markClean(form);
    scrollToCard('team_form_card');
}

function resetTeamForm() {
    const form = document.getElementById('team_form');
    document.getElementById('team_form_title').innerText = 'Create New Team';
    document.getElementById('team_id').value = '';
    form.reset();
    document.getElementById('members_container').replaceChildren();
    document.getElementById('goals_container').replaceChildren();
    document.getElementById('heroImagePreview')?.replaceChildren();
    memberCount = 0;
    goalCount = 0;
    markClean(form);
}

// --- Sponsors -------------------------------------------------------------------

function editSponsor(button) {
    const form = document.getElementById('sponsor_form');
    document.getElementById('sponsor_form_title').innerText = 'Edit Sponsor';
    document.getElementById('sponsor_id').value = button.dataset.id;
    form.querySelector('[name="name"]').value = button.dataset.name;
    form.querySelector('[name="website"]').value = button.dataset.website;
    form.querySelector('[name="level"]').value = button.dataset.level;
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
    document.getElementById('user_form_title').innerText = 'Edit User: ' + user.username;
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
    document.getElementById('user_form_title').innerText = 'Create New User';
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

// --- Team awards ------------------------------------------------------------------

function teamAwardInputs() {
    return Array.from(document.querySelectorAll('#team_awards_list input[type="number"]'));
}

function teamAwardsDirty() {
    return teamAwardInputs().some(input => input.value !== input.dataset.original);
}

function showTeamAwards(teamNum) {
    const teamAwards = JSON.parse(document.getElementById('team_awards_data').textContent);
    const container = document.getElementById('team_awards_list');
    const form = document.getElementById('team_awards_form');
    const msg = document.getElementById('no_team_msg');

    if (!teamNum) {
        form.hidden = true;
        msg.hidden = false;
        return;
    }

    container.replaceChildren();
    const filtered = teamAwards.filter(a => String(a.team_number) === String(teamNum));

    if (filtered.length === 0) {
        container.append(el('p', {
            className: 'team-awards-empty',
            text: 'No awards found for this team. Please seed them first.',
        }));
    } else {
        filtered.forEach(award => {
            const count = String(award.count ?? 0);
            const input = el('input', {
                type: 'number', name: `team_award_${award._id}`, min: '0', value: count,
                className: 'team-award-input', 'aria-label': `${award.title} count`,
                dataset: { original: count },
            });
            container.append(el('div', { className: 'award-item' }, [
                el('span', { className: 'team-award-title', text: award.title }),
                input,
            ]));
        });
    }

    form.hidden = false;
    msg.hidden = true;
}

// "Reset Changes" restores the counts as loaded. It used to set every count
// to zero, which one Save then wrote over the team's whole award history.
function resetTeamAwards() {
    teamAwardInputs().forEach(input => {
        input.value = input.dataset.original;
    });
    Admin.notify('Team award counts restored', 'info');
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
    notify(message, category = 'info') {
        const stack = document.getElementById('toast-stack');
        if (!stack) return;

        const toast = el('div', { className: `status-msg ${category}`, text: message });
        stack.append(toast);

        setTimeout(() => {
            toast.classList.add('is-leaving');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        }, 5000);
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
            <p><strong>Tabs:</strong> Use the tab bar to jump between sections; each tab's link is shareable.</p>
            <p><strong>Search:</strong> The search box filters the tab you are on. Each panel also has its own filter box.</p>
            <p><strong>Unsaved changes:</strong> You will be asked before a form with unsaved edits is cleared.</p>
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
    'reset-event': ['event_form', resetEventForm],
    'reset-team': ['team_form', resetTeamForm],
    'reset-sponsor': ['sponsor_form', resetSponsorForm],
    'reset-user': ['userForm', resetUserForm],
};

const EDITS = {
    'edit-event': ['event_form', editEvent],
    'edit-team': ['team_form', editTeam],
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
    } else if (action === 'remove-row') {
        const form = trigger.closest('form');
        trigger.closest('.dynamic-row')?.remove();
        if (form) form.dataset.dirty = '1';
    } else if (action === 'add-member') {
        addMemberRow().querySelector('input[type="text"]')?.focus();
    } else if (action === 'add-goal') {
        addGoalRow().querySelector('input[type="text"]')?.focus();
    } else if (action === 'reset-team-awards') {
        resetTeamAwards();
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
    if (target.dataset.progressLabel) {
        const label = document.getElementById(target.dataset.progressLabel);
        if (label) label.textContent = `Progress (${target.value}%)`;
    }
    const form = target.form;
    if (form && DIRTY_FORMS.includes(form.id)) form.dataset.dirty = '1';
});

// The team selector swaps the award list, so check for unsaved counts first
// and put the selector back if the admin keeps editing.
let currentTeamSelection = '';

document.addEventListener('change', function (e) {
    const target = e.target;
    if (target.dataset.previewTarget) {
        previewImage(target, target.dataset.previewTarget);
    }
    if (target.form && DIRTY_FORMS.includes(target.form.id)) target.form.dataset.dirty = '1';

    if (target.id === 'team_selector') {
        const wanted = target.value;
        if (!teamAwardsDirty()) {
            currentTeamSelection = wanted;
            showTeamAwards(wanted);
            return;
        }
        target.value = currentTeamSelection;
        Dialog.confirm({
            title: 'Discard unsaved award counts?',
            message: 'The counts you changed for this team have not been saved.',
            confirmLabel: 'Discard',
        }).then(ok => {
            if (!ok) return;
            target.value = wanted;
            currentTeamSelection = wanted;
            showTeamAwards(wanted);
        });
    }
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
    const dirty = DIRTY_FORMS.some(id => isDirty(document.getElementById(id))) || teamAwardsDirty();
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
