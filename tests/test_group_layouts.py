"""Group page layouts: built around a group's goals and the people who own them."""
import os

import pytest
from bson import ObjectId

import api.index as app_module
from api import site_content

TWO = {'mission': 'Mission Board', 'other': 'Other'}


@pytest.fixture
def media(db, make_user):
    ada = make_user(username='ada', password='ada-password', email='ada@example.com')
    doc = {'kind': 'group', 'team_number': 'media', 'title': 'Media', 'season': '2026-27',
           'tagline': 'We tell the club story.',
           'members': [{'member_id': 'm1', 'name': 'Ada Byron', 'role': 'Builder', 'user_id': str(ada['_id'])},
                       {'member_id': 'm2', 'name': 'Grace Hopper', 'role': 'Media Captain'}],
           'goals': [{'name': 'Weekly reels', 'progress': 40, 'note': 'One short video a week.',
                      'owners': ['m1', 'gone']},
                     {'name': 'Photo every event', 'progress': 100, 'owners': ['m2', 'm1']},
                     {'name': 'New logo', 'progress': 0}]}
    doc['_id'] = db['teams'].insert_one(doc).inserted_id
    return doc


def login(client, username, password):
    client.post('/login', data={'username': username, 'password': password})
    return client


def board(team):
    with app_module.app.test_request_context():
        return app_module.goal_board(team)


def test_every_group_layout_has_a_template_and_stylesheet():
    for key in site_content.GROUP_LAYOUTS:
        assert os.path.exists(f'templates/group_layouts/{key}.html'), key
        assert os.path.exists(f'static/css/pages/group-layouts/{key}.css'), key
        assert key not in site_content.TEAM_LAYOUTS, key  # the picker thumbnails share one macro


# --- goal board -----------------------------------------------------------------

def test_board_links_goals_and_people(media):
    b = board(media)
    reels, photos, logo = b['goals']
    assert [o['name'] for o in reels['owners']] == ['Ada Byron']  # 'gone' is skipped
    assert (reels['status'], photos['status'], logo['status']) == ('active', 'done', 'todo')
    assert (b['done'], b['active'], b['todo'], b['overall']) == (1, 1, 1, 47)
    assert [g['name'] for g in b['open']] == ['New logo']
    # The captain leads, so comes first; each person carries the goals they own.
    assert [p['name'] for p in b['people']] == ['Grace Hopper', 'Ada Byron']
    assert [g['name'] for g in b['people'][1]['goals']] == ['Weekly reels', 'Photo every event']


def test_board_survives_bare_data():
    b = board({'kind': 'group', 'goals': [{'name': 'X', 'progress': 'lots'}], 'members': None})
    assert b['goals'][0]['progress'] == 0 and b['people'] == [] and b['overall'] == 0


# --- rendering ------------------------------------------------------------------

def test_mission_board_renders_goals_with_their_people(client, media):
    body = client.get('/team/media').data.decode()
    assert 'data-layout="mission"' in body
    assert 'group-layouts/mission.css' in body and 'css/pages/group.css' in body
    assert 'We tell the club story.' in body
    assert '1 of 3 done · 47% overall' in body
    assert 'One short video a week.' in body
    assert 'stroke-dasharray="40 100"' in body
    assert 'Goals Ada Byron is on' in body
    assert 'robot-showcase' not in body


def test_empty_group_still_renders(client, db):
    db['teams'].insert_one({'kind': 'group', 'team_number': 'fund', 'title': 'Fundraising'})
    body = client.get('/team/fund').data.decode()
    assert "This season's goals are on the way." in body
    assert 'Roster coming soon for this group.' in body


# --- editing --------------------------------------------------------------------

def test_goals_save_notes_and_roster_owners(client, db, media):
    login(client, 'ada', 'ada-password')
    resp = client.post(f"/api/team/{media['_id']}/list/goals", json={'items': [
        {'name': 'Reels', 'progress': 50, 'note': '  weekly  ', 'owners': ['m2', 'm2', 'stranger', 'm1']},
        {'name': 'Logo', 'progress': 0, 'note': '', 'owners': []},
    ]})
    assert resp.status_code == 200
    goals = db['teams'].find_one({'_id': media['_id']})['goals']
    assert goals == [{'name': 'Reels', 'progress': 50, 'note': 'weekly', 'owners': ['m2', 'm1']},
                     {'name': 'Logo', 'progress': 0}]


