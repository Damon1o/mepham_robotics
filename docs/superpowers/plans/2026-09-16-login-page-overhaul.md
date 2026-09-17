# Login Page Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the standalone login page with a site-styled one whose controls all work (Remember me, redirect back, show/hide password), and add login rate limiting plus an emailed password-reset flow.

**Architecture:** All server code stays in `api/index.py` (the repo's single Flask module), added as small helpers next to the existing auth decorators. Rate-limit counters and reset tokens live in two new MongoDB collections with TTL indexes, because Vercel runs many short-lived instances and in-memory state does not survive. Email goes out through the Resend HTTP API using `requests`, which is already a dependency. Templates extend `base.html`; all styles go in `static/css/pages/login.css`; a small `static/js/login.js` handles the password toggle. A new pytest suite runs against `mongomock`, so no test touches the real database or sends email.

**Tech Stack:** Flask 3.1, Jinja2, pymongo 4.12, bcrypt, requests, pytest + mongomock (dev only), plain CSS with site tokens, Lucide icons.

Spec: `docs/superpowers/specs/2026-09-16-login-page-overhaul-design.md`

## Global Constraints

- CSS never lives in HTML: templates get no `style=` attributes and no `<style>` blocks.
- Reuse existing tokens from `static/css/styles.css`: `--maroon-dark: #800000`, `--maroon-light: #944547`, `--accent-gold: #ffd700`, `--text-dark: #1a1a1a`, `--text-light: #666`, `--spacing-md: 1.5rem`, `--spacing-lg: 2.5rem`, `--spacing-xl: 4rem`, `--transition-base`, `--font-display`.
- Card look: `border: 3px solid var(--text-dark)`, `border-radius: 16px`, `box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2)`. Dark mode via `[data-theme="dark"]`: card `#1e1e1e`, border `#444`, heading `#d4a0a1`, body text `#bbb`.
- Rate limit: 5 attempts per (key, IP) within 15 minutes. Reset tokens: `secrets.token_urlsafe(32)`, only the SHA-256 hash stored, valid 1 hour, single use.
- Remember me: `PERMANENT_SESSION_LIFETIME` 30 days. Cookies: `HttpOnly`, `SameSite=Lax`, `Secure` only when the `VERCEL` env var is set.
- Forgot-password never reveals whether an email matched.
- Email env vars: `RESEND_API_KEY`, `RESEND_FROM`. No new runtime dependency in `requirements.txt`.
- Forms that must post to Flask carry `data-native-submit` (otherwise `static/js/script.js` sends them to a Google Form).
- Passwords are `.strip()`ed on login, admin create, and reset, matching existing stored passwords.
- Commit message style: short imperative sentence, no `feat:` prefix, ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Map

| File | Responsibility |
|------|----------------|
| `requirements-dev.txt` (new) | pytest + mongomock for local tests only |
| `tests/conftest.py` (new) | mongomock-backed `db`, `client`, `make_user` fixtures |
| `tests/test_smoke.py` (new) | auth pages render and opt out of the form interceptor |
| `tests/test_password_reset.py` (new) | forgot/reset flow, email helper, reset rate limit |
| `tests/test_login.py` (new) | sign-in, remember me, next redirect, lockout, cookie config |
| `api/index.py` | auth helpers, `/login`, `/forgot-password`, `/reset-password/<token>`, decorators |
| `templates/login.html` | rewritten, extends `base.html` |
| `templates/forgot_password.html` (new) | request reset link |
| `templates/reset_password.html` (new) | set new password |
| `static/css/pages/login.css` | rewritten; shared by all three auth pages |
| `static/js/login.js` (new) | password toggle, confirm match, disable submit |
| `static/js/script.js` | generic `data-native-submit` opt-out |

## Shared Verification Commands

**TESTS** (repo root):

```bash
python -m pytest tests -q
```

**RENDER** (repo root) confirms the three pages return 200 and every `/static/` URL resolves:

```bash
python -c "
import re, sys, mongomock
sys.path.insert(0, '.')
import api.index as m
mdb = mongomock.MongoClient()['mepham']
m.get_db = lambda: mdb
c = m.app.test_client()
for path in ['/login', '/forgot-password', '/reset-password/not-a-token']:
    r = c.get(path)
    html = r.get_data(as_text=True)
    print(path, r.status_code)
    for url in set(re.findall(r'(/static/[^\"?\' )]+)', html)):
        s = c.get(url).status_code
        if s != 200: print('  MISSING', url, s)
"
```

Expected: `/login 200`, `/forgot-password 200`, `/reset-password/not-a-token 400`, no `MISSING` lines.

**NO-INLINE-CSS** (repo root):

```bash
grep -n 'style=\|<style' templates/login.html templates/forgot_password.html templates/reset_password.html || echo clean
```

Expected: `clean`.

---

### Task 1: Test harness and form interceptor opt-out

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`
- Modify: `static/js/script.js` (submit handler around lines 381-433)
- Modify: `templates/login.html` (the `<form id="loginForm" ...>` tag)

**Interfaces:**
- Produces: pytest fixtures `db` (mongomock database patched into `api.index.get_db`), `client` (Flask test client), `make_user(username='alice', password='correct-horse', email='alice@example.com', role='member') -> dict` (inserted user doc including `_id`).
- Produces: the `data-native-submit` form attribute contract used by Tasks 2 and 3.

- [ ] **Step 1: Add dev requirements**

`requirements-dev.txt`:

```text
-r requirements.txt
pytest==9.*
mongomock==4.*
```

Run: `python -m pip install -r requirements-dev.txt`
Expected: installs or reports already satisfied.

- [ ] **Step 2: Write fixtures**

`tests/conftest.py`:

```python
import os
import sys

import bcrypt
import mongomock
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('MONGO_URI', 'mongodb://tests-use-mongomock')

import api.index as app_module  # noqa: E402


@pytest.fixture
def db(monkeypatch):
    mock_db = mongomock.MongoClient()['mepham']
    monkeypatch.setattr(app_module, 'get_db', lambda: mock_db)
    monkeypatch.setattr(app_module, '_auth_indexes_ready', False, raising=False)
    return mock_db


@pytest.fixture
def client(db):
    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


@pytest.fixture
def make_user(db):
    def _make(username='alice', password='correct-horse', email='alice@example.com', role='member'):
        doc = {
            'username': username,
            'email': email,
            'password': bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(4)),
            'role': role,
        }
        doc['_id'] = db['users'].insert_one(doc).inserted_id
        return doc
    return _make
