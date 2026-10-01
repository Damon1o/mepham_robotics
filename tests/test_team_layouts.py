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


# --- 04 Meet the Team -------------------------------------------------------

def meet_page(client, db, setup, **fields):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'meet', **fields}})
    return client.get('/team/77628L').data.decode()


def test_meet_leads_with_the_people(client, db, setup, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'x')
    body = meet_page(client, db, setup, journey=[{'date': 'Sep 2025', 'title': 'Kickoff'}])
    assert 'css/pages/team-layouts/meet.css' in body
    assert 'class="crew-header"' in body and 'class="hero-image' not in body
    order = [body.index(marker) for marker in
             ('class="crew-header"', 'id="team"', 'teamcta-band', 'Kickoff', 'Competition Awards',
              'id="skills-panel"', 'id="results-section"')]
    assert order == sorted(order)
    assert body.count('Competition Awards') == 1


def test_meet_header_shows_faces_and_counts_the_rest(client, db, setup):
    members = [{'member_id': f'm{i}', 'name': f'Pat Lee{i}'} for i in range(11)]
    header = meet_page(client, db, setup, members=members)
    header = header[header.index('class="crew-header"'):header.index('</header>')]
    assert header.count('crew-face crew-face--initials') == 8
    assert '+3' in header and 'Meet the 11' in header and 'href="#team"' in header


def test_meet_without_members_falls_back_to_classic(client, db, setup):
    body = meet_page(client, db, setup, members=[])
    assert 'data-layout="meet"' in body
    assert 'class="hero-image' in body and 'crew-header' not in body


# --- 05 Dossier -------------------------------------------------------------

def dossier_page(client, db, setup, **fields):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'dossier', **fields}})
    return client.get('/team/77628L').data.decode()


def rail_of(body):
    return body[body.index('class="dossier-rail"'):body.index('class="dossier-main"')]


def test_dossier_rail_holds_the_quick_facts(client, db, setup):
    db['awards'].insert_one({'team_number': '77628L', 'title': 'Design Award', 'count': 2, 'sort': 1})
    body = dossier_page(client, db, setup, division='High School', since=2020, worlds_appearances=1,
                        specs={'drive_train': 'X-Drive'}, notebook_link='https://example.com/nb')
    assert 'css/pages/team-layouts/dossier.css' in body
    assert 'class="dossier-head"' in body and 'class="hero-image' not in body
    rail = rail_of(body)
    for fact in ('High School', '2025-26', '>2</dd>', '1&times;', '2020', 'Design Award &times;2', 'X-Drive',
                 'season-switcher', 'https://example.com/nb', 'https://events.vex.com/teams/V5RC/77628L'):
        assert fact in rail, fact
    # Specs, seasons and the notebook live in the rail only, not a second time below.
    assert 'Technical Specifications' not in body and body.count('season-switcher"') == 1
    assert body.count('Engineering Notebook') == 1


def test_dossier_main_column_order(client, db, setup, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'x')
    body = dossier_page(client, db, setup, journey=[{'date': 'Sep 2025', 'title': 'Kickoff'}])
    assert 'id="skills-panel"' in rail_of(body)
    main = body[body.index('class="dossier-main"'):]
    order = [main.index(marker) for marker in
             ('Competition Awards', 'id="scoreboard-band"', 'id="results-section"', 'id="team"',
              'robot-showcase', 'Kickoff', 'teamcta-band')]
    assert order == sorted(order)
    assert body.count('Competition Awards') == 1


def test_dossier_rail_skips_what_a_team_lacks(client, db, setup):
    rail = rail_of(dossier_page(client, db, setup))
    for missing in ('Division', 'Worlds', 'Since', 'Top honor', 'title">Robot', 'Engineering Notebook'):
        assert missing not in rail, missing
    assert '>Members</dt>' in rail and 'RobotEvents profile' in rail


# --- 06 Tabbed Hub ----------------------------------------------------------

def tabs_page(client, db, setup, **fields):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'tabs', **fields}})
    return client.get('/team/77628L').data.decode()


def tab_keys(body):
    import re
    return re.findall(r'data-hub-tab="([a-z]+)"', body)


def test_tabs_split_the_page_into_panels(client, db, setup, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'x')
    body = tabs_page(client, db, setup, specs={'drive_train': 'X-Drive'}, goals=[{'name': 'Win', 'progress': 100}],
                     journey=[{'date': 'Sep 2025', 'title': 'Kickoff'}])
    assert 'css/pages/team-layouts/tabs.css' in body and 'class="hero-image' in body
    assert tab_keys(body) == ['overview', 'results', 'robot', 'team', 'journey']
    # Only Overview is open; the rest start hidden.
    assert 'id="hub-overview" class="hub-panel" role="tabpanel" aria-labelledby="hub-tab-overview" data-hub-panel="overview">' in body
    for key in ('results', 'robot', 'team', 'journey'):
        assert f'data-hub-panel="{key}" hidden>' in body, key

    def panel(key):
        start = body.index(f'id="hub-{key}"')
        end = body.find('role="tabpanel"', body.index('role="tabpanel"', start) + 1)
        return body[start:end if end > 0 else len(body)]
    overview = panel('overview')
    assert 'Competition Awards' in overview and 'id="skills-panel"' in overview and 'class="hub-tiles"' in overview
    assert 'id="results-section"' in panel('results')
    assert 'X-Drive' in panel('robot') and 'id="team"' in panel('team') and 'Kickoff' in panel('journey')
    assert body.count('Competition Awards') == 1


