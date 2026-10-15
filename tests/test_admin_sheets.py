"""Bake sale and volunteer sheets in the admin Events tab, and editors' access to that tab."""
import datetime

import pytest

import api.index as app_module

SOON = datetime.datetime(2026, 10, 24, 9, 0)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(app_module, 'club_now', lambda: datetime.datetime(2026, 10, 15, 12, 0))


def login(client, make_user, username, role):
    user = make_user(username=username, password=f'{username}-password', email=f'{username}@example.com', role=role)
    client.post('/login', data={'username': username, 'password': f'{username}-password'})
    return user


def add_sheet(client, **form):
    data = {'sheet_title': 'Fall bake sale', 'sheet_kind': 'bake_sale', 'sheet_location': 'Front lobby',
            'sheet_date': SOON.strftime('%Y-%m-%dT%H:%M'), 'sheet_details': ''}
    data.update(form)
    return client.post('/admin/add-sheet', data=data)


def test_editor_gets_only_the_events_tab(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    db['users'].insert_one({'username': 'secret-person', 'email': 'hidden@example.com', 'password': b'x',
                            'role': 'member'})
    page = client.get('/admin').get_data(as_text=True)
    assert 'id="tab-events"' in page and 'Bake sales &amp; volunteering' in page
    assert 'id="tab-users"' not in page and 'id="panel-users"' not in page
    assert 'hidden@example.com' not in page
    assert 'Manage Events' in page


def test_members_still_cannot_open_admin(client, make_user, db):
    login(client, make_user, 'mo', 'member')
    assert client.get('/admin').status_code == 302
    assert add_sheet(client).status_code == 302
    assert db['signup_sheets'].count_documents({}) == 0


def test_editor_can_manage_events(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    client.post('/admin/add-competition', data={'comp_name': 'Scrimmage', 'comp_kind': 'scrimmage',
                                                'comp_date': '2026-10-20T09:00'})
    event = db['competitions'].find_one({'name': 'Scrimmage'})
    assert event
    assert client.post(f"/admin/api/events/{event['_id']}", json={'field': 'location', 'value': 'Gym'}).status_code == 200
    assert db['competitions'].find_one({'_id': event['_id']})['location'] == 'Gym'


def test_sheet_added_in_admin_shows_in_the_hub(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    add_sheet(client)
    sheet = db['signup_sheets'].find_one({'title': 'Fall bake sale'})
    assert [r['name'] for r in sheet['roles']] == ['Baker', 'Seller', 'Setup', 'Cleanup']
    assert 'Fall bake sale' in client.get('/resources').get_data(as_text=True)


def test_volunteer_sheet_starts_with_a_volunteer_role(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    add_sheet(client, sheet_title='Robot demo helpers', sheet_kind='volunteer')
    sheet = db['signup_sheets'].find_one({'title': 'Robot demo helpers'})
    assert [r['name'] for r in sheet['roles']] == ['Volunteer']


def test_hub_sign_ups_show_in_admin_and_survive_an_edit(client, make_user, db, clock):
    ed = login(client, make_user, 'ed', 'editor')
    add_sheet(client)
    sheet = db['signup_sheets'].find_one()
    db['users'].update_one({'_id': ed['_id']}, {'$set': {'full_name': 'Ed Itor'}})
    client.post(f"/api/hub/sheets/{sheet['_id']}/signup", json={'role': 'baker', 'on': True, 'note': 'Brownies'})

    page = client.get('/admin').get_data(as_text=True)
    assert 'Ed Itor' in page and 'Brownies' in page and '<strong>1</strong>/16 spots' in page

    reply = client.post(f"/admin/api/sheets/{sheet['_id']}", json={'field': 'title', 'value': 'Winter bake sale'})
    assert reply.status_code == 200
    saved = db['signup_sheets'].find_one({'_id': sheet['_id']})
    assert saved['title'] == 'Winter bake sale' and saved['signups']['baker'][0]['note'] == 'Brownies'
    assert 'Winter bake sale' in client.get('/resources').get_data(as_text=True)


def test_sheet_field_edits_are_checked(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    add_sheet(client)
    sheet_id = db['signup_sheets'].find_one()['_id']
    assert client.post(f'/admin/api/sheets/{sheet_id}', json={'field': 'title', 'value': ''}).status_code == 400
    assert client.post(f'/admin/api/sheets/{sheet_id}', json={'field': 'date', 'value': 'soon'}).status_code == 400
    assert client.post(f'/admin/api/sheets/{sheet_id}', json={'field': 'roles', 'value': []}).status_code == 400
    assert client.post(f'/admin/api/sheets/{sheet_id}', json={'field': 'date', 'value': '2026-11-01T10:30'}).status_code == 200
    assert db['signup_sheets'].find_one()['date'] == datetime.datetime(2026, 11, 1, 10, 30)


def test_editor_deletes_a_sheet(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    add_sheet(client)
    sheet_id = db['signup_sheets'].find_one()['_id']
    client.post(f'/admin/delete-sheet/{sheet_id}')
    assert db['signup_sheets'].count_documents({}) == 0
