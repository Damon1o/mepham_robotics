"""Profile customisation and keeping a person's name and photo the same everywhere.

The account holds the name and photo; every roster card linked to it (each team,
group and season) and the card parked on the account carry a copy.
"""

import io

import pytest

import api.index as app_module


@pytest.fixture
def uploads(monkeypatch):
    keys, deleted = [], []
    # Keys are stamped to the second, so number the URLs to keep two quick uploads apart.
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda file, key: keys.append(key) or f'https://blob.example/{key}?v={len(keys)}')
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    return keys, deleted


@pytest.fixture
def alice(client, db, make_user):
    user = make_user()
    client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    return user


@pytest.fixture
def rosters(db, alice):
    """Alice on a robot team this season, a group, and last season's team; plus Bob unlinked."""
    uid = str(alice['_id'])
    ids = {}
    for key, doc in {
        'team': {'team_number': '1599A', 'season': '2026-2027'},
        'group': {'team_number': 'media', 'kind': 'group', 'title': 'Media', 'season': '2026-2027'},
        'old': {'team_number': '1599A', 'season': '2025-2026'},
    }.items():
        doc['members'] = [{'member_id': f'{key}-a', 'name': 'Alice', 'role': 'Builder', 'user_id': uid, 'photo': ''},
                          {'member_id': f'{key}-b', 'name': 'Bob', 'role': 'Coder', 'user_id': '', 'photo': ''}]
        ids[key] = db['teams'].insert_one(doc).inserted_id
    return ids


def _cards(db, ids, who='a'):
    return [next(m for m in db['teams'].find_one({'_id': i})['members'] if m['member_id'].endswith(f'-{who}'))
            for i in ids.values()]


def _png(name='me.png'):
    return {'photo': (io.BytesIO(b'\x89PNG\r\n\x1a\n'), name)}


# --- Photo from the account ------------------------------------------------------------------

def test_account_photo_reaches_every_linked_card(client, db, alice, rosters, uploads):
    resp = client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    assert resp.status_code == 302
    url = db['users'].find_one({'_id': alice['_id']})['photo']
    assert url.startswith('https://blob.example/users/alice/')
    assert all(c['photo'] == url for c in _cards(db, rosters))
    assert all(c['photo'] == '' for c in _cards(db, rosters, 'b'))
    # Roles and other card fields are untouched.
    assert all(c['role'] == 'Builder' for c in _cards(db, rosters))


def test_replacing_the_photo_deletes_the_old_file(client, db, alice, rosters, uploads):
    _, deleted = uploads
    client.post('/account/photo', data=_png('one.png'), content_type='multipart/form-data')
    first = db['users'].find_one({'_id': alice['_id']})['photo']
    client.post('/account/photo', data=_png('two.png'), content_type='multipart/form-data')
    assert deleted == [first]


def test_removing_the_photo_clears_it_everywhere(client, db, alice, rosters, uploads):
    _, deleted = uploads
    client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    url = db['users'].find_one({'_id': alice['_id']})['photo']
    client.post('/account/photo/remove')
    assert 'photo' not in db['users'].find_one({'_id': alice['_id']})
    assert all(c['photo'] == '' for c in _cards(db, rosters))
    assert deleted == [url]


def test_a_photo_another_page_still_shows_is_kept(client, db, alice, rosters, uploads):
    _, deleted = uploads
    client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    url = db['users'].find_one({'_id': alice['_id']})['photo']
    db['teams'].update_one({'_id': rosters['team']}, {'$set': {'hero_image': url}})
    client.post('/account/photo/remove')
    assert deleted == []


def test_photo_upload_rejects_other_file_types(client, db, alice, uploads):
    resp = client.post('/account/photo', data={'photo': (io.BytesIO(b'MZ'), 'evil.exe')},
                       content_type='multipart/form-data', follow_redirects=True)
    assert 'not an accepted file type' in resp.get_data(as_text=True)
    assert 'photo' not in db['users'].find_one({'_id': alice['_id']})


def test_the_parked_card_follows_too(client, db, alice, uploads):
    db['users'].update_one({'_id': alice['_id']}, {'$set': {'roster_card': {
        'member_id': 'p1', 'name': 'Alice', 'role': 'Lead', 'photo': ''}}})
    client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    client.post('/account/profile', data={'full_name': 'Alice Liddell', 'email': 'alice@example.com'})
    parked = db['users'].find_one({'_id': alice['_id']})['roster_card']
    assert parked['photo'].startswith('https://') and parked['name'] == 'Alice Liddell' and parked['role'] == 'Lead'


