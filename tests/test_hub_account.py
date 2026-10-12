"""Member Hub: stars and recently opened links on the account, and "New" since the last visit."""
import re

import pytest

LIBRARY = [
    {'shelf': 'code', 'title': 'PROS docs', 'url': 'https://pros.cs.purdue.edu', 'note': ''},
    {'shelf': 'build', 'title': 'CAD guide', 'url': '/static/cad.pdf', 'note': ''},
]


@pytest.fixture
def library(db):
    db['site_metadata'].update_one({'_id': 'site_content'},
                                   {'$set': {'values': {'resources': {'library': LIBRARY}}}}, upsert=True)


@pytest.fixture
def member(client, make_user, library):
    user = make_user(username='alice', password='alice-password', role='member')
    client.post('/login', data={'username': 'alice', 'password': 'alice-password'})
    return user


def page(client):
    return client.get('/resources').get_data(as_text=True)


def starred(html):
    return set(re.findall(r'data-star="([^"]+)" aria-pressed="true"', html))


def test_starring_is_kept_on_the_account(client, db, member):
    resp = client.post('/api/hub/star', json={'url': '/static/cad.pdf', 'on': True})
    assert resp.status_code == 200 and resp.get_json() == {'stars': ['/static/cad.pdf']}
    assert db['users'].find_one({'_id': member['_id']})['hub_stars'] == ['/static/cad.pdf']
    html = page(client)
    assert starred(html) == {'/static/cad.pdf'}
    assert 'data-star-count>1<' in html
    assert client.post('/api/hub/star', json={'url': '/static/cad.pdf', 'on': False}).get_json() == {'stars': []}


def test_only_library_links_can_be_starred(client, member):
    assert client.post('/api/hub/star', json={'url': 'https://evil.example', 'on': True}).status_code == 404


def test_hub_api_needs_a_member(client, library):
    assert client.post('/api/hub/star', json={'url': '/static/cad.pdf', 'on': True}).status_code == 401


def test_browser_stars_import_once_and_skip_removed_links(client, db, member):
    assert 'data-stars-imported="false"' in page(client)
    resp = client.post('/api/hub/stars/import', json={'urls': ['https://pros.cs.purdue.edu', '/gone', 5]})
    assert resp.get_json() == {'stars': ['https://pros.cs.purdue.edu']}
    assert 'data-stars-imported="true"' in page(client)


def test_recently_opened_is_newest_first_and_deduplicated(client, db, member):
    for url in ('/static/cad.pdf', 'https://pros.cs.purdue.edu', '/static/cad.pdf', '/not-in-library'):
        assert client.post('/api/hub/opened', json={'url': url}).status_code == 204
    assert db['users'].find_one({'_id': member['_id']})['hub_recent'] == ['/static/cad.pdf',
                                                                          'https://pros.cs.purdue.edu']
    html = page(client)
    recent = html.split('class="hub-recent"', 1)[1].split('</nav>', 1)[0]
    assert recent.index('CAD guide') < recent.index('PROS docs')


def test_recent_list_is_capped(client, db, member):
    import api.index as app_module
    db['users'].update_one({'_id': member['_id']}, {'$set': {'hub_recent': [f'/x{n}' for n in range(10)]}})
    client.post('/api/hub/opened', json={'url': '/static/cad.pdf'})
    assert len(db['users'].find_one({'_id': member['_id']})['hub_recent']) == app_module.HUB_RECENT_KEPT


def test_new_links_are_marked_after_the_first_visit(client, db, member):
    first = page(client)
    assert 'hub-new' not in first and 'data-shelf="new"' not in first  # first visit: nothing is "new"
    db['site_metadata'].update_one({'_id': 'site_content'}, {'$push': {'values.resources.library': {
        'shelf': 'learn', 'title': 'Odometry primer', 'url': 'https://odom.example', 'note': ''}}})
    second = page(client)
    assert re.search(r'data-row data-new data-shelf="learn" data-url="https://odom.example"', second)
    assert second.count('<span class="hub-new">New</span>') == 1
    assert 'data-shelf="new"' in second
    # Seen now: the next visit no longer calls it new.
    assert 'hub-new' not in page(client)
