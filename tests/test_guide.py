"""New member guide (/guide): who sees which chapters, saving progress, and the links into it."""
import json
import pathlib
import re

import pytest

from api import guide

ROOT = pathlib.Path(__file__).resolve().parent.parent
ICONS_JS = (ROOT / 'static' / 'js' / 'icons.js').read_text(encoding='utf-8')
BUNDLED = set(json.loads(re.search(r'var ICONS = (\{.*\});', ICONS_JS).group(1)))
MEMBER_KEYS = [c['key'] for c in guide.CHAPTERS if not c.get('role')]


def sign_in(client, make_user, username, role='member'):
    make_user(username=username, password=f'{username}-password', email=f'{username}@example.com', role=role)
    client.post('/login', data={'username': username, 'password': f'{username}-password'})
    return client


@pytest.fixture
def member(client, make_user):
    return sign_in(client, make_user, 'newbie')


def set_site(db, key, value):
    db['site_metadata'].update_one({'_id': 'site_content'}, {'$set': {f'values.{key}': value}}, upsert=True)


def chapter_ids(html):
    return re.findall(r'data-chapter="([a-z]+)"', html)


def mark(client, key, done=True):
    return client.post('/api/guide/step', json={'key': key, 'done': done})


# --- Who sees it ----------------------------------------------------------------------

def test_signed_out_visitors_are_sent_to_sign_in(client):
    resp = client.get('/guide')
    assert resp.status_code == 302 and '/login' in resp.headers['Location']


def test_a_member_sees_every_member_chapter_in_order(member):
    html = member.get('/guide').get_data(as_text=True)
    assert chapter_ids(html) == MEMBER_KEYS
    assert 'Editor tools' not in html and 'Run the site' not in html
    assert '0</b> <span>of %d chapters done' % len(MEMBER_KEYS) in html


@pytest.mark.parametrize('role, extra', [('editor', ['editors']), ('admin', ['editors', 'admins'])])
def test_editors_and_admins_get_their_own_chapters(client, make_user, role, extra):
    sign_in(client, make_user, 'boss', role)
    assert chapter_ids(client.get('/guide').get_data(as_text=True)) == MEMBER_KEYS + extra


def test_every_chapter_has_a_show_me_tour_button(member):
    html = member.get('/guide').get_data(as_text=True)
    assert re.findall(r'data-tour-start="([a-z]+)"', html) == MEMBER_KEYS
    assert 'Take the guided tour' in html


def test_steps_about_switched_off_features_are_left_out(member, db):
    html = member.get('/guide').get_data(as_text=True)
    assert 'is <b>Steven</b>' in html and 'Anyone with the link' in html
    set_site(db, 'assistant.enabled', False)
    set_site(db, 'people.allow_public', False)
    html = member.get('/guide').get_data(as_text=True)
    assert 'is <b>Steven</b>' not in html and 'Anyone with the link' not in html


def test_guide_icons_are_bundled(client, make_user):
    sign_in(client, make_user, 'boss', 'admin')
    html = client.get('/guide').get_data(as_text=True)
    assert set(re.findall(r'data-lucide="([^"]+)"', html)) <= BUNDLED


# --- Progress -------------------------------------------------------------------------

def test_marking_a_chapter_done_is_saved_to_the_account(member, db):
    resp = mark(member, 'hub')
    assert resp.status_code == 200 and resp.get_json() == {'done': ['hub']}
    assert db['users'].find_one({'username': 'newbie'})['guide_done'] == ['hub']
    html = member.get('/guide').get_data(as_text=True)
    assert 'id="ch-hub" data-chapter="hub"' in html and 'class="guide-ch is-done" id="ch-hub"' in html
    # The resume link skips to the first chapter not done yet.
    assert f'href="#ch-{MEMBER_KEYS[0]}" data-guide-resume' in html

    assert mark(member, 'hub', done=False).get_json() == {'done': []}


def test_unknown_chapters_are_refused(member, db):
    assert mark(member, 'nope').status_code == 404
    assert 'guide_done' not in db['users'].find_one({'username': 'newbie'})


def test_saving_progress_needs_a_sign_in(client):
    assert mark(client, 'hub').status_code == 401