```

- [ ] **Step 3: Write the failing smoke test**

`tests/test_smoke.py`:

```python
def test_login_page_opts_out_of_form_interceptor(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'data-native-submit' in resp.data
```

- [ ] **Step 4: Run it to verify it fails**

Run: `python -m pytest tests/test_smoke.py -q`
Expected: FAIL on `assert b'data-native-submit' in resp.data`.

- [ ] **Step 5: Add the attribute to the current login form**

In `templates/login.html` change:

```html
            <form id="loginForm" method="POST" action="{{ url_for('login') }}">
```

to:

```html
            <form id="loginForm" method="POST" action="{{ url_for('login') }}" data-native-submit>
```

- [ ] **Step 6: Replace the id special cases in `static/js/script.js`**

Change:

```js
            // IGNORE ADMIN, LOGIN, AND CHATBOT FORMS
            if (this.id === 'loginForm' || this.id === 'chatbot-form' || this.getAttribute('action')?.startsWith('/admin')) {
                return;
            }
```

to:

```js
            // Forms marked data-native-submit (auth pages), admin forms, and the chatbot post normally
            if (this.hasAttribute('data-native-submit') || this.id === 'chatbot-form' || this.getAttribute('action')?.startsWith('/admin')) {
                return;
            }
```

and delete this now-unreachable branch:

```js
            } else if (this.id === 'loginForm') {
                // Keep login logic separate or handle elsewhere if needed
                // For now, let's just let it pass or handle explicitly
                return;
            }
```

replacing it with the closing brace of the previous branch:

```js
            }
```

- [ ] **Step 7: Verify**

Run: `python -m pytest tests -q` — Expected: `1 passed`.
Run: `node --check static/js/script.js` — Expected: no output.
Run: `grep -n "loginForm" static/js/script.js || echo none` — Expected: `none`.

- [ ] **Step 8: Commit**

```bash
git add requirements-dev.txt tests/conftest.py tests/test_smoke.py static/js/script.js templates/login.html
git commit -m "Add auth test harness and data-native-submit form opt-out

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Rate-limit helpers and password reset flow

**Files:**
- Modify: `api/index.py` (imports at top; activity maps near lines 150-190; helpers after `role_required`; new routes after `logout`)
- Create: `templates/forgot_password.html`
- Create: `templates/reset_password.html`
- Create: `tests/test_password_reset.py`

**Interfaces:**
- Consumes: fixtures from Task 1.
- Produces (module-level in `api/index.py`, used by Task 3):
  - `LOGIN_MAX_ATTEMPTS = 5`, `LOGIN_WINDOW = datetime.timedelta(minutes=15)`, `RESET_TOKEN_TTL = datetime.timedelta(hours=1)`
  - `_utcnow() -> datetime.datetime` (naive UTC)
  - `_client_ip() -> str`
  - `_ensure_auth_indexes() -> None` guarded by global `_auth_indexes_ready`
  - `_lockout_minutes(key: str, ip: str) -> int` (0 when not locked)
  - `_record_attempt(key: str, ip: str) -> None`
  - `_clear_attempts(key: str, ip: str | None = None) -> None`
  - `send_email(to: str, subject: str, text: str, html_body: str) -> bool`
  - routes `forgot_password` (`/forgot-password`) and `reset_password` (`/reset-password/<token>`)
  - template CSS classes used by Task 4: `auth-section`, `auth-card`, `auth-panel`, `auth-title`, `auth-intro`, `auth-notice`, `auth-error`, `auth-form`, `form-group`, `password-field`, `password-toggle`, `icon-show`, `icon-hide`, `auth-submit`, `auth-back`, `auth-link`

- [ ] **Step 1: Write the failing tests**

`tests/test_password_reset.py`:

