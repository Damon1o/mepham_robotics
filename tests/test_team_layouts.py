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
