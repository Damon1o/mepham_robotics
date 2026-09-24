"""Regressions for admin dashboard bugs found during the audit."""
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
    client.post('/admin/update-stats', data={'teams_count': 5, 'members_count': 18,
                                             'awards_count': 4, 'hours_built': 250})

    entry = db['activities'].find_one({'type': 'stats_update'})
    assert entry['details']['teams_change'] == 3
    assert entry['details']['members_change'] == 8
    assert entry['details']['awards_change'] == 0
    assert entry['details']['hours_change'] == 150
    assert db['site_metadata'].find_one({'_id': 'global_stats'})['teams_count'] == 5


def test_award_update_logs_the_award_title(client, db, make_user):
    """Award documents store `title`; the log read `name` and always said
    'Unknown'."""
    award_id = db['awards'].insert_one(
        {'title': 'Excellence Award', 'count': 1}).inserted_id
    _as_admin(client, make_user)
    client.post('/admin/update-awards', data={f'award_{award_id}': '4'})

    entry = db['activities'].find_one({'type': 'awards_update'})
    assert entry['details']['award_changes'][0]['name'] == 'Excellence Award'
    assert entry['details']['award_changes'][0]['change'] == 3


def test_team_award_update_logs_the_award_title(client, db, make_user):
    award_id = db['awards'].insert_one(
        {'title': 'Design Award', 'team_number': '77628D', 'count': 0}).inserted_id
    _as_admin(client, make_user)
    client.post('/admin/update-team-awards', data={f'team_award_{award_id}': '2'})

    entry = db['activities'].find_one({'type': 'awards_update'})
    assert entry['details']['team_award_changes'][0]['award'] == 'Design Award'


def test_deleting_a_team_removes_its_awards(client, db, make_user, monkeypatch):
    team_id = db['teams'].insert_one({'team_number': '77628X', 'members': []}).inserted_id
    db['awards'].insert_one({'team_number': '77628X', 'title': 'Design Award', 'count': 1})
    db['awards'].insert_one({'title': 'Design Award', 'count': 9})  # global, must survive

    _as_admin(client, make_user)
    client.post(f'/admin/delete-team/{team_id}')

    assert db['teams'].count_documents({}) == 0
    assert db['awards'].count_documents({'team_number': '77628X'}) == 0
    assert db['awards'].count_documents({'team_number': {'$exists': False}}) == 1


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
    assert db['teams'].count_documents({}) == 0


def test_activity_timestamps_are_utc(client, db, make_user):
    _as_admin(client, make_user)
    client.post('/admin/update-stats', data={'teams_count': 1, 'members_count': 1,
                                             'awards_count': 1, 'hours_built': 1})
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
    resp = client.post(f'/admin/delete-team/{ObjectId()}')
    assert resp.status_code == 302
