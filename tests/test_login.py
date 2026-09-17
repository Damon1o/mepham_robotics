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
