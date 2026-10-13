"""Member pages (/people/<id>): who can see and edit them, what they show, and the links to them."""
import io

import pytest

import api.index as app_module
from api import people, robotevents


@pytest.fixture
def ada(make_user):
    return make_user(username='ada', password='ada-password', email='ada@example.com')


@pytest.fixture
def bo(make_user):
    return make_user(username='bo', password='bo-password', email='bo@example.com')


def sign_in(client, username):
    client.post('/login', data={'username': username, 'password': f'{username}-password'})


def card(user, **extra):
    return dict({'member_id': 'c-' + str(user['_id'])[-6:], 'name': user['username'].title(),
                 'user_id': str(user['_id'])}, **extra)


def page(user):
    return f"/people/{user['_id']}"


def save(client, user, section, data):
    return client.post(f"/api/people/{user['_id']}/profile", json={'section': section, 'data': data})


@pytest.fixture
def uploads(monkeypatch):
    keys, deleted = [], []
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda file, key: keys.append(key) or f'https://blob.example/{key}?v={len(keys)}')
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    return keys, deleted


# --- Who can see it -------------------------------------------------------------------

def test_signed_out_visitors_cannot_see_a_members_only_page(client, ada):
    resp = client.get(page(ada))
    html = resp.get_data(as_text=True)
    assert resp.status_code == 403
    assert 'This page is for club members' in html and 'id="pf_name"' not in html


def test_a_public_page_opens_for_anyone_and_stays_out_of_search(client, db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'full_name': 'Ada Lovelace',
                                                          'profile': {'visibility': 'public'}}})
    resp = client.get(page(ada))
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200 and 'Ada Lovelace' in html
    assert '<meta name="robots" content="noindex">' in html
    assert 'data-edit-toggle' not in html


def test_any_signed_in_member_can_see_a_members_only_page_but_not_edit_it(client, ada, bo):
    sign_in(client, 'bo')
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'id="pf_name"' in html and 'data-edit-toggle' not in html and 'College-app kit' not in html


def test_unknown_and_pending_accounts_have_no_page(client, db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'status': 'pending'}})
    assert client.get(page(ada)).status_code == 404
    assert client.get('/people/not-an-id').status_code == 404
    assert client.get('/people/0123456789abcdef01234567').status_code == 404


def test_people_me_goes_to_your_own_page(client, ada):
    sign_in(client, 'ada')
    resp = client.get('/people/me')
    assert resp.status_code == 302 and resp.headers['Location'].endswith(page(ada))


# --- Editing ----------------------------------------------------------------------------

def test_the_owner_sees_the_editors_and_the_college_app_kit(client, ada):
    sign_in(client, 'ada')
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'data-edit-toggle' in html and 'data-editor="honors"' in html and 'College-app kit' in html
    assert 'data-editor-seed' in html


def test_saving_about_me_shows_on_the_page(client, db, ada):
    sign_in(client, 'ada')
    resp = save(client, ada, 'about', {'headline': '  Lead   programmer ', 'bio': 'Hi.\n\n\n\nI build robots.',
                                       'grad_year': '2028', 'skills': ['CAD', 'cad', ' Driving '],
                                       'visibility': 'public'})
    assert resp.status_code == 200
    stored = db['users'].find_one({'_id': ada['_id']})['profile']
    assert stored['headline'] == 'Lead programmer' and stored['bio'] == 'Hi.\n\nI build robots.'
    assert stored['skills'] == ['CAD', 'Driving'] and stored['grad_year'] == 2028
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'Class of 2028' in html and '<p>I build robots.</p>' in html and 'Public: anyone with the link' in html


@pytest.mark.parametrize('section, data, message', [
    ('about', {'headline': 'x' * 81}, 'Headline must be 80'),
    ('about', {'grad_year': '28'}, 'four-digit year'),
    ('about', {'visibility': 'everyone'}, 'who can see'),
    ('links', {'links': [{'url': 'javascript:alert(1)'}]}, 'https://'),
    ('honors', {'honors': [{'title': 'A', 'pinned': True}] * 4}, 'Pin up to 3'),
    ('honors', {'honors': [{'title': 'A', 'hours': 'lots'}]}, 'Hours must be a number'),
    ('activity', {'activity': 'x' * 151}, '150 characters'),
    ('password', {}, 'does not exist'),
])
def test_bad_input_is_refused_with_a_reason(client, ada, section, data, message):
    sign_in(client, 'ada')
    resp = save(client, ada, section, data)
    assert resp.status_code == 400 and message in resp.get_json()['error']


