// Extracted from templates/admin.html inline <script> blocks
function editEvent(id, name, location, dateStr) {
    document.getElementById('event_form_title').innerText = 'Edit Event';
    document.getElementById('event_form').action = '/admin/update-competition/' + id;
    document.getElementsByName('comp_name')[0].value = name;
    document.getElementsByName('comp_location')[0].value = location;
    document.getElementsByName('comp_date')[0].value = dateStr;
    window.scrollTo({ top: document.getElementById('event_form').offsetTop - 100, behavior: 'smooth' });
}

function resetEventForm() {
    document.getElementById('event_form_title').innerText = 'Add New Event';
    document.getElementById('event_form').action = document.getElementById('event_form').dataset.defaultAction;
    document.getElementById('event_form').reset();
}

let memberCount = 0;
function addMemberRow(data = {}) {
    const container = document.getElementById('members_container');
    const i = memberCount++;
    const row = document.createElement('div');
    row.className = 'dynamic-row';
    row.innerHTML = `
        <button type="button" class="remove-btn" onclick="this.parentElement.remove()">&times;</button>
        <input type="hidden" name="member_photo_path_${i}" value="${data.photo || 'static/assets/profile/base.png'}">
        <div class="form-group">
            <label>Member Name</label>
            <input type="text" name="member_name_${i}" value="${data.name || ''}" required>
        </div>
        <div class="form-group">
            <label>Role</label>
            <input type="text" name="member_role_${i}" value="${data.role || ''}" required>
        </div>
        <div class="form-group">
            <label>Link User Account (Optional)</label>
            <select name="member_user_${i}">
                <option value="">-- No link --</option>
            </select>
        </div>
        <div class="form-group">
            <label>Profile Image (${data.photo ? 'Current exists' : 'Default used'})</label>
            <input type="file" name="member_photo_${i}" accept="image/*" onchange="previewMemberImage(this, ${i})">
            ${data.photo ? `<div class="image-preview" id="member_preview_${i}"><img src="${data.photo}" alt="Current photo" style="max-width: 100px; max-height: 100px;"></div>` : ''}
        </div>
    `;

    const users = JSON.parse(document.getElementById('admin_users_data').textContent);
    const select = row.querySelector(`select[name="member_user_${i}"]`);
    users.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u._id;
        opt.textContent = u.username;
        if (data.user_id === u._id) opt.selected = true;
        select.appendChild(opt);
    });

    container.appendChild(row);
}

let goalCount = 0;
function addGoalRow(data = {}) {
    const container = document.getElementById('goals_container');
    const i = goalCount++;
    const row = document.createElement('div');
    row.className = 'dynamic-row';
    row.innerHTML = `
        <button type="button" class="remove-btn" onclick="this.parentElement.remove()">&times;</button>
        <div class="form-group">
            <label>Goal Name</label>
            <input type="text" name="goal_name_${i}" value="${data.name || ''}" required>
        </div>
        <div class="form-group">
            <label>Progress (${data.progress || 0}%)</label>
            <input type="range" name="goal_progress_${i}" value="${data.progress || 0}" min="0" max="100" oninput="this.previousElementSibling.innerText = 'Progress (' + this.value + '%)'">
        </div>
    `;
    container.appendChild(row);
}

function editTeam(teamJson) {
    const team = JSON.parse(teamJson);
    document.getElementById('team_form_title').innerText = 'Edit Team ' + team.team_number;
    document.getElementById('team_id').value = team._id;
    document.getElementsByName('team_number')[0].value = team.team_number;
    document.getElementsByName('nickname')[0].value = team.nickname || '';
    document.getElementsByName('tagline')[0].value = team.tagline || '';
    document.getElementsByName('drive_train')[0].value = team.specs.drive_train || '';
    document.getElementsByName('lift_system')[0].value = team.specs.lift_system || '';
    document.getElementsByName('intake')[0].value = team.specs.intake || '';
    document.getElementsByName('auton_consistency')[0].value = team.specs.auton_consistency || '';
    document.getElementsByName('notebook_link')[0].value = team.notebook_link || '#';

    // Clear and rebuild dynamic rows
    document.getElementById('members_container').innerHTML = '';
    memberCount = 0;
    team.members.forEach(m => addMemberRow(m));

    document.getElementById('goals_container').innerHTML = '';
    goalCount = 0;
    team.goals.forEach(g => addGoalRow(g));

    window.scrollTo({ top: document.getElementById('team_form_card').offsetTop - 50, behavior: 'smooth' });
}

