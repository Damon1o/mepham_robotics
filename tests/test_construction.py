"""Site settings -> Under construction: the whole site or chosen pages show a notice to visitors."""
import pytest

import api.index as app_module
from api import site_content


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def visitor(db):
    return app_module.app.test_client()


def save(client, key, value):
    response = client.post('/admin/api/site', json={'key': key, 'value': value})
    assert response.status_code == 200, response.get_data(as_text=True)


def test_everything_is_open_by_default(admin, visitor):
    response = visitor.get('/about')
    assert response.status_code == 200
    assert 'construction-page' not in response.get_data(as_text=True)


def test_the_whole_site_switch_covers_every_public_page(admin, visitor, db):
    save(admin, 'construction.enabled', True)
    save(admin, 'construction.heading', 'Back soon')
    db['teams'].insert_one({'team_number': '1A'})
    for path in ('/', '/about', '/contact', '/donate', '/achievements', '/privacy', '/team/1A'):
        response = visitor.get(path)
        assert response.status_code == 503, path
        assert 'Back soon' in response.get_data(as_text=True)
        assert response.headers['Retry-After']


def test_sign_in_static_files_and_health_stay_open(admin, visitor):
    save(admin, 'construction.enabled', True)
    assert visitor.get('/login').status_code == 200
    assert visitor.get('/static/css/styles.css').status_code == 200
    assert 'Member Login' in visitor.get('/').get_data(as_text=True)


def test_single_pages_can_be_picked(admin, visitor):
    save(admin, 'construction.pages', [{'page': 'donate'}, {'page': 'about'}])
    assert visitor.get('/donate').status_code == 503
    assert visitor.get('/about').status_code == 503
    assert visitor.get('/contact').status_code == 200
    # A single page offers the way home; the whole site does not.
    assert 'Go Home' in visitor.get('/donate').get_data(as_text=True)


def test_editors_and_admins_see_the_real_page_with_a_strip(admin, make_user, client):
    save(admin, 'construction.enabled', True)
    about = admin.get('/about')
    assert about.status_code == 200
    assert 'Visitors see the construction notice' in about.get_data(as_text=True)
    assert 'Visitors see the construction notice' not in admin.get('/login').get_data(as_text=True)


def test_members_still_see_the_notice(admin, make_user, db):
    save(admin, 'construction.enabled', True)
    make_user(username='mem', password='member-password', email='mem@example.com', role='member')
    member = app_module.app.test_client()
    member.post('/login', data={'username': 'mem', 'password': 'member-password'})
    page = member.get('/')
    assert page.status_code == 503
    assert 'Member Login' not in page.get_data(as_text=True)


def test_only_listed_pages_can_be_picked(admin):
    response = admin.post('/admin/api/site', json={'key': 'construction.pages', 'value': [{'page': 'admin_site'}]})
    assert response.status_code == 400


def test_under_construction_ignores_endpoints_outside_the_list():
    assert not site_content.under_construction({'enabled': True}, 'login')
    assert site_content.under_construction({'enabled': False, 'pages': [{'page': 'about'}]}, 'about')
