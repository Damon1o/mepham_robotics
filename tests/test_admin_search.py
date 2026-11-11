"""Finding things as an admin: the search index behind Ctrl+K, the deep links it hands out,
"Edit This Page", and the site editor's one-section-at-a-time menu."""
import datetime as dt
import pathlib

import pytest

import api.index as app_module
from api import site_content

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = '/admin/api/search-index'


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def items(client):
    return client.get(INDEX).get_json()['items']


def find(found, kind, title):
    return next(i for i in found if i['kind'] == kind and i['title'] == title)


# --- Who gets it ------------------------------------------------------------------------------

def test_index_is_for_admins_only(client, make_user):
    assert client.get(INDEX, headers={'Accept': 'application/json'}).status_code == 401
    make_user(username='ed', password='ed-password-1', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'ed-password-1'})
    assert client.get(INDEX, headers={'Accept': 'application/json'}).status_code == 403
    assert 'data-admin-index' not in client.get('/').get_data(as_text=True)


def test_admin_pages_point_the_search_box_at_the_index(admin):
    resp = admin.get(INDEX)
    assert resp.status_code == 200 and 'no-store' in resp.headers['Cache-Control']
    page = admin.get('/about').get_data(as_text=True)
    assert f'data-admin-index="{INDEX}"' in page
    assert 'Search pages, settings, people' in page


# --- What it finds ----------------------------------------------------------------------------

def test_every_setting_is_listed_with_a_link_to_itself(admin):
    found = items(admin)
    urls = {i['url'] for i in found if i['kind'] == 'Setting'}
    for section in site_content.SECTIONS:
        assert any(i['kind'] == 'Settings' and i['url'] == f'/admin/site#{section.key}' for i in found), section.key
        for field in section.fields:
            key = f'{section.key}.{field.key}'
            expected = '/admin#events?at=siteEditor' if key in app_module.FUNDRAISER_LIST_KEYS else f'/admin/site#{key}'
            assert expected in urls, key


def test_a_setting_is_found_by_the_words_it_shows(admin):
    tagline = next(i for i in items(admin) if i['url'] == '/admin/site#general.tagline')
    assert tagline['title'] == 'Tagline' and 'Club details' in tagline['desc']
    assert 'Build. Code. Compete.' in tagline['keywords']
    admin.post('/admin/api/site', json={'key': 'general.tagline', 'value': 'Gears and grit'})
    tagline = next(i for i in items(admin) if i['url'] == '/admin/site#general.tagline')
    assert tagline['keywords'] == 'Gears and grit'


def test_list_settings_are_searched_by_their_entries_but_not_image_addresses():
    words = app_module._search_words([{'title': 'Perseverance', 'text': 'We keep going'},
                                      {'image': {'src': 'https://blob.example/x.webp', 'alt': 'Pit crew'}}])
    assert words == 'Perseverance We keep going Pit crew'
    assert len(app_module._search_words('word ' * 2000)) == app_module.SEARCH_VALUE_MAX


