import pytest


@pytest.fixture
def team_factory(db):
    def _make(team_number='77628A', **overrides):
        doc = {
            'team_number': team_number,
            'season': '2025-26',
            'nickname': 'Hydra',
            'tagline': 'Precision. Power. Performance.',
            'division': 'High School',
            'since': 2019,
            'worlds_appearances': 2,
            'hero_image': 'static/assets/photos/hero.png',
            'stl_path': 'https://blob.example.com/robot.stl',
            'notebook_link': 'https://example.com/notebook',
            'specs': {
                'drive_train': 'X-Drive',
                'lift_system': '',
                'intake': 'Flex Wheel',
                'auton_consistency': '',
            },
            'members': [
                {'name': 'Bo Diaz', 'role': 'Builder', 'subteam': 'Mechanical',
                 'photo': 'static/assets/profile/base.png'},
                {'name': 'Ada Lovelace', 'role': 'Captain', 'roles': ['Captain', 'Programmer'],
                 'since': 2022, 'subteam': 'Programming', 'photo': ''},
            ],
            'goals': [
                {'name': 'Win States', 'progress': 100},
                {'name': 'Skills 200', 'progress': 40},
            ],
            'journey': [
                {'date': '2019', 'title': 'Team founded', 'description': 'First season.'},
            ],
        }
        doc.update(overrides)
        db['teams'].insert_one(doc)
        return doc
    return _make


@pytest.fixture
def award_factory(db):
    def _make(team_number='77628A', title='Excellence Award', count=2):
        doc = {'team_number': team_number, 'title': title, 'count': count,
               'icon': 'trophy.png', 'layout': '', 'border': '', 'shimmer': False}
        db['awards'].insert_one(doc)
        return doc
    return _make


