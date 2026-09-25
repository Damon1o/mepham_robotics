"""Autosaving admin controls: stats, award steppers, event fields, quick team create."""
import datetime

import pytest
from bson import ObjectId


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def test_stat_autosave(admin, db):
    resp = admin.post('/admin/api/stats', json={'field': 'hours_built', 'value': 1200})
    assert resp.status_code == 200
    assert db['site_metadata'].find_one({'_id': 'global_stats'})['hours_built'] == 1200
    assert db['activities'].find_one({'type': 'stats_update'})['details']['hours_change'] == 1200


@pytest.mark.parametrize('payload', [
    {'field': 'bogus', 'value': 1},
    {'field': 'teams_count', 'value': 'abc'},
    {'field': 'teams_count', 'value': -1},
])
def test_stat_autosave_validation(admin, db, payload):
    assert admin.post('/admin/api/stats', json=payload).status_code == 400


def test_award_stepper(admin, db):
    aid = db['awards'].insert_one({'title': 'Excellence', 'count': 2}).inserted_id
    resp = admin.post(f'/admin/api/awards/{aid}', json={'count': 3})
    assert resp.status_code == 200
    assert db['awards'].find_one({'_id': aid})['count'] == 3
    log = db['activities'].find_one({'type': 'awards_update'})
    assert log['details']['count_change'] == 1


def test_award_stepper_rejects_negative(admin, db):
    aid = db['awards'].insert_one({'title': 'Excellence', 'count': 2}).inserted_id
    assert admin.post(f'/admin/api/awards/{aid}', json={'count': -1}).status_code == 400


def test_award_stepper_unknown_award(admin, db):
    assert admin.post(f"/admin/api/awards/{'a' * 24}", json={'count': 1}).status_code == 404


def test_event_inline_edit(admin, db):
    eid = db['competitions'].insert_one({'name': 'Old', 'location': 'Gym',
                                         'date': datetime.datetime(2026, 11, 1, 9, 0)}).inserted_id
    assert admin.post(f'/admin/api/events/{eid}', json={'field': 'name', 'value': 'Regionals'}).status_code == 200
    assert admin.post(f'/admin/api/events/{eid}',
                      json={'field': 'date', 'value': '2026-12-05T08:30'}).status_code == 200
    event = db['competitions'].find_one({'_id': eid})
    assert event['name'] == 'Regionals'
    assert event['date'] == datetime.datetime(2026, 12, 5, 8, 30)


@pytest.mark.parametrize('payload', [
    {'field': 'date', 'value': 'next tuesday'},
    {'field': 'name', 'value': ''},
    {'field': '_id', 'value': 'x'},
])
def test_event_inline_edit_validation(admin, db, payload):
    eid = db['competitions'].insert_one({'name': 'Old', 'location': 'Gym',
                                         'date': datetime.datetime(2026, 11, 1)}).inserted_id
    assert admin.post(f'/admin/api/events/{eid}', json=payload).status_code == 400


def test_quick_create_team_opens_editor(admin, db):
    resp = admin.post('/admin/quick-team', data={'team_number': '12345Z'})
    assert resp.status_code == 302
    doc = db['teams'].find_one({'team_number': '12345Z'})
    assert resp.headers['Location'].endswith(f"/manage/team/{doc['_id']}")
    assert doc['members'] == [] and doc['goals'] == []


def test_quick_create_team_rejects_duplicates(admin, db):
    db['teams'].insert_one({'team_number': '12345Z'})
    admin.post('/admin/quick-team', data={'team_number': '12345Z'})
    assert db['teams'].count_documents({'team_number': '12345Z'}) == 1


def test_admin_page_uses_autosave_controls(admin, db):
    db['awards'].insert_one({'title': 'Excellence', 'count': 2})
    page = admin.get('/admin').get_data(as_text=True)
    assert 'data-stat-field' in page
    assert 'data-award-id' in page
    assert 'Update All Awards' not in page
    assert 'Update Stats' not in page


def test_admin_team_cards_link_to_editor(admin, db):
    tid = db['teams'].insert_one({'team_number': '77628D', 'members': []}).inserted_id
    page = admin.get('/admin').get_data(as_text=True)
    assert f'/manage/team/{tid}' in page


def test_inline_endpoints_need_admin(client, db, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    assert client.post('/admin/api/stats', json={'field': 'hours_built', 'value': 1}).status_code == 403
