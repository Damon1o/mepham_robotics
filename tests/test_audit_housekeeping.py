"""Loose ends from the November 2026 audit: local run, activity log, error pages, sitemap, privacy."""
import pathlib
import re

import pytest

import api.index as app_module

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = (ROOT / 'api' / 'index.py').read_text(encoding='utf-8')


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


# --- `python api/index.py` ---------------------------------------------------------------

def test_flat_import_fallback_loads_every_module_the_package_import_does():
    """Run as a script, the app takes the `except ImportError` branch; a module missing
    there (it was `devices`) only failed later, when a page first used it."""
    packaged = re.search(r'^    from api import (.+)$', SOURCE, re.M).group(1).split(', ')
    fallback = SOURCE.split('except ImportError:', 1)[1].split('load_dotenv()', 1)[0]
    assert sorted(re.findall(r'^    import (\w+)$', fallback, re.M)) == sorted(packaged)


# --- Activity log ----------------------------------------------------------------------------

def test_every_logged_activity_type_has_an_icon_title_and_filter_group():
    logged = set(re.findall(r"log_activity\(\s*'(\w+)'", SOURCE))
    assert len(logged) > 30
    assert logged - set(app_module.ACTIVITY_TYPES) == set()
    groups = {key for key, _ in app_module.ACTIVITY_GROUPS}
    assert {group for _, _, group in app_module.ACTIVITY_TYPES.values()} <= groups


# --- Error pages ---------------------------------------------------------------------------------

def test_wrong_method_gets_the_site_error_card(client):
    response = client.get('/logout')
    page = response.get_data(as_text=True)
    assert response.status_code == 405
    assert 'error-page' in page and '405' in page
    assert 'POST' in response.headers['Allow']
    assert '<title>405 Method Not Allowed</title>' not in page


def test_rejected_form_page_is_unchanged(raw_client):
    page = raw_client.post('/logout').get_data(as_text=True)
    assert '400' in page and 'Request Rejected' in page and 'security token' in page


@pytest.mark.parametrize('referrer, expected', [
    ('http://localhost/admin?tab=teams', '/admin?tab=teams'),
    ('http://localhost/', '/'),
    ('https://evil.example/landing', ''),
    ('http://localhost.evil.example/admin', ''),
    ('', ''),
])
def test_too_large_upload_only_goes_back_to_our_own_pages(referrer, expected):
    headers = {'Referer': referrer} if referrer else {}
    with app_module.app.test_request_context('/admin/save-sponsor', method='POST', headers=headers):
        assert app_module._same_site_referrer() == expected


# --- Sitemap --------------------------------------------------------------------------------------

def test_sitemap_leaves_out_pages_under_construction(admin, db):
    db['teams'].insert_one({'team_number': '1A'})
    before = admin.get('/sitemap.xml').get_data(as_text=True)
    assert '/donate</loc>' in before and '/team/1A</loc>' in before

    response = admin.post('/admin/api/site', json={'key': 'construction.pages',
                                                   'value': [{'page': 'donate'}, {'page': 'team_page'}]})
    assert response.status_code == 200, response.get_data(as_text=True)
    after = admin.get('/sitemap.xml').get_data(as_text=True)
    assert '/donate</loc>' not in after and '/team/1A</loc>' not in after
    assert '/about</loc>' in after


# --- Privacy policy -------------------------------------------------------------------------------

@pytest.mark.parametrize('topic', ['Discord', 'Signed-in devices', 'Member pages and photos', 'sign-in and sign-out',
                                   'two-step'])
def test_privacy_policy_covers_what_members_store(client, topic):
    assert topic in client.get('/privacy').get_data(as_text=True)


# --- Unused files ---------------------------------------------------------------------------------

def test_hero_source_image_stays_out_of_the_deployment():
    ignored = (ROOT / '.vercelignore').read_text(encoding='utf-8').split()
    assert 'static/assets/photos/hero.png' in ignored
    for page in (ROOT / 'templates').rglob('*.html'):
        assert 'hero.png' not in page.read_text(encoding='utf-8'), page.name
