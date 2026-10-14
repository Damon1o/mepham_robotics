"""Member Hub meeting sign-in/sign-out and sign-up sheets (api/sheets.py)."""
import datetime

import pytest

import api.index as app_module
from api import sheets

# Default meeting: Tuesday and Friday, 15:00-17:00.
MEETING = {'days': [2, 5], 'start': '15:00', 'end': '17:00'}
TUESDAY = datetime.datetime(2026, 10, 13, 15, 30)


@pytest.fixture
def clock(monkeypatch):
    """Set the club's clock: clock(datetime)."""
    def set_to(moment):
        monkeypatch.setattr(app_module, 'club_now', lambda: moment)
    set_to(TUESDAY)
    return set_to


def login(client, make_user, username, role='member'):
    user = make_user(username=username, password=f'{username}-password', email=f'{username}@example.com', role=role)
    client.post('/login', data={'username': username, 'password': f'{username}-password'})
    return user


# --- Pure helpers ----------------------------------------------------------------------

def test_window_opens_an_hour_early_and_closes_two_hours_late():
    assert sheets.sign_in_window(MEETING, TUESDAY.replace(hour=14, minute=0))['start'].hour == 15
    assert sheets.sign_in_window(MEETING, TUESDAY.replace(hour=13, minute=59)) is None
    assert sheets.sign_in_window(MEETING, TUESDAY.replace(hour=19, minute=0)) is not None
    assert sheets.sign_in_window(MEETING, TUESDAY.replace(hour=19, minute=1)) is None
    wednesday = TUESDAY + datetime.timedelta(days=1)
    assert sheets.sign_in_window(MEETING, wednesday) is None


def test_a_forgotten_sign_out_counts_only_to_the_meeting_end():
    row = {'in_at': TUESDAY.replace(minute=0), 'out_at': None}
    end = TUESDAY.replace(hour=17, minute=0)
    assert sheets.minutes_present(row, end, TUESDAY.replace(hour=16, minute=0)) == 60
    assert sheets.minutes_present(row, end, TUESDAY + datetime.timedelta(days=2)) == 120
    assert sheets.fmt_minutes(125) == '2h 05m' and sheets.fmt_minutes(45) == '45m' and sheets.fmt_minutes(60) == '1h'


def test_recent_meeting_days_are_meeting_days_newest_first():
    days = sheets.recent_meeting_days(MEETING, TUESDAY.date(), count=3)
    assert days == [datetime.date(2026, 10, 13), datetime.date(2026, 10, 9), datetime.date(2026, 10, 6)]
    assert sheets.recent_meeting_days(dict(MEETING, days=[]), TUESDAY.date()) == []


def test_clean_sheet_validates_and_keeps_role_keys():
    body = {'title': '  Fall   bake sale ', 'date': '2026-10-17T09:00',
            'roles': [{'name': 'Baker', 'slots': 3, 'prompt': 'What?'}, {'name': 'Baker', 'slots': 1}, {'name': ''}]}
    fields, error = sheets.clean_sheet(body)
    assert error is None and fields['title'] == 'Fall bake sale'
    assert [r['key'] for r in fields['roles']] == ['baker', 'baker-2']
    # A renamed role keeps its key, so the people on it stay.
    body['roles'] = [{'key': 'baker', 'name': 'Bakers', 'slots': 3}]
    fields, _ = sheets.clean_sheet(body, fields['roles'])
    assert fields['roles'][0]['key'] == 'baker'
    assert sheets.clean_sheet(dict(body, title=''))[1]
    assert sheets.clean_sheet(dict(body, date='soon'))[1]
    assert sheets.clean_sheet(dict(body, roles=[]))[1]
    assert sheets.clean_sheet(dict(body, roles=[{'name': 'X', 'slots': 0}]))[1]