def test_someone_else_cannot_edit_your_page_but_an_admin_can(client, db, make_user, ada, bo):
    sign_in(client, 'bo')
    assert save(client, ada, 'about', {'headline': 'Hacked'}).status_code == 403
    make_user(username='root', password='root-password', email='r@example.com', role='admin')
    client.post('/logout')
    sign_in(client, 'root')
    assert save(client, ada, 'about', {'headline': 'Tidied by an admin'}).status_code == 200
    assert db['users'].find_one({'_id': ada['_id']})['profile']['headline'] == 'Tidied by an admin'


def test_signed_out_saves_are_refused(client, ada):
    assert save(client, ada, 'about', {'headline': 'x'}).status_code == 401


def test_honors_are_grouped_pinned_and_linked(client, db, ada):
    sign_in(client, 'ada')
    save(client, ada, 'honors', {'honors': [
        {'kind': 'award', 'title': 'Excellence Award', 'event': 'LI Regional', 'when': 'Mar 2026',
         'link': 'https://www.robotevents.com/x', 'pinned': True},
        {'kind': 'outreach', 'title': 'Library robot demos', 'hours': '12.5'},
        {'kind': 'made-up', 'title': 'Mystery'},
        {'title': '   '},
    ]})
    honors = db['users'].find_one({'_id': ada['_id']})['profile']['honors']
    assert [h['kind'] for h in honors] == ['award', 'outreach', 'other']
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'pf-plaque' in html and 'LI Regional · Mar 2026' in html
    assert 'Outreach &amp; service' in html and '12.5 hours' in html and '<dt>Hours</dt>' in html
    assert 'href="https://www.robotevents.com/x"' in html and 'rel="noopener nofollow ugc"' in html


def test_links_get_an_icon_and_a_label(client, ada):
    sign_in(client, 'ada')
    save(client, ada, 'links', {'links': [{'url': 'https://github.com/ada'}, {'label': 'Site', 'url': 'https://ada.dev'}]})
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'data-lucide="github"' in html and '<span>github.com</span>' in html and '<span>Site</span>' in html


# --- Photos ------------------------------------------------------------------------------

def test_photos_upload_caption_reorder_and_delete(client, db, ada, uploads):
    keys, deleted = uploads
    sign_in(client, 'ada')
    url = f"/api/people/{ada['_id']}/photos"
    first = client.post(url, data={'photo': (io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'a.png'), 'caption': 'Worlds'},
                        content_type='multipart/form-data').get_json()['photo']
    second = client.post(url, data={'photo': (io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'b.png')},
                         content_type='multipart/form-data').get_json()['photo']
    assert keys[0].startswith('users/ada/gallery_')

    resp = save(client, ada, 'photos', {'photos': [{'path': second['path'], 'caption': 'Pit'},
                                                   {'path': 'https://evil.example/x.png', 'caption': 'no'}]})
    assert resp.status_code == 200
    stored = db['users'].find_one({'_id': ada['_id']})['profile']['photos']
    assert [p['caption'] for p in stored] == ['Pit', 'Worlds']  # unknown path dropped, missing one kept

    assert client.delete(url, json={'path': first['path']}).status_code == 200
    assert deleted == [first['path']]
    assert client.delete(url, json={'path': 'https://evil.example/x.png'}).status_code == 404


def test_photo_upload_refuses_other_files(client, ada, uploads):
    sign_in(client, 'ada')
    resp = client.post(f"/api/people/{ada['_id']}/photos", data={'photo': (io.BytesIO(b'MZ'), 'evil.exe')},
                       content_type='multipart/form-data')
    assert resp.status_code == 400 and 'not an accepted file type' in resp.get_json()['error']


def test_a_page_photo_is_never_deleted_while_still_in_use(db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'profile.photos': [{'path': 'https://b/x.png'}]}})
    assert app_module._blob_still_used('https://b/x.png')


# --- Records: team history, moves, awards --------------------------------------------------