def test_goal_note_has_a_limit(client, media):
    login(client, 'ada', 'ada-password')
    resp = client.post(f"/api/team/{media['_id']}/list/goals",
                       json={'items': [{'name': 'Reels', 'note': 'x' * 201}]})
    assert resp.status_code == 400


def test_group_editor_offers_owner_chips(client, media):
    login(client, 'ada', 'ada-password')
    body = client.get(f"/manage/team/{media['_id']}").data.decode()
    assert 'data-owner="m1"' in body and 'aria-pressed="true"' in body
    assert 'data-key="note"' in body


def test_robot_team_editor_has_no_owner_chips(client, db, media):
    db['teams'].insert_one({'team_number': '77628A', 'members': [
        {'member_id': 'r1', 'name': 'Ada', 'user_id': media['members'][0]['user_id']}]})
    team = db['teams'].find_one({'team_number': '77628A'})
    login(client, 'ada', 'ada-password')
    body = client.get(f"/manage/team/{team['_id']}").data.decode()
    assert 'data-owner=' not in body and 'data-key="note"' not in body


def test_group_can_pick_a_group_layout(client, db, media, monkeypatch):
    monkeypatch.setattr(site_content, 'GROUP_LAYOUTS', TWO)
    login(client, 'ada', 'ada-password')
    url = f"/api/team/{media['_id']}/field"
    assert client.post(url, json={'field': 'layout', 'value': 'other'}).status_code == 200
    assert db['teams'].find_one({'_id': media['_id']})['layout'] == 'other'
    assert client.post(url, json={'field': 'layout', 'value': 'spotlight'}).status_code == 400


def test_group_layout_site_default_and_fallback(db, media, monkeypatch):
    monkeypatch.setattr(site_content, 'GROUP_LAYOUTS', TWO)
    db['site_metadata'].update_one({'_id': 'site_content'}, {'$set': {'values.teams.group_layout': 'other'}},
                                   upsert=True)
    with app_module.app.test_request_context():
        assert app_module.team_layout({'kind': 'group'}) == 'other'
        assert app_module.team_layout({'kind': 'group', 'layout': 'mission'}) == 'mission'
        assert app_module.team_layout({'kind': 'group', 'layout': 'gone'}) == 'other'


def render_as(client, db, team, layout):
    db['teams'].update_one({'_id': team['_id']}, {'$set': {'layout': layout}})
    return client.get(f"/team/{team['team_number']}").data.decode()


def test_yearbook_puts_leads_first_then_the_wall(client, db, media):
    body = render_as(client, db, media, 'yearbook')
    assert 'data-layout="yearbook"' in body and 'group-layouts/yearbook.css' in body
    assert body.index('Leads the group') < body.index('class="gy-wall"') < body.index('class="gy-checklist"')
    assert body.index('Grace Hopper') < body.index('Ada Byron')
    assert 'data-progress="40"' in body


def test_yearbook_without_people_falls_back_to_mission_board(client, db):
    team = {'kind': 'group', 'team_number': 'fund', 'title': 'Fundraising', 'layout': 'yearbook',
            'goals': [{'name': 'Bake sale', 'progress': 10}]}
    team['_id'] = db['teams'].insert_one(team).inserted_id
    body = client.get('/team/fund').data.decode()
    assert 'class="gm-goal-grid"' in body and 'gy-wall' not in body


def test_tracker_sorts_goals_into_columns(client, db, media):
    body = render_as(client, db, media, 'tracker')
    assert 'data-layout="tracker"' in body and 'group-layouts/tracker.css' in body
    todo = body[body.index('gt-col--todo'):body.index('gt-col--active')]
    active = body[body.index('gt-col--active'):body.index('gt-col--done')]
    done = body[body.index('gt-col--done'):body.index('id="team"')]
    assert 'New logo' in todo and 'Nobody on it yet' in todo
    assert 'Weekly reels' in active and 'data-progress="40"' in active
    assert 'Photo every event' in done
    assert 'data-progress="47"' in body  # the season band
    assert "Who's on what" in body


def test_tracker_without_goals_falls_back_to_mission_board(client, db, media):
    db['teams'].update_one({'_id': media['_id']}, {'$set': {'goals': []}})
    body = render_as(client, db, media, 'tracker')
    assert 'class="gm-people-grid"' in body and 'gt-board' not in body
