"""Homepage fundraisers, edited at /manage/fundraisers by the fundraising group.

They live in the site content (section "fundraisers"), so they share the site
editor's saving, validation and image uploads. Admins can edit them from the
site editor too.
"""
import datetime

import pytest

from api import site_content

FUTURE = '2099-10-12T10:00'
PAST = '2001-01-01T10:00'


def entry(**overrides):
    row = {'name': 'Bake Sale', 'starts': FUTURE, 'ends': '', 'location': 'Main lobby',
           'description': 'Cookies for parts.', 'image': None, 'link_label': 'Sign up',
           'link_url': 'https://example.com/signup', 'goal': None, 'raised': None,
           'featured': False, 'hidden': False}
    row.update(overrides)
    return row


def login(client, make_user, username, role='member'):
    user = make_user(username=username, password='pw-' + username, email=f'{username}@example.com', role=role)
    client.post('/login', data={'username': username, 'password': 'pw-' + username})
    return user


@pytest.fixture
def groups(db):
    """A Fundraising group and a Media group, both empty."""
    for slug, title in (('fundraising', 'Fundraising'), ('media', 'Media')):
        db['teams'].insert_one({'kind': 'group', 'team_number': slug, 'title': title,
                                'season': '2026-27', 'members': []})


def join(db, slug, user):
    db['teams'].update_one({'team_number': slug}, {'$push': {'members': {
        'member_id': f'm-{user["username"]}', 'name': user['username'], 'user_id': str(user['_id'])}}})


def save(client, key, value):
    return client.post('/admin/api/site', json={'key': key, 'value': value})


# --- Who can edit -------------------------------------------------------------------

def test_fundraising_group_member_can_edit(client, db, make_user, groups):
    user = login(client, make_user, 'finn')
    join(db, 'fundraising', user)
    assert client.get('/manage/fundraisers').status_code == 200
    resp = save(client, 'fundraisers.entries', [entry()])
    assert resp.status_code == 200, resp.get_json()
    stored = db['site_metadata'].find_one({'_id': 'site_content'})['values']['fundraisers']['entries']
    assert stored[0]['name'] == 'Bake Sale'
    assert db['activities'].find_one({'type': 'fundraiser_edit'})['user'] == 'finn'


def test_other_members_cannot_edit(client, db, make_user, groups):
    user = login(client, make_user, 'mia')
    join(db, 'media', user)
    resp = client.get('/manage/fundraisers')
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/my-team')
    assert save(client, 'fundraisers.heading', 'Hi').status_code == 403
    assert client.post('/admin/api/site/image', data={}).status_code == 403


def test_group_members_only_reach_the_fundraisers_section(client, db, make_user, groups):
    user = login(client, make_user, 'finn')
    join(db, 'fundraising', user)
    assert save(client, 'home.hero_title', 'Pwned').status_code == 403
    assert client.post('/admin/api/site/reset', json={'key': 'home.hero_title'}).status_code == 403
    assert client.get('/admin/site').status_code == 302


def test_only_editors_pick_the_fundraising_group(client, db, make_user, groups):
    user = login(client, make_user, 'finn')
    join(db, 'fundraising', user)
    assert save(client, 'fundraisers.owner_group', 'media').status_code == 403


def test_signed_out_visitors_get_a_login_prompt(client, groups):
    assert client.post('/admin/api/site', json={'key': 'fundraisers.heading', 'value': 'x'}).status_code == 401
    assert client.get('/manage/fundraisers').status_code == 302


def test_editors_and_admins_can_edit(client, make_user, groups):
    login(client, make_user, 'eddie', role='editor')
    assert client.get('/manage/fundraisers').status_code == 200
    assert save(client, 'fundraisers.heading', 'Help Us Out').status_code == 200


def test_changing_the_group_moves_access(client, db, make_user, groups):
    finn = make_user(username='finn', password='pw-finn', email='finn@example.com')
    join(db, 'fundraising', finn)
    login(client, make_user, 'root', role='admin')
    assert save(client, 'fundraisers.owner_group', 'media').status_code == 200
    assert save(client, 'fundraisers.owner_group', 'nope').status_code == 400
    client.post('/logout')
    client.post('/login', data={'username': 'finn', 'password': 'pw-finn'})
    assert save(client, 'fundraisers.heading', 'x').status_code == 403


def test_renaming_the_group_keeps_its_access(client, db, make_user, groups):
    login(client, make_user, 'root', role='admin')
    group = db['teams'].find_one({'team_number': 'fundraising'})
    resp = client.post(f'/api/team/{group["_id"]}/field', json={'field': 'team_number', 'value': 'boosters'})
    assert resp.status_code == 200, resp.get_json()
    values = db['site_metadata'].find_one({'_id': 'site_content'})['values']
    assert values['fundraisers']['owner_group'] == 'boosters'


# --- Validation -----------------------------------------------------------------------

@pytest.mark.parametrize('bad', [
    {'name': ''},
    {'starts': ''},
    {'starts': 'next friday'},
    {'goal': -5},
    {'raised': 2.5},
    {'goal': 'lots'},
    {'link_url': 'javascript:alert(1)'},
])
def test_bad_fundraisers_are_rejected(client, make_user, groups, bad):
    login(client, make_user, 'eddie', role='editor')
    assert save(client, 'fundraisers.entries', [entry(**bad)]).status_code == 400


def test_goal_and_raised_are_optional(client, make_user, groups):
    login(client, make_user, 'eddie', role='editor')
    resp = save(client, 'fundraisers.entries', [entry(goal=500, raised=None)])
    assert resp.get_json()['value'][0]['raised'] is None


# --- Homepage -------------------------------------------------------------------------

