"""Outgoing email: the Resend client, forgot-password, and admin/member notifications."""
import re

import pytest

import api.index as app_module
from api import mail


@pytest.fixture
def outbox(monkeypatch):
    """Turn email on and capture what would be sent instead of calling Resend."""
    monkeypatch.setenv('RESEND_API_KEY', 're_test')
    monkeypatch.setenv('MAIL_FROM', 'Mepham Robotics <club@example.com>')
    sent = []

    class Response:
        status_code = 200
        text = ''

    def fake_post(url, json, timeout, headers):
        assert url == mail.RESEND_URL
        assert headers['Authorization'] == 'Bearer re_test'
        sent.append(json)
        return Response()

    monkeypatch.setattr(mail.requests, 'post', fake_post)
    return sent


@pytest.fixture
def no_email(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.delenv('MAIL_FROM', raising=False)


def _link(message):
    return re.search(r'https?://\S+/reset-password/\S+', message['text']).group(0)


# --- Client -------------------------------------------------------------------

def test_send_is_a_no_op_without_configuration(no_email, monkeypatch):
    monkeypatch.setattr(mail.requests, 'post', lambda *a, **k: pytest.fail('should not send'))
    assert mail.send('a@example.com', 'Hi', 'Body') is False


def test_send_reports_a_refusal(outbox, monkeypatch):
    class Refused:
        status_code = 422
        text = 'bad from'

    monkeypatch.setattr(mail.requests, 'post', lambda *a, **k: Refused())
    assert mail.send('a@example.com', 'Hi', 'Body') is False


def test_send_survives_a_network_error(outbox, monkeypatch):
    def boom(*a, **k):
        raise mail.requests.ConnectionError('down')

    monkeypatch.setattr(mail.requests, 'post', boom)
    assert mail.send('a@example.com', 'Hi', 'Body') is False


def test_send_skips_empty_recipient_lists(outbox):
    assert mail.send([], 'Hi', 'Body') is False
    assert outbox == []


# --- Forgot password -------------------------------------------------------------

def test_forgot_password_redirects_to_login_without_email(client, no_email):
    assert client.get('/forgot-password').status_code == 302
    page = client.get('/login').get_data(as_text=True)
    assert 'Contact a team admin' in page
    assert '/forgot-password' not in page


def test_login_links_to_forgot_password_when_email_works(client, outbox):
    assert '/forgot-password' in client.get('/login').get_data(as_text=True)


def test_forgot_password_emails_a_working_link(client, db, make_user, outbox):
    make_user()
    resp = client.post('/forgot-password', data={'username': 'Alice@Example.com'})
    assert resp.status_code == 200
    assert b'reset link is on its way' in resp.data
    assert len(outbox) == 1 and outbox[0]['to'] == ['alice@example.com']

    path = _link(outbox[0]).split('://', 1)[1].split('/', 1)[1]
    done = client.post(f'/{path}', data={'password': 'fresh-password', 'confirm_password': 'fresh-password'})
    assert done.status_code == 302
    assert client.post('/login', data={'username': 'alice', 'password': 'fresh-password'}).status_code == 302


def test_forgot_password_reads_the_same_for_unknown_accounts(client, db, make_user, outbox):
    make_user()
    known = client.post('/forgot-password', data={'username': 'alice'}).get_data(as_text=True)
    unknown = client.post('/forgot-password', data={'username': 'nobody'}).get_data(as_text=True)
    assert len(outbox) == 1
    strip = lambda page: re.sub(r'value="[^"]*"', '', page)
    assert strip(known) == strip(unknown)


def test_forgot_password_ignores_pending_accounts(client, db, make_user, outbox):
    user = make_user()
    db['users'].update_one({'_id': user['_id']}, {'$set': {'status': 'pending'}})
    client.post('/forgot-password', data={'username': 'alice'})
    assert outbox == []


def test_forgot_password_caps_mail_per_account(client, db, make_user, outbox, monkeypatch):
    make_user()
    ips = iter(f'10.0.0.{i}' for i in range(50))
    monkeypatch.setattr(app_module, '_client_ip', lambda: next(ips))
    for _ in range(app_module.FORGOT_ACCOUNT_LIMIT + 2):
        client.post('/forgot-password', data={'username': 'alice'})
    assert len(outbox) == app_module.FORGOT_ACCOUNT_LIMIT


def test_forgot_password_rate_limits_a_network(client, db, outbox):
    for _ in range(app_module.FORGOT_RATE_LIMIT):
        client.post('/forgot-password', data={'username': 'nobody'})
    assert client.post('/forgot-password', data={'username': 'nobody'}).status_code == 429


def test_new_link_replaces_the_old_one(client, db, make_user, outbox, monkeypatch):
    make_user()
    client.post('/forgot-password', data={'username': 'alice'})
    client.post('/forgot-password', data={'username': 'alice'})
    assert db['password_resets'].count_documents({}) == 1
    old_path = '/' + _link(outbox[0]).split('://', 1)[1].split('/', 1)[1]
    assert client.get(old_path).status_code == 400


# --- Notifications ------------------------------------------------------------------

def test_contact_message_alerts_admins_with_reply_to(client, db, make_user, outbox):
    make_user(username='root', email='root@example.com', role='admin')
    make_user(username='kid', email='kid@example.com', role='member')
    resp = client.post('/api/contact', json={'name': 'Pat', 'email': 'pat@example.com',
                                             'message': 'Can we sponsor you?', 'topic': 'sponsor'})
    assert resp.status_code == 200
    assert len(outbox) == 1
    assert outbox[0]['to'] == ['root@example.com']
    assert outbox[0]['reply_to'] == 'pat@example.com'
    assert 'Can we sponsor you?' in outbox[0]['text']


def test_contact_still_works_without_email(client, db, make_user, no_email):
    make_user(username='root', email='root@example.com', role='admin')
    resp = client.post('/api/contact', json={'name': 'Pat', 'email': 'pat@example.com', 'message': 'Hi'})
    assert resp.status_code == 200
    assert db['contact_messages'].count_documents({}) == 1


def test_signup_alerts_admins(client, db, make_user, outbox):
    make_user(username='root', email='root@example.com', role='admin')
    client.post('/signup', data={'username': 'newbie', 'email': 'newbie@example.com',
                                 'password': 'long-enough', 'confirm_password': 'long-enough'})
    assert [m['to'] for m in outbox] == [['root@example.com']]
    assert 'newbie' in outbox[0]['subject']


def test_approval_emails_the_new_member(client, db, make_user, outbox):
    make_user(username='root', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'correct-horse'})
    pending = db['users'].insert_one({'username': 'newbie', 'email': 'newbie@example.com',
                                      'password': b'x', 'role': 'member', 'status': 'pending'}).inserted_id
    resp = client.post(f'/admin/api/users/{pending}/approve', json={'role': 'member'})
    assert resp.status_code == 200
    assert outbox[-1]['to'] == ['newbie@example.com']
    assert 'ready' in outbox[-1]['subject']