def test_tabs_actions_people_teams_events_and_sponsors(admin, db, make_user):
    make_user(username='ada', password='ada-password', email='ada@example.com')
    db['users'].update_one({'username': 'ada'}, {'$set': {'full_name': 'Ada Lovelace'}})
    make_user(username='newkid', password='new-password', email='new@example.com')
    db['users'].update_one({'username': 'newkid'}, {'$set': {'status': 'pending'}})
    team_id = db['teams'].insert_one({'team_number': '77628A', 'season': '2025-26', 'nickname': 'Hydra'}).inserted_id
    soon = app_module.club_now().replace(tzinfo=None) + dt.timedelta(days=5)
    db['competitions'].insert_many([
        {'name': 'Regional & Qualifier', 'date': soon, 'location': 'Gym'},
        {'name': 'Last year', 'date': soon - dt.timedelta(days=400)},
    ])
    db['sponsors'].insert_one({'name': 'Acme Tools', 'tier': 'gold'})
    found = items(admin)

    assert find(found, 'Admin', 'People tab')['url'] == '/admin#users'
    assert find(found, 'Action', 'Add an event')['url'] == '/admin#events?add'
    assert find(found, 'Action', 'Post an announcement')['url'] == '/admin/site#announcement'
    ada = find(found, 'Person', 'Ada Lovelace')
    assert ada['url'] == '/admin#users?find=ada' and 'ada@example.com' in ada['keywords']
    assert 'Member account' in ada['desc']
    waiting = find(found, 'Person', 'newkid')
    assert waiting['url'] == '/admin#users' and 'Waiting for approval' in waiting['desc']
    team = find(found, 'Team', 'Edit the 77628A (2025-26) page')
    assert team['url'] == f'/manage/team/{team_id}' and 'Hydra' in team['keywords']
    # The name travels in the address, so it is escaped.
    assert find(found, 'Event', 'Regional & Qualifier')['url'] == '/admin#events?find=Regional%20%26%20Qualifier'
    assert not any(i['title'] == 'Last year' for i in found)
    assert find(found, 'Sponsor', 'Acme Tools')['desc'] == 'Gold sponsor'
    # Every item has what the search box reads, and all of it is for signed-in admins.
    for item in found:
        assert set(item) == {'kind', 'title', 'url', 'desc', 'keywords', 'members'} and item['members'] is True


# --- "Edit This Page" ----------------------------------------------------------------------------

@pytest.mark.parametrize('path,anchor', [('/', 'home'), ('/about', 'about'), ('/donate', 'donate'),
                                          ('/contact', 'contact'), ('/events', 'events')])
def test_admins_get_an_edit_link_on_pages_the_editor_covers(admin, path, anchor):
    page = admin.get(path).get_data(as_text=True)
    assert f'href="/admin/site#{anchor}"' in page and 'Edit This Page' in page


def test_no_edit_link_for_visitors_or_on_pages_without_settings(client, admin):
    assert 'Edit This Page' not in admin.get('/privacy').get_data(as_text=True)
    admin.post('/logout')
    assert 'Edit This Page' not in client.get('/about').get_data(as_text=True)


# --- The pages that use it -------------------------------------------------------------------

def test_dashboard_search_opens_the_site_search(admin):
    page = admin.get('/admin').get_data(as_text=True)
    assert 'data-open-search' in page and 'id="adminSearch"' not in page


def test_dashboard_reads_what_to_do_from_the_address():
    source = (ROOT / 'static/js/admin.js').read_text(encoding='utf-8')
    for part in ("params.has('find')", "params.has('add')", "params.has('at')", 'history.replaceState'):
        assert part in source, part
    # Each tab a search result can filter has its filter box on the page.
    templates = ''.join(p.read_text(encoding='utf-8') for p in (ROOT / 'templates/admin').glob('_*.html'))
    for box in ('users_filter', 'teams_filter', 'events_filter', 'awards_filter', 'sponsors_filter', 'messages_filter'):
        assert f"'{box}'" in source and f'id="{box}"' in templates, box


def test_site_editor_shows_one_section_at_a_time(admin):
    page = admin.get('/admin/site').get_data(as_text=True)
    assert 'settings-layout is-paged' in page and 'data-only-changed' in page
    assert page.count('class="settings-pager"') == len(site_content.SECTIONS)
    first, last = site_content.SECTIONS[0], site_content.SECTIONS[-1]
    assert f'class="settings-pager-next" href="#{site_content.SECTIONS[1].key}"' in page
    assert f'class="settings-pager-prev" href="#{site_content.SECTIONS[-2].key}"' in page
    assert f'class="settings-pager-prev" href="#{last.key}"' not in page
    assert f'class="settings-pager-next" href="#{first.key}"' not in page
    source = (ROOT / 'static/js/site-editor.js').read_text(encoding='utf-8')
    assert "addEventListener('hashchange'" in source and 'is-found' in source


def test_one_section_editors_are_not_paged(admin):
    page = admin.get('/manage/fundraisers').get_data(as_text=True)
    assert 'is-paged' not in page and 'settings-pager' not in page
