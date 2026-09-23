"""Content loose ends: fabricated data, placeholders, dead links, inline CSS."""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def member(client, make_user):
    make_user(username='pat', password='pat-password')
    client.post('/login', data={'username': 'pat', 'password': 'pat-password'})
    return client


# --- Achievements --------------------------------------------------------------

def test_achievements_ships_no_fabricated_matches(client):
    page = client.get('/achievements').get_data(as_text=True)
    for fake in ('1234A', '5678B', '9999Z', '45 - 30'):
        assert fake not in page
    assert 'Loading match results' in page


def test_achievements_has_no_dead_season_filters(client):
    assert 'filter-tab' not in client.get('/achievements').get_data(as_text=True)


def test_achievements_shows_an_empty_state(client):
    assert 'Award history is being added' in client.get('/achievements').get_data(as_text=True)


# --- Team page ---------------------------------------------------------------------

def test_team_page_has_no_placeholder_viewer(client, db):
    db['teams'].insert_one({'team_number': '77628D', 'nickname': 'D', 'members': [], 'goals': []})
    resp = client.get('/team/77628D')
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert 'PLACEHOLDER' not in page
    assert 'viewer-btn' not in page
    assert 'Download CAD model' not in page


def test_team_page_offers_the_stl_download(client, db):
    db['teams'].insert_one({'team_number': '77628D', 'members': [], 'goals': [],
                            'stl_path': 'https://blob.example/model.stl'})
    page = client.get('/team/77628D').get_data(as_text=True)
    assert 'href="https://blob.example/model.stl"' in page


@pytest.mark.parametrize('link,shown', [(None, False), ('#', False),
                                        ('https://docs.example/notebook', True)])
def test_notebook_button_only_with_a_real_link(client, db, link, shown):
    db['teams'].insert_one({'team_number': '77628D', 'members': [], 'goals': [], 'notebook_link': link})
    page = client.get('/team/77628D').get_data(as_text=True)
    assert ('Engineering Notebook' in page) is shown


# --- Links ---------------------------------------------------------------------------

def test_checklist_anchor_exists(member):
    assert 'id="checklist"' in member.get('/standards').get_data(as_text=True)


def test_resources_has_no_links_to_missing_content(member):
    page = member.get('/resources').get_data(as_text=True)
    for gone in ('Odometry Logs', 'Match Analysis Logs', 'Wiring 101'):
        assert gone not in page
    for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', page):
        assert 'rel="noopener"' in tag


def test_carousel_is_shared(client):
    index = client.get('/').get_data(as_text=True)
    about = client.get('/about').get_data(as_text=True)
    assert 'Team Gallery' in index and 'carousel10.jpg' in index
    assert 'Team Moments' in about and 'carousel10.jpg' in about


# --- Accessibility -----------------------------------------------------------------------

def test_glossary_filter_is_labelled_and_headings_nest(member):
    page = member.get('/glossary').get_data(as_text=True)
    assert 'for="glossarySearch"' in page
    assert '<h2>A</h2>' in page
    assert '<h3>A</h3>' not in page


def test_error_pages_have_a_heading_and_the_theme(client):
    page = client.get('/no-such-page').get_data(as_text=True)
    assert '<h1 class="error-message">' in page
    assert 'js/theme.js' in page


# --- Inline CSS and dead JS ---------------------------------------------------------------

# Dynamic values passed as custom properties are the documented exception, and
# the awards grid partial is protected from edits.
STYLE_ALLOWED = {
    'team.html': ['--team-hero-image'],
    'awards_grid.html': ['grid-column: 1 / -1'],
}


def test_templates_carry_no_inline_css():
    for path in (ROOT / 'templates').rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        assert '<style' not in text, path.name
        for style in re.findall(r'style="([^"]*)"', text):
            allowed = STYLE_ALLOWED.get(path.name, [])
            assert any(a in style for a in allowed), f'{path.name}: style="{style}"'


@pytest.mark.parametrize('dead', ['.timeline-container', "img[data-src]", '.nav-overlay',
                                  'initFilterTabs', 'Feb 22, 2026'])
def test_script_has_no_dead_selectors(dead):
    assert dead not in (ROOT / 'static/js/script.js').read_text(encoding='utf-8')


def test_team_page_survives_a_bare_document(client, db):
    db['teams'].insert_one({'team_number': '77628Z'})
    assert client.get('/team/77628Z').status_code == 200