```python
import datetime
import hashlib
import re

import bcrypt
import pytest

import api.index as app_module


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_send(to, subject, text, html_body):
        calls.append({'to': to, 'subject': subject, 'text': text, 'html': html_body})
        return True

    monkeypatch.setattr(app_module, 'send_email', fake_send)
    return calls


def _token_from(call):
    return re.search(r'/reset-password/(\S+)', call['text']).group(1)


def test_forgot_password_response_identical_for_known_and_unknown(client, make_user, sent):
    make_user(email='alice@example.com')
    known = client.post('/forgot-password', data={'email': 'Alice@Example.com'})
    unknown = client.post('/forgot-password', data={'email': 'nobody@example.com'})
    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data
    assert [c['to'] for c in sent] == ['alice@example.com']


def test_forgot_password_stores_only_token_hash(client, db, make_user, sent):
    make_user()
    client.post('/forgot-password', data={'email': 'alice@example.com'})
    token = _token_from(sent[0])
    doc = db['password_resets'].find_one()
    assert doc['token_hash'] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(doc)


def test_new_request_replaces_old_token(client, db, make_user, sent):
    make_user()
    client.post('/forgot-password', data={'email': 'alice@example.com'})
    client.post('/forgot-password', data={'email': 'alice@example.com'})
    assert db['password_resets'].count_documents({}) == 1
    assert client.get(f'/reset-password/{_token_from(sent[0])}').status_code == 400
    assert client.get(f'/reset-password/{_token_from(sent[1])}').status_code == 200


def test_reset_with_valid_token_updates_password_once(client, db, make_user, sent):
    user = make_user()
    client.post('/forgot-password', data={'email': 'alice@example.com'})
    token = _token_from(sent[0])

    resp = client.post(f'/reset-password/{token}',
                       data={'password': 'brand-new-pass', 'confirm_password': 'brand-new-pass'})
    assert resp.status_code == 302
    assert resp.location.endswith('/login')

    stored = db['users'].find_one({'_id': user['_id']})
    assert bcrypt.checkpw(b'brand-new-pass', stored['password'])
    assert db['password_resets'].count_documents({}) == 0
    assert db['activities'].find_one({'type': 'password_reset'})

    reused = client.post(f'/reset-password/{token}',
                         data={'password': 'another-pass-1', 'confirm_password': 'another-pass-1'})
    assert reused.status_code == 400


def test_reset_rejects_expired_token(client, db, make_user, sent):
    make_user()
    client.post('/forgot-password', data={'email': 'alice@example.com'})
    db['password_resets'].update_many({}, {'$set': {
        'created_at': app_module._utcnow() - datetime.timedelta(hours=1, minutes=1)}})
    assert client.get(f'/reset-password/{_token_from(sent[0])}').status_code == 400


def test_reset_rejects_unknown_token(client):
    resp = client.get('/reset-password/not-a-real-token')
    assert resp.status_code == 400
    assert b'/forgot-password' in resp.data


@pytest.mark.parametrize('password,confirm,message', [
    ('short', 'short', b'at least 8 characters'),
    ('long-enough-1', 'long-enough-2', b'do not match'),
])
def test_reset_validates_password(client, make_user, sent, password, confirm, message):
    make_user()
    client.post('/forgot-password', data={'email': 'alice@example.com'})
    resp = client.post(f'/reset-password/{_token_from(sent[0])}',
                       data={'password': password, 'confirm_password': confirm})
    assert resp.status_code == 400
    assert message in resp.data


def test_forgot_password_is_rate_limited(client, make_user, sent):
    make_user()
    for _ in range(7):
        client.post('/forgot-password', data={'email': 'alice@example.com'})
    assert len(sent) == app_module.LOGIN_MAX_ATTEMPTS


def test_send_email_without_config_returns_false(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.delenv('RESEND_FROM', raising=False)
    assert app_module.send_email('a@example.com', 'Subject', 'text', '<p>html</p>') is False


def test_send_email_posts_to_resend(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 're_test')
    monkeypatch.setenv('RESEND_FROM', 'Mepham Robotics <noreply@example.com>')
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(app_module.requests, 'post', fake_post)
    assert app_module.send_email('a@example.com', 'Subject', 'text', '<p>html</p>') is True
    assert captured['url'] == 'https://api.resend.com/emails'
    assert captured['headers']['Authorization'] == 'Bearer re_test'
    assert captured['json']['to'] == ['a@example.com']
    assert captured['timeout'] == 10
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_password_reset.py -q`
Expected: FAIL (404 on `/forgot-password`, `AttributeError` for `send_email` / `_utcnow`).

- [ ] **Step 3: Add imports**

At the top of `api/index.py`, after `import datetime`, add:

```python
import hashlib
import html
import math
import re
import secrets
```

- [ ] **Step 4: Register activity icon and title**

In `get_activity_icon`'s `icons` dict add `'password_reset': '🔑',` and in `get_activity_title`'s `titles` dict add `'password_reset': 'Password reset',`.

- [ ] **Step 5: Add helpers after `role_required`**

Insert directly after the `role_required` function:

```python
# --- Auth helpers: rate limiting, reset tokens, email ---
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW = datetime.timedelta(minutes=15)
RESET_TOKEN_TTL = datetime.timedelta(hours=1)
_auth_indexes_ready = False

def _utcnow():
    """Naive UTC now; MongoDB TTL indexes compare against UTC."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    return forwarded.split(',')[0].strip() or request.remote_addr or ''

def _ensure_auth_indexes():
    global _auth_indexes_ready
    if _auth_indexes_ready:
        return
    db['login_attempts'].create_index('created_at', expireAfterSeconds=int(LOGIN_WINDOW.total_seconds()))
    db['login_attempts'].create_index([('key', 1), ('ip', 1)])
    db['password_resets'].create_index('created_at', expireAfterSeconds=int(RESET_TOKEN_TTL.total_seconds()))
    db['password_resets'].create_index('token_hash', unique=True)
    _auth_indexes_ready = True

def _lockout_minutes(key, ip):
    """Minutes until (key, ip) may try again, or 0 if not locked out."""
    since = _utcnow() - LOGIN_WINDOW
    attempts = list(db['login_attempts'].find(
        {'key': key, 'ip': ip, 'created_at': {'$gte': since}}).sort('created_at', 1))
    if len(attempts) < LOGIN_MAX_ATTEMPTS:
        return 0
    unlock_at = attempts[0]['created_at'] + LOGIN_WINDOW
    return max(1, math.ceil((unlock_at - _utcnow()).total_seconds() / 60))

def _record_attempt(key, ip):
    _ensure_auth_indexes()
    db['login_attempts'].insert_one({'key': key, 'ip': ip, 'created_at': _utcnow()})

def _clear_attempts(key, ip=None):
    query = {'key': key}
    if ip is not None:
        query['ip'] = ip
    db['login_attempts'].delete_many(query)

def _hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def send_email(to, subject, text, html_body):
    """Send one email through Resend. Returns False instead of raising."""
    api_key = os.getenv('RESEND_API_KEY')
    sender = os.getenv('RESEND_FROM')
    if not api_key or not sender:
        app.logger.error('send_email: RESEND_API_KEY or RESEND_FROM is not set')
        return False
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {api_key}'},
            json={'from': sender, 'to': [to], 'subject': subject, 'text': text, 'html': html_body},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        app.logger.exception('send_email: Resend request failed')
        return False

def _reset_email_bodies(username, link):
    text = (
        f"Hi {username},\n\n"
        f"Someone asked to reset your Mepham Robotics password. Use this link within 1 hour:\n\n"
        f"{link}\n\n"
        f"If you didn't ask for this, you can ignore this email."
    )
    safe_name = html.escape(username)
    safe_link = html.escape(link, quote=True)
    html_body = (
        f"<p>Hi {safe_name},</p>"
        f"<p>Someone asked to reset your Mepham Robotics password. This link works for 1 hour:</p>"
        f"<p><a href=\"{safe_link}\" style=\"display:inline-block;padding:12px 20px;background:#800000;"
        f"color:#ffffff;text-decoration:none;border-radius:8px;font-weight:bold;\">Reset password</a></p>"
        f"<p>If you didn't ask for this, you can ignore this email.</p>"
    )
    return text, html_body

def _find_reset(token):
    doc = db['password_resets'].find_one({'token_hash': _hash_token(token)})
    if not doc or _utcnow() - doc['created_at'] > RESET_TOKEN_TTL:
        return None
    return doc
```

(The inline `style` in the email HTML is required by email clients and does not violate the no-CSS-in-templates rule, which covers site templates.)

- [ ] **Step 6: Add the routes after `logout`**

```python
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        ip = _client_ip()
        key = f'reset:{email}'
        if email and not _lockout_minutes(key, ip):
            _record_attempt(key, ip)
            user = db['users'].find_one({'email': {'$regex': f'^{re.escape(email)}$', '$options': 'i'}})
            if user and user.get('email'):
                token = secrets.token_urlsafe(32)
                db['password_resets'].delete_many({'user_id': user['_id']})
                db['password_resets'].insert_one({
                    'user_id': user['_id'],
                    'token_hash': _hash_token(token),
                    'created_at': _utcnow(),
                })
                link = url_for('reset_password', token=token, _external=True)
                text, html_body = _reset_email_bodies(user['username'], link)
                send_email(user['email'], 'Reset your Mepham Robotics password', text, html_body)
        return render_template('forgot_password.html', active_page='login', sent=True)
    return render_template('forgot_password.html', active_page='login', sent=False)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset = _find_reset(token)
    user = db['users'].find_one({'_id': reset['user_id']}) if reset else None
    if not user:
        return render_template('reset_password.html', active_page='login', invalid=True), 400

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        error = None
        if len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        if error:
            return render_template('reset_password.html', active_page='login', invalid=False, error=error), 400

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        db['users'].update_one({'_id': user['_id']}, {'$set': {'password': hashed}})
        db['password_resets'].delete_many({'user_id': user['_id']})
        _clear_attempts(user['username'].lower())
        if user.get('email'):
            _clear_attempts(user['email'].lower())
        log_activity('password_reset', f'Password reset for {user["username"]}',
                     user=user['username'], details={'username': user['username']})
        flash('Password updated. Sign in with your new password.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', active_page='login', invalid=False)
```

- [ ] **Step 7: Create `templates/forgot_password.html`**

```html
{% extends "base.html" %}

{% block title %}Forgot Password | Mepham Robotics{% endblock %}
{% block meta_description %}Request a link to reset your Mepham Robotics member password.{% endblock %}

{% block page_styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/login.css') }}">
{% endblock %}

{% block content %}
<section class="auth-section">
    <div class="auth-card">
        <div class="auth-panel">
            <h1 class="auth-title">Forgot password</h1>
            {% if sent %}
            <p class="auth-notice" role="status">
                If an account with that email exists, we've sent a reset link. It expires in 1 hour.
                No email on your account? Ask an admin to reset your password.
            </p>
            {% else %}
            <p class="auth-intro">Enter the email on your account and we'll send you a link to set a new password.</p>
            <form id="forgotForm" class="auth-form" method="POST" action="{{ url_for('forgot_password') }}"
                data-native-submit>
                <div class="form-group">
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" required autocomplete="email" autofocus>
                </div>
                <button type="submit" class="auth-submit">Send reset link</button>
            </form>
            {% endif %}
            <p class="auth-back"><a href="{{ url_for('login') }}" class="auth-link">Back to login</a></p>
        </div>
    </div>
</section>
{% endblock %}

{% block page_scripts %}
<script src="{{ url_for('static', filename='js/login.js') }}" defer></script>
{% endblock %}
```