function editSponsor(id, name, website, level) {
    document.getElementById('sponsor_form_title').innerText = 'Edit Sponsor';
    document.getElementById('sponsor_form').action = '/admin/save-sponsor';
    document.getElementById('sponsor_id').value = id;
    document.getElementById('sponsor_form').querySelector('[name="name"]').value = name;
    document.getElementsByName('website')[0].value = website;
    document.getElementsByName('level')[0].value = level;
    window.scrollTo({ top: document.getElementById('sponsor_form_card').offsetTop - 50, behavior: 'smooth' });
}

function resetSponsorForm() {
    document.getElementById('sponsor_form_title').innerText = 'Add New Sponsor';
    document.getElementById('sponsor_form').action = '/admin/save-sponsor';
    document.getElementById('sponsor_id').value = '';
    document.getElementById('sponsor_form').reset();
}

function showTeamAwards(teamNum) {
    const teamAwards = JSON.parse(document.getElementById('team_awards_data').textContent);
    const container = document.getElementById('team_awards_list');
    const form = document.getElementById('team_awards_form');
    const msg = document.getElementById('no_team_msg');

    if (!teamNum) {
        form.style.display = 'none';
        msg.style.display = 'block';
        return;
    }

    container.innerHTML = '';
    const filtered = teamAwards.filter(a => a.team_number === teamNum);

    if (filtered.length === 0) {
        container.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #999; padding: 1rem;">No awards found for this team. Please seed them first.</p>';
    } else {
        filtered.forEach(award => {
            const item = document.createElement('div');
            item.className = 'award-item';
            item.innerHTML = `
                <span style="font-size: 0.9rem;">${award.title}</span>
                <input type="number" name="team_award_${award._id}" value="${award.count}" min="0" style="width: 70px; padding: 0.4rem;">
            `;
            container.appendChild(item);
        });
    }

    form.style.display = 'block';
    msg.style.display = 'none';
}

function resetTeamForm() {
    document.getElementById('team_form_title').innerText = 'Create New Team';
    document.getElementById('team_id').value = '';
    document.getElementById('team_form').reset();
    document.getElementById('members_container').innerHTML = '';
    document.getElementById('goals_container').innerHTML = '';
    memberCount = 0;
    goalCount = 0;
}

// New enhanced functions
function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

function confirmDelete(form, type) {
    Dialog.confirm({
        title: `Delete ${type}`,
        message: `Are you sure you want to delete this ${type}? This action cannot be undone.`,
        confirmLabel: 'Delete',
    }).then(confirmed => {
        if (confirmed) form.submit();
    });
    return false;
}

function searchAdminContent() {
    const searchTerm = document.getElementById('adminSearch').value.toLowerCase();
    const cards = document.querySelectorAll('.admin-card');

    cards.forEach(card => {
        const cardContent = card.textContent.toLowerCase();
        if (cardContent.includes(searchTerm)) {
            card.style.display = 'block';
            card.style.animation = 'slideIn 0.3s ease';
        } else {
            card.style.display = 'none';
        }
    });
}

function resetTeamAwards() {
    const inputs = document.querySelectorAll('#team_awards_list input[type="number"]');
    inputs.forEach(input => {
        input.value = 0;
    });
    Admin.notify('Team awards reset to zero', 'info');
}

