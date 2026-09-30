"""Selectable team page layouts: site default, per-season team override, editor picker."""
import os

import pytest
from bson import ObjectId

import api.index as app_module
from api import site_content

EXTRA = {'classic': 'Classic Stack', 'spotlight': 'Robot Spotlight'}


@pytest.fixture
def setup(db, make_user):
    alice = make_user(username='alice', password='alice-password', email='alice@example.com')
    make_user(username='mallory', password='mallory-password', email='m@example.com')
    old = db['teams'].insert_one({'team_number': '77628L', 'season': '2024-25', 'specs': {},
                                  'members': [{'member_id': 'm1', 'name': 'Alice', 'user_id': str(alice['_id'])}]})
    new = db['teams'].insert_one({'team_number': '77628L', 'season': '2025-26', 'specs': {},
                                  'members': [{'member_id': 'm2', 'name': 'Alice', 'user_id': str(alice['_id'])}]})
    group = db['teams'].insert_one({'kind': 'group', 'team_number': 'media', 'title': 'Media',
                                    'members': [{'member_id': 'm3', 'name': 'Alice', 'user_id': str(alice['_id'])}]})
    return {'old': str(old.inserted_id), 'new': str(new.inserted_id), 'group': str(group.inserted_id)}


def login(client, username, password):
    client.post('/login', data={'username': username, 'password': password})
    return client


def set_default(db, layout):
    db['site_metadata'].update_one({'_id': 'site_content'}, {'$set': {'values.teams.layout': layout}}, upsert=True)


def resolve(team):
    with app_module.app.test_request_context():
        return app_module.team_layout(team)


# --- resolution -------------------------------------------------------------

def test_every_layout_has_a_template_and_stylesheet():
    for key in site_content.TEAM_LAYOUTS:
        assert os.path.exists(f'templates/team_layouts/{key}.html'), key
        if key != 'classic':
            assert os.path.exists(f'static/css/pages/team-layouts/{key}.css'), key


def test_classic_is_the_default(db):
    assert resolve({'team_number': '1A'}) == 'classic'


def test_team_pick_beats_site_default(db, monkeypatch):
    monkeypatch.setattr(site_content, 'TEAM_LAYOUTS', EXTRA)
    set_default(db, 'spotlight')
    assert resolve({'team_number': '1A'}) == 'spotlight'
    assert resolve({'team_number': '1A', 'layout': 'classic'}) == 'classic'


def test_removed_layout_falls_back(db, monkeypatch):
    monkeypatch.setattr(site_content, 'TEAM_LAYOUTS', EXTRA)
    set_default(db, 'spotlight')
    assert resolve({'team_number': '1A', 'layout': 'gone'}) == 'spotlight'
    monkeypatch.setattr(site_content, 'TEAM_LAYOUTS', {'classic': 'Classic Stack'})
    assert resolve({'team_number': '1A', 'layout': 'gone'}) == 'classic'


def test_groups_always_use_classic(db, monkeypatch):
    monkeypatch.setattr(site_content, 'TEAM_LAYOUTS', EXTRA)
    set_default(db, 'spotlight')
    assert resolve({'kind': 'group', 'team_number': 'media', 'layout': 'spotlight'}) == 'classic'


# --- rendering --------------------------------------------------------------

def test_page_renders_inside_layout_wrapper(client, setup):
    body = client.get('/team/77628L').data.decode()
    assert 'data-layout="classic"' in body
    assert 'Competition Awards' in body
    assert 'team-layouts/' not in body  # classic needs no extra stylesheet


def test_group_page_renders_classic(client, setup):
    body = client.get('/team/media').data.decode()
    assert 'data-layout="classic"' in body


def test_classic_keeps_skills_out_of_the_hero(client, setup, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'x')
    body = client.get('/team/77628L').data.decode()
    hero = body[body.index('class="hero-image'):body.index('class="breadcrumb')]
    assert 'skills-panel' not in hero
    assert body.index('id="skills-panel"') < body.index('Competition Awards') < body.index('id="results-section"')


# --- 02 Scoreboard ----------------------------------------------------------

def scoreboard_page(client, db, setup, **fields):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'scoreboard', **fields}})
    return client.get('/team/77628L').data.decode()


def board_of(body):
    return body[body.index('class="sb-board"'):body.index('</header>')]


def test_scoreboard_board_needs_no_live_data(client, db, setup, monkeypatch):
    # Production runs without a RobotEvents token; the board must still be full.
    monkeypatch.delenv('ROBOTEVENTS_TOKEN', raising=False)
    db['awards'].insert_many([
        {'team_number': '77628L', 'title': 'Excellence Award', 'count': 2, 'sort': 1},
        {'team_number': '77628L', 'title': 'Think Award', 'count': 1, 'sort': 2}])
    body = scoreboard_page(client, db, setup, worlds_appearances=2, since=2019)
    assert 'css/pages/team-layouts/scoreboard.css' in body
    assert 'class="hero-image' not in body and 'skills-panel' not in body and 'sb-live' not in body
    board = board_of(body)
    for label, value in (('Awards', '3'), ('Worlds', '2&times;'), ('Members', '1'), ('Seasons', '2'),
                         ('Since', '2019')):
        assert f'>{label}</dt>' in board and f'>{value}</dd>' in board, label
    assert 'Top honor' in board and 'Excellence Award &times;2' in board
    order = [body.index(marker) for marker in ('class="sb-board"', 'Competition Awards', 'id="team"')]
    assert order == sorted(order)