# --- Name from the account ---------------------------------------------------------------------

def test_account_name_reaches_every_linked_card(client, db, alice, rosters):
    client.post('/account/profile', data={'full_name': 'Alice Liddell', 'email': 'alice@example.com'})
    assert all(c['name'] == 'Alice Liddell' for c in _cards(db, rosters))
    assert all(c['name'] == 'Bob' for c in _cards(db, rosters, 'b'))


def test_clearing_the_name_shows_the_username_on_cards(client, db, alice, rosters):
    client.post('/account/profile', data={'full_name': 'Alice Liddell', 'email': 'alice@example.com'})
    client.post('/account/profile', data={'full_name': '', 'email': 'alice@example.com'})
    assert all(c['name'] == 'alice' for c in _cards(db, rosters))


def test_admin_rename_reaches_the_cards(client, db, make_user, alice, rosters):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    admin = app_module.app.test_client()
    admin.post('/login', data={'username': 'root', 'password': 'root-password'})
    admin.post(f"/admin/update-user/{alice['_id']}", data={
        'username': 'alice', 'email': 'alice@example.com', 'role': 'member', 'full_name': 'Alice Pleasance'})
    assert all(c['name'] == 'Alice Pleasance' for c in _cards(db, rosters))


# --- Edits made from a team page flow back -------------------------------------------------------------