- [ ] **Step 8: Create `templates/reset_password.html`**

```html
{% extends "base.html" %}

{% block title %}Reset Password | Mepham Robotics{% endblock %}
{% block meta_description %}Set a new password for your Mepham Robotics member account.{% endblock %}

{% block page_styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/login.css') }}">
{% endblock %}

{% block content %}
<section class="auth-section">
    <div class="auth-card">
        <div class="auth-panel">
            <h1 class="auth-title">Reset password</h1>
            {% if invalid %}
            <p class="auth-error" role="alert">This reset link is invalid or has expired.</p>
            <p class="auth-back"><a href="{{ url_for('forgot_password') }}" class="auth-link">Request a new link</a></p>
            {% else %}
            <p class="auth-intro">Choose a new password with at least 8 characters.</p>
            {% if error %}
            <p class="auth-error" role="alert">{{ error }}</p>
            {% endif %}
            <form id="resetForm" class="auth-form" method="POST" data-native-submit>
                <div class="form-group">
                    <label for="password">New password</label>
                    <div class="password-field">
                        <input type="password" id="password" name="password" required minlength="8"
                            autocomplete="new-password" autofocus>
                        <button type="button" class="password-toggle" aria-controls="password"
                            aria-label="Show password" aria-pressed="false">
                            <i data-lucide="eye" class="icon-show"></i>
                            <i data-lucide="eye-off" class="icon-hide"></i>
                        </button>
                    </div>
                </div>
                <div class="form-group">
                    <label for="confirm_password">Confirm password</label>
                    <input type="password" id="confirm_password" name="confirm_password" required minlength="8"
                        autocomplete="new-password">
                </div>
                <button type="submit" class="auth-submit">Update password</button>
            </form>
            <p class="auth-back"><a href="{{ url_for('login') }}" class="auth-link">Back to login</a></p>
            {% endif %}
        </div>
    </div>
</section>
{% endblock %}

{% block page_scripts %}
<script src="{{ url_for('static', filename='js/login.js') }}" defer></script>
{% endblock %}
```

(`static/js/login.js` is created in Task 4; until then RENDER reports it as `MISSING`, which is expected for this task only.)

- [ ] **Step 9: Run tests**

Run: `python -m pytest tests -q`
Expected: all pass, 0 failed.

- [ ] **Step 10: Check templates**

Run NO-INLINE-CSS. Expected: `clean`.

- [ ] **Step 11: Commit**

```bash
git add api/index.py templates/forgot_password.html templates/reset_password.html tests/test_password_reset.py
git commit -m "Add password reset flow with emailed single-use tokens

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Sign-in behavior and login template

**Files:**
- Modify: `api/index.py` (app config after `app.secret_key`; `login_required`; `role_required`; `login` route)
- Modify: `api/index.py` (`admin_create_user`: no change needed; passwords already stripped)
- Rewrite: `templates/login.html`
- Rewrite: `static/css/pages/login.css` (cleared here, filled in Task 4)
- Create: `tests/test_login.py`
- Modify: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `_client_ip`, `_lockout_minutes`, `_record_attempt`, `_clear_attempts`, route `forgot_password` from Task 2.
- Produces: `_safe_next(target: str | None) -> str`; login template classes used by Task 4: `auth-card--split`, `auth-visual`, `auth-visual-img`, `auth-visual-copy`, `auth-flash`, `auth-flash--<category>`, `auth-row`, `auth-remember`.

- [ ] **Step 1: Write the failing tests**

`tests/test_login.py`:

```python
import pytest

import api.index as app_module


def _session_cookie(resp):
    return next(h for h in resp.headers.getlist('Set-Cookie') if h.startswith('session='))


def test_login_with_username_sets_session(client, make_user):
    make_user(role='admin')
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    assert resp.status_code == 302
    assert resp.location == '/'
    with client.session_transaction() as s:
        assert s['user'] == 'alice'
        assert s['role'] == 'admin'


def test_login_with_email(client, make_user):
    make_user()
    resp = client.post('/login', data={'username': 'alice@example.com', 'password': 'correct-horse'})
    assert resp.status_code == 302


def test_bad_password_shows_error(client, make_user):
    make_user()
    resp = client.post('/login', data={'username': 'alice', 'password': 'wrong'})
    assert resp.status_code == 401
    assert b'Invalid credentials' in resp.data
    assert b'value="alice"' in resp.data


def test_login_clears_previous_session_data(client, make_user):
    make_user()
    with client.session_transaction() as s:
        s['stale'] = 'value'
    client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    with client.session_transaction() as s:
        assert 'stale' not in s


def test_remember_me_sets_persistent_cookie(client, make_user):
    make_user()
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse', 'remember': '1'})
    assert 'Expires=' in _session_cookie(resp)


def test_without_remember_me_cookie_is_session_only(client, make_user):
    make_user()
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    assert 'Expires=' not in _session_cookie(resp)


def test_next_redirect_is_honored(client, make_user):
    make_user(role='admin')
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse', 'next': '/admin#users'})
    assert resp.location == '/admin#users'


@pytest.mark.parametrize('target', ['//evil.com', 'https://evil.com', '/\\evil.com', 'evil.com', ''])
def test_unsafe_next_falls_back_to_home(client, make_user, target):
    make_user()
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse', 'next': target})
    assert resp.location == '/'


def test_protected_page_redirects_to_login_with_next(client):
    resp = client.get('/standards')
    assert resp.status_code == 302
    assert resp.location == '/login?next=/standards'


