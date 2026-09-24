"""Newsletter signup, unsubscribe, and the admin CSV export."""
import pytest

import api.index as app_module


def _admin(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})


def test_signup_stores_subscriber(client, db):
    resp = client.post('/api/newsletter', json={'email': 'Fan@Example.COM'})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    doc = db['newsletter_subscribers'].find_one({'email': 'fan@example.com'})
    assert doc and doc['unsubscribe_token']


def test_signup_is_idempotent(client, db):
    client.post('/api/newsletter', json={'email': 'fan@example.com'})
    first = db['newsletter_subscribers'].find_one({'email': 'fan@example.com'})
    resp = client.post('/api/newsletter', json={'email': 'fan@example.com'})
    assert resp.status_code == 200
    assert db['newsletter_subscribers'].count_documents({}) == 1
    # The original token survives, so earlier unsubscribe links keep working.
    assert db['newsletter_subscribers'].find_one(
        {'email': 'fan@example.com'})['unsubscribe_token'] == first['unsubscribe_token']


def test_signup_rejects_bad_address(client, db):
    resp = client.post('/api/newsletter', json={'email': 'not-an-email'})
    assert resp.status_code == 400
    assert db['newsletter_subscribers'].count_documents({}) == 0


def test_signup_rejects_oversized_address(client, db):
    resp = client.post('/api/newsletter',
                       json={'email': 'a' * 300 + '@example.com'})
    assert resp.status_code == 400
    assert db['newsletter_subscribers'].count_documents({}) == 0


def test_honeypot_looks_successful_but_stores_nothing(client, db):
    resp = client.post('/api/newsletter',
                       json={'email': 'bot@example.com', 'website': 'spam'})
    assert resp.status_code == 200
    assert db['newsletter_subscribers'].count_documents({}) == 0


def test_signup_is_rate_limited(client, db):
    for i in range(app_module.NEWSLETTER_RATE_LIMIT):
        assert client.post('/api/newsletter',
                           json={'email': f'fan{i}@example.com'}).status_code == 200
    resp = client.post('/api/newsletter', json={'email': 'onemore@example.com'})
    assert resp.status_code == 429


def test_unsubscribe_removes_the_address(client, db):
    client.post('/api/newsletter', json={'email': 'fan@example.com'})
    token = db['newsletter_subscribers'].find_one({})['unsubscribe_token']
    resp = client.get(f'/unsubscribe/{token}')
    assert resp.status_code == 200
    assert b'unsubscribed' in resp.data
    assert db['newsletter_subscribers'].count_documents({}) == 0


def test_unsubscribe_with_unknown_token_is_harmless(client, db):
    client.post('/api/newsletter', json={'email': 'fan@example.com'})
    resp = client.get('/unsubscribe/nope')
    assert resp.status_code == 200
    assert db['newsletter_subscribers'].count_documents({}) == 1


def test_csv_export_requires_admin(client, make_user):
    make_user(username='member', password='member-password', role='member')
    client.post('/login', data={'username': 'member', 'password': 'member-password'})
    assert client.get('/admin/subscribers.csv').status_code == 302


@pytest.mark.parametrize('value,expected', [
    ('=HYPERLINK("http://evil")', "'=HYPERLINK(\"http://evil\")"),
    ('+1234', "'+1234"),
    ('-cmd', "'-cmd"),
    ('@SUM(A1)', "'@SUM(A1)"),
    ('\tinjected', "'\tinjected"),
    ('fan@example.com', 'fan@example.com'),
    (None, ''),
])
def test_csv_safe_neutralises_formulas(value, expected):
    assert app_module.csv_safe(value) == expected


def test_csv_export_neutralises_formula_addresses(client, db, make_user):
    """A subscriber can pick their own address, and it lands in a spreadsheet
    an admin opens."""
    db['newsletter_subscribers'].insert_one(
        {'email': '=HYPERLINK("http://evil.example","click")@example.com',
         'created_at': app_module._utcnow()})
    _admin(client, make_user)
    body = client.get('/admin/subscribers.csv').get_data(as_text=True)
    assert '"\'=HYPERLINK' in body
    assert not any(line.startswith('=') for line in body.splitlines())


def test_csv_export_lists_subscribers(client, db, make_user):
    client.post('/api/newsletter', json={'email': 'fan@example.com'})
    _admin(client, make_user)
    resp = client.get('/admin/subscribers.csv')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    assert b'fan@example.com' in resp.data
