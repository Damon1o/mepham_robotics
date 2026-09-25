"""Self sign-up, the pending state, and admin approval."""
import pytest


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def _signup(client, **extra):
    data = {'username': 'newbie', 'email': 'newbie@example.com',
            'password': 'long-enough-pw', 'confirm_password': 'long-enough-pw'}
    data.update(extra)
    return client.post('/signup', data=data)


def test_signup_page_renders(client, db):
    resp = client.get('/signup')
    assert resp.status_code == 200
    assert 'Create account' in resp.get_data(as_text=True)


def test_login_page_links_to_signup(client, db):
    assert '/signup' in client.get('/login').get_data(as_text=True)


def test_signup_creates_a_pending_member(client, db):
    resp = _signup(client)
    assert resp.status_code == 200
    user = db['users'].find_one({'username': 'newbie'})
    assert user['status'] == 'pending'
    assert user['role'] == 'member'
    assert user['password'] != b'long-enough-pw'
    assert 'waiting for approval' in resp.get_data(as_text=True).lower()


def test_signup_records_the_requested_team(client, db):
    team_id = db['teams'].insert_one({'team_number': '77628D'}).inserted_id
    _signup(client, requested_team=str(team_id))
    assert db['users'].find_one({'username': 'newbie'})['requested_team'] == str(team_id)


def test_signup_ignores_an_unknown_team(client, db):
    _signup(client, requested_team='not-a-team')
    assert 'requested_team' not in db['users'].find_one({'username': 'newbie'})


@pytest.mark.parametrize('extra,message', [
    ({'username': ''}, 'username'),
    ({'username': 'has space'}, 'username'),
    ({'email': 'nope'}, 'email'),
    ({'password': 'short', 'confirm_password': 'short'}, '8 characters'),
    ({'confirm_password': 'different-pw'}, 'do not match'),
])
def test_signup_validation(client, db, extra, message):
    resp = _signup(client, **extra)
    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True).lower()
    assert db['users'].count_documents({}) == 0


def test_signup_rejects_taken_username_or_email(client, db, make_user):
    make_user(username='newbie', email='other@example.com')
    assert _signup(client).status_code == 400
    assert _signup(client, username='fresh', email='other@example.com').status_code == 400
    assert db['users'].count_documents({}) == 1


def test_signup_username_check_is_case_insensitive(client, db, make_user):
    make_user(username='Newbie', email='x@example.com')
    assert _signup(client).status_code == 400


def test_signup_is_rate_limited(client, db):
    for i in range(5):
        _signup(client, username=f'user{i}', email=f'u{i}@example.com')
    resp = _signup(client, username='user9', email='u9@example.com')
    assert resp.status_code == 429


def test_pending_user_cannot_log_in(client, db):
    _signup(client)
    resp = client.post('/login', data={'username': 'newbie', 'password': 'long-enough-pw'})
    assert resp.status_code == 403
    assert 'waiting for an admin' in resp.get_data(as_text=True).lower()
    with client.session_transaction() as sess:
        assert 'user' not in sess


def test_pending_user_with_wrong_password_gets_the_generic_error(client, db):
    _signup(client)
    resp = client.post('/login', data={'username': 'newbie', 'password': 'wrong-password'})
    assert resp.status_code == 401
    assert 'approval' not in resp.get_data(as_text=True).lower()


def test_existing_users_without_status_still_log_in(client, make_user):
    make_user(username='legacy', password='legacy-password')
    resp = client.post('/login', data={'username': 'legacy', 'password': 'legacy-password'})
    assert resp.status_code == 302


def test_admin_sees_pending_requests(admin, db):
    db['users'].insert_one({'username': 'waiting', 'email': 'w@example.com', 'password': b'x',
                            'role': 'member', 'status': 'pending'})
    page = admin.get('/admin').get_data(as_text=True)
    assert 'Pending approval' in page
    assert 'waiting' in page


def test_approve_activates_and_places_on_team(admin, db):
    team_id = db['teams'].insert_one({'team_number': '77628D', 'members': []}).inserted_id
    uid = db['users'].insert_one({'username': 'waiting', 'email': 'w@example.com', 'password': b'x',
                                  'role': 'member', 'status': 'pending'}).inserted_id
    resp = admin.post(f'/admin/api/users/{uid}/approve', json={'role': 'editor', 'team_id': str(team_id)})
    assert resp.status_code == 200
    user = db['users'].find_one({'_id': uid})
    assert user['status'] == 'active'
    assert user['role'] == 'editor'
    members = db['teams'].find_one({'_id': team_id})['members']
    assert [m['user_id'] for m in members] == [str(uid)]
    assert members[0]['name'] == 'waiting'
    assert members[0]['member_id']


def test_approve_rejects_bad_role(admin, db):
    uid = db['users'].insert_one({'username': 'waiting', 'password': b'x', 'status': 'pending'}).inserted_id
    assert admin.post(f'/admin/api/users/{uid}/approve', json={'role': 'owner'}).status_code == 400
    assert db['users'].find_one({'_id': uid})['status'] == 'pending'


def test_reject_deletes_the_request(admin, db):
    uid = db['users'].insert_one({'username': 'waiting', 'password': b'x', 'status': 'pending'}).inserted_id
    assert admin.post(f'/admin/api/users/{uid}/reject').status_code == 200
    assert db['users'].find_one({'_id': uid}) is None


def test_reject_refuses_active_accounts(admin, db, make_user):
    user = make_user(username='active-one', email='a1@example.com')
    assert admin.post(f"/admin/api/users/{user['_id']}/reject").status_code == 400
    assert db['users'].find_one({'_id': user['_id']})


def test_approval_endpoints_need_admin(client, db, make_user):
    make_user(username='plain', password='plain-password', email='p@example.com')
    client.post('/login', data={'username': 'plain', 'password': 'plain-password'})
    uid = db['users'].insert_one({'username': 'waiting', 'password': b'x', 'status': 'pending'}).inserted_id
    resp = client.post(f'/admin/api/users/{uid}/approve', json={'role': 'member'})
    assert resp.status_code == 403
    assert db['users'].find_one({'_id': uid})['status'] == 'pending'


def test_inline_role_change(admin, db, make_user):
    user = make_user(username='bob', email='bob@example.com')
    resp = admin.post(f"/admin/api/users/{user['_id']}/role", json={'role': 'editor'})
    assert resp.status_code == 200
    changed = db['users'].find_one({'_id': user['_id']})
    assert changed['role'] == 'editor'
    assert changed['session_version'] == 1


def test_inline_role_change_keeps_the_last_admin(admin, db):
    root = db['users'].find_one({'username': 'root'})
    resp = admin.post(f"/admin/api/users/{root['_id']}/role", json={'role': 'member'})
    assert resp.status_code == 400
    assert db['users'].find_one({'_id': root['_id']})['role'] == 'admin'


def test_editor_can_reach_member_pages(client, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    assert client.get('/resources').status_code == 200


def test_session_of_a_user_moved_back_to_pending_stops_working(client, db, make_user):
    user = make_user(username='alice', password='alice-password')
    client.post('/login', data={'username': 'alice', 'password': 'alice-password'})
    assert client.get('/resources').status_code == 200
    db['users'].update_one({'_id': user['_id']}, {'$set': {'status': 'pending'}})
    assert client.get('/resources').status_code == 302
