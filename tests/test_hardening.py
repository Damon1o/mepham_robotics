"""Hardening from the November 2026 audit: self-hosted scripts, login cap per address, password length."""
import base64
import hashlib
import pathlib
import re

import pytest

import api.index as app_module

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = ROOT / 'static' / 'js'
VENDOR = JS / 'vendor'


# --- No outside script hosts ------------------------------------------------------------------

def test_csp_only_runs_scripts_from_this_site(client):
    csp = client.get('/').headers['Content-Security-Policy']
    script_src = next(part.strip() for part in csp.split(';') if part.strip().startswith('script-src'))
    assert script_src == "script-src 'self'"


def test_no_script_is_loaded_from_a_cdn():
    hosts = re.compile(r'cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com')
    for path in list(JS.glob('*.js')) + list((ROOT / 'templates').rglob('*.html')):
        assert not hosts.search(path.read_text(encoding='utf-8')), path.name


@pytest.mark.parametrize('name', ['marked-9.1.6.min.js', 'dompurify-3.1.6.min.js'])
def test_vendored_chat_libraries_match_the_hash_the_page_checks(name):
    """script.js loads each file with an SRI hash, so a changed file would simply not run."""
    digest = base64.b64encode(hashlib.sha384((VENDOR / name).read_bytes()).digest()).decode()
    script = (JS / 'script.js').read_text(encoding='utf-8')
    assert re.search(rf"'{re.escape(name)}',\s*'sha384-{re.escape(digest)}'", script), name


def test_vendored_three_modules_share_one_instance():
    """The examples import three by relative path; a bare 'three' needs an import map."""
    folder = VENDOR / 'three-0.160.0'
    assert (folder / 'three.module.min.js').stat().st_size > 500_000
    for name in ('STLLoader.js', 'OrbitControls.js'):
        text = (folder / name).read_text(encoding='utf-8')
        assert "from './three.module.min.js';" in text and "from 'three'" not in text, name
    team = (JS / 'team.js').read_text(encoding='utf-8')
    for name in ('three.module.min.js', 'STLLoader.js', 'OrbitControls.js'):
        assert f"import(THREE_BASE + '{name}')" in team


def test_vendored_files_are_served(client):
    for name in ('marked-9.1.6.min.js', 'dompurify-3.1.6.min.js', 'three-0.160.0/STLLoader.js'):
        response = client.get(f'/static/js/vendor/{name}')
        assert response.status_code == 200, name
        assert 'javascript' in response.mimetype


# --- Sign-in attempts per address -----------------------------------------------------------------

def test_one_address_cannot_try_a_password_on_every_account(client, make_user):
    make_user(username='erin', password='erin-password', email='erin@example.com')
    spray = {'X-Forwarded-For': '203.0.113.7'}
    for i in range(app_module.LOGIN_MAX_IP_ATTEMPTS):
        resp = client.post('/login', data={'username': f'user{i}', 'password': 'Spring2026!'}, headers=spray)
        assert resp.status_code == 401
    # The next account it tries is refused, even with the right password...
    resp = client.post('/login', data={'username': 'erin', 'password': 'erin-password'}, headers=spray)
    assert resp.status_code == 429
    # ...while everyone else signs in as usual.
    resp = client.post('/login', data={'username': 'erin', 'password': 'erin-password'},
                       headers={'X-Forwarded-For': '198.51.100.9'})
    assert resp.status_code == 302


# --- Password length ------------------------------------------------------------------------------

@pytest.mark.parametrize('password, problem', [
    ('short', 'at least 8'),
    ('x' * 73, '72 characters or fewer'),
    ('é' * 37, '72 characters or fewer'),   # 74 bytes: bcrypt counts bytes
    ('x' * 72, ''),
    ('correct horse battery staple', ''),
])
def test_password_length_rule(password, problem):
    assert problem in app_module._password_length_error(password)
    assert bool(app_module._password_length_error(password)) == bool(problem)


def test_signup_refuses_a_password_bcrypt_would_cut_short(client, db):
    long_password = 'x' * 80
    resp = client.post('/signup', data={'username': 'longpass', 'email': 'long@example.com',
                                        'password': long_password, 'confirm_password': long_password})
    assert resp.status_code == 400
    assert '72 characters or fewer' in resp.get_data(as_text=True)
    assert db['users'].find_one({'username': 'longpass'}) is None


def test_reset_refuses_a_password_bcrypt_would_cut_short(client, db, make_user):
    user = make_user()
    token = 'b' * 43
    db['password_resets'].insert_one({'user_id': user['_id'], 'token_hash': app_module._hash_token(token),
                                      'created_at': app_module._utcnow()})
    resp = client.post(f'/reset-password/{token}', data={'password': 'y' * 80, 'confirm_password': 'y' * 80})
    assert resp.status_code == 400
    assert '72 characters or fewer' in resp.get_data(as_text=True)
    # The token is still good for a second try.
    assert db['password_resets'].count_documents({'user_id': user['_id']}) == 1


def test_account_refuses_a_password_bcrypt_would_cut_short(client, make_user):
    make_user()
    client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    resp = client.post('/account/password', data={'current_password': 'correct-horse',
                                                  'new_password': 'z' * 80, 'confirm_password': 'z' * 80})
    assert resp.status_code == 400
    assert 'Your new password must be 72 characters or fewer' in resp.get_data(as_text=True)
