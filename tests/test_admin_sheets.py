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


# --- Bake sale events make their own sheet -----------------------------------------------

def add_bake_sale(client, db, **form):
    data = {'comp_name': 'Halloween bake sale', 'comp_kind': 'bake_sale', 'comp_location': 'Cafeteria',
            'comp_date': SOON.strftime('%Y-%m-%dT%H:%M'), 'comp_details': 'Drop off by 8.'}
    data.update(form)
    client.post('/admin/add-competition', data=data)
    return db['competitions'].find_one({'kind': 'bake_sale'})


def test_scheduling_a_bake_sale_makes_a_baker_and_seller_sheet(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    event = add_bake_sale(client, db)
    sheet = db['signup_sheets'].find_one({'event_id': str(event['_id'])})
    assert [(r['key'], r['name']) for r in sheet['roles']] == [('baker', 'Baker'), ('seller', 'Seller')]
    assert (sheet['title'], sheet['date'], sheet['location']) == ('Halloween bake sale', SOON, 'Cafeteria')
    assert sheet['details'] == 'Drop off by 8.' and sheet['signups'] == {}
    hub = client.get('/resources').get_data(as_text=True)
    assert f'href="#sheet-{sheet["_id"]}"' in hub and f'id="sheet-{sheet["_id"]}"' in hub
    assert 'ev-k-bake_sale' in client.get('/events?month=2026-10').get_data(as_text=True)
    # Members sign up on it like any other sheet.
    reply = client.post(f"/api/hub/sheets/{sheet['_id']}/signup", json={'role': 'seller', 'on': True, 'note': '9-10'})
    assert reply.status_code == 200


def test_other_events_get_no_sheet(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    client.post('/admin/add-competition', data={'comp_name': 'Demo day', 'comp_kind': 'outreach',
                                                'comp_date': '2026-10-20T09:00'})
    assert db['signup_sheets'].count_documents({}) == 0


def test_bake_sale_sheet_follows_event_edits(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    event = add_bake_sale(client, db)
    for field, value in (('name', 'Spooky bake sale'), ('date', '2026-10-31T11:00'), ('location', 'Gym')):
        assert client.post(f"/admin/api/events/{event['_id']}", json={'field': field, 'value': value}).status_code == 200
    sheet = db['signup_sheets'].find_one({'event_id': str(event['_id'])})
    assert (sheet['title'], sheet['date'], sheet['location']) == (
        'Spooky bake sale', datetime.datetime(2026, 10, 31, 11, 0), 'Gym')
    assert db['signup_sheets'].count_documents({}) == 1


def test_switching_an_event_to_a_bake_sale_makes_its_sheet(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    client.post('/admin/add-competition', data={'comp_name': 'Fundraiser', 'comp_kind': 'club',
                                                'comp_date': '2026-10-20T09:00'})
    event = db['competitions'].find_one()
    client.post(f"/admin/api/events/{event['_id']}", json={'field': 'kind', 'value': 'bake_sale'})
    assert db['signup_sheets'].find_one({'event_id': str(event['_id'])})
    # Switching back drops the sheet while nobody is on it.
    client.post(f"/admin/api/events/{event['_id']}", json={'field': 'kind', 'value': 'club'})
    assert db['signup_sheets'].count_documents({}) == 0


def test_switching_away_keeps_a_sheet_people_signed_up_on(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    event = add_bake_sale(client, db)
    sheet = db['signup_sheets'].find_one()
    client.post(f"/api/hub/sheets/{sheet['_id']}/signup", json={'role': 'baker', 'on': True, 'note': 'Cookies'})
    client.post(f"/admin/api/events/{event['_id']}", json={'field': 'kind', 'value': 'club'})
    assert db['signup_sheets'].find_one()['signups']['baker'][0]['note'] == 'Cookies'


def test_deleting_a_bake_sale_deletes_its_sheet(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    event = add_bake_sale(client, db)
    add_sheet(client, sheet_title='Unrelated sheet')
    client.post(f"/admin/delete-competition/{event['_id']}")
    assert [s['title'] for s in db['signup_sheets'].find()] == ['Unrelated sheet']


def test_bake_sale_scheduled_earlier_gets_a_sheet_when_the_hub_opens(client, make_user, db, clock):
    """Bake sales already on the calendar, of any type, named like one."""
    login(client, make_user, 'mo', 'member')
    db['competitions'].insert_many([
        {'name': 'Fall Bake Sale', 'kind': 'club', 'date': SOON, 'location': 'Lobby'},
        {'name': 'Old bake sale', 'kind': 'bake_sale', 'date': datetime.datetime(2026, 9, 1, 9, 0)},
        {'name': 'Robot demo', 'kind': 'outreach', 'date': SOON}])
    page = client.get('/resources').get_data(as_text=True)
    sheet = db['signup_sheets'].find_one()
    assert db['signup_sheets'].count_documents({}) == 1
    assert sheet['title'] == 'Fall Bake Sale' and [r['name'] for r in sheet['roles']] == ['Baker', 'Seller']
    assert 'Fall Bake Sale' in page and f'href="#sheet-{sheet["_id"]}"' in page
    # Opening it again makes nothing new.
    client.get('/resources')
    assert db['signup_sheets'].count_documents({}) == 1


def test_bake_sale_fundraiser_gets_a_sheet(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    entry = {'name': 'Bake sale for Worlds', 'starts': '2026-10-24T10:00', 'location': 'Cafeteria'}
    assert client.post('/admin/api/site', json={'key': 'fundraisers.entries', 'value': [entry]}).status_code == 200
    assert 'Bake sale for Worlds' in client.get('/resources').get_data(as_text=True)
    sheet = db['signup_sheets'].find_one({'event_id': 'fundraiser:2026-10-24T10:00'})
    assert sheet['date'] == datetime.datetime(2026, 10, 24, 10, 0) and sheet['location'] == 'Cafeteria'


def test_deleted_bake_sale_sheet_stays_deleted(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    add_bake_sale(client, db)
    sheet = db['signup_sheets'].find_one()
    client.post(f"/admin/delete-sheet/{sheet['_id']}")
    client.get('/resources')
    client.get('/admin')
    assert db['signup_sheets'].count_documents({}) == 0


def test_own_edits_to_a_bake_sale_sheet_stick(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    event = add_bake_sale(client, db)
    sheet = db['signup_sheets'].find_one()
    client.post(f"/admin/api/sheets/{sheet['_id']}", json={'field': 'title', 'value': 'Treats table'})
    client.get('/resources')
    assert db['signup_sheets'].find_one()['title'] == 'Treats table'
    # Until the bake sale itself changes.
    client.post(f"/admin/api/events/{event['_id']}", json={'field': 'location', 'value': 'Gym'})
    saved = db['signup_sheets'].find_one()
    assert (saved['title'], saved['location']) == ('Treats table', 'Gym')


# --- Fundraisers in the Events tab ------------------------------------------------------

def test_fundraiser_lists_moved_to_the_events_tab(client, make_user, db, clock):
    login(client, make_user, 'root', 'admin')
    events_tab = client.get('/admin').get_data(as_text=True)
    assert 'data-key="fundraisers.entries"' in events_tab and 'data-key="fundraisers.history"' in events_tab
    site_page = client.get('/admin/site').get_data(as_text=True)
    assert 'data-key="fundraisers.entries"' not in site_page and 'data-key="fundraisers.history"' not in site_page
    assert 'Fundraisers are now in' in site_page
    # How the homepage shows them stays in Site settings.
    assert 'data-key="fundraisers.heading"' in site_page


def test_editor_edits_fundraisers_from_the_events_tab(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    page = client.get('/admin').get_data(as_text=True)
    assert 'data-key="fundraisers.entries"' in page and 'id="siteEditor"' in page
    entry = {'name': 'Car wash', 'starts': '2026-10-24T10:00'}
    reply = client.post('/admin/api/site', json={'key': 'fundraisers.entries', 'value': [entry]})
    assert reply.status_code == 200
    assert 'Car wash' in client.get('/admin').get_data(as_text=True)
    assert 'Car wash' in client.get('/events?month=2026-10').get_data(as_text=True)


def test_fundraising_group_page_still_has_the_lists(client, make_user, db, clock):
    login(client, make_user, 'ed', 'editor')
    page = client.get('/manage/fundraisers').get_data(as_text=True)
    assert 'data-key="fundraisers.entries"' in page
