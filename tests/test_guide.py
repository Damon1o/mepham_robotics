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


def test_try_links_point_at_real_pages(client, make_user):
    sign_in(client, make_user, 'boss', 'admin')
    html = client.get('/guide').get_data(as_text=True)
    hrefs = re.findall(r'class="guide-btn guide-btn--try" href="([^"]+)"', html)
    assert hrefs and 'data-search-open' in html
    for href in hrefs:
        resp = client.get(href.split('#')[0])
        assert resp.status_code in (200, 302), href


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


def test_the_guide_stays_in_the_menu_until_every_chapter_is_done(member):
    home = member.get('/').get_data(as_text=True)
    assert 'Member guide</span>' in home and f'0/{len(MEMBER_KEYS)}' in home
    hub = member.get('/resources').get_data(as_text=True)
    assert 'New here? Take the member guide' in hub

    for key in MEMBER_KEYS:
        mark(member, key)
    assert 'Member guide</span>' not in member.get('/').get_data(as_text=True)
    assert 'class="hub-guide"' not in member.get('/resources').get_data(as_text=True)
    # Still reachable, and the finish card is showing.
    html = member.get('/guide').get_data(as_text=True)
    assert 'Member guide</span>' in html and 'guide-finish is-complete' in html


def test_admin_only_chapters_do_not_count_toward_a_members_progress(member, db):
    db['users'].update_one({'username': 'newbie'}, {'$set': {'guide_done': MEMBER_KEYS + ['admins']}})
    assert f'{len(MEMBER_KEYS)}</b> <span>of {len(MEMBER_KEYS)}' in member.get('/guide').get_data(as_text=True)


def test_search_offers_the_guide_only_to_members(client, make_user):
    assert '"title": "New Member Guide"' not in client.get('/').get_data(as_text=True)
    sign_in(client, make_user, 'newbie')
    assert '"title": "New Member Guide"' in client.get('/').get_data(as_text=True)
    assert 'Disallow: /guide' in client.get('/robots.txt').get_data(as_text=True)
