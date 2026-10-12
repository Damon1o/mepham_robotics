"""My account: "My history" (rosters by season, team awards, events said Going to)."""
import datetime

import pytest

import api.index as app_module


@pytest.fixture
def member(client, make_user):
    user = make_user(username='ada', password='ada-password', email='ada@example.com')
    client.post('/login', data={'username': 'ada', 'password': 'ada-password'})
    return user


def card(user, **extra):
    return dict({'member_id': 'c-' + str(user['_id'])[-4:], 'name': 'Ada', 'user_id': str(user['_id'])}, **extra)


def test_seasons_newest_first_with_roles_and_team_awards(client, db, member):
    db['teams'].insert_many([
        {'team_number': '77628A', 'season': '2025-26', 'nickname': 'Hydra',
         'members': [card(member, role='Builder', subteam='Mechanical')]},
        {'team_number': '77628B', 'season': '2026-27', 'members': [card(member, role='Captain', roles=['Driver'])]},
        {'kind': 'group', 'team_number': 'media', 'title': 'Media', 'season': '2026-27',
         'members': [card(member, role='Photographer')]},
        {'team_number': '77628C', 'season': '2026-27', 'members': [{'member_id': 'x', 'name': 'Someone else'}]},
    ])
    db['awards'].insert_many([{'team_number': '77628B', 'title': 'Excellence Award', 'count': 2},
                              {'team_number': '77628B', 'title': 'Think Award', 'count': 1},
                              {'title': 'Club-wide row', 'count': 9}])
    with app_module.app.test_request_context():
        history = app_module.account_history(db['users'].find_one({'_id': member['_id']}))
    assert [s['season'] for s in history['seasons']] == ['2026-27', '2025-26']
    newest = history['seasons'][0]['teams']
    assert [(t['label'], t['roles'], t['awards']) for t in newest] == [
        ('77628B', ['Captain', 'Driver'], 3), ('Media', ['Photographer'], 0)]
    older = history['seasons'][1]['teams'][0]
    assert older['subteam'] == 'Mechanical' and older['url'].endswith('/team/77628A?season=2025-26')
    assert history['team_count'] == 3


def test_events_answered_going_split_into_past_and_upcoming(client, db, member):
    now = app_module.club_now()
    uid = str(member['_id'])
    going = {uid: {'status': 'going'}}
    db['competitions'].insert_many([
        {'name': 'Last Spring', 'date': now - datetime.timedelta(days=200), 'rsvps': going},
        {'name': 'Last Fall', 'date': now - datetime.timedelta(days=30), 'rsvps': going},
        {'name': 'Maybe Day', 'date': now - datetime.timedelta(days=10), 'rsvps': {uid: {'status': 'maybe'}}},
        {'name': 'Next Month', 'date': now + datetime.timedelta(days=30), 'rsvps': going},
    ])
    with app_module.app.test_request_context():
        history = app_module.account_history(db['users'].find_one({'_id': member['_id']}))
    assert [e['name'] for e in history['went']] == ['Last Fall', 'Last Spring']
    assert [e['name'] for e in history['going']] == ['Next Month']
    assert history['went_total'] == 2


def test_account_page_shows_the_history_panel(client, db, member):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2026-27',
                            'members': [card(member, role='Builder', subteam='Mechanical')]})
    html = client.get('/account').get_data(as_text=True)
    assert 'href="#history"' in html and 'id="history"' in html
    assert '2026-27 season' in html and 'Builder · Mechanical' in html


def test_empty_history_explains_itself(client, member):
    html = client.get('/account').get_data(as_text=True)
    assert 'Nothing yet. Once you' in html
