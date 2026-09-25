"""Shared team editor: team members edit their own team, editors/admins edit any."""
import io

import pytest
from bson import ObjectId

import api.index as app_module


@pytest.fixture
def uploads(monkeypatch):
    keys = []

    def _upload(file, key):
        keys.append(key)
        return f'https://blob.example/{key}'

    monkeypatch.setattr(app_module, 'upload_to_vercel_blob', _upload)
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', lambda url: None)
    return keys


@pytest.fixture
def setup(db, make_user):
    alice = make_user(username='alice', password='alice-password', email='alice@example.com')
    bob = make_user(username='bob', password='bob-password', email='bob@example.com')
    team_id = db['teams'].insert_one({
        'team_number': '77628D', 'nickname': 'Old', 'specs': {}, 'goals': [],
        'members': [
            {'member_id': 'ma', 'name': 'Alice', 'role': 'Driver', 'user_id': str(alice['_id'])},
            {'member_id': 'mb', 'name': 'Bob', 'role': 'Builder', 'user_id': str(bob['_id'])},
        ]}).inserted_id
    other_id = db['teams'].insert_one({'team_number': '77628P', 'members': []}).inserted_id
    return {'team': str(team_id), 'other': str(other_id), 'alice': alice, 'bob': bob}


def login(client, username, password):
    client.post('/login', data={'username': username, 'password': password})
    return client


def team(db, team_id):
    return db['teams'].find_one({'_id': ObjectId(team_id)})


# --- Access ---------------------------------------------------------------------

def test_my_team_redirects_to_the_editor(client, setup):
    login(client, 'alice', 'alice-password')
    resp = client.get('/my-team')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith(f"/manage/team/{setup['team']}")


def test_my_team_without_a_team_explains(client, db, make_user):
    make_user(username='loner', password='loner-password', email='l@example.com')
    login(client, 'loner', 'loner-password')
    resp = client.get('/my-team')
    assert resp.status_code == 200
    assert 'not on a team roster yet' in resp.get_data(as_text=True).lower()


def test_my_team_needs_login(client, db):
    assert client.get('/my-team').status_code == 302


def test_member_opens_own_team_editor(client, setup):
    login(client, 'alice', 'alice-password')
    page = client.get(f"/manage/team/{setup['team']}").get_data(as_text=True)
    assert 'data-autosave' in page
    assert 'name="team_number"' not in page  # admin-only field hidden


def test_member_cannot_open_other_team(client, setup):
    login(client, 'alice', 'alice-password')
    assert client.get(f"/manage/team/{setup['other']}").status_code == 403


