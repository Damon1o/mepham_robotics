"""Drop zones: files dragged (or pasted) onto a card, row or list upload where it says.

The dragging itself runs in the browser (static/js/controls.js); these check the
one new endpoint and that each page marks its drop targets for the right people.
"""
import io
import re

import pytest
from bson import ObjectId

import api.index as app_module


@pytest.fixture
def uploads(monkeypatch):
    keys, deleted = [], []
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda file, key: keys.append(key) or f'https://blob.example/{key}')
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    return keys, deleted


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def _logo(name='acme.png'):
    return {'logo': (io.BytesIO(b'\x89PNG\r\n\x1a\n'), name)}


def _tag(page, marker):
    """The opening tag of the element carrying `marker`."""
    at = page.index(marker)
    return page[page.rindex('<', 0, at):page.index('>', at) + 1]


# --- Sponsor logo, dropped on the sponsor's row --------------------------------------------

def test_a_dropped_logo_replaces_the_old_one(admin, db, uploads):
    keys, deleted = uploads
    sponsor = db['sponsors'].insert_one({'name': 'Acme', 'level': 'Gold',
                                         'logo': 'https://blob.example/old.png'}).inserted_id
    resp = admin.post(f'/admin/api/sponsor/{sponsor}/logo', data=_logo(), content_type='multipart/form-data')
    assert resp.status_code == 200
    url = resp.get_json()['url']
    assert url == f'https://blob.example/{keys[0]}' and keys[0].startswith('sponsors/')
    assert db['sponsors'].find_one({'_id': sponsor})['logo'] == url
    assert deleted == ['https://blob.example/old.png']


def test_a_dropped_logo_must_be_an_image(admin, db, uploads):
    keys, _ = uploads
    sponsor = db['sponsors'].insert_one({'name': 'Acme', 'level': 'Gold'}).inserted_id
    resp = admin.post(f'/admin/api/sponsor/{sponsor}/logo', data=_logo('logo.html'), content_type='multipart/form-data')
    assert resp.status_code == 400 and 'error' in resp.get_json()
    assert not keys and 'logo' not in db['sponsors'].find_one({'_id': sponsor})


def test_a_logo_for_a_missing_sponsor_is_refused(admin, uploads):
    keys, _ = uploads
    resp = admin.post(f'/admin/api/sponsor/{ObjectId()}/logo', data=_logo(), content_type='multipart/form-data')
    assert resp.status_code == 404 and not keys
    assert admin.post('/admin/api/sponsor/not-an-id/logo', data=_logo(),
                      content_type='multipart/form-data').status_code == 404


def test_only_admins_can_drop_a_logo(client, db, make_user, uploads):
    keys, _ = uploads
    sponsor = db['sponsors'].insert_one({'name': 'Acme', 'level': 'Gold'}).inserted_id
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    resp = client.post(f'/admin/api/sponsor/{sponsor}/logo', data=_logo(), content_type='multipart/form-data')
    assert resp.status_code in (401, 403) and not keys


# --- Which pages mark what -------------------------------------------------------------------

def test_the_dashboard_marks_team_tiles_and_sponsors(admin, db):
    team = db['teams'].insert_one({'team_number': '1A', 'members': [],
                                   'hero_image': 'https://blob.example/hero.png'}).inserted_id
    sponsor = db['sponsors'].insert_one({'name': 'Acme', 'level': 'Gold'}).inserted_id
    page = admin.get('/admin').get_data(as_text=True)

    tile = _tag(page, f'data-team-id="{team}" data-team-name')
    assert 'data-drop="event"' in tile and 'image/png' in tile
    assert 'class="team-tile-photo" src="https://blob.example/hero.png"' in page

    row = _tag(page, f'data-sponsor-id="{sponsor}"')
    assert 'data-drop="event"' in row and 'Acme’s logo' in row
    assert 'data-drop="event"' in _tag(page, 'id="sponsor_list_card"')
    assert 'data-drop-input="f-logo"' in _tag(page, 'id="sponsor_form_card"')


def test_the_people_board_shows_member_photos(admin, db):
    db['teams'].insert_one({'team_number': '1A', 'members': [
        {'member_id': 'm1', 'name': 'Avery Stone', 'photo': 'https://blob.example/avery.png'},
        {'member_id': 'm2', 'name': 'Blake Hill'}]})
    page = admin.get('/admin').get_data(as_text=True)
    assert '<img src="https://blob.example/avery.png" alt="" loading="lazy">' in page
    assert re.search(r'class="roster-avatar" aria-hidden="true">BH</span>', page)


@pytest.fixture
def roster(db, make_user):
    alice = make_user(username='alice', password='alice-password', email='alice@example.com')
    team_id = db['teams'].insert_one({'team_number': '77628D', 'specs': {}, 'goals': [], 'members': [
        {'member_id': 'ma', 'name': 'Alice Park', 'role': 'Driver', 'user_id': str(alice['_id'])},
        {'member_id': 'mb', 'name': 'Bob Reyes', 'role': 'Builder'},
    ]}).inserted_id
    return f'/manage/team/{team_id}'


def test_admins_can_drop_on_the_whole_roster(admin, roster):
    page = admin.get(roster).get_data(as_text=True)
    grid = _tag(page, 'id="memberGrid"')
    assert 'data-drop="event"' in grid and 'data-drop-multiple' in grid and '.csv' in grid
    assert 'Set as Bob Reyes’s photo' in _tag(page, 'data-member-id="mb"')
    assert 'data-drop-label="Use as the banner photo"' in page
    assert 'data-drop-label="Use as the CAD model"' in page


def test_members_can_only_drop_on_their_own_row(client, roster):
    client.post('/login', data={'username': 'alice', 'password': 'alice-password'})
    page = client.get(roster).get_data(as_text=True)
    assert 'data-drop' not in _tag(page, 'id="memberGrid"')
    assert 'data-drop' in _tag(page, 'data-member-id="ma"')
    assert 'data-drop' not in _tag(page, 'data-member-id="mb"')
    assert 'Use as the CAD model' not in page


def test_the_site_editor_marks_photo_rows_and_the_gallery(admin):
    page = admin.get('/admin/site').get_data(as_text=True)
    gallery = _tag(page, 'data-key="gallery.photos"')
    assert 'data-drop="event"' in gallery and 'data-drop-multiple' in gallery
    hero = _tag(page, 'data-key="home.hero_image"')
    assert 'data-drop ' in hero and 'Use this photo' in hero
    assert 'data-drop' not in _tag(page, 'data-key="general.club_name"')