def test_signed_in_user_is_redirected_away_from_login(client, make_user):
    make_user()
    with client.session_transaction() as s:
        s['user'] = 'alice'
        s['role'] = 'member'
    resp = client.get('/login?next=/notebook')
    assert resp.status_code == 302
    assert resp.location == '/notebook'


def test_lockout_after_max_failures(client, make_user):
    make_user()
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS):
        client.post('/login', data={'username': 'alice', 'password': 'wrong'})
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    assert resp.status_code == 429
    assert b'Too many attempts' in resp.data
    with client.session_transaction() as s:
        assert 'user' not in s


def test_lockout_key_is_case_insensitive(client, make_user):
    make_user()
    for name in ['alice', 'ALICE', 'Alice', 'aLice', 'alicE']:
        client.post('/login', data={'username': name, 'password': 'wrong'})
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    assert resp.status_code == 429


def test_success_clears_failed_attempts(client, db, make_user):
    make_user()
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS - 1):
        client.post('/login', data={'username': 'alice', 'password': 'wrong'})
    client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    assert db['login_attempts'].count_documents({'key': 'alice'}) == 0


def test_session_cookie_config():
    config = app_module.app.config
    assert config['SESSION_COOKIE_HTTPONLY'] is True
    assert config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert config['PERMANENT_SESSION_LIFETIME'].days == 30
```

Append to `tests/test_smoke.py`:

```python
def test_login_page_links_to_forgot_password(client):
    resp = client.get('/login')
    assert b'href="/forgot-password"' in resp.data
    assert b'name="remember"' in resp.data
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_login.py tests/test_smoke.py -q`
Expected: several FAIL (status 200 instead of 401, no `Expires=`, redirect to `/login` without `next`, config keys missing).

- [ ] **Step 3: Add session config**

In `api/index.py`, directly after `app.secret_key = ...`:

```python
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.getenv('VERCEL')),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=30),
)
```

- [ ] **Step 4: Add `_safe_next` and pass `next` from the decorators**

Replace the existing `login_required` and `role_required` with:

```python
def _safe_next(target):
    """Only allow same-site relative paths as post-login redirects."""
    if target and target.startswith('/') and not target.startswith(('//', '/\\')):
        return target
    return url_for('index')

def _login_redirect():
    return redirect(url_for('login', next=request.full_path.rstrip('?')))

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return _login_redirect()
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user' not in session:
                return _login_redirect()
            if session.get('role') != role and session.get('role') != 'admin':
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator
```

Note: `url_for('login', next='/standards')` encodes to `/login?next=/standards` (Werkzeug leaves `/` unescaped in query values). If the test sees `%2F`, change the assertion's expected value to match; the behavior is equivalent.

- [ ] **Step 5: Rewrite the `login` route**

Replace the existing `login` function with:

```python
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = _safe_next(request.values.get('next'))
    if 'user' in session:
        return redirect(next_url)

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        attempt_key = identifier.lower()
        ip = _client_ip()

        wait = _lockout_minutes(attempt_key, ip)
        if wait:
            error = f'Too many attempts. Try again in {wait} minute{"s" if wait != 1 else ""}.'
            return render_template('login.html', active_page='login', error=error,
                                   next=next_url, username=identifier), 429

        user = db['users'].find_one({'$or': [{'username': identifier}, {'email': identifier}]})
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            _clear_attempts(attempt_key, ip)
            session.clear()
            session['user'] = user['username']
            session['role'] = user.get('role', 'member')
            session.permanent = bool(request.form.get('remember'))
            return redirect(next_url)

        _record_attempt(attempt_key, ip)
        return render_template('login.html', active_page='login',
                               error='Invalid credentials. Please try again.',
                               next=next_url, username=identifier), 401

    return render_template('login.html', active_page='login', next=next_url)
```

- [ ] **Step 6: Rewrite `templates/login.html`**

```html
{% extends "base.html" %}

{% block title %}Member Login | Mepham Robotics{% endblock %}
{% block meta_description %}Sign in to the Mepham Robotics member area.{% endblock %}