def test_editor_opens_any_team_with_admin_fields(client, setup, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    login(client, 'ed', 'editor-password')
    page = client.get(f"/manage/team/{setup['other']}").get_data(as_text=True)
    assert 'name="team_number"' in page


def test_nav_shows_my_team_for_rostered_user(client, setup):
    login(client, 'alice', 'alice-password')
    assert 'My Team' in client.get('/about').get_data(as_text=True)


# --- Team fields ------------------------------------------------------------------

def test_member_updates_whitelisted_field(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': 'nickname', 'value': 'New'})
    assert resp.status_code == 200
    assert team(db, setup['team'])['nickname'] == 'New'


def test_member_updates_spec(client, db, setup):
    login(client, 'alice', 'alice-password')
    client.post(f"/api/team/{setup['team']}/field", json={'field': 'specs.intake', 'value': 'Rollers'})
    assert team(db, setup['team'])['specs']['intake'] == 'Rollers'


@pytest.mark.parametrize('field', ['team_number', 'season', 'stl_path', '_id', 'members', 'specs'])
def test_member_cannot_touch_admin_fields(client, db, setup, field):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': field, 'value': 'x'})
    assert resp.status_code == 403
    assert team(db, setup['team'])['team_number'] == '77628D'


def test_editor_can_change_team_number(client, db, setup, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    login(client, 'ed', 'editor-password')
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': 'team_number', 'value': '99999A'})
    assert resp.status_code == 200
    assert team(db, setup['team'])['team_number'] == '99999A'


def test_unknown_field_is_rejected_even_for_admin(client, db, setup, make_user):
    make_user(username='root', password='root-password', email='r@example.com', role='admin')
    login(client, 'root', 'root-password')
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': 'password', 'value': 'x'})
    assert resp.status_code == 400


def test_numeric_admin_fields_are_validated(client, db, setup, make_user):
    make_user(username='root', password='root-password', email='r@example.com', role='admin')
    login(client, 'root', 'root-password')
    assert client.post(f"/api/team/{setup['team']}/field",
                       json={'field': 'since', 'value': 'abc'}).status_code == 400
    assert client.post(f"/api/team/{setup['team']}/field",
                       json={'field': 'since', 'value': '2019'}).status_code == 200
    assert team(db, setup['team'])['since'] == 2019


def test_field_value_length_is_capped(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': 'tagline', 'value': 'x' * 5000})
    assert resp.status_code == 400


def test_outsider_cannot_write(client, db, setup, make_user):
    make_user(username='eve', password='eve-password', email='eve@example.com')
    login(client, 'eve', 'eve-password')
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': 'nickname', 'value': 'pwned'})
    assert resp.status_code == 403
    assert team(db, setup['team'])['nickname'] == 'Old'


def test_anonymous_cannot_write(client, db, setup):
    resp = client.post(f"/api/team/{setup['team']}/field", json={'field': 'nickname', 'value': 'x'})
    assert resp.status_code == 401


def test_goals_list_replace(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/list/goals",
                       json={'items': [{'name': 'Skills', 'progress': 140}, {'name': '', 'progress': 5}]})
    assert resp.status_code == 200
    assert team(db, setup['team'])['goals'] == [{'name': 'Skills', 'progress': 100}]


def test_journey_is_admin_only(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/list/journey", json={'items': []})
    assert resp.status_code == 403


# --- Member cards -------------------------------------------------------------------

def test_member_edits_own_card(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/member/ma", json={'field': 'role', 'value': 'Captain'})
    assert resp.status_code == 200
    assert team(db, setup['team'])['members'][0]['role'] == 'Captain'


def test_member_cannot_edit_teammate_card(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/member/mb", json={'field': 'role', 'value': 'Nope'})
    assert resp.status_code == 403
    assert team(db, setup['team'])['members'][1]['role'] == 'Builder'


def test_member_cannot_relink_own_card(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/member/ma", json={'field': 'user_id', 'value': 'x'})
    assert resp.status_code == 400


def test_member_roles_field_splits_on_commas(client, db, setup):
    login(client, 'alice', 'alice-password')
    client.post(f"/api/team/{setup['team']}/member/ma", json={'field': 'roles', 'value': 'Captain, Coder ,'})
    assert team(db, setup['team'])['members'][0]['roles'] == ['Captain', 'Coder']


def test_editor_adds_and_removes_members(client, db, setup, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    login(client, 'ed', 'editor-password')
    resp = client.post(f"/api/team/{setup['other']}/member", json={'name': 'Dana'})
    assert resp.status_code == 200
    mid = resp.get_json()['member']['member_id']
    assert [m['name'] for m in team(db, setup['other'])['members']] == ['Dana']
    assert client.delete(f"/api/team/{setup['other']}/member/{mid}").status_code == 200
    assert team(db, setup['other'])['members'] == []


def test_member_cannot_add_members(client, db, setup):
    login(client, 'alice', 'alice-password')
    assert client.post(f"/api/team/{setup['team']}/member", json={'name': 'X'}).status_code == 403


# --- Uploads ----------------------------------------------------------------------------

def _png():
    return (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'0' * 64), 'pic.png')


def test_member_uploads_hero_image(client, db, setup, uploads):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/image", data={'hero_image': _png()},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    assert team(db, setup['team'])['hero_image'].startswith('https://blob.example/')


def test_member_uploads_own_photo_only(client, db, setup, uploads):
    login(client, 'alice', 'alice-password')
    ok = client.post(f"/api/team/{setup['team']}/image",
                     data={'member_photo': _png(), 'member_id': 'ma'}, content_type='multipart/form-data')
    assert ok.status_code == 200
    denied = client.post(f"/api/team/{setup['team']}/image",
                         data={'member_photo': _png(), 'member_id': 'mb'}, content_type='multipart/form-data')
    assert denied.status_code == 403


def test_member_cannot_upload_cad(client, db, setup, uploads):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['team']}/image",
                       data={'stl_file': (io.BytesIO(b'solid x'), 'robot.stl')}, content_type='multipart/form-data')
    assert resp.status_code == 403
    assert uploads == []
