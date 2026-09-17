import datetime
import hashlib

import bcrypt
import pytest

import api.index as app_module


def _insert_token(db, user, token, created_at=None):
    db['password_resets'].insert_one({
        'user_id': user['_id'],
        'token_hash': app_module._hash_token(token),
        'created_at': created_at or app_module._utcnow(),
    })


def _login_as(client, make_user, role, username):
    make_user(username=username, role=role, email=f'{username}@example.com')
    client.post('/login', data={'username': username, 'password': 'correct-horse'})


def _generated_link(client):
    with client.session_transaction() as s:
        return s.get('_generated_reset_link')


def test_reset_with_valid_token_updates_password_once(client, db, make_user):
    user = make_user()
    token = 'a' * 43
    _insert_token(db, user, token)

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


def test_reset_rejects_expired_token(client, db, make_user):
    user = make_user()
    token = 'b' * 43
    _insert_token(db, user, token,
                  created_at=app_module._utcnow() - datetime.timedelta(hours=1, minutes=1))
    assert client.get(f'/reset-password/{token}').status_code == 400


def test_reset_rejects_unknown_token(client):
    resp = client.get('/reset-password/not-a-real-token')
    assert resp.status_code == 400
    assert resp.headers['Referrer-Policy'] == 'no-referrer'


@pytest.mark.parametrize('password,confirm,message', [
    ('short', 'short', b'at least 8 characters'),
    ('long-enough-1', 'long-enough-2', b'do not match'),
])
def test_reset_validates_password(client, db, make_user, password, confirm, message):
    user = make_user()
    token = 'c' * 43
    _insert_token(db, user, token)
    resp = client.post(f'/reset-password/{token}',
                       data={'password': password, 'confirm_password': confirm})
    assert resp.status_code == 400
    assert message in resp.data


def test_admin_generate_reset_link_creates_working_link(client, db, make_user):
    _login_as(client, make_user, 'admin', 'boss')
    target = make_user(username='alice', email='alice@example.com')

    resp = client.post(f'/admin/generate-reset-link/{target["_id"]}')
    assert resp.status_code == 302

    link = _generated_link(client)
    assert link is not None
    token = link.rsplit('/', 1)[-1]

    doc = db['password_resets'].find_one({'user_id': target['_id']})
    assert doc is not None
    assert doc['token_hash'] == hashlib.sha256(token.encode()).hexdigest()

    reset_resp = client.post(f'/reset-password/{token}',
                             data={'password': 'new-secure-pass', 'confirm_password': 'new-secure-pass'})
    assert reset_resp.status_code == 302
    stored = db['users'].find_one({'_id': target['_id']})
    assert bcrypt.checkpw(b'new-secure-pass', stored['password'])

    reused = client.post(f'/reset-password/{token}',
                         data={'password': 'another-1', 'confirm_password': 'another-1'})
    assert reused.status_code == 400


def test_admin_generate_reset_link_replaces_old_token(client, db, make_user):
    _login_as(client, make_user, 'admin', 'boss')
    target = make_user(username='alice', email='alice@example.com')

    client.post(f'/admin/generate-reset-link/{target["_id"]}')
    token1 = _generated_link(client).rsplit('/', 1)[-1]

    client.post(f'/admin/generate-reset-link/{target["_id"]}')
    token2 = _generated_link(client).rsplit('/', 1)[-1]

    assert token1 != token2
    assert db['password_resets'].count_documents({'user_id': target['_id']}) == 1
    assert client.get(f'/reset-password/{token1}').status_code == 400
    assert client.get(f'/reset-password/{token2}').status_code == 200


def test_admin_generate_reset_link_uses_public_base_url(client, db, make_user, monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://mepham.example.org')
    _login_as(client, make_user, 'admin', 'boss')
    target = make_user(username='alice', email='alice@example.com')

    client.post(f'/admin/generate-reset-link/{target["_id"]}')
    link = _generated_link(client)
    assert link.startswith('https://mepham.example.org/reset-password/')


def test_admin_generate_reset_link_rejects_non_admin(client, db, make_user):
    _login_as(client, make_user, 'member', 'rando')
    target = make_user(username='alice', email='alice@example.com')

    resp = client.post(f'/admin/generate-reset-link/{target["_id"]}')
    assert resp.status_code == 302
    assert resp.location != '/admin#users'
    assert db['password_resets'].count_documents({'user_id': target['_id']}) == 0


def test_admin_generate_reset_link_rejects_logged_out(client, db, make_user):
    target = make_user(username='alice', email='alice@example.com')
    resp = client.post(f'/admin/generate-reset-link/{target["_id"]}')
    assert resp.status_code == 302
    assert resp.location.startswith('/login')
    assert db['password_resets'].count_documents({'user_id': target['_id']}) == 0