def test_tabs_skip_topics_a_team_lacks(client, db, setup):
    body = tabs_page(client, db, setup)
    assert tab_keys(body) == ['overview', 'team']
    tiles = body[body.index('class="hub-tiles"'):body.index('</nav>', body.index('class="hub-tiles"'))]
    assert 'data-hub-open="team"' in tiles and 'data-hub-open="robot"' not in tiles


def test_tabs_overview_tiles_summarise_stored_data(client, db, setup):
    body = tabs_page(client, db, setup, nickname='Hydra', specs={'drive_train': 'X-Drive'},
                     goals=[{'name': 'A', 'progress': 100}, {'name': 'B', 'progress': 40}],
                     journey=[{'date': '2025', 'title': 'Kickoff'}])
    tiles = body[body.index('class="hub-tiles"'):body.index('</nav>', body.index('class="hub-tiles"'))]
    for text in ('>1</span>', 'member', 'Hydra', 'X-Drive', '1/2', 'goals met', '1 milestones'):
        assert text in tiles, text


# --- 07 Season Timeline -----------------------------------------------------

def timeline_page(client, db, setup, **fields):
    db['teams'].update_one({'_id': ObjectId(setup['new'])}, {'$set': {'layout': 'timeline', **fields}})
    return client.get('/team/77628L').data.decode()


def test_loose_dates_parse():
    parse = app_module.parse_loose_date
    assert parse('Sep 2025').month == 9 and parse('Sept 2025').month == 9
    assert parse('January 12, 2026').day == 12 and parse('Jan. 12, 2026').day == 12
    assert parse('2026-03-01').month == 3 and parse('03/01/2026').day == 1 and parse('2024').year == 2024
    assert parse('Early season') is None and parse('') is None


def test_timeline_merges_milestones_and_events_by_date(client, db, setup):
    import datetime
    db['competitions'].insert_many([
        # Same name a season earlier: must not be picked for 2025-26.
        {'name': 'LI Qualifier', 'date': datetime.datetime(2025, 1, 10), 'location': 'Old Gym'},
        {'name': 'LI Qualifier', 'date': datetime.datetime(2026, 1, 17, 9), 'location': 'Mepham HS'}])
    body = timeline_page(client, db, setup, journey=[
        {'date': 'Build week', 'title': 'Build starts'},  # no date: stays first
        {'date': 'Sep 2025', 'title': 'Kickoff'},
        {'date': 'Feb 2026', 'title': 'Rebuild'}],
        events=[{'name': 'Scrimmage', 'photos': ['static/a.png']},  # no competition: closes the list
                {'name': 'LI Qualifier', 'photos': ['static/b.png'] * 6}])
    assert 'css/pages/team-layouts/timeline.css' in body and 'data-timeline' in body
    spine = body[body.index('data-timeline'):body.index('</ol>', body.index('data-timeline'))]
    order = [spine.index(f'data-name="{name}"') for name in
             ('Build starts', 'Kickoff', 'LI Qualifier', 'Rebuild', 'Scrimmage')]
    assert order == sorted(order)
    assert 'data-when="2026-01-17"' in spine and 'Jan 17, 2026' in spine and 'Mepham HS' in spine
    assert 'Old Gym' not in spine
    assert spine.count('class="tl-photo"') == 5 and '+2' in spine  # four shown, the rest counted
    order = [body.index(marker) for marker in ('class="hero-image', 'data-timeline', 'Competition Awards', 'id="team"')]
    assert order == sorted(order)


def test_timeline_puts_goals_above_the_spine(client, db, setup):
    body = timeline_page(client, db, setup, goals=[{'name': 'Win States', 'progress': 50}],
                         journey=[{'date': '2025', 'title': 'Kickoff'}])
    assert body.index('Season Goals') < body.index('data-timeline') < body.index('Competition Awards')


def test_timeline_without_a_story_falls_back_to_classic(client, db, setup):
    body = timeline_page(client, db, setup)
    assert 'data-layout="timeline"' in body
    assert 'data-timeline' not in body and 'class="hero-image' in body
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


def test_editor_picker_loads_the_carousel(client, setup):
    # The radios stay in the page as the form; the carousel only enhances them.
    login(client, 'alice', 'alice-password')
    body = client.get(f"/manage/team/{setup['new']}").data.decode()
    assert 'class="layout-picker" role="radiogroup"' in body and 'data-carousel' in body
    for asset in ('css/circular-carousel.css', 'js/circular-carousel.js', 'js/layout-carousel.js'):
        assert asset in body, asset
    assert body.index('js/circular-carousel.js') < body.index('js/layout-carousel.js')


def test_group_editor_has_no_layout_picker(client, setup):
    login(client, 'alice', 'alice-password')
    body = client.get(f"/manage/team/{setup['group']}").data.decode()
    assert 'data-autosave="layout"' not in body


def test_site_default_accepts_only_listed_layouts():
    content = site_content.SECTIONS
    field = next(s for s in content if s.key == 'teams').by_key['layout']
    assert field.default == 'classic'
    assert set(field.choices) == set(site_content.TEAM_LAYOUTS)
