"""Events page (/events): calendar sources, month grid, feeds and admin event types."""
import datetime
import json
import re

import pytest

import api.index as app_module
from api import events


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def soon(days, hour=9):
    return (app_module.club_now() + datetime.timedelta(days=days)).replace(hour=hour, minute=0, second=0,
                                                                            microsecond=0)


MEETING = {'days': [2, 5], 'start': '15:00', 'end': '17:00', 'room': 'Room LL01'}  # Tuesday & Friday


# --- Pure helpers -------------------------------------------------------------------------

def test_meeting_items_fall_on_meeting_days():
    items = events.meeting_items(MEETING, datetime.date(2026, 10, 5), datetime.date(2026, 10, 11))
    assert [i['start'] for i in items] == [datetime.datetime(2026, 10, 6, 15), datetime.datetime(2026, 10, 9, 15)]
    assert items[0]['end'] == datetime.datetime(2026, 10, 6, 17)
    assert items[0]['kind'] == 'meeting' and items[0]['location'] == 'Room LL01'
    assert events.meeting_items(dict(MEETING, days=[]), datetime.date(2026, 10, 5), datetime.date(2026, 10, 11)) == []


def test_event_rows_without_kind_are_competitions():
    item = events.event_item({'_id': 'x', 'name': 'Qualifier', 'date': datetime.datetime(2026, 11, 7, 8)})
    assert item['kind'] == 'competition' and item['label'] == 'Competition'
    assert item['end'] == datetime.datetime(2026, 11, 7, 16)
    assert events.event_item({'name': 'No date'}) is None
    assert events.event_item({'name': 'Odd', 'kind': 'nonsense', 'date': datetime.datetime(2026, 1, 1)})['kind'] \
        == 'competition'


def test_fundraisers_skip_drafts_and_default_to_one_day():
    rows = [{'name': 'Bake sale', 'starts': '2026-10-10T09:00', 'ends': ''},
            {'name': 'Secret', 'starts': '2026-10-11T09:00', 'hidden': True},
            {'name': 'Car wash', 'starts': '2026-10-17T09:00', 'ends': '2026-10-18T15:00'}]
    items = events.fundraiser_items(rows)
    assert [i['name'] for i in items] == ['Bake sale', 'Car wash']
    assert items[0]['end'] == datetime.datetime(2026, 10, 10, 23, 59)


def test_month_grid_is_whole_weeks_and_spans_multi_day_items():
    car_wash = events.fundraiser_items([{'name': 'Car wash', 'starts': '2026-10-17T09:00',
                                         'ends': '2026-10-18T15:00'}])
    weeks = events.month_weeks(2026, 10, car_wash, datetime.date(2026, 10, 7))
    days = [d for w in weeks for d in w]
    assert len(days) % 7 == 0 and days[0]['date'].weekday() == 6  # starts on a Sunday
    marked = [d['date'].day for d in days if d['items']]
    assert marked == [17, 18]
    today = next(d for d in days if d['today'])
    assert today['date'] == datetime.date(2026, 10, 7)
    assert not next(d for d in days if d['date'] == datetime.date(2026, 9, 27))['in_month']


def test_month_param_is_forgiving():
    today = datetime.date(2026, 10, 7)
    assert events.parse_month('2027-02', today) == (2027, 2)
    for bad in (None, '', 'soon', '2026-13', '1999-01', '2026-1-1'):
        assert events.parse_month(bad, today) == (2026, 10)
    assert events.shift_month(2026, 12, 1) == (2027, 1)
    assert events.shift_month(2026, 1, -1) == (2025, 12)


def test_google_link_uses_club_time():
    item = events.event_item({'_id': 'a', 'name': 'Qualifier', 'date': datetime.datetime(2026, 11, 7, 8),
                              'location': 'Bellmore, NY'})
    url = events.google_url(item, 'America/New_York')
    assert 'dates=20261107T080000%2F20261107T160000' in url
    assert 'ctz=America%2FNew_York' in url and 'location=Bellmore%2C+NY' in url