def test_csv_neutralises_formulas():
    rows = [{'user_id': 'a', 'day': '2026-10-13', 'in_at': TUESDAY, 'out_at': TUESDAY.replace(hour=16, minute=30)}]
    text = sheets.attendance_csv(rows, {'a': '=HYPERLINK("x")'}, MEETING, TUESDAY)
    assert "'=HYPERLINK" in text and ',60,' in text


# --- Meeting sign-in -------------------------------------------------------------------

def test_member_signs_in_and_out(client, make_user, db, clock):
    login(client, make_user, 'alice')
    html = client.get('/resources').get_data(as_text=True)
    assert 'data-attend="in"' in html and 'Sign-in sheet' not in html  # members don't see the sheet

    reply = client.post('/api/hub/attendance', json={'action': 'in'})
    assert reply.status_code == 200 and 'data-attend="out"' in reply.get_json()['html']
    # A double tap doesn't make a second row.
    client.post('/api/hub/attendance', json={'action': 'in'})
    assert db['attendance'].count_documents({}) == 1

    clock(TUESDAY.replace(hour=17, minute=0))
    reply = client.post('/api/hub/attendance', json={'action': 'out'})
    assert 'Signed out at' in reply.get_json()['html']
    row = db['attendance'].find_one()
    assert row['day'] == '2026-10-13' and row['out_at'].hour == 17

    reply = client.post('/api/hub/attendance', json={'action': 'undo'})
    assert db['attendance'].find_one()['out_at'] is None
    assert '1h 30m' in client.get('/resources').get_data(as_text=True)


def test_sign_in_is_closed_away_from_meetings(client, make_user, db, clock):
    login(client, make_user, 'alice')
    clock(TUESDAY + datetime.timedelta(days=1))
    assert client.post('/api/hub/attendance', json={'action': 'in'}).status_code == 400
    assert 'Sign-in is closed' in client.get('/resources').get_data(as_text=True)
    assert db['attendance'].count_documents({}) == 0


def test_editor_keeps_the_sheet(client, make_user, db, clock):
    bob = make_user(username='bob', password='bob-password', email='bob@example.com')
    login(client, make_user, 'ed', role='editor')
    html = client.get('/resources').get_data(as_text=True)
    assert 'Sign-in sheet' in html and f'value="{bob["_id"]}"' in html

    day = '2026-10-13'
    reply = client.post('/api/hub/attendance/sheet', json={'day': day, 'user_id': str(bob['_id']), 'action': 'in'})
    assert reply.status_code == 200 and 'bob' in reply.get_json()['html']
    assert db['attendance'].find_one({'user_id': str(bob['_id'])})['by'] == 'ed'

    # A past day gets the meeting's own times.
    client.post('/api/hub/attendance/sheet', json={'day': '2026-10-09', 'user_id': str(bob['_id']), 'action': 'in'})
    client.post('/api/hub/attendance/sheet', json={'day': '2026-10-09', 'user_id': str(bob['_id']), 'action': 'out'})
    past = db['attendance'].find_one({'day': '2026-10-09'})
    assert (past['in_at'].hour, past['out_at'].hour) == (15, 17)
    assert 'bob' in client.get('/api/hub/attendance/sheet?day=2026-10-09').get_json()['html']

    csv = client.get('/hub/attendance.csv')
    assert csv.mimetype == 'text/csv' and '2026-10-09,bob,15:00,17:00,120,ed' in csv.get_data(as_text=True)

    client.post('/api/hub/attendance/sheet', json={'day': day, 'user_id': str(bob['_id']), 'action': 'remove'})
    assert db['attendance'].count_documents({'day': day}) == 0
    assert client.post('/api/hub/attendance/sheet', json={'day': '2027-01-01', 'user_id': str(bob['_id']),
                                                          'action': 'in'}).status_code == 400


def test_members_cannot_keep_the_sheet(client, make_user, clock):
    bob = make_user(username='bob', password='bob-password', email='bob@example.com')
    login(client, make_user, 'alice')
    body = {'day': '2026-10-13', 'user_id': str(bob['_id']), 'action': 'in'}
    assert client.post('/api/hub/attendance/sheet', json=body).status_code == 403
    assert client.get('/hub/attendance.csv').status_code == 302


