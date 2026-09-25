"""Admin dashboard: team/sponsor saves and the page's own markup."""
import io
import re

import pytest

import api.index as app_module


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def uploads(monkeypatch):
    """Capture blob uploads instead of calling Vercel."""
    keys = []

    def _upload(file, key):
        keys.append(key)
        return f'https://blob.example/{key}'

    monkeypatch.setattr(app_module, 'upload_to_vercel_blob', _upload)
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', lambda url: None)
    return keys


# --- Team saves -------------------------------------------------------------

def _team_form(**extra):
    data = {'team_number': '77628D', 'nickname': 'Dreadnought', 'tagline': 'Go'}
    data.update(extra)
    return data


def test_deleting_a_middle_row_keeps_the_rest(admin, db):
    """Rows 0 and 2 survive a deleted row 1. The old `while member_name_{i}`
    loop stopped at the gap and dropped member 2."""
    admin.post('/admin/save-team', data=_team_form(
        member_name_0='Avery', member_role_0='Driver',
        member_name_2='Blake', member_role_2='Builder',
        goal_name_0='Skills', goal_progress_0='40',
        goal_name_5='Auton', goal_progress_5='80',
    ))
    team = db['teams'].find_one({'team_number': '77628D'})
    assert [m['name'] for m in team['members']] == ['Avery', 'Blake']
    assert [g['name'] for g in team['goals']] == ['Skills', 'Auton']


def test_rows_are_saved_in_index_order(admin, db):
    admin.post('/admin/save-team', data=_team_form(
        member_name_10='Last', member_role_10='x',
        member_name_2='First', member_role_2='x',
    ))
    team = db['teams'].find_one({'team_number': '77628D'})
    assert [m['name'] for m in team['members']] == ['First', 'Last']


def test_goal_progress_is_clamped(admin, db):
    admin.post('/admin/save-team', data=_team_form(
        goal_name_0='Over', goal_progress_0='250',
        goal_name_1='Junk', goal_progress_1='abc',
    ))
    goals = db['teams'].find_one({'team_number': '77628D'})['goals']
    assert [g['progress'] for g in goals] == [100, 0]


def test_team_save_routes_uploads_through_the_validator(admin, db, uploads):
    admin.post('/admin/save-team', data=_team_form(
        member_name_0='Avery', member_role_0='Driver',
        member_photo_0=(io.BytesIO(b'img'), 'avery.png'),
        hero_image=(io.BytesIO(b'img'), 'hero.jpg'),
    ), content_type='multipart/form-data')
    team = db['teams'].find_one({'team_number': '77628D'})
    assert team['hero_image'].startswith('https://blob.example/teams/77628D/hero_')
    assert team['members'][0]['photo'].startswith('https://blob.example/teams/77628D/members/Avery_')


def test_team_save_rejects_a_disguised_upload(admin, db, uploads):
    resp = admin.post('/admin/save-team', data=_team_form(
        hero_image=(io.BytesIO(b'<script>'), 'hero.html'),
    ), content_type='multipart/form-data', follow_redirects=True)
    assert not uploads
    assert db['teams'].count_documents({}) == 0
    assert b'not an accepted file type' in resp.data


# --- Sponsor saves ------------------------------------------------------------

def test_sponsor_create_then_update(admin, db, uploads):
    admin.post('/admin/save-sponsor', data={'name': 'Acme', 'website': 'https://acme.example',
                                            'level': 'Gold'})
    sponsor = db['sponsors'].find_one({'name': 'Acme'})
    assert sponsor['level'] == 'Gold'

    admin.post('/admin/save-sponsor', data={
        'sponsor_id': str(sponsor['_id']), 'name': 'Acme', 'website': 'https://acme.example',
        'level': 'Platinum', 'logo': (io.BytesIO(b'img'), 'logo.png'),
    }, content_type='multipart/form-data')
    assert db['sponsors'].count_documents({}) == 1
    updated = db['sponsors'].find_one({'_id': sponsor['_id']})
    assert updated['level'] == 'Platinum'
    assert updated['logo'].startswith('https://blob.example/sponsors/Acme_')


# --- Dashboard markup -----------------------------------------------------------

def test_dashboard_has_no_inline_script(admin, db):
    db['teams'].insert_one({'team_number': '77628D', 'members': [], 'goals': []})
    db['users'].insert_one({'username': 'bob', 'role': 'member', 'password': b'x'})
    page = admin.get('/admin').get_data(as_text=True)
    assert not re.search(r'\son(click|change|submit|keyup|input)=', page)
    for attributes, body in re.findall(r'<script\b([^>]*)>(.*?)</script>', page, re.S):
        # JSON data islands are inert under CSP; executable inline script is not.
        assert 'src=' in attributes or 'application/json' in attributes or not body.strip()


def test_dashboard_edit_buttons_carry_their_update_urls(admin, db):
    comp = db['competitions'].insert_one({'name': 'Q', 'location': 'L',
                                          'date': app_module._utcnow()}).inserted_id
    page = admin.get('/admin').get_data(as_text=True)
    # Events are edited in place now; each row carries the id its autosave posts to.
    assert f'data-event-id="{comp}"' in page
    assert 'data-update-url="/admin/update-user/' in page


def test_dashboard_controls_are_labelled(admin, db):
    page = admin.get('/admin').get_data(as_text=True)
    assert not re.search(r'<label>', page), 'a <label> without for= remains'
    assert 'aria-live="polite"' in page


def test_admin_js_builds_rows_without_html_strings():
    import pathlib
    source = (pathlib.Path(__file__).resolve().parent.parent / 'static/js/admin.js').read_text(encoding='utf-8')
    # Only the static help copy may be assigned as HTML.
    assignments = re.findall(r'\.innerHTML\s*=\s*([^;\n]+)', source)
    assert assignments == ['html'], assignments


# --- Member photos ------------------------------------------------------------

@pytest.mark.parametrize('stored,expected', [
    ('static/assets/profile/base.png', '/static/assets/other/base.png'),  # never existed
    ('', '/static/assets/other/base.png'),
    (None, '/static/assets/other/base.png'),
    ('static/assets/profile/damon.png', '/static/assets/profile/damon.png'),
    ('https://blob.example/a.png', 'https://blob.example/a.png'),
])
def test_image_urls_fall_back_to_a_real_placeholder(client, stored, expected):
    with app_module.app.test_request_context('/'):
        assert app_module.get_image_url(stored).split('?')[0] == expected


def test_member_without_photo_gets_the_real_placeholder(admin, db):
    admin.post('/admin/save-team', data=_team_form(member_name_0='Avery', member_role_0='Driver'))
    member = db['teams'].find_one({'team_number': '77628D'})['members'][0]
    assert member['photo'] == app_module.DEFAULT_MEMBER_PHOTO