def put(db, **values):
    db['site_metadata'].update_one({'_id': 'site_content'},
                                   {'$set': {f'values.fundraisers.{k}': v for k, v in values.items()}}, upsert=True)


def test_homepage_shows_the_next_fundraiser_with_progress(client, db):
    put(db, entries=[entry(name='Car Wash', starts='2099-11-01T09:00', goal=2000, raised=500),
                     entry(name='Bake Sale')])
    html = client.get('/').get_data(as_text=True)
    assert 'Next Fundraiser' in html
    assert html.index('Bake Sale') < html.index('Car Wash')
    assert '<progress max="100" value="25"' in html and '$2,000' in html


def test_past_and_draft_fundraisers_are_hidden(client, db):
    put(db, entries=[entry(name='Old Raffle', starts=PAST), entry(name='Secret Gala', hidden=True)])
    html = client.get('/').get_data(as_text=True)
    assert 'Old Raffle' not in html and 'Secret Gala' not in html
    assert 'fundraisers-section' not in html  # "scheduled" hides an empty section


def test_always_mode_shows_the_empty_message(client, db):
    put(db, mode='always')
    assert 'No fundraisers right now' in client.get('/').get_data(as_text=True)


def test_never_mode_hides_everything(client, db):
    put(db, mode='never', entries=[entry()])
    assert 'Bake Sale' not in client.get('/').get_data(as_text=True)


def test_pinned_fundraiser_comes_first():
    now = datetime.datetime(2099, 1, 1)
    cards = site_content.fundraiser_cards(
        [entry(name='Soon'), entry(name='Later', starts='2099-12-01T10:00', featured=True)], now, 4)
    assert [c['name'] for c in cards] == ['Later', 'Soon']


def test_multi_day_fundraiser_is_live_until_it_ends():
    now = datetime.datetime(2099, 10, 13, 12)
    [card] = site_content.fundraiser_cards([entry(ends='2099-10-14T18:00')], now, 4)
    assert card['live'] and card['days_away'] == -1
    assert site_content.fundraiser_cards([entry()], now, 4) == []


# --- Past fundraisers -----------------------------------------------------------------

def past(**overrides):
    row = {'name': 'Spring Raffle', 'date': '2025-04-12', 'raised': 800, 'goal': 1000,
           'description': 'New motors.', 'image': None}
    row.update(overrides)
    return row


def test_group_members_can_add_past_fundraisers(client, db, make_user, groups):
    user = login(client, make_user, 'finn')
    join(db, 'fundraising', user)
    resp = save(client, 'fundraisers.history', [past()])
    assert resp.status_code == 200, resp.get_json()
    page = client.get('/manage/fundraisers').get_data(as_text=True)
    assert 'Earlier fundraisers' in page and 'type="date"' in page


@pytest.mark.parametrize('bad', [{'name': ''}, {'date': ''}, {'date': '2025-02-30'}, {'date': 'last spring'},
                                 {'raised': -1}])
def test_bad_past_fundraisers_are_rejected(client, make_user, groups, bad):
    login(client, make_user, 'eddie', role='editor')
    assert save(client, 'fundraisers.history', [past(**bad)]).status_code == 400


def test_past_list_merges_ended_entries_newest_first():
    now = datetime.datetime(2026, 10, 7)
    entries = [entry(name='Car Wash', starts='2026-06-01T09:00', raised=450),
               entry(name='Gala', starts='2026-05-01T18:00', hidden=True),
               entry(name='Future Sale', starts=FUTURE),
               entry(name='Spring Raffle', starts='2025-04-12T10:00', raised=1)]
    rows, total = site_content.past_fundraisers(entries, [past()], now)
    assert [r['name'] for r in rows] == ['Car Wash', 'Spring Raffle']
    # The history copy wins over the same fundraiser in the main list.
    assert rows[1]['raised'] == 800 and rows[1]['percent'] == 80
    assert total == 1250
    assert rows[0]['percent'] is None


def test_donate_page_shows_the_track_record(client, db):
    put(db, history=[past(), past(name='Bottle Drive', date='2024-11-02', raised=200, goal=None, description='')],
        entries=[entry(name='Car Wash', starts=PAST, raised=50)])
    html = client.get('/donate').get_data(as_text=True)
    assert 'Our Fundraising Track Record' in html
    assert '$1,050</strong> raised across\n            3 fundraisers' in html
    assert html.index('Spring Raffle') < html.index('Bottle Drive') < html.index('Car Wash')
    assert '$800</strong> raised of $1,000' in html and 'value="80"' in html


def test_track_record_hides_when_off_or_empty(client, db):
    assert 'track-record' not in client.get('/donate').get_data(as_text=True)
    put(db, history=[past()], show_history=False)
    assert 'track-record' not in client.get('/donate').get_data(as_text=True)


def test_past_fundraisers_land_on_the_events_calendar(client, db):
    put(db, history=[past(date='2025-04-12')])
    html = client.get('/events?month=2025-04').get_data(as_text=True)
    panel = html.split('data-day-panel="2025-04-12"')[1].split('</div>')[0]
    assert 'Spring Raffle' in panel and 'All day' in panel


def test_past_fundraisers_are_all_day_in_calendar_files():
    from api import events
    [item] = events.history_items([past()])
    body = events.ics_calendar('x', [item], 'example.org', 'America/New_York',
                               datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc))
    assert 'DTSTART;VALUE=DATE:20250412' in body and 'DTEND;VALUE=DATE:20250413' in body
    assert 'dates=20250412%2F20250413' in events.google_url(item, 'America/New_York')


def test_limit_and_percent_cap():
    now = datetime.datetime(2099, 1, 1)
    cards = site_content.fundraiser_cards([entry(goal=100, raised=250)] * 5, now, 3)
    assert len(cards) == 3 and cards[0]['percent'] == 100