const Admin = {
    notify(message, category = 'info') {
        const stack = document.getElementById('toast-stack');
        if (!stack) return;

        const toast = document.createElement('div');
        toast.className = `status-msg ${category}`;
        toast.style.display = 'block';
        toast.textContent = message;
        stack.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('is-leaving');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        }, 5000);
    },

    attachListFilter(inputSelector, itemSelector, matchFn) {
        const input = document.querySelector(inputSelector);
        if (!input) return;
        const match = matchFn || ((item, term) => item.textContent.toLowerCase().includes(term));
        input.addEventListener('input', () => {
            const term = input.value.trim().toLowerCase();
            document.querySelectorAll(itemSelector).forEach(item => {
                item.classList.toggle('is-hidden', term !== '' && !match(item, term));
            });
        });
    },
};

// Image preview functionality
function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    const file = input.files[0];

    if (file) {
        const reader = new FileReader();
        reader.onload = function (e) {
            preview.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
            preview.style.display = 'block';
        }
        reader.readAsDataURL(file);
    } else {
        preview.style.display = 'none';
    }
}

// Member image preview functionality
function previewMemberImage(input, index) {
    const previewId = `member_preview_${index}`;
    let preview = document.getElementById(previewId);

    if (!preview) {
        preview = document.createElement('div');
        preview.className = 'image-preview';
        preview.id = previewId;
        input.parentNode.appendChild(preview);
    }

    const file = input.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function (e) {
            preview.innerHTML = `<img src="${e.target.result}" alt="Preview" style="max-width: 100px; max-height: 100px;">`;
            preview.style.display = 'block';
        }
        reader.readAsDataURL(file);
    } else {
        preview.style.display = 'none';
    }
}

// Form validation for user creation
document.getElementById('userForm')?.addEventListener('submit', function (e) {
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm_password').value;

    if (password !== confirmPassword) {
        e.preventDefault();
        Admin.notify('Passwords do not match!', 'error');
        return false;
    }

    if (password.length < 8) {
        e.preventDefault();
        Admin.notify('Password must be at least 8 characters long', 'error');
        return false;
    }

    showLoading();
    return true;
});

// Help functionality
function showHelp() {
    Dialog.alert({
        title: 'Admin Dashboard Help',
        message: `
            <p><strong>Tabs:</strong> Use the tab bar to jump between sections; each tab's link is shareable.</p>
            <p><strong>Search:</strong> Use the search box at the top, or each panel's own filter box, to narrow a list.</p>
            <p><strong>Need more help?</strong> Contact the system administrator.</p>
        `,
        confirmLabel: 'Got it!',
    });
}

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
        const focusable = dialogEl.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
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

    function open({ title, message, confirmLabel, cancelLabel, showCancel }) {
        els();
        lastFocused = document.activeElement;
        titleEl.textContent = title || '';
        messageEl.innerHTML = message || '';
        confirmBtn.textContent = confirmLabel;
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

    function alertDialog({ title, message, confirmLabel = 'OK' } = {}) {
        return open({ title, message, confirmLabel, showCancel: false });
    }

    return { confirm: confirmDialog, alert: alertDialog };
})();

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
        document.querySelector('.admin-tabs').addEventListener('keydown', onKeydown);
        window.addEventListener('hashchange', onHashChange);
        show(currentTab());
    }

    return { init, go };
})();

document.addEventListener('DOMContentLoaded', () => AdminTabs.init());

document.addEventListener('DOMContentLoaded', function () {
    Admin.attachListFilter('#events_filter', '#panel-events .event-item');
    Admin.attachListFilter('#awards_filter', '#panel-awards .award-item');
    Admin.attachListFilter('#teams_filter', '#panel-teams .data-list > .data-item');
    Admin.attachListFilter('#sponsors_filter', '#panel-sponsors .data-list > .data-item');
});

document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('#toast-stack .status-msg').forEach(toast => {
        setTimeout(() => {
            toast.classList.add('is-leaving');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        }, 5000);
    });
});
