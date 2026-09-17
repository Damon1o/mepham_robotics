# Login Page Overhaul — Design Spec

> **Superseded in part, 2026-09-17:** the owner has no Resend account, so email delivery,
> the `RESEND_API_KEY`/`RESEND_FROM` env vars and the public `/forgot-password` page were dropped.
> Reset tokens remain; an admin now generates a reset link from the admin user manager
> (`POST /admin/generate-reset-link/<id>`) and hands it to the person. Optional `PUBLIC_BASE_URL`
> sets the link's host.

Date: 2026-09-16
Scope: `templates/login.html`, new `templates/forgot_password.html` and `templates/reset_password.html`,
`static/css/pages/login.css`, new `static/js/login.js`, auth code in `api/index.py`, form opt-out in
`static/js/script.js`

## Goal

Replace the standalone dark-glass login page with one that matches the main site, and make every control
on it real. Today "Remember me" and "Forgot Password?" do nothing, the field labeled "Email" also accepts
usernames, the illustration half is empty, styles live inline, and there is no protection against
password guessing. The overhaul adds a working password-reset flow over email and login rate limiting.

Out of scope: site-wide CSRF tokens, self sign-up, two-factor auth, and revoking other active sessions
after a password reset.

## Pages

All three templates extend `base.html` (site nav and footer, Balsamiq Sans, maroon and gold). All styles
go in `static/css/pages/login.css`; no `style` attributes or `<style>` blocks in templates. The three
pages share one card component.

### `/login`

Bold bordered card, two columns, stacking to one column under 768px:

- **Left panel:** team photo `static/assets/photos/carousel6.jpg` with a maroon overlay, heading
  "Welcome back, Team 77628", one line of copy: "Sign in to reach member resources and the admin
  dashboard."
- **Right panel:** heading "Member Login", then:
  - "Username or email" text field (`autocomplete="username"`)
  - "Password" field (`autocomplete="current-password"`) with a show/hide toggle button
    (`aria-pressed`, Lucide `eye` / `eye-off`)
  - "Remember me" checkbox (`name="remember"`)
  - "Forgot password?" link to `/forgot-password`
  - "Sign in" submit button
  - Error area (`role="alert"`) for bad credentials or lockout
  - Hidden `next` field carrying the post-login destination

A visitor who is already signed in and requests `GET /login` is redirected to the `next` target, or `/`.

### `/forgot-password`

Same card, single column. One email field and a "Send reset link" button. After any submission the page
shows the same confirmation: "If an account with that email exists, we've sent a reset link. It expires
in 1 hour. No email on your account? Ask an admin to reset your password." The response never reveals
whether the email matched.

### `/reset-password/<token>`

Same card, single column. "New password" and "Confirm password" fields (8+ characters, must match,
checked on both client and server). An invalid, expired, or used token renders an error state with a link
to `/forgot-password` instead of the form. Success clears the token, flashes "Password updated. Sign in
with your new password.", and redirects to `/login`.

## Behavior

### Sign in

- Lookup by `username` or `email`, as today.
- On success: `session.clear()` first (prevents session fixation), then set `user` and `role`.
- **Remember me:** checked sets `session.permanent = True` with `PERMANENT_SESSION_LIFETIME` of 30 days;
  unchecked leaves a browser-session cookie.
- **Cookie flags:** `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = 'Lax'`,
  `SESSION_COOKIE_SECURE = True` when the `VERCEL` env var is set (production and previews), off locally.
- **Redirect after login:** `login_required` and `role_required` redirect to
  `url_for('login', next=request.full_path)`. The `next` value is accepted only when it starts with a
  single `/` and does not start with `//` or `/\`; anything else falls back to `/`.

### Rate limiting

- Collection `login_attempts`: `{key, ip, created_at}`, TTL index on `created_at` expiring after
  15 minutes.
- `key` is the lowercased submitted identifier. `ip` is the first entry of `X-Forwarded-For`, falling back
  to `request.remote_addr`.
- Before checking the password, count documents matching `key` and `ip`. At 5 or more, reject without
  checking and show "Too many attempts. Try again in N minutes.", where N is computed from the oldest
  matching attempt.
- Each failed login inserts one document. A successful login deletes documents matching `key` and `ip`.

### Password reset

- **Request:** normalize the email (strip, lowercase) and find a user whose email matches
  case-insensitively. If found and the user has an email, generate `secrets.token_urlsafe(32)`, store
  `{user_id, token_hash: sha256(token), created_at}` in `password_resets` (TTL index, 1 hour), and email
  the link `url_for('reset_password', token=token, _external=True)`. Earlier unused tokens for that user
  are deleted first. Forgot-password submissions go through the same `login_attempts` limiter, keyed as
  `reset:<email>`.
- **Redeem:** hash the URL token and look it up. The document must exist and be under 1 hour old (checked
  in code; the TTL sweep can lag). On a valid POST, bcrypt the new password, update the user, delete every
  `password_resets` document for that user, delete that user's `login_attempts`, and log a
  `password_reset` activity.

### Email

- Provider: **Resend**, installed through the Vercel Marketplace so `RESEND_API_KEY` is provisioned on the
  project. `RESEND_FROM` (for example `Mepham Robotics <noreply@<verified-domain>>`) is set as a project
  env var.
- Sent with `requests.post('https://api.resend.com/emails', ...)`, 10-second timeout. No new Python
  dependency.
- The email has a plain-text part and a simple HTML part: greeting with username, reset button/link,
  1-hour expiry note, and "ignore this if you didn't ask".
- If the key is missing or the call fails, log the error server-side and still show the generic
  confirmation.

### Existing form interceptor

`static/js/script.js` intercepts every form submit and posts it to a Google Form unless the form is on an
allowlist. Replace the `id === 'loginForm'` special cases with a generic opt-out: forms carrying
`data-native-submit` submit normally. All three auth forms carry it.

### Client script

`static/js/login.js`, loaded only by the auth pages: password show/hide toggle, confirm-password match
check on the reset form, and disabling the submit button while submitting.

## Setup Prerequisites (done by the user)

1. `npm i -g vercel`, `vercel login`, `vercel link` in the repo.
2. Install the Resend integration from the Vercel Marketplace and verify a sending domain in Resend.
3. Add `RESEND_FROM` as a project env var.
4. `vercel env pull` to get the vars locally.

Code can be built and tested before this is done (email sending is mocked in tests); a real reset email
needs it.

## Testing

- Flask test client backed by `mongomock`, no real database or email:
  - login success, bad password, username vs email lookup
  - lockout after 5 failures, message shown, counter cleared on success
  - `next` redirect honored for `/admin`, rejected for `//evil.com`, `https://evil.com`, `/\evil.com`
  - Remember me sets a persistent cookie; unchecked does not
  - signed-in `GET /login` redirects
  - forgot-password: same response for known and unknown emails; Resend call made only for known
  - reset: valid token updates password; expired, reused, and unknown tokens rejected
- Browser check of all three pages at 1280px and 375px: layout, show/hide toggle, error states, and that
  submits reach Flask (not the Google Form).
