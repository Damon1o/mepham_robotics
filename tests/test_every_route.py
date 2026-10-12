"""Every GET route renders against messy, production-shaped data, signed out and as an admin.

Feature tests seed tidy documents; real ones are years old and patchy. The group
page 500s (#84) shipped because no test had a group without a saved layout and a
member with a photo. This seeds that kind of data once and walks the whole URL
map, so a new route or template is covered without anyone remembering to add it.
"""
import datetime

import pytest

from api import index as app_module

PHOTO = 'https://example.public.blob.vercel-storage.com/photo.jpg'
SKIP = {'static'}  # served files, not pages


@pytest.fixture
def messy_db(db, make_user, monkeypatch):
    for key in ('ROBOTEVENTS_API_KEY', 'ROBOTEVENTS_TOKEN', 'CHATBOT_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    admin = make_user(username='admin', password='admin-password', email='admin@example.com', role='admin')
    db['users'].update_one({'_id': admin['_id']}, {'$set': {'photo': PHOTO, 'display_name': 'Ada Admin'}})
    member = make_user(username='bo', password='bo-password', email='bo@example.com')
    db['users'].insert_one({'username': 'pending', 'email': 'p@example.com', 'role': 'pending',
                            'password': b'x'})
    now = app_module.club_now()

    db['teams'].insert_many([
        # Older robot team: no layout, no season, legacy placeholder photo, odd values.
        {'team_number': '77628A', 'nickname': 'Hydra', 'hero_image': 'static/assets/profile/base.png',
         'members': [{'name': 'Bo Diaz', 'photo': 'static/assets/profile/base.png', 'user_id': str(member['_id'])},
                     {'name': 'Grace', 'role': None, 'photo': PHOTO},
                     {'name': ''}],
         'goals': [{'name': 'Skills 200', 'progress': 'lots'}, {'name': 'States'}],
         'journey': [{'title': 'Founded'}], 'specs': None},
        # Newer robot team with everything filled in and a saved layout.
        {'team_number': '77628B', 'season': '2026-27', 'layout': 'magazine', 'hero_image': PHOTO,
         'stl_path': 'https://blob.example.com/robot.stl', 'notebook_link': 'https://example.com/nb',
         'specs': {'drive_train': 'Tank'}, 'members': [{'member_id': 'b1', 'name': 'Cy', 'photo': PHOTO}]},
        # Bare team: only the number.
        {'team_number': '77628Z'},
        # Group with no saved layout and a member with a photo (the #84 shape).
        {'kind': 'group', 'team_number': 'media', 'title': 'Media',
         'members': [{'member_id': 'g1', 'name': 'Grace Hopper', 'photo': PHOTO},
                     {'member_id': 'g2', 'name': 'Bo Diaz', 'user_id': str(member['_id'])}],
         'goals': [{'name': 'Reels', 'progress': 40, 'owners': ['g1', 'gone']}, {'name': 'Logo', 'note': None}]},
        # Empty group.
        {'kind': 'group', 'team_number': 'fundraising', 'title': 'Fundraising', 'members': []},
    ])
    db['awards'].insert_many([
        {'team_number': '77628A', 'title': 'Excellence Award', 'count': 2, 'icon': 'design_award.png'},
        {'team_number': '77628A', 'title': 'Think Award', 'count': 0},
        {'title': 'Club award with no team', 'icon': 'missing.png'},
    ])
    db['competitions'].insert_many([
        {'name': 'Regional Qualifier', 'date': now + datetime.timedelta(days=10), 'location': 'Gym',
         'kind': 'competition', 'link': 'https://robotevents.com/x'},
        {'name': 'Old scrimmage', 'date': now - datetime.timedelta(days=200)},
        {'name': 'Meeting', 'date': now + datetime.timedelta(days=1), 'kind': 'meeting', 'location': ''},
    ])
    db['contact_messages'].insert_many([
        {'name': 'Ada', 'email': 'ada@example.com', 'message': 'Hello', 'status': 'new',
         'created_at': datetime.datetime(2026, 9, 17, 12)},
        {'name': '', 'email': 'x@example.com', 'message': 'Alumni update', 'topic': 'alumni'},
    ])
    db['newsletter_subscribers'].insert_one({'email': 'fan@example.com', 'unsubscribe_token': 'tok123'})
    db['sponsors'].insert_many([{'name': 'Acme', 'logo_path': PHOTO}, {'name': 'No Logo Co'}])
    return db


def get_routes():
    for rule in app_module.app.url_map.iter_rules():
        if 'GET' in rule.methods and rule.endpoint not in SKIP:
            yield rule


def urls(db):
    teams = list(db['teams'].find())
    event = db['competitions'].find_one({'kind': 'competition'})
    by_arg = {
        'team_number': [t['team_number'] for t in teams],
        'team_id': [str(t['_id']) for t in teams],
        'event_id': [str(event['_id'])],
        'token': ['tok123', 'not-a-real-token'],
        # Every account (pending one included) plus one that does not exist.
        'user_id': [str(u['_id']) for u in db['users'].find()] + ['0123456789abcdef01234567', 'nope'],
    }
    for rule in get_routes():
        if not rule.arguments:
            yield rule.rule
            continue
        (arg,) = rule.arguments
        for value in by_arg[arg]:
            yield rule.rule.replace(f'<{arg}>', value)


def test_every_route_with_arguments_is_seeded():
    """A new route with an unknown URL argument needs a value in urls() above."""
    known = {'team_number', 'team_id', 'event_id', 'token', 'user_id'}
    for rule in get_routes():
        assert set(rule.arguments) <= known, rule.rule


@pytest.mark.parametrize('who', ['anonymous', 'member', 'admin'])
def test_no_route_errors_on_messy_data(client, messy_db, who):
    if who != 'anonymous':
        username = 'admin' if who == 'admin' else 'bo'
        client.post('/login', data={'username': username, 'password': f'{username}-password'})
    failures = []
    for url in urls(messy_db):
        resp = client.get(url)
        if resp.status_code >= 500:
            failures.append(f'{url} -> {resp.status_code}')
    assert not failures
