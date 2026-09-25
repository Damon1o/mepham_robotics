// Auth pages: password visibility toggle, confirm-password match, single submit
document.querySelectorAll('.password-toggle').forEach(button => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input) return;
    button.addEventListener('click', () => {
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(show));
        button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    });
});

// Any auth form with a confirm field (reset password, sign-up) checks the match live.
const confirmForm = document.querySelector('.auth-form #confirm_password')?.form;
if (confirmForm) {
    const password = confirmForm.querySelector('#password');
    const confirm = confirmForm.querySelector('#confirm_password');
    const checkMatch = () => {
        confirm.setCustomValidity(confirm.value && confirm.value !== password.value ? 'Passwords do not match.' : '');
    };
    password.addEventListener('input', checkMatch);
    confirm.addEventListener('input', checkMatch);
}

document.querySelectorAll('.auth-form').forEach(form => {
    form.addEventListener('submit', () => {
        const submit = form.querySelector('[type="submit"]');
        if (submit) submit.disabled = true;
    });
});

// Re-enable buttons when the page is restored from the back/forward cache
window.addEventListener('pageshow', () => {
    document.querySelectorAll('.auth-form [type="submit"]').forEach(button => {
        button.disabled = false;
    });
});
