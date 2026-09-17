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
