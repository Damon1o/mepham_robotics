"""static/js/icons.js carries only the Lucide icons the site uses; make sure none go missing.

When one of these fails, re-run scripts/build_icons.py (see its docstring).
"""
import json
import pathlib
import re

import pytest

from api import events, site_content

ROOT = pathlib.Path(__file__).resolve().parent.parent
ICONS_JS = (ROOT / 'static' / 'js' / 'icons.js').read_text(encoding='utf-8')
BUNDLED = set(json.loads(re.search(r'var ICONS = (\{.*\});', ICONS_JS).group(1)))


@pytest.fixture
def signed_in(client, make_user):
    make_user(username='pat', password='pat-password', role='admin')
    client.post('/login', data={'username': 'pat', 'password': 'pat-password'})
    return client


def rendered_icons(page):
    return set(re.findall(r'data-lucide="([^"]+)"', page))


def test_no_page_loads_the_full_lucide_bundle():
    for path in (ROOT / 'templates').rglob('*.html'):
        assert 'lucide.min.js' not in path.read_text(encoding='utf-8'), path.name


@pytest.mark.parametrize('path', ['/', '/about', '/achievements', '/contact', '/donate', '/events',
                                  '/alumni', '/safety-quiz', '/privacy', '/credits', '/signup',
                                  '/login', '/this-page-does-not-exist'])
def test_public_page_icons_are_bundled(client, path):
    assert rendered_icons(client.get(path).get_data(as_text=True)) <= BUNDLED


@pytest.mark.parametrize('path', ['/admin', '/admin/site', '/account', '/resources', '/glossary',
                                  '/branding', '/standards', '/notebook', '/my-team'])
def test_signed_in_page_icons_are_bundled(signed_in, path):
    resp = signed_in.get(path)
    assert resp.status_code == 200
    assert rendered_icons(resp.get_data(as_text=True)) <= BUNDLED


@pytest.mark.parametrize('layout', sorted(site_content.TEAM_LAYOUTS))
def test_team_page_icons_are_bundled(client, db, layout):
    db['teams'].insert_one({
        'team_number': '77628A', 'season': '2025-26', 'layout': layout, 'nickname': 'Hydra',
        'stl_path': 'https://blob.example.com/robot.stl', 'notebook_link': 'https://example.com/nb',
        'specs': {'drive_train': 'X-Drive'}, 'goals': [{'name': 'Win States', 'progress': 40}],
        'members': [{'name': 'Ada Lovelace', 'role': 'Captain'}],
        'journey': [{'date': '2019', 'title': 'Founded', 'description': 'First season.'}]})
    db['awards'].insert_one({'team_number': '77628A', 'title': 'Excellence Award', 'count': 2,
                             'icon': 'trophy.png'})
    resp = client.get('/team/77628A')
    assert resp.status_code == 200
    assert rendered_icons(resp.get_data(as_text=True)) <= BUNDLED


@pytest.mark.parametrize('layout', sorted(site_content.GROUP_LAYOUTS))
def test_group_page_icons_are_bundled(client, db, layout):
    db['teams'].insert_one({
        'kind': 'group', 'team_number': 'media', 'title': 'Media', 'season': '2026-27', 'layout': layout,
        'members': [{'member_id': 'm1', 'name': 'Ada Byron', 'role': 'Builder'}],
        'goals': [{'name': 'Weekly reels', 'progress': 40, 'note': 'One a week.', 'owners': ['m1']},
                  {'name': 'New logo', 'progress': 0}]})
    resp = client.get('/team/media')
    assert resp.status_code == 200
    assert rendered_icons(resp.get_data(as_text=True)) <= BUNDLED


def test_icon_choice_lists_are_bundled():
    names = set(site_content.ICONS)
    names |= {icon for _label, icon, _hosts in site_content.SOCIAL_PLATFORMS.values()}
    names |= {icon for _name, icon in site_content.RESOURCE_SHELVES.values()}
    names |= {icon for _name, icon in site_content.ALUMNI_PATHS.values()}
    names |= {icon for _name, icon in events.KINDS.values()}
    names |= {section.icon for section in site_content.SECTIONS}
    assert names - BUNDLED == set()


def test_icons_written_into_templates_are_bundled():
    """Catches icons that only render with data present (a share button on an award, say)."""
    for path in (ROOT / 'templates').rglob('*.html'):
        for name in re.findall(r'data-lucide="([a-z0-9-]+)"', path.read_text(encoding='utf-8')):
            assert name in BUNDLED, f'{path.name}: {name}'


def test_icons_written_into_js_are_bundled():
    for path in (ROOT / 'static' / 'js').glob('*.js'):
        for name in re.findall(r'data-lucide="([a-z0-9-]+)"', path.read_text(encoding='utf-8')):
            assert name in BUNDLED, f'{path.name}: {name}'