def test_career_timeline_shows_a_team_switch_and_trophy_cases(client, db, ada):
    db['teams'].insert_many([
        {'team_number': '77628A', 'season': '2024-25', 'members': [card(ada, role='Builder')]},
        {'team_number': '77628B', 'season': '2025-26', 'members': [card(ada, role='Captain', roles=['Driver'])]},
        {'kind': 'group', 'team_number': 'media', 'title': 'Media', 'season': '2025-26',
         'members': [card(ada, role='Photographer')]},
    ])
    db['awards'].insert_many([{'team_number': '77628B', 'title': 'Excellence Award', 'count': 2},
                              {'team_number': '77628A', 'title': 'Think Award', 'count': 0}])
    sign_in(client, 'ada')
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'Transferred <b>77628A</b>' in html and '<b>77628B</b></p>' in html
    assert 'Captain / Driver' in html and 'Since 2024' in html
    assert 'Team trophy cases' in html and '×2' in html and 'Think Award' not in html


def test_activity_draft_fits_the_common_app_limits():
    history = {'seasons': [{'season': '2025-26', 'teams': [{'label': '77628B', 'group': False,
                                                           'roles': ['Captain', 'Lead Programmer', 'Driver']}]},
                           {'season': '2024-25', 'teams': [{'label': '77628A', 'group': False, 'roles': ['Builder']}]}],
               'team_count': 2, 'went_total': 0}
    profile = people.profile_view({'honors': [
        {'kind': 'award', 'title': 'Excellence Award at the Long Island Regional Championship ' * 2, 'pinned': True},
        {'kind': 'outreach', 'title': 'Demos', 'hours': 20}]})
    draft = people.activity_draft('Mepham Robotics', history, profile)
    assert draft['position'] == 'Captain & Lead Programmer, Team 77628B'
    assert len(draft['position']) <= 50 and len(draft['activity']) <= 150
    assert draft['activity'].startswith('Competed in VEX Robotics for 2 seasons; 20 outreach hours; won Excellence')


def test_events_only_show_to_signed_in_viewers(client, db, ada):
    now = app_module.club_now()
    db['competitions'].insert_one({'name': 'Kickoff Scrimmage', 'date': now - app_module.datetime.timedelta(days=20),
                                   'rsvps': {str(ada['_id']): {'status': 'going'}}})
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'profile': {'visibility': 'public'}}})
    assert 'Kickoff Scrimmage' not in client.get(page(ada)).get_data(as_text=True)
    sign_in(client, 'ada')
    assert 'Kickoff Scrimmage' in client.get(page(ada)).get_data(as_text=True)


# --- Verified RobotEvents awards ------------------------------------------------------------

def test_verified_awards_need_a_token(client, db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'profile': {'visibility': 'public'}}})
    assert client.get(f"/api/people/{ada['_id']}/verified").status_code == 204


def test_verified_awards_are_listed_per_season(client, db, ada, monkeypatch):
    db['teams'].insert_many([
        {'team_number': '77628B', 'season': '2025-26', 'robotevents_number': '77628X', 'members': [card(ada)]},
        {'kind': 'group', 'team_number': 'media', 'season': '2025-26', 'members': [card(ada)]},
    ])
    monkeypatch.setattr(robotevents, 'get_token', lambda: 'token')
    monkeypatch.setattr(robotevents, 'season_id', lambda db, label: 190)
    asked = []
    monkeypatch.setattr(robotevents, 'team_summary', lambda db, number, season_id=None: asked.append(number) or {
        'awards': [{'title': 'Think Award (VRC/VEXU/VAIRC)', 'event': 'LI Regional'}]})
    assert client.get(f"/api/people/{ada['_id']}/verified").status_code == 404  # members only, signed out
    sign_in(client, 'ada')
    data = client.get(f"/api/people/{ada['_id']}/verified").get_json()
    assert asked == ['77628X']
    assert data['seasons'] == [{'season': '2025-26', 'team': '77628B', 'url': robotevents.team_url('77628X'),
                                'awards': [{'title': 'Think Award (VRC/VEXU/VAIRC)', 'event': 'LI Regional'}]}]
    assert 'data-verified-url' in client.get(page(ada)).get_data(as_text=True)


# --- Links into the page ---------------------------------------------------------------------

def test_team_roster_names_link_to_member_pages_for_signed_in_viewers(client, db, ada, bo):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2026-27',
                            'members': [card(ada, role='Builder'), {'member_id': 'x', 'name': 'No Account'}]})
    href = f'href="{page(ada)}"'
    assert href not in client.get('/team/77628A').get_data(as_text=True)
    sign_in(client, 'bo')
    html = client.get('/team/77628A').get_data(as_text=True)
    assert href in html and 'is-person' in html