# --- Sign-up sheets ------------------------------------------------------------------------

def make_sheet(client, **extra):
    body = {'title': 'Fall bake sale', 'date': '2026-10-17T09:00', 'location': 'Lobby',
            'roles': [{'name': 'Baker', 'slots': 2, 'prompt': 'What are you bringing?'}, {'name': 'Seller', 'slots': 1}]}
    reply = client.post('/api/hub/sheets', json=dict(body, **extra))
    assert reply.status_code == 200, reply.get_data(as_text=True)
    return reply


def test_bake_sale_signups(client, make_user, db, clock):
    login(client, make_user, 'ed', role='editor')
    assert 'Fall bake sale' in make_sheet(client).get_json()['html']
    sheet_id = str(db['signup_sheets'].find_one()['_id'])

    client.post('/logout')
    login(client, make_user, 'alice')
    html = client.get('/resources').get_data(as_text=True)
    assert 'Fall bake sale' in html and 'data-sheet-new' not in html  # members can't make sheets

    url = f'/api/hub/sheets/{sheet_id}/signup'
    reply = client.post(url, json={'role': 'baker', 'on': True, 'note': 'Brownies'})
    assert 'Brownies' in reply.get_json()['html'] and "you're on it" in reply.get_json()['html']
    # Signing up again only changes the note.
    client.post(url, json={'role': 'baker', 'on': True, 'note': 'Lemon bars'})
    bakers = db['signup_sheets'].find_one()['signups']['baker']
    assert len(bakers) == 1 and bakers[0]['note'] == 'Lemon bars'

    client.post(url, json={'role': 'seller', 'on': True})
    client.post('/logout')
    login(client, make_user, 'bob')
    full = client.post(url, json={'role': 'seller', 'on': True})
    assert full.status_code == 409 and 'full' in full.get_json()['error']
    # Members can't take someone else off.
    alice = db['users'].find_one({'username': 'alice'})
    assert client.post(url, json={'role': 'seller', 'on': False, 'user_id': str(alice['_id'])}).status_code == 403

    client.post(url, json={'role': 'baker', 'on': True})
    client.post(url, json={'role': 'baker', 'on': False})
    assert [s['user_id'] for s in db['signup_sheets'].find_one()['signups']['baker']] == [str(alice['_id'])]


def test_editor_edits_and_deletes_sheets(client, make_user, db, clock):
    alice = make_user(username='alice', password='alice-password', email='alice@example.com')
    login(client, make_user, 'ed', role='editor')
    make_sheet(client)
    sheet = db['signup_sheets'].find_one()
    db['signup_sheets'].update_one({'_id': sheet['_id']}, {'$set': {'signups': {
        'baker': [{'user_id': str(alice['_id']), 'note': 'Cookies'}],
        'seller': [{'user_id': str(alice['_id']), 'note': ''}]}}})

    # Renaming Baker keeps Alice on it; dropping Seller takes her off that role.
    reply = client.post(f"/api/hub/sheets/{sheet['_id']}", json={
        'title': 'Bake sale', 'date': '2026-10-17T10:00', 'roles': [{'key': 'baker', 'name': 'Bakers', 'slots': 4}]})
    assert reply.status_code == 200
    saved = db['signup_sheets'].find_one()
    assert saved['title'] == 'Bake sale' and list(saved['signups']) == ['baker']

    # Editors can take people off.
    client.post(f"/api/hub/sheets/{sheet['_id']}/signup", json={'role': 'baker', 'on': False,
                                                                 'user_id': str(alice['_id'])})
    assert db['signup_sheets'].find_one()['signups']['baker'] == []

    assert client.post('/api/hub/sheets', json={'title': '', 'date': '2026-10-17T09:00'}).status_code == 400
    assert client.delete(f"/api/hub/sheets/{sheet['_id']}").status_code == 200
    assert db['signup_sheets'].count_documents({}) == 0


