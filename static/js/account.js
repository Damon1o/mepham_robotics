// Account page: two-step QR code, backup code copy/download/print, the section
// nav's current-section highlight, the password strength meter, the profile's
// password prompt for a new email, and the theme picker.

(function drawSetupQr() {
    const box = document.querySelector('[data-qr]');
    if (!box || typeof qrcode !== 'function') return;
    const qr = qrcode(0, 'M');
    qr.addData(box.dataset.qr);
    qr.make();
    // The library builds the SVG from the otpauth link alone, so it is safe to insert.
    box.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
})();

// --- Backup codes -------------------------------------------------------------

function flashLabel(button, text) {
    const label = button.querySelector('span');
    const before = label.textContent;
    label.textContent = text;
    setTimeout(() => { label.textContent = before; }, 2000);
}

document.querySelectorAll('[data-copy-codes]').forEach(button => {
    button.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(button.dataset.copyCodes);
            flashLabel(button, 'Copied');
        } catch (err) {
            flashLabel(button, 'Select and copy them above');
        }
    });
});

document.querySelectorAll('[data-download-codes]').forEach(button => {
    button.addEventListener('click', () => {
        const text = [
            `Mepham Robotics backup codes for @${button.dataset.account}`,
            'Each code signs you in once when you cannot use your authenticator app.',
            '',
            button.dataset.downloadCodes,
            '',
        ].join('\n');
        const link = document.createElement('a');
        link.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
        link.download = 'mepham-backup-codes.txt';
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
        flashLabel(button, 'Downloaded');
    });
});

document.querySelectorAll('[data-print-codes]').forEach(button => {
    button.addEventListener('click', () => {
        document.body.classList.add('is-printing-codes');
        window.print();
    });
});
window.addEventListener('afterprint', () => document.body.classList.remove('is-printing-codes'));

// --- Section nav --------------------------------------------------------------

(function sectionNav() {
    const links = [...document.querySelectorAll('[data-acct-link]')];
    const panels = links.map(a => document.querySelector(a.hash)).filter(Boolean);
    if (!panels.length) return;
    const strip = links[0].closest('ul');
    let current = null;
    const mark = panel => {
        if (panel === current) return;
        current = panel;
        links.forEach(a => {
            const on = a.hash === `#${panel.id}`;
            a.classList.toggle('is-current', on);
            if (on) a.setAttribute('aria-current', 'true');
            else a.removeAttribute('aria-current');
            // On the phone strip, slide the active chip into view without moving the page.
            if (on && strip.scrollWidth > strip.clientWidth) {
                strip.scrollTo({ left: a.offsetLeft - strip.clientWidth / 2 + a.offsetWidth / 2, behavior: 'smooth' });
            }
        });
    };
    // The current section is the last one whose top has passed a third of the way down the
    // screen, except that a last panel already fully on screen wins, since it can't scroll that high.
    const pick = () => {
        const line = window.innerHeight / 3;
        const last = panels[panels.length - 1].getBoundingClientRect();
        if (last.bottom <= window.innerHeight && last.top < window.innerHeight * 0.8) {
            mark(panels[panels.length - 1]);
            return;
        }
        mark(panels.filter(p => p.getBoundingClientRect().top <= line).pop() || panels[0]);
    };
    let queued = false;
    window.addEventListener('scroll', () => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; pick(); });
    }, { passive: true });
    pick();
})();

// --- Password strength ---------------------------------------------------------

(function strengthMeter() {
    const meter = document.querySelector('.acct-strength');
    const input = document.getElementById('new_password');
    if (!meter || !input) return;
    const label = meter.querySelector('.acct-strength-label');
    const min = Number(meter.dataset.min) || 8;
    const words = ['', 'Weak', 'Okay', 'Good', 'Strong'];

    // A rough guide, not a gate: length matters most, variety and repeats nudge it.
    function score(pw) {
        if (pw.length < min) return pw ? 1 : 0;
        let points = 1;
        if (pw.length >= 12) points++;
        if (pw.length >= 16) points++;
        const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(r => r.test(pw)).length;
        if (kinds >= 3) points++;
        if (/(.)\1{2,}/.test(pw) || /^(?:password|12345678|qwerty)/i.test(pw)) points--;
        return Math.max(1, Math.min(4, points));
    }

    input.addEventListener('input', () => {
        const s = score(input.value);
        meter.dataset.strength = String(s);
        label.textContent = !input.value ? `At least ${min} characters`
            : input.value.length < min ? `${min - input.value.length} more character${min - input.value.length === 1 ? '' : 's'}`
            : words[s];
    });
})();

// --- Profile: a new email asks for the password ------------------------------------

(function emailPassword() {
    const form = document.querySelector('[data-profile-form]');
    if (!form) return;
    const email = form.querySelector('#email');
    const box = form.querySelector('[data-email-password]');
    const password = box.querySelector('input');
    const sync = () => {
        const changed = email.value.trim().toLowerCase() !== email.dataset.original.toLowerCase();
        box.hidden = !changed;
        password.required = changed;
    };
    email.addEventListener('input', sync);
    sync();
})();

// --- Theme picker ---------------------------------------------------------------

(function themePicker() {
    const picker = document.querySelector('[data-theme-picker]');
    if (!picker || !window.MephamTheme) return;
    const current = picker.querySelector(`input[value="${window.MephamTheme.get()}"]`);
    if (current) current.checked = true;
    picker.addEventListener('change', e => {
        window.MephamTheme.set(e.target.value);
        // The footer toggle shows the theme's name; keep it in step.
        if (typeof paintThemeLabel === 'function') paintThemeLabel();
    });
})();