def test_the_guide_lives_in_the_member_hub(member):
    hub = member.get('/resources').get_data(as_text=True)
    assert 'New here? Take the tour' in hub and f'0 of {len(MEMBER_KEYS)} chapters done' in hub
    assert 'data-tour-start' in hub and 'href="/guide"' in hub
    # Not a separate menu item: the guide lights up the Member Hub link instead.
    html = member.get('/guide').get_data(as_text=True)
    hub_link = re.search(r'<a href="/resources" class="nav-link([^"]*)"', html)
    assert hub_link and 'active' in hub_link.group(1)

    for key in MEMBER_KEYS:
        mark(member, key)
    # It stays in the Hub once finished, to retake.
    hub = member.get('/resources').get_data(as_text=True)
    assert 'hub-guide is-complete' in hub and 'Retake the tour' in hub
    assert 'guide-finish is-complete' in member.get('/guide').get_data(as_text=True)


# --- Guided tour ----------------------------------------------------------------------

def tour(client):
    resp = client.get('/api/guide/tour')
    assert resp.status_code == 200
    return resp.get_json()


def test_the_tour_needs_a_sign_in(client):
    assert client.get('/api/guide/tour').status_code == 401
    html = client.get('/').get_data(as_text=True)
    assert 'js/tour.js' not in html and 'css/tour.css' not in html


def test_the_tour_follows_the_chapters_a_member_can_see(member):
    data = tour(member)
    assert [c['key'] for c in data['chapters']] == MEMBER_KEYS
    assert data['hub'] == '/resources'
    assert all(c['steps'] for c in data['chapters'])
    assert 'js/tour.js' in member.get('/').get_data(as_text=True)


def test_admins_tour_the_admin_panel(client, make_user):
    sign_in(client, make_user, 'boss', 'admin')
    keys = [c['key'] for c in tour(client)['chapters']]
    assert keys == MEMBER_KEYS + ['editors', 'admins']


def test_every_tour_step_lands_on_a_page_it_matches(client, make_user, db):
    """Each step's page loads, and its match pattern accepts where that page ends up."""
    user = make_user(username='boss', password='boss-password', email='boss@example.com', role='admin')
    db['teams'].insert_one({'team_number': '77628A', 'season': '2026-27',
                            'members': [{'member_id': 'm1', 'name': 'Boss', 'user_id': str(user['_id'])}]})
    client.post('/login', data={'username': 'boss', 'password': 'boss-password'})
    for chapter in tour(client)['chapters']:
        for step in chapter['steps']:
            resp = client.get(step['url'], follow_redirects=True)
            assert resp.status_code == 200, step['url']
            assert re.search(step['match'], resp.request.path), (step['url'], resp.request.path)


def test_tour_steps_about_switched_off_features_are_left_out(member, db):
    titles = lambda: [s['title'] for c in tour(member)['chapters'] for s in c['steps']]  # noqa: E731
    assert 'Ask Steven' in titles()
    set_site(db, 'assistant.enabled', False)
    assert 'Ask Steven' not in titles()


def test_tour_targets_exist_on_their_pages(client, make_user, db):
    """Required (non-optional) spotlight targets must be in the page the member lands on."""
    user = make_user(username='boss', password='boss-password', email='boss@example.com', role='admin')
    client.post('/login', data={'username': 'boss', 'password': 'boss-password'})
    simple = {'#': 'id', '.': 'class'}
    for chapter in tour(client)['chapters']:
        for step in chapter['steps']:
            target = step['target']
            if step['optional'] or not target:
                continue
            html = client.get(step['url'], follow_redirects=True).get_data(as_text=True)
            last = target.split()[-1]
            if last[0] in simple and re.fullmatch(r'[#.][\w-]+', last):
                attr, name = simple[last[0]], last[1:]
                pattern = rf'{attr}="{name}"' if attr == 'id' else rf'class="[^"]*\b{name}\b'
                assert re.search(pattern, html), (step['url'], target)
            else:
                assert re.sub(r'[\[\]"]', '', last).split('=')[0] in html, (step['url'], target)


def test_admin_only_chapters_do_not_count_toward_a_members_progress(member, db):
    db['users'].update_one({'username': 'newbie'}, {'$set': {'guide_done': MEMBER_KEYS + ['admins']}})
    assert f'{len(MEMBER_KEYS)}</b> <span>of {len(MEMBER_KEYS)}' in member.get('/guide').get_data(as_text=True)


def test_search_offers_the_guide_only_to_members(client, make_user):
    assert '"title": "New Member Guide"' not in client.get('/').get_data(as_text=True)
    sign_in(client, make_user, 'newbie')
    assert '"title": "New Member Guide"' in client.get('/').get_data(as_text=True)
    assert 'Disallow: /guide' in client.get('/robots.txt').get_data(as_text=True)