def test_own_card_photo_from_the_team_editor_becomes_the_profile_photo(client, db, alice, rosters, uploads):
    resp = client.post(f"/api/team/{rosters['team']}/image",
                       data={'member_id': 'team-a', 'member_photo': (io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'me.png')},
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    url = db['users'].find_one({'_id': alice['_id']})['photo']
    assert all(c['photo'] == url for c in _cards(db, rosters))


def test_removing_the_card_photo_removes_the_profile_photo(client, db, alice, rosters, uploads):
    client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    resp = client.delete(f"/api/team/{rosters['group']}/image", json={'kind': 'member_photo', 'member_id': 'group-a'})
    assert resp.status_code == 200
    assert 'photo' not in db['users'].find_one({'_id': alice['_id']})
    assert all(c['photo'] == '' for c in _cards(db, rosters))


def test_renaming_own_card_renames_the_account(client, db, alice, rosters):
    resp = client.post(f"/api/team/{rosters['team']}/member/team-a", json={'field': 'name', 'value': 'Ally L'})
    assert resp.status_code == 200
    assert db['users'].find_one({'_id': alice['_id']})['full_name'] == 'Ally L'
    assert all(c['name'] == 'Ally L' for c in _cards(db, rosters))


def test_unlinked_cards_still_edit_alone(client, db, make_user, rosters, uploads):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    admin = app_module.app.test_client()
    admin.post('/login', data={'username': 'root', 'password': 'root-password'})
    admin.post(f"/api/team/{rosters['team']}/member/team-b", json={'field': 'name', 'value': 'Robert'})
    names = [c['name'] for c in _cards(db, rosters, 'b')]
    assert names == ['Robert', 'Bob', 'Bob']


# --- Joining a roster ------------------------------------------------------------------------------

def test_a_new_card_starts_with_the_account_photo_and_name(db, make_user, client):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    team = db['teams'].insert_one({'team_number': '1A', 'members': []}).inserted_id
    uid = db['users'].insert_one({'username': 'jdoe', 'full_name': 'Jane Doe', 'email': 'j@example.com',
                                  'photo': 'https://blob.example/users/jdoe/photo.png', 'password': b'x',
                                  'role': 'member', 'status': 'pending'}).inserted_id
    client.post(f'/admin/api/users/{uid}/approve', json={'role': 'member', 'team_id': str(team)})
    card = db['teams'].find_one({'_id': team})['members'][0]
    assert card['name'] == 'Jane Doe' and card['photo'] == 'https://blob.example/users/jdoe/photo.png'


def test_linking_a_photographed_card_gives_the_account_that_photo(db, make_user, client):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    casey = make_user(username='casey', password='casey-password', email='c@example.com')
    db['teams'].insert_one({'team_number': '1A', 'members': [
        {'member_id': 'm1', 'name': 'Casey Jones', 'user_id': '', 'photo': 'https://blob.example/c.png'}]})
    assert client.post('/admin/api/roster/link',
                       json={'member_id': 'm1', 'user_id': str(casey['_id'])}).status_code == 200
    stored = db['users'].find_one({'_id': casey['_id']})
    assert stored['photo'] == 'https://blob.example/c.png' and stored['full_name'] == 'Casey Jones'


# --- Catching up data saved before syncing existed -------------------------------------------------------

def test_older_data_is_brought_into_step_once(client, db, make_user, uploads):
    _, deleted = uploads
    named = make_user(username='alice')
    db['users'].update_one({'_id': named['_id']}, {'$set': {'full_name': 'Alice Liddell'}})
    bare = make_user(username='bob', password='bob-password', email='bob@example.com')
    db['teams'].insert_many([
        {'team_number': '1A', 'season': '2025-2026', 'members': [
            {'member_id': 'a1', 'name': 'Al', 'user_id': str(named['_id']), 'photo': 'https://blob.example/old-a.png'},
            {'member_id': 'b1', 'name': 'Bobby', 'user_id': str(bare['_id']), 'photo': 'https://blob.example/old-b.png'}]},
        {'team_number': '1A', 'season': '2026-2027', 'members': [
            {'member_id': 'a2', 'name': 'Alice', 'user_id': str(named['_id']), 'photo': ''},
            {'member_id': 'b2', 'name': 'Robert B', 'user_id': str(bare['_id']), 'photo': 'https://blob.example/new-b.png'}]},
    ])
    client.get('/team/1A')
    cards = {m['member_id']: m for t in db['teams'].find() for m in t['members']}
    # The account's name wins; with no account photo, the newest card's photo is adopted.
    assert cards['a1']['name'] == cards['a2']['name'] == 'Alice Liddell'
    assert cards['a1']['photo'] == cards['a2']['photo'] == ''
    # No name or photo on the account: both come from the newest season's card.
    assert cards['b1']['name'] == cards['b2']['name'] == 'Robert B'
    assert cards['b1']['photo'] == cards['b2']['photo'] == 'https://blob.example/new-b.png'
    assert db['users'].find_one({'_id': bare['_id']})['full_name'] == 'Robert B'
    # Catching up never deletes files.
    assert deleted == []
    # And it only runs once.
    db['teams'].update_one({'members.member_id': 'a2'}, {'$set': {'members.$.name': 'Changed'}})
    app_module._profiles_reconciled = False
    client.get('/team/1A')
    assert next(m for t in db['teams'].find() for m in t['members'] if m['member_id'] == 'a2')['name'] == 'Changed'


# --- Showing it ------------------------------------------------------------------------------------------

def test_side_menu_shows_name_photo_and_colour(client, db, alice, uploads):
    client.post('/account/profile', data={'full_name': 'Alice Liddell', 'email': 'alice@example.com',
                                          'avatar_tone': 'teal'})
    page = client.get('/about').get_data(as_text=True)
    assert 'nav-avatar avatar-tone--teal' in page and '<strong>Alice Liddell</strong>' in page
    client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    page = client.get('/about').get_data(as_text=True)
    assert 'has-photo' in page and 'https://blob.example/users/alice/' in page


def test_admin_people_list_shows_photos(client, db, make_user, alice, uploads):
    client.post('/account/photo', data=_png(), content_type='multipart/form-data')
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    admin = app_module.app.test_client()
    admin.post('/login', data={'username': 'root', 'password': 'root-password'})
    assert 'https://blob.example/users/alice/' in admin.get('/admin').get_data(as_text=True)


def test_avatar_colour_must_be_listed(client, db, alice):
    resp = client.post('/account/profile', data={'email': 'alice@example.com', 'avatar_tone': 'url(evil)'})
    assert resp.status_code == 400
    assert 'avatar_tone' not in db['users'].find_one({'_id': alice['_id']})


# --- Start page --------------------------------------------------------------------------------------------

def test_sign_in_lands_on_the_chosen_start_page(client, db, alice):
    assert client.post('/account/preferences', data={'start_page': 'events_page'}).status_code == 302
    client.post('/logout')
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse', 'next': '/'})
    assert resp.location.endswith('/events')


def test_a_page_that_asked_for_sign_in_still_wins(client, db, alice):
    client.post('/account/preferences', data={'start_page': 'events_page'})
    client.post('/logout')
    resp = client.post('/login', data={'username': 'alice', 'password': 'correct-horse', 'next': '/account'})
    assert resp.location.endswith('/account')


def test_start_page_must_be_listed(client, db, alice):
    client.post('/account/preferences', data={'start_page': 'admin_dashboard'})
    assert 'start_page' not in db['users'].find_one({'_id': alice['_id']})