{% block page_styles %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/login.css') }}">
{% endblock %}

{% block content %}
<section class="auth-section">
    <div class="auth-card auth-card--split">
        <div class="auth-visual">
            <img src="{{ url_for('static', filename='assets/photos/carousel6.jpg') }}"
                alt="Mepham Robotics team members with their robot" class="auth-visual-img">
            <div class="auth-visual-copy">
                <h1>Welcome back, Team 77628</h1>
                <p>Sign in to reach member resources and the admin dashboard.</p>
            </div>
        </div>

        <div class="auth-panel">
            <h2 class="auth-title">Member Login</h2>

            {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
            <p class="auth-flash auth-flash--{{ category }}" role="status">{{ message }}</p>
            {% endfor %}
            {% endwith %}

            {% if error %}
            <p class="auth-error" role="alert">{{ error }}</p>
            {% endif %}

            <form id="loginForm" class="auth-form" method="POST" action="{{ url_for('login') }}" data-native-submit>
                <input type="hidden" name="next" value="{{ next }}">
                <div class="form-group">
                    <label for="username">Username or email</label>
                    <input type="text" id="username" name="username" value="{{ username or '' }}" required
                        autocomplete="username" autocapitalize="none" spellcheck="false" autofocus>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <div class="password-field">
                        <input type="password" id="password" name="password" required autocomplete="current-password">
                        <button type="button" class="password-toggle" aria-controls="password"
                            aria-label="Show password" aria-pressed="false">
                            <i data-lucide="eye" class="icon-show"></i>
                            <i data-lucide="eye-off" class="icon-hide"></i>
                        </button>
                    </div>
                </div>
                <div class="auth-row">
                    <label class="auth-remember">
                        <input type="checkbox" name="remember" value="1"> Remember me
                    </label>
                    <a href="{{ url_for('forgot_password') }}" class="auth-link">Forgot password?</a>
                </div>
                <button type="submit" class="auth-submit">Sign in</button>
            </form>
        </div>
    </div>
</section>
{% endblock %}

{% block page_scripts %}
<script src="{{ url_for('static', filename='js/login.js') }}" defer></script>
{% endblock %}
```

- [ ] **Step 7: Clear the old login stylesheet**

Its rules target the deleted standalone markup and set `body { height: 100vh; overflow: hidden; }`, which breaks `base.html`. Replace the whole of `static/css/pages/login.css` with:

```css
/* Page styles: login, forgot password, reset password */
```

- [ ] **Step 8: Run tests**

Run: TESTS. Expected: all pass, 0 failed.
Run: NO-INLINE-CSS. Expected: `clean`.

- [ ] **Step 9: Commit**

```bash
git add api/index.py templates/login.html static/css/pages/login.css tests/test_login.py tests/test_smoke.py
git commit -m "Rebuild login on base layout with remember me, safe redirects, and lockout

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Auth page styles and script

**Files:**
- Rewrite: `static/css/pages/login.css`
- Create: `static/js/login.js`

**Interfaces:**
- Consumes: class names from Tasks 2 and 3; element ids `password`, `confirm_password`, `resetForm`.
- Produces: nothing consumed later.

- [ ] **Step 1: Write `static/js/login.js`**

```js
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

const resetForm = document.getElementById('resetForm');
if (resetForm) {
    const password = resetForm.querySelector('#password');
    const confirm = resetForm.querySelector('#confirm_password');
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
```

- [ ] **Step 2: Write `static/css/pages/login.css`**

```css
/* Page styles: login, forgot password, reset password */

.auth-section {
    display: flex;
    justify-content: center;
    padding: var(--spacing-xl) var(--spacing-md);
}

.auth-card {
    width: 100%;
    max-width: 480px;
    background: #fff;
    border: 3px solid var(--text-dark);
    border-radius: 16px;
    box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2);
    overflow: hidden;
}

.auth-card--split {
    max-width: 960px;
    display: grid;
    grid-template-columns: 1fr 1fr;
}

/* Photo panel */
.auth-visual {
    position: relative;
    min-height: 460px;
}

.auth-visual-img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.auth-visual::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(128, 0, 0, 0.2) 0%, rgba(74, 0, 0, 0.92) 100%);
    pointer-events: none;
}

.auth-visual-copy {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 1;
    padding: var(--spacing-lg);
    color: #fff;
}

.auth-visual-copy h1 {
    font-family: var(--font-display);
    font-size: clamp(1.6rem, 3vw, 2.2rem);
    margin: 0 0 0.5rem;
    color: #fff;
    text-align: left;
}

.auth-visual-copy p {
    margin: 0;
    color: rgba(255, 255, 255, 0.9);
}

/* Form panel */
.auth-panel {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: var(--spacing-lg);
}

.auth-title {
    font-family: 'Space Mono', monospace;
    color: var(--maroon-dark);
    margin: 0 0 1rem;
    text-align: left;
}

.auth-title::after {
    display: none;
}

.auth-intro {
    color: var(--text-light);
    margin: 0 0 1.5rem;
}

.auth-form .form-group {
    margin-bottom: 1.25rem;
}

.auth-form label {
    display: block;
    font-weight: 700;
    margin-bottom: 0.4rem;
    color: var(--text-dark);
}

.auth-form input[type="text"],
.auth-form input[type="email"],
.auth-form input[type="password"] {
    width: 100%;
    box-sizing: border-box;
    padding: 0.75rem 1rem;
    border: 2px solid var(--text-dark);
    border-radius: 10px;
    font: inherit;
    background: #fff;
    color: var(--text-dark);
}

.auth-form input:focus {
    outline: none;
    border-color: var(--maroon-dark);
    box-shadow: 0 0 0 3px rgba(255, 215, 0, 0.5);
}

.password-field {
    position: relative;
}

.auth-form .password-field input {
    padding-right: 3rem;
}

.password-toggle {
    position: absolute;
    top: 50%;
    right: 0.5rem;
    transform: translateY(-50%);
    display: flex;
    padding: 0.35rem;
    background: none;
    border: none;
    color: var(--text-light);
    cursor: pointer;
}

.password-toggle:hover,
.password-toggle:focus-visible {
    color: var(--maroon-dark);
}

.password-toggle .icon-hide,
.password-toggle[aria-pressed="true"] .icon-show {
    display: none;
}

.password-toggle[aria-pressed="true"] .icon-hide {
    display: inline;
}

.auth-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
}

.auth-form .auth-remember {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    font-weight: 400;
    cursor: pointer;
}

.auth-remember input {
    width: 1.1rem;
    height: 1.1rem;
    accent-color: var(--maroon-dark);
}

.auth-link {
    color: var(--maroon-dark);
    font-weight: 700;
    text-decoration: underline;
    text-underline-offset: 3px;
}

.auth-submit {
    width: 100%;
    padding: 0.9rem 1rem;
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--text-dark);
    background: var(--accent-gold);
    border: 3px solid var(--text-dark);
    border-radius: 10px;
    box-shadow: 4px 4px 0 var(--text-dark);
    cursor: pointer;
    transition: transform var(--transition-base), box-shadow var(--transition-base);
}

.auth-submit:hover {
    transform: translate(-2px, -2px);
    box-shadow: 6px 6px 0 var(--text-dark);
}

.auth-submit:active {
    transform: translate(2px, 2px);
    box-shadow: 2px 2px 0 var(--text-dark);
}

.auth-submit:disabled {
    opacity: 0.7;
    cursor: progress;
    transform: none;
}

.auth-back {
    margin: 1.5rem 0 0;
    text-align: center;
}

/* Messages */
.auth-error,
.auth-flash,
.auth-notice {
    margin: 0 0 1rem;
    padding: 0.75rem 1rem;
    border: 2px solid;
    border-radius: 10px;
    font-weight: 700;
}

.auth-error,
.auth-flash--error {
    background: #fdecea;
    border-color: var(--maroon-dark);
    color: var(--maroon-dark);
}

.auth-notice,
.auth-flash--success,
.auth-flash--info {
    background: #eaf7ee;
    border-color: #2e7d32;
    color: #1b5e20;
}

/* Dark mode */
[data-theme="dark"] .auth-card {
    background: #1e1e1e;
    border-color: #444;
}

[data-theme="dark"] .auth-title,
[data-theme="dark"] .auth-link {
    color: #d4a0a1;
}

[data-theme="dark"] .auth-intro {
    color: #bbb;
}

[data-theme="dark"] .auth-form label {
    color: #eee;
}

[data-theme="dark"] .auth-form input[type="text"],
[data-theme="dark"] .auth-form input[type="email"],
[data-theme="dark"] .auth-form input[type="password"] {
    background: #2a2a2a;
    border-color: #555;
    color: #eee;
}

[data-theme="dark"] .password-toggle {
    color: #bbb;
}

@media (max-width: 768px) {
    .auth-card--split {
        grid-template-columns: 1fr;
    }

    .auth-visual {
        min-height: 220px;
    }

    .auth-panel,
    .auth-visual-copy {
        padding: var(--spacing-md);
    }
}

@media (prefers-reduced-motion: reduce) {
    .auth-submit {
        transition: none;
    }

    .auth-submit:hover,
    .auth-submit:active {
        transform: none;
    }
}
```

- [ ] **Step 3: Static checks**

Run: `node --check static/js/login.js` — Expected: no output.
Run: `python -c "s=open('static/css/pages/login.css').read(); print(s.count('{'), s.count('}'))"` — Expected: two equal numbers.
Run: RENDER — Expected: `/login 200`, `/forgot-password 200`, `/reset-password/not-a-token 400`, no `MISSING`.
Run: TESTS — Expected: all pass.

- [ ] **Step 4: Browser check**

Start a mongomock-backed server (never point it at the real database):

```bash
python -c "
import sys, mongomock, bcrypt
sys.path.insert(0, '.')
import api.index as m
mdb = mongomock.MongoClient()['mepham']
m.get_db = lambda: mdb
mdb.users.insert_one({'username': 'demo', 'email': 'demo@example.com', 'password': bcrypt.hashpw(b'password1', bcrypt.gensalt()), 'role': 'admin'})
m.send_email = lambda to, subject, text, html_body: print(text) or True
m.app.run(port=5055)
"
```

At 1280px and 375px wide, in light and dark theme, check:
- `/login`: photo left / form right on desktop; photo above form on mobile; no horizontal scroll.
- Eye button toggles password visibility and icon; `aria-pressed` flips.
- Wrong password shows the red error and keeps the username; network tab shows a POST to `/login` (not `docs.google.com`).
- `demo` / `password1` with Remember me lands on `/`; nav shows Logout.
- `/admin` while signed out lands on `/login?next=/admin`, and signing in returns to `/admin`.
- `/forgot-password` with `demo@example.com` shows the notice; the server console prints the reset link; opening it shows the reset form; mismatched passwords are blocked; a valid reset redirects to `/login` with the green flash.

Stop the server afterwards.

- [ ] **Step 5: Commit**

```bash
git add static/css/pages/login.css static/js/login.js
git commit -m "Style auth pages to match site and add password toggle script

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Provision Resend and verify a real reset email

This task needs the project owner's accounts. An agent executing the plan stops at Step 1 and hands these steps to the user.

**Files:** none (environment only)

- [ ] **Step 1: User links the Vercel project**

```bash
npm i -g vercel
vercel login
vercel link
```

- [ ] **Step 2: User installs Resend from the Marketplace**

```bash
vercel integration add resend
```

If the CLI hands off to the browser, finish the install in the Vercel dashboard. Then in the Resend dashboard, add and verify a sending domain (DNS records).

- [ ] **Step 3: User sets the sender**

```bash
vercel env add RESEND_FROM
```

Value: `Mepham Robotics <noreply@<verified-domain>>`, for Production, Preview, and Development.

- [ ] **Step 4: Pull env vars and confirm names (never print values)**

```bash
vercel env pull .env.local --yes
grep -o '^RESEND_[A-Z_]*' .env.local
```

Expected: `RESEND_API_KEY` and `RESEND_FROM`.

- [ ] **Step 5: Live check on a preview deployment**

Deploy a preview (`vercel`), open `/forgot-password` on the preview URL, and submit the email of a test account you control. Expected: an email arrives within a minute, the link opens the reset form on the preview host, and resetting lets you sign in with the new password.
