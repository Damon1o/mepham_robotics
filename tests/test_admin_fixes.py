"""Regressions for admin dashboard bugs found during the audits."""
import pytest
from bson import ObjectId

import api.index as app_module


def _as_admin(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def test_stats_update_logs_the_real_delta(client, db, make_user):
    """The old code read the previous stats *after* writing, so every logged
    change was zero."""
    db['site_metadata'].insert_one({'_id': 'global_stats', 'teams_count': 2,
                                    'members_count': 10, 'awards_count': 4,
                                    'hours_built': 100})
    _as_admin(client, make_user)
    client.post('/admin/api/stats', json={'field': 'teams_count', 'value': 5})

    entry = db['activities'].find_one({'type': 'stats_update'})
    assert entry['details']['teams_change'] == 3
    assert db['site_metadata'].find_one({'_id': 'global_stats'})['teams_count'] == 5


def test_award_update_logs_the_award_title(client, db, make_user):
    award_id = db['awards'].insert_one({'title': 'Excellence Award', 'count': 1}).inserted_id
    _as_admin(client, make_user)
    client.post(f'/admin/api/awards/{award_id}', json={'count': 4})

    entry = db['activities'].find_one({'type': 'awards_update'})
    assert entry['details']['title'] == 'Excellence Award'
    assert entry['details']['count_change'] == 3
    assert 'Excellence Award' in entry['description']


def test_team_award_update_names_the_team(client, db, make_user):
    award_id = db['awards'].insert_one(
        {'title': 'Design Award', 'team_number': '77628D', 'count': 0}).inserted_id
    _as_admin(client, make_user)
    client.post(f'/admin/api/awards/{award_id}', json={'count': 2})

    entry = db['activities'].find_one({'type': 'awards_update'})
    assert entry['details']['team_number'] == '77628D'
    assert 'Team 77628D "Design Award"' in entry['description']


def test_deleting_a_team_removes_its_awards(client, db, make_user, monkeypatch):
    team_id = db['teams'].insert_one({'team_number': '77628X', 'members': []}).inserted_id
    db['awards'].insert_one({'team_number': '77628X', 'title': 'Design Award', 'count': 1})
    db['awards'].insert_one({'title': 'Design Award', 'count': 9})  # global, must survive

    _as_admin(client, make_user)
    client.post(f'/admin/delete-team/{team_id}')

    assert db['teams'].count_documents({}) == 0
    assert db['awards'].count_documents({'team_number': '77628X'}) == 0
    assert db['awards'].count_documents({'team_number': {'$exists': False}}) == 1


def test_deleting_one_season_keeps_the_awards_other_seasons_share(client, db, make_user):
    """Award counters are keyed by team number; deleting last season's profile
    used to wipe the counts the current season still shows."""
    old = db['teams'].insert_one({'team_number': '77628A', 'season': '2025-26', 'members': []}).inserted_id
    db['teams'].insert_one({'team_number': '77628A', 'season': '2026-27', 'members': []})
    db['awards'].insert_one({'team_number': '77628A', 'title': 'Design Award', 'count': 3})

    _as_admin(client, make_user)
    client.post(f'/admin/delete-team/{old}')

    assert db['teams'].count_documents({'team_number': '77628A'}) == 1
    assert db['awards'].find_one({'team_number': '77628A'})['count'] == 3


def test_deleting_a_team_removes_its_uploaded_files(client, db, make_user, monkeypatch):
    deleted = []
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    team_id = db['teams'].insert_one({
        'team_number': '77628Y',
        'hero_image': 'https://blob.example/hero.png',
        'stl_path': 'https://blob.example/model.stl',
        'members': [{'name': 'Avery', 'photo': 'https://blob.example/avery.png'},
                    {'name': 'Bo', 'photo': 'static/assets/profile/base.png'}],
    }).inserted_id

    _as_admin(client, make_user)
    client.post(f'/admin/delete-team/{team_id}')

    assert sorted(deleted) == ['https://blob.example/avery.png',
                               'https://blob.example/hero.png',
                               'https://blob.example/model.stl']


def test_deleting_a_season_keeps_files_another_season_still_shows(client, db, make_user, monkeypatch):
    deleted = []
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    old = db['teams'].insert_one({'team_number': '77628A', 'season': '2025-26',
                                  'hero_image': 'https://blob.example/hero.png', 'members': []}).inserted_id
    db['teams'].insert_one({'team_number': '77628A', 'season': '2026-27',
                            'hero_image': 'https://blob.example/hero.png', 'members': []})
    _as_admin(client, make_user)
    client.post(f'/admin/delete-team/{old}')
    assert deleted == []


def test_blob_delete_failure_does_not_block_the_team_delete(client, db, make_user,
                                                            monkeypatch):
    def _boom(url):
        raise RuntimeError('blob store down')

    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', _boom)
    team_id = db['teams'].insert_one({
        'team_number': '77628Z', 'hero_image': 'https://blob.example/hero.png',
        'members': []}).inserted_id

    _as_admin(client, make_user)
    resp = client.post(f'/admin/delete-team/{team_id}')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('#teams')
    assert db['teams'].count_documents({}) == 0


def test_activity_timestamps_are_utc(client, db, make_user):
    _as_admin(client, make_user)
    client.post('/admin/api/stats', json={'field': 'hours_built', 'value': 1})
    stamp = db['activities'].find_one({'type': 'stats_update'})['timestamp']
    assert abs((app_module._utcnow() - stamp).total_seconds()) < 60


def test_time_ago_handles_a_future_timestamp(monkeypatch):
    import datetime
    future = app_module._utcnow() + datetime.timedelta(minutes=5)
    assert app_module.get_time_ago(future) == 'Just now'


def test_new_user_password_must_meet_the_minimum(client, db, make_user):
    _as_admin(client, make_user)
    client.post('/admin/create-user', data={'username': 'shorty', 'password': 'abc',
                                            'role': 'member'})
    assert db['users'].find_one({'username': 'shorty'}) is None


def test_user_update_rejects_a_short_new_password(client, db, make_user):
    target = make_user(username='target', password='target-password')
    _as_admin(client, make_user)
    original = db['users'].find_one({'_id': target['_id']})['password']
    client.post(f'/admin/update-user/{target["_id"]}',
                data={'username': 'target', 'password': 'abc', 'role': 'member'})
    assert db['users'].find_one({'_id': target['_id']})['password'] == original


def test_unknown_object_id_is_handled(client, make_user):
    _as_admin(client, make_user)
    resp = client.post(f'/admin/delete-team/{ObjectId()}', follow_redirects=True)
    assert resp.status_code == 200
    assert b'That team no longer exists.' in resp.data


@pytest.mark.parametrize('path', ['/admin/delete-team/nope', '/admin/delete-sponsor/nope',
                                  '/admin/delete-competition/nope', '/admin/delete-user/nope',
                                  '/admin/generate-reset-link/nope'])
def test_malformed_ids_get_a_plain_message_not_a_logged_error(client, make_user, path, caplog):
    _as_admin(client, make_user)
    resp = client.post(path, follow_redirects=True)
    assert resp.status_code == 200
    assert b'logged for the site maintainer' not in resp.data
    assert b'no longer exists' in resp.data


# --- Redirects keep the admin on their tab ---------------------------------------

@pytest.mark.parametrize('path,data,tab', [
    ('/admin/add-competition', {'comp_name': 'Q', 'comp_location': 'L', 'comp_date': '2026-11-01T08:30'}, 'events'),
    ('/admin/save-sponsor', {'name': 'Acme', 'level': 'Gold'}, 'sponsors'),
    ('/admin/create-user', {'username': 'newbie', 'password': 'long-enough-pw', 'role': 'member'}, 'users'),
])
def test_form_saves_return_to_their_tab(client, make_user, path, data, tab):
    _as_admin(client, make_user)
    resp = client.post(path, data=data)
    assert resp.headers['Location'].endswith('#' + tab)


# --- Validation that used to be missing -----------------------------------------------

@pytest.mark.parametrize('data', [
    {'comp_name': '', 'comp_location': 'L', 'comp_date': '2026-11-01T08:30'},
    {'comp_name': 'x' * 5000, 'comp_location': 'L', 'comp_date': '2026-11-01T08:30'},
    {'comp_name': 'Q', 'comp_location': 'L', 'comp_date': '2026-11-01T08:30', 'comp_link': 'javascript:alert(1)'},
])
def test_add_event_validates_like_the_inline_editor(client, db, make_user, data):
    _as_admin(client, make_user)
    client.post('/admin/add-competition', data=data)
    assert db['competitions'].count_documents({}) == 0


@pytest.mark.parametrize('data', [
    {'name': '', 'level': 'Gold'},
    {'name': 'Acme', 'level': 'Diamond<b>'},
    {'name': 'Acme', 'level': 'Gold', 'website': 'javascript:alert(1)'},
])
def test_sponsor_save_validates(client, db, make_user, data):
    _as_admin(client, make_user)
    client.post('/admin/save-sponsor', data=data)
    assert db['sponsors'].count_documents({}) == 0


def test_saving_an_unknown_sponsor_id_does_not_claim_success(client, db, make_user):
    _as_admin(client, make_user)
    resp = client.post('/admin/save-sponsor', data={'sponsor_id': str(ObjectId()), 'name': 'Ghost',
                                                    'level': 'Gold'}, follow_redirects=True)
    assert b'no longer exists' in resp.data
    assert db['sponsors'].count_documents({}) == 0


def test_sponsor_logo_can_be_removed(client, db, make_user, monkeypatch):
    deleted = []
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    sid = db['sponsors'].insert_one({'name': 'Acme', 'level': 'Gold',
                                     'logo': 'https://blob.example/logo.png'}).inserted_id
    _as_admin(client, make_user)
    client.post('/admin/save-sponsor', data={'sponsor_id': str(sid), 'name': 'Acme', 'level': 'Gold',
                                             'remove_logo': '1'})
    assert 'logo' not in db['sponsors'].find_one({'_id': sid})
    assert deleted == ['https://blob.example/logo.png']


def test_sponsors_are_listed_by_tier(client, db):
    db['sponsors'].insert_many([{'name': 'Bronze Co', 'level': 'Bronze'}, {'name': 'Plat Co', 'level': 'Platinum'},
                                {'name': 'Gold Co', 'level': 'Gold'}])
    page = client.get('/donate').get_data(as_text=True)
    assert page.index('Plat Co') < page.index('Gold Co') < page.index('Bronze Co')


@pytest.mark.parametrize('data', [
    {'username': 'ROOT', 'password': 'long-enough-pw'},                      # case-insensitive clash
    {'username': 'a b/<x>', 'password': 'long-enough-pw'},                   # username rules
    {'username': 'newbie', 'email': 'not-an-email', 'password': 'long-enough-pw'},
    {'username': 'newbie', 'password': 'long-enough-pw', 'confirm_password': 'different-pw'},
])
def test_admin_created_accounts_follow_the_signup_rules(client, db, make_user, data):
    _as_admin(client, make_user)
    client.post('/admin/create-user', data=dict(data, role='member'))
    assert db['users'].count_documents({}) == 1


def test_admin_created_accounts_are_active(client, db, make_user):
    _as_admin(client, make_user)
    client.post('/admin/create-user', data={'username': 'newbie', 'password': 'long-enough-pw', 'role': 'member',
                                            'full_name': 'New Bie'})
    user = db['users'].find_one({'username': 'newbie'})
    assert user['status'] == 'active' and user['full_name'] == 'New Bie' and user['created_at']


def test_duplicate_email_is_rejected_on_edit(client, db, make_user):
    make_user(username='taken', password='taken-password', email='taken@example.com')
    target = make_user(username='target', password='target-password', email='target@example.com')
    _as_admin(client, make_user)
    client.post(f'/admin/update-user/{target["_id"]}',
                data={'username': 'target', 'email': 'taken@example.com', 'role': 'member'})
    assert db['users'].find_one({'_id': target['_id']})['email'] == 'target@example.com'


def test_legacy_usernames_can_still_be_edited(client, db, make_user):
    """Accounts made before the username rules must not be locked out of edits."""
    target = make_user(username='Old Name', password='target-password', email='old@example.com')
    _as_admin(client, make_user)
    client.post(f'/admin/update-user/{target["_id"]}',
                data={'username': 'Old Name', 'email': 'new@example.com', 'role': 'editor'})
    user = db['users'].find_one({'_id': target['_id']})
    assert user['email'] == 'new@example.com' and user['role'] == 'editor'


# --- JSON API errors ----------------------------------------------------------------

def test_admin_api_csrf_failure_is_json(raw_client, make_user):
    make_user(username='root', password='root-password', role='admin')
    raw_client.post('/login', data={'username': 'root', 'password': 'root-password'})
    resp = raw_client.post('/admin/api/stats', json={'field': 'hours_built', 'value': 1})
    assert resp.status_code == 400
    assert resp.is_json and 'session expired' in resp.get_json()['error']


def test_unknown_admin_api_route_is_json(client, make_user):
    _as_admin(client, make_user)
    resp = client.post('/admin/api/nope', json={})
    assert resp.status_code == 404 and resp.is_json


@pytest.mark.parametrize('value', [float('inf'), 10 ** 30, True, 3.9, '', None])
def test_numbers_reject_nonsense_with_a_message(client, make_user, value):
    _as_admin(client, make_user)
    resp = client.post('/admin/api/stats', json={'field': 'teams_count', 'value': value})
    assert resp.status_code == 400 and resp.is_json


def test_award_counts_are_bounded(client, db, make_user):
    aid = db['awards'].insert_one({'title': 'X', 'count': 1}).inserted_id
    _as_admin(client, make_user)
    assert client.post(f'/admin/api/awards/{aid}', json={'count': 10 ** 30}).status_code == 400
    assert db['awards'].find_one({'_id': aid})['count'] == 1