def test_past_sheets_are_closed_to_members_but_not_editors(client, make_user, db, clock):
    alice = make_user(username='alice', password='alice-password', email='alice@example.com')
    login(client, make_user, 'ed', role='editor')
    make_sheet(client, date='2026-10-01T09:00')
    sheet_id = db['signup_sheets'].find_one()['_id']
    assert 'Recent sheets (1)' in client.get('/resources').get_data(as_text=True)
    # Editors record who really came, after the day.
    reply = client.post(f'/api/hub/sheets/{sheet_id}/signup',
                        json={'role': 'baker', 'on': True, 'user_id': str(alice['_id']), 'note': 'Pie'})
    assert reply.status_code == 200 and 'Pie' in reply.get_json()['html']
    client.post('/logout')
    client.post('/login', data={'username': 'alice', 'password': 'alice-password'})
    assert client.post(f'/api/hub/sheets/{sheet_id}/signup', json={'role': 'seller', 'on': True}).status_code == 400


def test_members_cannot_make_sheets(client, make_user, clock):
    login(client, make_user, 'alice')
    assert client.post('/api/hub/sheets', json={'title': 'X'}).status_code == 403


def test_settings_can_hide_both(client, make_user, clock):
    login(client, make_user, 'root', role='admin')
    for key in ('resources.show_attendance', 'resources.show_sheets', 'resources.show_events'):
        assert client.post('/admin/api/site', json={'key': key, 'value': False}).status_code == 200
    html = client.get('/resources').get_data(as_text=True)
    assert 'data-attendance' not in html and 'data-sheets' not in html and 'data-hub-events' not in html


# --- Editors fill in past attendance -----------------------------------------------------

def test_editor_backfills_any_day_with_times(client, make_user, db, clock):
    bob = make_user(username='bob', password='bob-password', email='bob@example.com')
    cara = make_user(username='cara', password='cara-password', email='cara@example.com')
    login(client, make_user, 'ed', role='editor')
    # A Saturday in September: not a meeting day, still allowed.
    day = '2026-09-12'
    sheet = client.get(f'/api/hub/attendance/sheet?day={day}').get_json()['html']
    assert 'not a usual meeting day' in sheet

    reply = client.post('/api/hub/attendance/sheet', json={
        'day': day, 'action': 'in', 'user_ids': [str(bob['_id']), str(cara['_id'])],
        'in_time': '10:00', 'out_time': '13:30'})
    assert reply.status_code == 200
    rows = list(db['attendance'].find({'day': day}))
    assert len(rows) == 2 and all((r['in_at'].hour, r['out_at'].hour, r['out_at'].minute) == (10, 13, 30) for r in rows)

    # Fix one person's times.
    client.post('/api/hub/attendance/sheet', json={'day': day, 'action': 'set', 'user_id': str(bob['_id']),
                                                   'in_time': '11:00', 'out_time': ''})
    row = db['attendance'].find_one({'day': day, 'user_id': str(bob['_id'])})
    assert row['in_at'].hour == 11 and row['out_at'] is None

    bad = {'day': day, 'action': 'set', 'user_id': str(bob['_id'])}
    assert client.post('/api/hub/attendance/sheet', json=dict(bad, in_time='14:00', out_time='13:00')).status_code == 400
    assert client.post('/api/hub/attendance/sheet', json=dict(bad, in_time='noon')).status_code == 400
    assert client.post('/api/hub/attendance/sheet', json=dict(bad, action='in', user_ids=[])).status_code == 400

    # It counts toward the member's totals.
    client.post('/logout')
    client.post('/login', data={'username': 'cara', 'password': 'cara-password'})
    assert '3h 30m' in client.get('/resources').get_data(as_text=True)


