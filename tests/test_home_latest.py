"""Homepage: "Latest from the club" cards, the live match ticker, and event links."""
import datetime

import pytest

import api.index as app_module


def ago(days, hours=0):
    return app_module.club_now() - datetime.timedelta(days=days, hours=hours)


@pytest.fixture
def club(db):
    db['competitions'].insert_many([
        {'name': 'Fall Qualifier', 'kind': 'competition', 'date': ago(10), 'location': 'Bellmore'},
        {'name': 'Spring Signature', 'kind': 'competition', 'date': ago(200)},
        {'name': 'Library Day', 'kind': 'outreach', 'date': ago(2)},  # not a competition
    ])
    db['awards'].insert_many([{'title': 'Excellence Award', 'count': 3, 'sort': 0},
                              {'title': 'Design Award', 'count': 1, 'sort': 1}])
    db['site_metadata'].update_one({'_id': 'site_content'}, {'$set': {'values': {
        'alumni': {'people': [
            {'name': 'Ada Lovelace', 'class_year': 2026, 'school': 'MIT', 'path': 'computing'},
            {'name': 'Bo Diaz', 'class_year': 2026, 'school': 'Stony Brook University', 'path': 'engineering'},
            {'name': 'Cy Young', 'class_year': 2025, 'school': 'Hofstra', 'path': 'business'}]},
        'fundraisers': {'history': [{'name': 'Bake Sale', 'date': '2026-05-02', 'raised': 840, 'goal': 1000}]},
    }}}, upsert=True)


def test_cards_come_from_the_rest_of_the_site(client, club):
    with app_module.app.test_request_context():
        cards = app_module.home_latest()
    assert [c['kicker'] for c in cards] == ['Last competition', 'Awards won', 'Newest alumni', 'Last fundraiser']
    assert cards[0]['title'] == 'Fall Qualifier' and cards[0]['url'].startswith('/events/')
    assert cards[1]['title'] == '4 awards' and cards[1]['text'] == 'Most won: Excellence Award ×3'
    assert cards[2]['title'] == 'Class of 2026' and cards[2]['text'] == '2 graduates · MIT, Stony Brook University'
    assert cards[3]['title'] == '$840 raised' and 'Bake Sale' in cards[3]['text']


def test_a_competition_still_going_is_not_the_last_one(client, club, db):
    db['competitions'].insert_one({'name': 'Happening Now', 'kind': 'competition', 'date': ago(0, hours=1)})
    with app_module.app.test_request_context():
        assert app_module.home_latest()[0]['title'] == 'Fall Qualifier'


def test_one_card_alone_is_not_shown(client, db):
    db['awards'].insert_one({'title': 'Excellence Award', 'count': 1})
    with app_module.app.test_request_context():
        assert app_module.home_latest() == []
    assert 'latest-section' not in client.get('/').get_data(as_text=True)


def test_homepage_shows_the_strip_and_it_can_be_switched_off(client, db, club, make_user):
    assert 'Latest from the Club' in client.get('/').get_data(as_text=True)
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    client.post('/admin/api/site', json={'key': 'home.show_latest', 'value': False})
    assert 'latest-section' not in client.get('/').get_data(as_text=True)


def test_upcoming_events_link_to_their_own_pages(client, db):
    event = db['competitions'].insert_one({'name': 'Next Qualifier', 'date': ago(-5),
                                           'link': 'https://robotevents.com/x'}).inserted_id
    assert f'href="/events/{event}"' in client.get('/').get_data(as_text=True)


# --- Live ticker ----------------------------------------------------------------------------

def test_ticker_needs_a_competition_happening_now_and_a_key(client, db, monkeypatch):
    db['competitions'].insert_one({'name': 'Today Qualifier', 'kind': 'competition', 'date': ago(0, hours=2)})
    assert 'data-live-ticker' not in client.get('/').get_data(as_text=True)  # no RobotEvents key
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    html = client.get('/').get_data(as_text=True)
    assert 'data-live-ticker' in html and 'Today Qualifier' in html and 'js/home-live.js' in html


def test_no_ticker_between_competitions(client, db, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    db['competitions'].insert_many([
        {'name': 'Yesterday', 'kind': 'competition', 'date': ago(1)},
        {'name': 'Outreach now', 'kind': 'outreach', 'date': ago(0, hours=1)},
        {'name': 'Tomorrow', 'kind': 'competition', 'date': ago(-1)},
    ])
    html = client.get('/').get_data(as_text=True)
    assert 'data-live-ticker' not in html and 'home-live.js' not in html
