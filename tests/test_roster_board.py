"""Drag-and-drop roster moves on the admin People tab."""
import pytest


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def teams(db):
    d = db['teams'].insert_one({'team_number': '77628D', 'members': [
        {'member_id': 'm1', 'name': 'Avery', 'role': 'Driver', 'user_id': '', 'photo': 'p.png',
         'subteam': 'Mechanical'},
    ]}).inserted_id
    p = db['teams'].insert_one({'team_number': '77628P', 'members': []}).inserted_id
    return str(d), str(p)


def _members(db, team_id):
    from bson import ObjectId
    return db['teams'].find_one({'_id': ObjectId(team_id)})['members']


def test_move_member_between_teams_keeps_their_details(admin, db, teams):
    d, p = teams
    resp = admin.post('/admin/api/roster/move', json={'member_id': 'm1', 'to_team_id': p})
    assert resp.status_code == 200
    assert _members(db, d) == []
    moved = _members(db, p)
    assert len(moved) == 1
    assert moved[0]['name'] == 'Avery'
    assert moved[0]['subteam'] == 'Mechanical'
    assert moved[0]['member_id'] == 'm1'


def test_move_member_to_unassigned_removes_them(admin, db, teams):
    d, _ = teams
    resp = admin.post('/admin/api/roster/move', json={'member_id': 'm1', 'to_team_id': None})
    assert resp.status_code == 200
    assert _members(db, d) == []


def test_drop_user_account_onto_team_creates_linked_member(admin, db, teams, make_user):
    _, p = teams
    user = make_user(username='casey', email='casey@example.com')
    resp = admin.post('/admin/api/roster/move', json={'user_id': str(user['_id']), 'to_team_id': p})
    assert resp.status_code == 200
    body = resp.get_json()
    members = _members(db, p)
    assert members[0]['user_id'] == str(user['_id'])
    assert members[0]['name'] == 'casey'
    assert body['member']['member_id'] == members[0]['member_id']


def test_user_account_is_only_on_one_roster(admin, db, teams, make_user):
    d, p = teams
    user = make_user(username='casey', email='casey@example.com')
    admin.post('/admin/api/roster/move', json={'user_id': str(user['_id']), 'to_team_id': d})
    admin.post('/admin/api/roster/move', json={'user_id': str(user['_id']), 'to_team_id': p})
    assert [m['name'] for m in _members(db, d)] == ['Avery']
    assert [m['user_id'] for m in _members(db, p)] == [str(user['_id'])]


def test_unassign_and_return_keeps_the_card(admin, db, teams, make_user):
    d, p = teams
    user = make_user(username='casey', email='casey@example.com')
    db['teams'].update_one({'team_number': '77628D'}, {'$push': {'members': {
        'member_id': 'mc', 'name': 'Casey Park', 'role': 'Programmer', 'user_id': str(user['_id']),
        'photo': 'https://blob.example/casey.png'}}})
    admin.post('/admin/api/roster/move', json={'member_id': 'mc', 'to_team_id': None})
    assert all(m.get('user_id') != str(user['_id']) for m in _members(db, d))
    resp = admin.post('/admin/api/roster/move', json={'user_id': str(user['_id']), 'to_team_id': p})
    card = _members(db, p)[0]
    assert (card['name'], card['role'], card['member_id']) == ('Casey Park', 'Programmer', 'mc')
    assert resp.get_json()['member']['member_id'] == 'mc'
    assert 'roster_card' not in db['users'].find_one({'_id': user['_id']})


def test_move_to_same_team_is_a_no_op(admin, db, teams):
    d, _ = teams
    resp = admin.post('/admin/api/roster/move', json={'member_id': 'm1', 'to_team_id': d})
    assert resp.status_code == 200
    assert [m['member_id'] for m in _members(db, d)] == ['m1']


def test_move_unknown_member_is_404(admin, db, teams):
    _, p = teams
    assert admin.post('/admin/api/roster/move', json={'member_id': 'nope', 'to_team_id': p}).status_code == 404


def test_move_to_unknown_team_is_404(admin, db, teams):
    resp = admin.post('/admin/api/roster/move', json={'member_id': 'm1', 'to_team_id': 'f' * 24})
    assert resp.status_code == 404
    d, _ = teams
    assert len(_members(db, d)) == 1


def test_move_needs_admin(client, db, teams, make_user):
    make_user(username='plain', password='plain-password', email='p@example.com')
    client.post('/login', data={'username': 'plain', 'password': 'plain-password'})
    _, p = teams
    assert client.post('/admin/api/roster/move', json={'member_id': 'm1', 'to_team_id': p}).status_code == 403


def test_move_without_csrf_is_rejected(raw_client, db, teams):
    _, p = teams
    assert raw_client.post('/admin/api/roster/move', json={'member_id': 'm1', 'to_team_id': p}).status_code == 400


def test_dashboard_backfills_member_ids(admin, db):
    db['teams'].insert_one({'team_number': '1A', 'members': [{'name': 'Old Timer', 'role': 'x'}]})
    admin.get('/admin')
    member = db['teams'].find_one({'team_number': '1A'})['members'][0]
    assert member['member_id']


def test_board_renders_columns_and_cards(admin, db, teams, make_user):
    make_user(username='floater', email='f@example.com')
    page = admin.get('/admin').get_data(as_text=True)
    assert 'roster-board' in page
    assert 'Unassigned' in page
    assert 'Avery' in page
    assert 'floater' in page
    assert 'data-member-id="m1"' in page