def test_scoreboard_board_skips_what_a_team_lacks(client, db, setup):
    board = board_of(scoreboard_page(client, db, setup))
    assert '>Awards</dt>' in board and '>0</dd>' in board  # a scoreboard shows zero
    for missing in ('Worlds', 'Since', 'Top honor'):
        assert missing not in board, missing


def test_scoreboard_adds_live_rows_under_the_board(client, db, setup, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'x')
    body = scoreboard_page(client, db, setup)
    order = [body.index(marker) for marker in
             ('class="sb-board"', 'class="sb-live"', 'id="skills-panel"', 'id="scoreboard-band"',
              'Competition Awards', 'id="results-section"', 'id="team"')]
    assert order == sorted(order)


# --- 03 Robot Spotlight -----------------------------------------------------

def spotlight(db, setup, **fields):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'spotlight', **fields}})


def test_spotlight_leads_with_the_robot(client, db, setup):
    spotlight(db, setup, stl_path='https://blob.example/robot.stl', specs={'intake': 'Flex Wheel'},
              events=[{'name': 'States', 'photos': ['static/a.png', 'static/b.png']}])
    body = client.get('/team/77628L').data.decode()
    assert 'css/pages/team-layouts/spotlight.css' in body
    assert 'team-titlebar' in body and 'class="hero-image' not in body
    order = [body.index(marker) for marker in
             ('team-titlebar', 'id="robot-viewer"', 'Technical Specifications', 'robot-photos-strip',
              'Competition Awards', 'id="team"')]
    assert order == sorted(order)
    stage = body[body.index('class="spotlight-stage"'):body.index('robot-photos-strip')]
    assert 'id="robot-viewer"' in stage and 'Flex Wheel' in stage
    assert body.count('robot-photos-item') == 2 and 'viewer-gallery' not in body  # strip only, no second gallery


def test_spotlight_uses_photos_when_there_is_no_model(client, db, setup):
    spotlight(db, setup, events=[{'name': 'States', 'photos': ['static/a.png']}])
    body = client.get('/team/77628L').data.decode()
    assert 'team-titlebar' in body and 'viewer-gallery' in body
    assert 'robot-photos-strip' not in body


def test_spotlight_without_robot_media_falls_back_to_classic(client, db, setup):
    spotlight(db, setup)
    body = client.get('/team/77628L').data.decode()
    assert 'data-layout="spotlight"' in body
    assert 'class="hero-image' in body and 'team-titlebar' not in body and 'spotlight-stage' not in body
    assert body.count('Competition Awards') == 1


# --- saving -----------------------------------------------------------------

def test_member_picks_layout_for_one_season_only(client, db, setup, monkeypatch):
    monkeypatch.setattr(site_content, 'TEAM_LAYOUTS', EXTRA)
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['new']}/field", json={'field': 'layout', 'value': 'spotlight'})
    assert resp.status_code == 200
    assert db['teams'].find_one({'_id': ObjectId(setup['new'])})['layout'] == 'spotlight'
    assert 'layout' not in db['teams'].find_one({'_id': ObjectId(setup['old'])})


def test_blank_layout_returns_to_site_default(client, db, setup):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'classic'}})
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['new']}/field", json={'field': 'layout', 'value': ''})
    assert resp.status_code == 200
    assert 'layout' not in db['teams'].find_one({'_id': ObjectId(setup['new'])})


def test_unknown_layout_is_rejected(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['new']}/field", json={'field': 'layout', 'value': 'nope'})
    assert resp.status_code == 400
    assert 'layout' not in db['teams'].find_one({'_id': ObjectId(setup['new'])})


def test_groups_cannot_pick_a_layout(client, db, setup):
    login(client, 'alice', 'alice-password')
    resp = client.post(f"/api/team/{setup['group']}/field", json={'field': 'layout', 'value': 'classic'})
    assert resp.status_code == 400


def test_non_member_cannot_pick_a_layout(client, db, setup):
    login(client, 'mallory', 'mallory-password')
    resp = client.post(f"/api/team/{setup['new']}/field", json={'field': 'layout', 'value': 'classic'})
    assert resp.status_code == 403


# --- pickers ----------------------------------------------------------------

def test_editor_shows_layout_picker(client, setup):
    login(client, 'alice', 'alice-password')
    body = client.get(f"/manage/team/{setup['new']}").data.decode()
    assert 'data-autosave="layout"' in body
    assert 'Classic Stack' in body


def test_group_editor_has_no_layout_picker(client, setup):
    login(client, 'alice', 'alice-password')
    body = client.get(f"/manage/team/{setup['group']}").data.decode()
    assert 'data-autosave="layout"' not in body


def test_site_default_accepts_only_listed_layouts():
    content = site_content.SECTIONS
    field = next(s for s in content if s.key == 'teams').by_key['layout']
    assert field.default == 'classic'
    assert set(field.choices) == set(site_content.TEAM_LAYOUTS)