def html(client, team_number='77628A', **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    url = f'/team/{team_number}' + (f'?{query}' if query else '')
    resp = client.get(url)
    return resp, resp.data.decode()


# --- basic rendering -------------------------------------------------------

def test_team_page_renders(client, team_factory):
    team_factory()
    resp, body = html(client)
    assert resp.status_code == 200
    assert 'Team 77628A' in body


def test_bare_team_renders(client, db):
    db['teams'].insert_one({'team_number': '77628Z'})
    resp, body = html(client, '77628Z')
    assert resp.status_code == 200


# --- awards: never remove these -------------------------------------------

def test_awards_section_always_present(client, db, team_factory, award_factory):
    team_factory()
    award_factory()
    db['teams'].insert_one({'team_number': '77628Z'})

    _, populated = html(client)
    assert 'Competition Awards' in populated
    assert 'Excellence Award' in populated

    _, bare = html(client, '77628Z')
    assert 'Competition Awards' in bare


def test_awards_grid_partial_still_included():
    with open('templates/team.html', encoding='utf-8') as fh:
        source = fh.read()
    assert source.count('awards_grid.html') == 1


# --- honest empty states ---------------------------------------------------

def test_no_tba_placeholder(client, team_factory, db):
    team_factory()
    db['teams'].insert_one({'team_number': '77628Z'})
    assert 'TBA' not in html(client)[1]
    assert 'TBA' not in html(client, '77628Z')[1]


def test_empty_specs_section_hidden(client, db):
    db['teams'].insert_one({'team_number': '77628Z'})
    assert 'robot-specs' not in html(client, '77628Z')[1]


def test_populated_specs_render_only_filled_fields(client, team_factory):
    team_factory()
    body = html(client)[1]
    assert 'X-Drive' in body
    assert 'Flex Wheel' in body
    assert 'Lift System' not in body


def test_notebook_button_hidden_when_placeholder(client, team_factory):
    team_factory(notebook_link='#')
    assert 'Engineering Notebook' not in html(client)[1]


def test_notebook_button_shown_when_real(client, team_factory):
    team_factory()
    assert 'Engineering Notebook' in html(client)[1]


# --- goals -----------------------------------------------------------------

def test_goal_progress_has_aria(client, team_factory):
    team_factory()
    body = html(client)[1]
    assert 'role="progressbar"' in body
    assert 'aria-valuenow="40"' in body
    assert 'aria-valuemax="100"' in body


def test_goal_progress_clamped(client, team_factory):
    team_factory(goals=[{'name': 'Overshoot', 'progress': 150}])
    body = html(client)[1]
    assert 'aria-valuenow="100"' in body
    assert 'width: 150%' not in body


def test_goals_section_hidden_when_empty(client, team_factory):
    team_factory(goals=[])
    assert 'goals-section' not in html(client)[1]


# --- roster ----------------------------------------------------------------

def test_member_photo_fallback(client, team_factory):
    team_factory()
    assert 'static/assets/profile/base.png' in html(client)[1]


def test_member_initials_avatar_when_no_photo(client, team_factory):
    team_factory()
    body = html(client)[1]
    assert 'roster-initials' in body
    assert '>AL<' in body


def test_member_roles_chips(client, team_factory):
    team_factory()
    body = html(client)[1]
    assert body.count('roster-role-chip') >= 3
    assert 'Programmer' in body


def test_roster_grouped_by_subteam(client, team_factory):
    team_factory()
    body = html(client)[1]
    assert 'Mechanical' in body
    assert 'Programming' in body


def test_leadership_sorted_first(client, team_factory):
    team_factory(members=[
        {'name': 'Bo Diaz', 'role': 'Builder'},
        {'name': 'Ada Lovelace', 'role': 'Captain'},
    ])
    body = html(client)[1]
    assert body.index('Ada Lovelace') < body.index('Bo Diaz')


def test_roster_empty_state(client, team_factory):
    team_factory(members=[])
    assert 'Roster coming soon' in html(client)[1]


# --- identity bar and season switcher --------------------------------------

def test_identity_bar_stats(client, team_factory, award_factory):
    team_factory()
    award_factory(count=3)
    body = html(client)[1]
    assert '2 Members' in body
    assert '3 Awards' in body
    assert 'Since 2019' in body
    assert '2&times; Worlds' in body or '2× Worlds' in body


def test_identity_bar_omits_missing_stats(client, db):
    db['teams'].insert_one({'team_number': '77628Z'})
    body = html(client, '77628Z')[1]
    assert '0 Members' not in body
    assert 'Worlds' not in body


def test_season_switcher_hidden_for_single_season(client, team_factory):
    team_factory()
    assert 'season-switcher' not in html(client)[1]


def test_season_switcher_shown_for_multiple_seasons(client, team_factory):
    team_factory()
    team_factory(season='2024-25', nickname='Hydra I')
    body = html(client)[1]
    assert 'season-switcher' in body
    assert '2024-25' in body


def test_newest_season_selected_by_default(client, team_factory):
    team_factory(season='2024-25', nickname='Old Hydra')
    team_factory(season='2025-26', nickname='New Hydra')
    assert 'New Hydra' in html(client)[1]


def test_season_query_param_selects_document(client, team_factory):
    team_factory(season='2024-25', nickname='Old Hydra')
    team_factory(season='2025-26', nickname='New Hydra')
    body = html(client, season='2024-25')[1]
    assert 'Old Hydra' in body


def test_unknown_season_falls_back_to_newest(client, team_factory):
    team_factory(season='2025-26', nickname='New Hydra')
    resp, body = html(client, season='1999-00')
    assert resp.status_code == 200
    assert 'New Hydra' in body


# --- live data degradation -------------------------------------------------

def test_live_sections_hidden_without_token(client, team_factory, monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_TOKEN', raising=False)
    team_factory()
    body = html(client)[1]
    assert 'skills-panel' not in body
    assert 'scoreboard-band' not in body


# --- house rules -----------------------------------------------------------

def test_no_inline_styles(client, team_factory):
    team_factory()
    body = html(client)[1]
    content = body.split('<main')[-1] if '<main' in body else body
    assert content.count('--team-hero-image') == 1


def test_live_sections_present_with_token(client, team_factory, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    team_factory()
    body = html(client)[1]
    assert 'id="skills-panel"' in body
    assert 'id="scoreboard-band"' in body
    assert 'id="results-section"' in body
    # Skeletons ship hidden; team.js reveals them only once real data arrives.
    assert 'aria-busy="true"' in body


def test_live_panels_point_at_the_json_route(client, team_factory, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    team_factory()
    assert 'data-live-url="/api/team/77628A/live"' in html(client)[1]


def test_team_js_always_loaded(client, team_factory):
    team_factory()
    assert 'js/team.js' in html(client)[1]


def test_event_photos_only_published_with_live_enabled(client, team_factory, monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_TOKEN', raising=False)
    team_factory(events=[{'name': 'States', 'photos': ['static/assets/photos/hero.png']}])
    assert 'team_event_photos' not in html(client)[1]

    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    body = html(client)[1]
    assert 'team_event_photos' in body
    assert 'States' in body


def test_viewer_rendered_when_stl_present(client, team_factory):
    team_factory()
    body = html(client)[1]
    assert 'id="robot-viewer"' in body
    assert 'data-stl="https://blob.example.com/robot.stl"' in body
    assert 'Reset View' in body


def test_no_viewer_and_no_dead_button_without_stl(client, team_factory):
    team_factory(stl_path='')
    body = html(client)[1]
    assert 'robot-viewer' not in body
    assert 'Rotate</button>' not in body
    assert 'CAD model not published' in body


def test_photo_gallery_replaces_viewer_when_photos_exist(client, team_factory):
    team_factory(stl_path='', events=[{'name': 'States',
                                       'photos': ['static/assets/photos/hero.png']}])
    body = html(client)[1]
    assert 'viewer-gallery' in body
    assert 'CAD model not published' not in body


def test_missing_team_redirects(client):
    resp = client.get('/team/nope')
    assert resp.status_code == 302
