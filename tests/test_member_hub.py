"""Member Hub (/resources): editable library, this week tiles, drivetrain calculator."""
import datetime
import re

import pytest

import api.index as app_module
from api import site_content


@pytest.fixture
def member(client, make_user):
    make_user(username='alice', password='alice-password', role='member')
    client.post('/login', data={'username': 'alice', 'password': 'alice-password'})
    return client


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def save(client, key, value):
    response = client.post('/admin/api/site', json={'key': key, 'value': value})
    assert response.status_code == 200, response.get_data(as_text=True)


# --- Helpers ----------------------------------------------------------------------------

MEETING = {'days': [2, 5], 'start': '15:00', 'end': '17:00'}  # Tuesday & Friday
WEDNESDAY = datetime.datetime(2026, 10, 7, 12, 0)


def test_next_meeting_is_the_next_meeting_day():
    start, end = site_content.next_meeting(MEETING, WEDNESDAY)
    assert start == datetime.datetime(2026, 10, 9, 15, 0)
    assert end == datetime.datetime(2026, 10, 9, 17, 0)


def test_next_meeting_is_today_until_it_ends():
    tuesday = datetime.datetime(2026, 10, 6, 16, 0)
    assert site_content.next_meeting(MEETING, tuesday)[0].date() == tuesday.date()
    after = tuesday.replace(hour=17, minute=30)
    assert site_content.next_meeting(MEETING, after)[0] == datetime.datetime(2026, 10, 9, 15, 0)


def test_next_meeting_wraps_to_next_week():
    friday_evening = datetime.datetime(2026, 10, 9, 18, 0)
    only_friday = dict(MEETING, days=[5])
    assert site_content.next_meeting(only_friday, friday_evening)[0] == datetime.datetime(2026, 10, 16, 15, 0)


def test_next_meeting_without_days_is_none():
    assert site_content.next_meeting(dict(MEETING, days=[]), WEDNESDAY) is None


def test_shelves_keep_their_order_and_skip_empty_ones():
    rows = [site_content._resource('learn', 'B', '/b'), site_content._resource('code', 'A', '/a'),
            {'shelf': 'code', 'title': '', 'url': '/x'}]
    shelves = site_content.resource_shelves(rows)
    assert [key for key, *_ in shelves] == ['code', 'learn']
    assert [r['title'] for r in shelves[0][3]] == ['A']


def test_every_default_link_has_a_known_shelf():
    library = site_content.SECTION_MAP['resources'].by_key['library']
    assert all(row['shelf'] in site_content.RESOURCE_SHELVES for row in library.default)
    assert len(library.default) <= library.max_items


# --- Page -------------------------------------------------------------------------------

def test_members_see_the_hub(member):
    page = member.get('/resources').get_data(as_text=True)
    assert 'Member Hub' in page
    assert 'id="hub-q"' in page
    assert 'id="drivetrain"' in page
    assert 'Start here' in page and 'Safety quiz' in page
    assert 'js/resources.js' in page


def test_this_week_shows_the_next_competition_and_roster(member, db):
    db['competitions'].insert_one({'name': 'Hofstra Signature Event', 'location': 'Hofstra',
                                   'date': app_module.club_now() + datetime.timedelta(days=12)})
    page = member.get('/resources').get_data(as_text=True)
    assert 'Hofstra Signature Event' in page
    assert '12<small> days</small>' in page
    assert 'Free agent' in page


def test_past_competitions_are_not_next(member, db):
    db['competitions'].insert_one({'name': 'Old Scrimmage', 'location': '',
                                   'date': app_module.club_now() - datetime.timedelta(days=3)})
    page = member.get('/resources').get_data(as_text=True)
    assert 'Old Scrimmage' not in page
    assert 'Nothing on the calendar yet.' in page


def test_admins_edit_the_library(admin):
    save(admin, 'resources.library', [
        {'shelf': 'code', 'title': 'Odom notes', 'url': 'https://example.com/odom', 'note': 'Tracking wheels'},
    ])
    page = admin.get('/resources').get_data(as_text=True)
    assert 'Odom notes' in page and 'example.com' in page
    assert 'VEXcode V5 API' not in page
    assert 'Start here' not in page
    assert '/admin/site#resources' in page


def test_library_rejects_unknown_shelves_and_bad_links(admin):
    bad_shelf = admin.post('/admin/api/site', json={'key': 'resources.library', 'value': [
        {'shelf': 'nope', 'title': 'X', 'url': '/x', 'note': ''}]})
    assert bad_shelf.status_code == 400
    bad_link = admin.post('/admin/api/site', json={'key': 'resources.library', 'value': [
        {'shelf': 'code', 'title': 'X', 'url': 'javascript:alert(1)', 'note': ''}]})
    assert bad_link.status_code == 400


def test_sections_can_be_switched_off(admin):
    save(admin, 'resources.show_calculator', False)
    save(admin, 'resources.show_week', False)
    page = admin.get('/resources').get_data(as_text=True)
    assert 'id="drivetrain"' not in page
    assert 'hub-week' not in page


def test_external_links_open_safely(member):
    page = member.get('/resources').get_data(as_text=True)
    assert 'href="https://cad.onshape.com/" target="_blank" rel="noopener"' in page
    assert 'href="/glossary" target' not in page


# --- Around the site ----------------------------------------------------------------------

MEMBER_ONLY = ('/resources', '/glossary', '/branding', '/standards', '/notebook')


def test_members_only_pages_stay_out_of_the_sitemap(client):
    body = client.get('/sitemap.xml').get_data(as_text=True)
    for path in MEMBER_ONLY:
        assert f'{path}<' not in body


def test_robots_keeps_crawlers_off_members_only_pages(client):
    body = client.get('/robots.txt').get_data(as_text=True)
    for path in MEMBER_ONLY:
        assert f'Disallow: {path}\n' in body + '\n'


def test_nav_footer_and_breadcrumbs_name_the_hub(member):
    page = member.get('/glossary').get_data(as_text=True)
    assert len(re.findall(r'href="/resources"[^>]*>Member Hub</a>', page)) == 3
    assert '>Resources</a>' not in page


def test_visitors_get_no_hub_links(client):
    assert 'href="/resources"' not in client.get('/').get_data(as_text=True)


def test_hub_title_flows_everywhere(admin):
    save(admin, 'resources.hero_title', 'Pit Crew HQ')
    assert 'Back to the Pit Crew HQ' in admin.get('/standards').get_data(as_text=True)
    with app_module.app.test_request_context('/'):
        assert 'Pit Crew HQ at /resources' in app_module.chat_system_prompt()
