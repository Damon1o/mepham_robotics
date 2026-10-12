"""One event's page (/events/<id>) and members' RSVPs."""
import datetime
import json
import re

import pytest

import api.index as app_module


def soon(days, hour=9):
    return (app_module.club_now() + datetime.timedelta(days=days)).replace(hour=hour, minute=0, second=0,
                                                                            microsecond=0)


@pytest.fixture
def event(db):
    doc = {'name': 'Regional Qualifier', 'kind': 'competition', 'date': soon(10), 'location': 'Bellmore Gym',
           'details': 'Doors open at 7. Bring safety glasses.'}
    doc['_id'] = db['competitions'].insert_one(doc).inserted_id
    return doc


def sign_in(client, make_user, username='alice', **extra):
    user = make_user(username=username, password=f'{username}-password', email=f'{username}@example.com')
    if extra:
        app_module.get_db()['users'].update_one({'_id': user['_id']}, {'$set': extra})
    client.post('/login', data={'username': username, 'password': f'{username}-password'})
    return user


def rsvp(client, event, status):
    return client.post(f"/api/events/{event['_id']}/rsvp", json={'status': status})


def test_event_page_shows_the_event(client, event):
    html = client.get(f"/events/{event['_id']}").get_data(as_text=True)
    assert '<h1 id="ev-detail-name">Regional Qualifier</h1>' in html
    assert 'Bellmore Gym' in html and 'Bring safety glasses.' in html
    assert f"/events/{event['_id']}.ics" in html
    assert 'data-ev-seconds' in html  # countdown
    # Search engines get the event, pointing at this page.
    data = [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html)]
    ev = next(d for d in data if d.get('@type') == 'Event')
    assert ev['url'].endswith(f"/events/{event['_id']}")


def test_unknown_or_undated_events_are_404(client, db):
    assert client.get('/events/not-an-id').status_code == 404
    assert client.get('/events/' + '0' * 24).status_code == 404
    undated = db['competitions'].insert_one({'name': 'Someday'}).inserted_id
    assert client.get(f'/events/{undated}').status_code == 404


def test_ics_download_still_wins_over_the_page(client, event):
    resp = client.get(f"/events/{event['_id']}.ics")
    assert resp.status_code == 200 and resp.mimetype == 'text/calendar'


def test_events_page_links_to_each_event(client, event):
    html = client.get('/events').get_data(as_text=True)
    assert f'href="/events/{event["_id"]}"' in html


def test_sitemap_lists_upcoming_event_pages(client, event, db):
    db['competitions'].insert_one({'name': 'Long gone', 'date': soon(-60)})
    xml = client.get('/sitemap.xml').get_data(as_text=True)
    assert f"/events/{event['_id']}</loc>" in xml
    gone = db['competitions'].find_one({'name': 'Long gone'})
    assert str(gone['_id']) not in xml


def test_signed_out_visitors_see_counts_and_a_sign_in_link(client, event):
    html = client.get(f"/events/{event['_id']}").get_data(as_text=True)
    assert 'data-rsvp-count="going">0<' in html
    assert 'sign in</a> to say you' in html
    assert 'data-rsvp="going"' not in html


def test_rsvp_needs_an_account(client, event):
    assert rsvp(client, event, 'going').status_code == 401


def test_member_says_going_and_appears_in_the_list(client, make_user, event, db):
    sign_in(client, make_user, full_name='Alice Liddell')
    resp = rsvp(client, event, 'going')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['mine'] == 'going' and body['counts'] == {'going': 1, 'maybe': 0, 'no': 0}
    assert body['people'] == [{'name': 'Alice Liddell', 'initials': 'AL', 'status': 'going', 'photo': '',
                               'tone': ''}]

    html = client.get(f"/events/{event['_id']}").get_data(as_text=True)
    assert 'data-rsvp-count="going">1<' in html
    assert 'Alice Liddell' in html
    assert re.search(r'data-rsvp="going"\s+aria-pressed="true"', html)


def test_names_are_for_members_only(client, make_user, event):
    sign_in(client, make_user, full_name='Alice Liddell')
    rsvp(client, event, 'going')
    client.post('/logout')
    html = client.get(f"/events/{event['_id']}").get_data(as_text=True)
    assert 'data-rsvp-count="going">1<' in html
    assert 'Alice Liddell' not in html


def test_changing_and_clearing_an_answer(client, make_user, event, db):
    sign_in(client, make_user)
    rsvp(client, event, 'going')
    body = rsvp(client, event, 'maybe').get_json()
    assert body['counts'] == {'going': 0, 'maybe': 1, 'no': 0}
    assert body['people'][0]['status'] == 'maybe'
    body = rsvp(client, event, 'no').get_json()
    assert body['counts']['no'] == 1 and body['people'] == []  # can't-go answers are not listed
    body = rsvp(client, event, '').get_json()
    assert body['mine'] == '' and sum(body['counts'].values()) == 0
    assert db['competitions'].find_one({'_id': event['_id']}).get('rsvps') == {}


def test_going_people_come_before_maybes(client, make_user, event):
    sign_in(client, make_user, username='maya')
    rsvp(client, event, 'maybe')
    client.post('/logout')
    sign_in(client, make_user, username='gus')
    body = rsvp(client, event, 'going').get_json()
    assert [p['name'] for p in body['people']] == ['gus', 'maya']


def test_bad_answers_and_finished_events_are_refused(client, make_user, event, db):
    sign_in(client, make_user)
    assert rsvp(client, event, 'definitely').status_code == 400
    past = db['competitions'].insert_one({'name': 'Last year', 'date': soon(-30)}).inserted_id
    resp = client.post(f'/api/events/{past}/rsvp', json={'status': 'going'})
    assert resp.status_code == 400 and 'over' in resp.get_json()['error']
    assert client.post('/api/events/nope/rsvp', json={'status': 'going'}).status_code == 404


def test_past_event_page_closes_rsvps(client, make_user, db):
    past = db['competitions'].insert_one({'name': 'Last year', 'date': soon(-30)}).inserted_id
    sign_in(client, make_user)
    html = client.get(f'/events/{past}').get_data(as_text=True)
    assert 'This event has happened.' in html
    assert 'data-rsvp="going"' not in html
    assert 'Who came' in html


def test_other_upcoming_events_are_suggested(client, event, db):
    other = db['competitions'].insert_one({'name': 'Outreach Day', 'kind': 'outreach', 'date': soon(20)}).inserted_id
    html = client.get(f"/events/{event['_id']}").get_data(as_text=True)
    assert 'More coming up' in html and f'href="/events/{other}"' in html