def test_ics_escapes_folds_and_repeats_meetings():
    item = events.event_item({'_id': 'abc', 'name': 'Robots, Pizza; Fun', 'location': 'Gym',
                              'details': 'Line one\nline two ' + 'x' * 120,
                              'date': datetime.datetime(2026, 11, 7, 8)})
    body = events.ics_calendar('Club events', [item], 'example.org', 'America/New_York',
                               datetime.datetime(2026, 10, 7, 12, tzinfo=datetime.timezone.utc),
                               meeting=MEETING, meeting_from=datetime.date(2026, 10, 7))
    assert body.startswith('BEGIN:VCALENDAR\r\n') and body.endswith('END:VCALENDAR\r\n')
    assert 'SUMMARY:Robots\\, Pizza\\; Fun' in body
    assert 'DESCRIPTION:Line one\\nline two' in body
    assert 'UID:abc@example.org' in body
    assert 'DTSTART;TZID=America/New_York:20261107T080000' in body
    assert all(len(line.encode()) <= 75 for line in body.split('\r\n'))
    assert 'RRULE:FREQ=WEEKLY;BYDAY=TU,FR' in body
    # The repeating meeting starts on the first meeting day on or after meeting_from.
    assert 'DTSTART;TZID=America/New_York:20261009T150000' in body


def test_kinds_present_follow_chip_order():
    items = [{'kind': 'meeting'}, {'kind': 'outreach'}, {'kind': 'competition'}, {'kind': 'outreach'}]
    assert [k[0] for k in events.kinds_present(items)] == ['competition', 'outreach', 'meeting']
    assert events.kinds_present(items)[1][3] == 'Outreach'


# --- Page ---------------------------------------------------------------------------------

def test_events_page_shows_next_up_list_and_calendar(client, db):
    db['competitions'].insert_one({'name': 'Bellmore Qualifier', 'date': soon(10), 'location': 'Mepham Gym',
                                   'kind': 'competition', 'details': 'Doors at 7.', 'link': 'https://robotevents.com/x'})
    db['competitions'].insert_one({'name': 'Library Robot Day', 'date': soon(3), 'location': 'Bellmore Library',
                                   'kind': 'outreach'})
    page = client.get('/events').get_data(as_text=True)
    assert 'Next up' in page
    # The spotlight is the next event of any kind.
    spot = page.split('id="ev-spot-name"')[1].split('</h2>')[0]
    assert 'Library Robot Day' in spot
    assert 'Bellmore Qualifier' in page and 'Doors at 7.' in page
    assert 'data-filter="outreach"' in page and 'data-filter="competition"' in page
    assert 'id="calendar"' in page and 'data-day=' in page
    assert 'calendar.google.com/calendar/render' in page
    assert 'webcal://' in page
    assert re.search(r'href="/events/[0-9a-f]{24}\.ics"', page)


def test_events_page_lists_meetings_on_the_grid_only(client, db):
    page = client.get('/events').get_data(as_text=True)
    assert 'Every week' in page and 'Club meeting' in page
    assert 'data-kind="meeting"' in page
    list_part = page.split('id="ev-list-title"')[1]
    assert 'ev-item ev-k-meeting' not in list_part


def test_meetings_and_fundraisers_can_be_switched_off(admin, db):
    for key in ('events.show_meetings', 'events.show_fundraisers'):
        assert admin.post('/admin/api/site', json={'key': key, 'value': False}).status_code == 200
    page = admin.get('/events').get_data(as_text=True)
    assert 'Every week' not in page and 'data-kind="meeting"' not in page


def test_events_page_survives_odd_months(client, db):
    for month in ('2026-02', 'bogus', '1900-01'):
        assert client.get(f'/events?month={month}').status_code == 200
    page = client.get('/events?month=2030-07').get_data(as_text=True)
    assert 'July <span>2030</span>' in page
    assert 'month=2030-06' in page and 'month=2030-08' in page
    assert '>Today</a>' in page


def test_events_page_has_event_structured_data(client, db):
    db['competitions'].insert_one({'name': 'Bellmore Qualifier', 'date': soon(10), 'location': 'Mepham Gym'})
    db['competitions'].insert_one({'name': 'Somewhere', 'date': soon(12)})  # no location: no rich result
    page = client.get('/events').get_data(as_text=True)
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
    found = [b for b in blocks if b.get('@type') == 'Event']
    assert [b['name'] for b in found] == ['Bellmore Qualifier']
    assert found[0]['location']['name'] == 'Mepham Gym'
    assert found[0]['startDate'].startswith(soon(10).strftime('%Y-%m-%dT09:00'))


def test_past_competitions_show_as_recent(client, db):
    db['competitions'].insert_one({'name': 'Last Spring Open', 'date': soon(-20), 'kind': 'competition'})
    db['competitions'].insert_one({'name': 'Old Library Day', 'date': soon(-10), 'kind': 'outreach'})
    page = client.get('/events').get_data(as_text=True)
    recent = page.split('Recently')[1]
    assert 'Last Spring Open' in recent and 'Old Library Day' not in recent


