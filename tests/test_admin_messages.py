import datetime

import pytest
from bson import ObjectId


@pytest.fixture
def message(db):
    return db['contact_messages'].insert_one({
        'name': 'Ada Lovelace',
        'email': 'ada@example.com',
        'message': 'Hello team',
        'status': 'new',
        'created_at': datetime.datetime(2026, 9, 17, 12, 0, 0),
        'ip': '203.0.113.5',
        'user_agent': 'pytest',
    }).inserted_id


@pytest.fixture
def admin_client(client, make_user):
    make_user(username='root', password='hunter2hunter2', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'hunter2hunter2'})
    return client


@pytest.mark.parametrize('action', ['read', 'archive', 'delete'])
def test_anonymous_cannot_mutate_messages(client, db, message, action):
    resp = client.post(f'/admin/messages/{message}/{action}')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
    assert db['contact_messages'].count_documents({'_id': message}) == 1
    assert db['contact_messages'].find_one({'_id': message})['status'] == 'new'


def test_admin_marks_message_read(admin_client, db, message):
    resp = admin_client.post(f'/admin/messages/{message}/read')
    assert resp.status_code == 302
    assert db['contact_messages'].find_one({'_id': message})['status'] == 'read'
    assert db['activities'].count_documents({'type': 'message_read'}) == 1


def test_admin_archives_message(admin_client, db, message):
    admin_client.post(f'/admin/messages/{message}/archive')
    assert db['contact_messages'].find_one({'_id': message})['status'] == 'archived'
    assert db['activities'].count_documents({'type': 'message_archive'}) == 1


def test_admin_deletes_message(admin_client, db, message):
    admin_client.post(f'/admin/messages/{message}/delete')
    assert db['contact_messages'].count_documents({'_id': message}) == 0
    assert db['activities'].count_documents({'type': 'message_delete'}) == 1


def test_activity_log_never_stores_the_message_body(admin_client, db, message):
    admin_client.post(f'/admin/messages/{message}/read')
    entry = db['activities'].find_one({'type': 'message_read'})
    assert 'Hello team' not in str(entry)


def test_invalid_id_is_handled(admin_client):
    resp = admin_client.post('/admin/messages/not-an-object-id/read')
    assert resp.status_code == 302


def test_missing_message_is_handled(admin_client, db):
    resp = admin_client.post(f'/admin/messages/{ObjectId()}/read')
    assert resp.status_code == 302


def test_dashboard_lists_messages_and_unread_count(admin_client, db, message):
    resp = admin_client.get('/admin')
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'data-tab="messages"' in body
    assert 'ada@example.com' in body


def test_message_body_is_escaped_in_the_dashboard(admin_client, db):
    db['contact_messages'].insert_one({
        'name': 'Mallory',
        'email': 'mallory@example.com',
        'message': '<script>alert(1)</script>',
        'status': 'new',
        'created_at': datetime.datetime(2026, 9, 17, 12, 0, 0),
    })
    body = admin_client.get('/admin').data.decode()
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;' in body