def test_past_meeting_day_defaults_to_the_meeting_times(client, make_user, db, clock):
    bob = make_user(username='bob', password='bob-password', email='bob@example.com')
    login(client, make_user, 'ed', role='editor')
    html = client.get('/api/hub/attendance/sheet?day=2026-10-09').get_json()['html']
    assert 'value="15:00"' in html and 'value="17:00"' in html
    client.post('/api/hub/attendance/sheet', json={'day': '2026-10-09', 'action': 'in', 'user_id': str(bob['_id'])})
    row = db['attendance'].find_one()
    assert (row['in_at'].hour, row['out_at'].hour) == (15, 17)


# --- Event sign-ups -------------------------------------------------------------------------

@pytest.fixture
def events_db(db):
    upcoming = db['competitions'].insert_one({'name': 'Regional Qualifier', 'kind': 'competition',
                                              'date': datetime.datetime(2026, 10, 24, 8, 0)}).inserted_id
    past = db['competitions'].insert_one({'name': 'Fall Scrimmage', 'kind': 'scrimmage',
                                          'date': datetime.datetime(2026, 10, 3, 9, 0)}).inserted_id
    return upcoming, past


def test_member_signs_up_for_an_event_in_one_tap(client, make_user, db, clock, events_db):
    upcoming, past = events_db
    alice = login(client, make_user, 'alice')
    html = client.get('/resources').get_data(as_text=True)
    assert 'Regional Qualifier' in html and 'data-event-toggle' in html and 'Fall Scrimmage' not in html

    reply = client.post(f'/api/hub/events/{upcoming}', json={'on': True})
    assert "You're going" in reply.get_json()['html']
    assert db['competitions'].find_one({'_id': upcoming})['rsvps'][str(alice['_id'])]['status'] == 'going'

    client.post(f'/api/hub/events/{upcoming}', json={'on': False})
    assert str(alice['_id']) not in db['competitions'].find_one({'_id': upcoming}).get('rsvps', {})
    assert client.post(f'/api/hub/events/{past}', json={'on': True}).status_code == 400
    other = make_user(username='zed', password='zed-password', email='zed@example.com')
    assert client.post(f'/api/hub/events/{upcoming}', json={'on': True, 'user_id': str(other['_id'])}).status_code == 403


def test_events_page_list_has_one_tap_signup(client, make_user, db, events_db):
    upcoming, _ = events_db
    db['competitions'].update_one({'_id': upcoming}, {'$set': {'date': app_module.club_now() + datetime.timedelta(days=5)}})
    assert 'data-ev-signup' not in client.get('/events').get_data(as_text=True)  # signed out: no button
    alice = login(client, make_user, 'alice')
    assert 'data-ev-signup' in client.get('/events').get_data(as_text=True)
    # The button posts the event page's own "Going" answer.
    assert client.post(f'/api/events/{upcoming}/rsvp', json={'status': 'going'}).status_code == 200
    assert 'class="ev-signup is-on"' in client.get('/events').get_data(as_text=True)
    assert db['competitions'].find_one({'_id': upcoming})['rsvps'][str(alice['_id'])]['status'] == 'going'


def test_editor_records_who_came_to_past_events(client, make_user, db, clock, events_db):
    upcoming, past = events_db
    bob = make_user(username='bob', password='bob-password', email='bob@example.com')
    login(client, make_user, 'ed', role='editor')
    html = client.get('/resources').get_data(as_text=True)
    assert 'Past events: record who came (1)' in html and 'Fall Scrimmage' in html

    reply = client.post(f'/api/hub/events/{past}', json={'on': True, 'user_id': str(bob['_id'])})
    assert reply.status_code == 200
    assert db['competitions'].find_one({'_id': past})['rsvps'][str(bob['_id'])]['status'] == 'going'
    client.post(f'/api/hub/events/{past}', json={'on': False, 'user_id': str(bob['_id'])})
    assert str(bob['_id']) not in db['competitions'].find_one({'_id': past}).get('rsvps', {})