def test_events_page_is_in_nav_sitemap_search_and_llms(client, db):
    db['competitions'].insert_one({'name': 'Bellmore Qualifier', 'date': soon(10), 'location': 'Mepham Gym'})
    home = client.get('/').get_data(as_text=True)
    assert 'href="/events"' in home
    assert '/events</loc>' in client.get('/sitemap.xml').get_data(as_text=True)
    assert 'Disallow: /events' not in client.get('/robots.txt').get_data(as_text=True)
    llms = client.get('/llms.txt').get_data(as_text=True)
    assert 'Bellmore Qualifier' in llms and '/events.ics' in llms
    with app_module.app.test_request_context('/'):
        assert 'Bellmore Qualifier' in app_module.chat_system_prompt()


# --- Feeds --------------------------------------------------------------------------------

def test_feed_is_a_calendar_with_events_and_weekly_meetings(client, db):
    db['competitions'].insert_one({'name': 'Bellmore Qualifier', 'date': soon(10), 'location': 'Mepham Gym'})
    response = client.get('/events.ics')
    assert response.status_code == 200
    assert response.mimetype == 'text/calendar'
    body = response.get_data(as_text=True)
    assert 'SUMMARY:Bellmore Qualifier' in body
    assert 'RRULE:FREQ=WEEKLY;BYDAY=TU,FR' in body
    assert 'Content-Security-Policy' in response.headers


def test_single_event_download(client, db):
    eid = db['competitions'].insert_one({'name': 'Bellmore Qualifier', 'date': soon(10)}).inserted_id
    body = client.get(f'/events/{eid}.ics').get_data(as_text=True)
    assert body.count('BEGIN:VEVENT') == 1 and 'RRULE' not in body
    assert client.get('/events/not-an-id.ics').status_code == 404
    assert client.get('/events/0123456789abcdef01234567.ics').status_code == 404


# --- Admin and the rest of the site -----------------------------------------------------

def test_admin_adds_events_with_a_type_and_details(admin, db):
    admin.post('/admin/add-competition', data={'comp_name': 'Library Robot Day', 'comp_kind': 'outreach',
                                               'comp_details': 'Kids drive robots.',
                                               'comp_date': soon(4).strftime('%Y-%m-%dT%H:%M')})
    row = db['competitions'].find_one({'name': 'Library Robot Day'})
    assert row['kind'] == 'outreach' and row['details'] == 'Kids drive robots.'
    admin.post('/admin/add-competition', data={'comp_name': 'Bad', 'comp_kind': 'party',
                                               'comp_date': soon(4).strftime('%Y-%m-%dT%H:%M')})
    assert db['competitions'].find_one({'name': 'Bad'}) is None


def test_admin_edits_type_and_details_inline(admin, db):
    eid = db['competitions'].insert_one({'name': 'Q', 'date': soon(5)}).inserted_id
    assert admin.post(f'/admin/api/events/{eid}', json={'field': 'kind', 'value': 'scrimmage'}).status_code == 200
    assert admin.post(f'/admin/api/events/{eid}', json={'field': 'details', 'value': 'Bring spares'}).status_code == 200
    assert admin.post(f'/admin/api/events/{eid}', json={'field': 'kind', 'value': 'party'}).status_code == 400
    row = db['competitions'].find_one({'_id': eid})
    assert row['kind'] == 'scrimmage' and row['details'] == 'Bring spares'
    page = admin.get('/admin').get_data(as_text=True)
    assert 'data-event-field="kind"' in page and 'data-event-field="details"' in page


def test_countdown_and_hub_count_competitions_only(client, db, make_user):
    db['competitions'].insert_one({'name': 'Library Robot Day', 'date': soon(2), 'kind': 'outreach'})
    db['competitions'].insert_one({'name': 'Bellmore Qualifier', 'date': soon(9)})
    home = client.get('/').get_data(as_text=True)
    assert '<p class="countdown-event">Bellmore Qualifier</p>' in home
    assert 'Library Robot Day' in home  # still in the homepage's upcoming list
    make_user(username='alice', password='alice-password', role='member')
    client.post('/login', data={'username': 'alice', 'password': 'alice-password'})
    hub = client.get('/resources').get_data(as_text=True)
    tile = hub.split('Next competition')[1].split('</article>')[0]
    assert 'Bellmore Qualifier' in tile and 'Library Robot Day' not in tile


def test_competition_log_leaves_out_outreach(client, db):
    db['competitions'].insert_one({'name': 'Last Spring Open', 'date': soon(-20)})
    db['competitions'].insert_one({'name': 'Old Library Day', 'date': soon(-10), 'kind': 'outreach'})
    page = client.get('/achievements').get_data(as_text=True)
    assert 'Last Spring Open' in page and 'Old Library Day' not in page
