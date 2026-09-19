import pytest

VALID = {'name': '  Ada Lovelace  ', 'email': '  Ada@Example.COM ', 'message': '  Hello team  '}


def post(client, payload, ip='203.0.113.5'):
    return client.post('/api/contact', json=payload, headers={'X-Forwarded-For': ip})


def test_valid_submission_is_stored(client, db):
    resp = post(client, VALID)
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}

    docs = list(db['contact_messages'].find())
    assert len(docs) == 1
    doc = docs[0]
    assert doc['name'] == 'Ada Lovelace'
    assert doc['email'] == 'ada@example.com'
    assert doc['message'] == 'Hello team'
    assert doc['status'] == 'new'
    assert doc['ip'] == '203.0.113.5'
    assert doc['created_at'] is not None


@pytest.mark.parametrize('payload', [
    {'name': 'Ada', 'email': 'ada@example.com'},
    {'name': 'Ada', 'email': 'ada@example.com', 'message': '   '},
    {'name': '', 'email': 'ada@example.com', 'message': 'hi'},
    {'name': 'Ada', 'email': 'notanemail', 'message': 'hi'},
    {'name': 'Ada', 'email': 'ada@example', 'message': 'hi'},
    {'name': 'A' * 101, 'email': 'ada@example.com', 'message': 'hi'},
    {'name': 'Ada', 'email': 'ada@example.com', 'message': 'x' * 4001},
])
def test_invalid_submissions_rejected(client, db, payload):
    resp = post(client, payload)
    assert resp.status_code == 400
    assert resp.get_json()['error']
    assert db['contact_messages'].count_documents({}) == 0


def test_honeypot_looks_successful_but_stores_nothing(client, db):
    resp = post(client, dict(VALID, website='http://spam.example'))
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True}
    assert db['contact_messages'].count_documents({}) == 0


def test_fourth_message_from_same_ip_is_rate_limited(client, db):
    for _ in range(3):
        assert post(client, VALID).status_code == 200

    resp = post(client, VALID)
    assert resp.status_code == 429
    assert 'minute' in resp.get_json()['error'].lower()
    assert db['contact_messages'].count_documents({}) == 3


def test_rate_limit_is_per_ip(client, db):
    for _ in range(3):
        post(client, VALID, ip='203.0.113.5')
    assert post(client, VALID, ip='203.0.113.5').status_code == 429

    resp = post(client, VALID, ip='198.51.100.7')
    assert resp.status_code == 200
    assert db['contact_messages'].count_documents({'ip': '198.51.100.7'}) == 1


def test_message_html_is_stored_verbatim(client, db):
    post(client, dict(VALID, message='<script>alert(1)</script>'))
    assert db['contact_messages'].find_one()['message'] == '<script>alert(1)</script>'


@pytest.mark.parametrize('sent, stored', [
    ('join', 'join'),
    ('sponsor', 'sponsor'),
    ('general', 'general'),
    ('SPONSOR', 'sponsor'),
    ('nonsense', 'general'),
    (None, 'general'),
])
def test_topic_is_normalized_to_the_allowed_set(client, db, sent, stored):
    payload = dict(VALID)
    if sent is not None:
        payload['topic'] = sent
    assert post(client, payload).status_code == 200
    assert db['contact_messages'].find_one()['topic'] == stored


def test_contact_page_no_longer_uses_google_forms(client):
    resp = client.get('/contact')
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'id="contact-website"' in body
    assert 'aria-expanded' in body
    assert 'docs.google.com/forms' not in body