def test_public_pages_are_linked_for_everyone(client, db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'profile': {'visibility': 'public'}}})
    db['teams'].insert_one({'team_number': '77628A', 'members': [card(ada)]})
    assert f'href="{page(ada)}"' in client.get('/team/77628A').get_data(as_text=True)


def allow_public_pages(db, allowed):
    db['site_metadata'].update_one({'_id': app_module.SITE_CONTENT_ID},
                                   {'$set': {'values.people.allow_public': allowed}}, upsert=True)


def test_admins_can_turn_public_pages_off_and_back_on(client, db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'profile': {'visibility': 'public'}}})
    db['teams'].insert_one({'team_number': '77628A', 'members': [card(ada)]})
    href = f'href="{page(ada)}"'

    allow_public_pages(db, False)
    assert client.get(page(ada)).status_code == 403
    assert client.get(f"/api/people/{ada['_id']}/verified").status_code == 404
    assert href not in client.get('/team/77628A').get_data(as_text=True)

    allow_public_pages(db, True)
    assert client.get(page(ada)).status_code == 200
    assert href in client.get('/team/77628A').get_data(as_text=True)


def test_the_badge_flips_who_can_see_the_page_without_touching_about_me(client, db, ada):
    sign_in(client, 'ada')
    assert save(client, ada, 'about', {'headline': 'Builder', 'visibility': 'members'}).status_code == 200
    assert 'data-visibility-toggle' in client.get(page(ada)).get_data(as_text=True)
    assert save(client, ada, 'visibility', {'visibility': 'public'}).status_code == 200
    profile = db['users'].find_one({'_id': ada['_id']})['profile']
    assert profile['visibility'] == 'public' and profile['headline'] == 'Builder'
    assert save(client, ada, 'visibility', {'visibility': 'everyone'}).status_code == 400


def test_the_badge_cannot_make_a_page_public_while_admins_have_it_off(client, db, ada):
    allow_public_pages(db, False)
    sign_in(client, 'ada')
    assert 'data-visibility-toggle' not in client.get(page(ada)).get_data(as_text=True)
    resp = save(client, ada, 'visibility', {'visibility': 'public'})
    assert resp.status_code == 400 and 'turned off' in resp.get_json()['error']
    assert save(client, ada, 'visibility', {'visibility': 'members'}).status_code == 200


def test_with_public_pages_off_the_owner_sees_members_only_and_a_locked_choice(client, db, ada):
    db['users'].update_one({'_id': ada['_id']}, {'$set': {'profile': {'visibility': 'public'}}})
    allow_public_pages(db, False)
    sign_in(client, 'ada')
    html = client.get(page(ada)).get_data(as_text=True)
    assert 'pf-visibility--members' in html and 'Turned off by the club' in html
    assert 'value="public" disabled' in html and 'Shareable by link' not in html
    assert db['users'].find_one({'_id': ada['_id']})['profile']['visibility'] == 'public'


@pytest.mark.parametrize('layout', ['mission', 'yearbook', 'tracker', 'huddle', 'chapters'])
def test_every_group_layout_links_its_people(client, db, ada, bo, layout):
    db['teams'].insert_one({'kind': 'group', 'team_number': 'media', 'title': 'Media', 'layout': layout,
                            'members': [card(ada, role='Lead'), card(bo)],
                            'goals': [{'name': 'Reels', 'progress': 40, 'owners': [card(ada)['member_id']]}]})
    sign_in(client, 'bo')
    html = client.get('/team/media').get_data(as_text=True)
    assert f'href="{page(ada)}"' in html and f'href="{page(bo)}"' in html


@pytest.mark.parametrize('layout', ['classic', 'compact', 'meet', 'tabs'])
def test_team_layouts_link_their_people(client, db, ada, bo, layout):
    db['teams'].insert_one({'team_number': '77628A', 'layout': layout, 'members': [card(ada)]})
    sign_in(client, 'bo')
    assert f'href="{page(ada)}"' in client.get('/team/77628A').get_data(as_text=True)


def test_the_side_menu_account_chip_opens_your_page(client, ada):
    sign_in(client, 'ada')
    html = client.get('/about').get_data(as_text=True)
    assert f'<a class="nav-user" href="{page(ada)}"' in html
