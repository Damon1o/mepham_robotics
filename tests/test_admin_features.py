"""Dashboard features added in the admin audit: live club numbers, award categories,
seasons, login linking, messages, newsletter, activity, and the editor tools."""
import datetime
import io

import pytest
from bson import ObjectId

import api.index as app_module


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def uploads(monkeypatch):
    keys, deleted = [], []
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda file, key: keys.append(key) or f'https://blob.example/{key}')
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    return keys, deleted


# --- Club numbers: Auto / Typed -------------------------------------------------------

def test_auto_stats_count_current_rosters_and_club_awards(db):
    db['teams'].insert_many([
        {'team_number': '1A', 'season': '2025-26', 'members': [{}, {}, {}]},
        {'team_number': '1A', 'season': '2026-27', 'members': [{}]},       # newest season wins
        {'team_number': '1B', 'members': [{}, {}]},
        {'team_number': '1C', 'hidden': True, 'members': [{}]},            # retired: not counted
    ])
    db['awards'].insert_many([{'title': 'A', 'count': 2}, {'title': 'B', 'count': 3},
                              {'title': 'A', 'team_number': '1A', 'count': 9}])
    with app_module.app.test_request_context('/'):
        assert app_module.compute_auto_stats() == {'teams_count': 2, 'members_count': 3, 'awards_count': 5}


def test_auto_mode_drives_the_homepage(admin, db):
    db['site_metadata'].insert_one({'_id': 'global_stats', 'teams_count': 9, 'members_count': 9,
                                    'awards_count': 9, 'hours_built': 100})
    db['teams'].insert_one({'team_number': '1A', 'members': [{}, {}]})
    resp = admin.post('/admin/api/stats', json={'field': 'teams_count', 'mode': 'auto'})
    assert resp.get_json() == {'ok': True, 'mode': 'auto', 'value': 1}
    page = admin.get('/').get_data(as_text=True)
    assert '<div class="stat-number">1</div>' in page          # teams: live
    assert '<div class="stat-number">9</div>' in page          # members: still typed


def test_hours_cannot_be_automatic(admin):
    assert admin.post('/admin/api/stats', json={'field': 'hours_built', 'mode': 'auto'}).status_code == 400


def test_live_numbers_refresh_after_roster_changes(admin, db, make_user):
    team = db['teams'].insert_one({'team_number': '1A', 'members': []}).inserted_id
    admin.post(f'/api/team/{team}/member', json={'name': 'Avery'})
    assert db['site_metadata'].find_one({'_id': 'global_stats'})['auto']['members_count'] == 1


# --- Award categories ------------------------------------------------------------------

def test_new_category_reaches_every_team(admin, db):
    db['teams'].insert_many([{'team_number': '1A'}, {'team_number': '1B'}])
    resp = admin.post('/admin/api/award-categories', json={'title': 'Think Award', 'icon': 'innovate_award.png'})
    assert resp.status_code == 200
    cid = resp.get_json()['id']
    assert db['awards'].count_documents({'category_id': cid}) == 2
    assert db['awards'].find_one({'_id': ObjectId(cid)})['count'] == 0


@pytest.mark.parametrize('body', [{'title': '', 'icon': 'innovate_award.png'},
                                  {'title': 'X', 'icon': '../../secret.png'},
                                  {'title': 'X', 'icon': 'innovate_award.png', 'border': 'rainbow'}])
def test_category_fields_are_validated(admin, db, body):
    assert admin.post('/admin/api/award-categories', json=body).status_code == 400
    assert db['awards'].count_documents({}) == 0


def test_duplicate_category_names_are_refused(admin, db):
    db['awards'].insert_one({'title': 'Design Award', 'icon': 'design_award.png', 'count': 1})
    resp = admin.post('/admin/api/award-categories', json={'title': 'design award', 'icon': 'design_award.png'})
    assert resp.status_code == 409


def test_renaming_a_category_renames_team_copies(admin, db):
    cid = db['awards'].insert_one({'title': 'Old', 'icon': 'design_award.png', 'count': 1}).inserted_id
    db['awards'].insert_one({'title': 'Old', 'team_number': '1A', 'count': 4})   # legacy: no category_id
    assert admin.post(f'/admin/api/award-categories/{cid}', json={'title': 'New', 'border': 'gold'}).status_code == 200
    team_row = db['awards'].find_one({'team_number': '1A'})
    assert team_row['title'] == 'New' and team_row['border'] == 'gold' and team_row['count'] == 4


def test_deleting_a_category_removes_team_counts(admin, db):
    cid = db['awards'].insert_one({'title': 'Gone', 'icon': 'design_award.png', 'count': 1}).inserted_id
    db['awards'].insert_one({'title': 'Gone', 'team_number': '1A', 'count': 4, 'category_id': str(cid)})
    assert admin.delete(f'/admin/api/award-categories/{cid}').status_code == 200
    assert db['awards'].count_documents({}) == 0


def test_categories_reorder_and_pages_follow(admin, db):
    a = db['awards'].insert_one({'title': 'Alpha', 'icon': 'design_award.png', 'count': 1}).inserted_id
    db['awards'].insert_one({'title': 'Beta', 'icon': 'judges_award.png', 'count': 1})
    admin.post(f'/admin/api/award-categories/{a}/move', json={'step': 1})
    page = admin.get('/achievements').get_data(as_text=True)
    assert page.index('Beta') < page.index('Alpha')


def test_team_page_survives_an_award_without_an_icon(client, db):
    db['teams'].insert_one({'team_number': '1A', 'members': []})
    db['awards'].insert_one({'title': 'Legacy', 'team_number': '1A', 'count': 1})
    assert client.get('/team/1A').status_code == 200


# --- Events ----------------------------------------------------------------------------

def test_prune_removes_only_past_events(admin, db):
    now = app_module.club_now()
    db['competitions'].insert_many([{'name': 'Old', 'date': now - datetime.timedelta(days=3)},
                                    {'name': 'Soon', 'date': now + datetime.timedelta(days=3)}])
    assert admin.post('/admin/api/events/prune').get_json()['deleted'] == 1
    assert [c['name'] for c in db['competitions'].find()] == ['Soon']


def test_dashboard_separates_past_events(admin, db):
    now = app_module.club_now()
    db['competitions'].insert_many([{'name': 'Kickoff', 'date': now - datetime.timedelta(days=3)},
                                    {'name': 'Regionals', 'date': now + datetime.timedelta(days=3)}])
    page = admin.get('/admin').get_data(as_text=True)
    assert 'Past events' in page
    assert page.index('Regionals') < page.index('Kickoff')


def test_event_links_are_saved_and_shown(admin, db):
    eid = db['competitions'].insert_one({'name': 'Q', 'date': app_module.club_now() + datetime.timedelta(days=5)}).inserted_id
    assert admin.post(f'/admin/api/events/{eid}', json={'field': 'link', 'value': 'https://robotevents.com/x'}).status_code == 200
    assert admin.post(f'/admin/api/events/{eid}', json={'field': 'link', 'value': 'javascript:x'}).status_code == 400
    assert 'href="https://robotevents.com/x"' in admin.get('/').get_data(as_text=True)


# --- Seasons -----------------------------------------------------------------------------

def test_new_season_copies_the_team_and_moves_logins(admin, db, make_user):
    kid = make_user(username='kid', password='kid-password', email='kid@example.com')
    old = db['teams'].insert_one({'team_number': '1A', 'season': '2025-26', 'nickname': 'Hydra',
                                  'goals': [{'name': 'Win', 'progress': 50}],
                                  'members': [{'member_id': 'm1', 'name': 'Kid', 'user_id': str(kid['_id'])}]}).inserted_id
    resp = admin.post(f'/admin/api/teams/{old}/new-season', json={'season': '2026-27'})
    assert resp.status_code == 200
    new = db['teams'].find_one({'season': '2026-27'})
    assert new['nickname'] == 'Hydra' and new['goals'] == []
    assert new['members'][0]['user_id'] == str(kid['_id']) and new['members'][0]['member_id'] != 'm1'
    assert db['teams'].find_one({'_id': old})['members'][0]['user_id'] == ''
    assert admin.post(f'/admin/api/teams/{old}/new-season', json={'season': '2026-27'}).status_code == 409


def test_nav_lists_a_multi_season_team_once(client, db):
    db['teams'].insert_many([{'team_number': '1A', 'season': '2025-26'}, {'team_number': '1A', 'season': '2026-27'}])
    page = client.get('/about').get_data(as_text=True)
    nav = page.split('id="teamDropdown"')[1].split('</div>')[0]
    assert nav.count('/team/1A') == 1


# --- People: claiming and linking cards, pending accounts -----------------------------------

def test_approval_can_claim_an_existing_card(admin, db):
    team = db['teams'].insert_one({'team_number': '1A', 'members': [
        {'member_id': 'm1', 'name': 'Avery Real', 'user_id': ''}]}).inserted_id
    uid = db['users'].insert_one({'username': 'avery', 'email': 'a@example.com', 'password': b'x',
                                  'role': 'member', 'status': 'pending'}).inserted_id
    resp = admin.post(f'/admin/api/users/{uid}/approve', json={'role': 'member', 'member_id': 'm1'})
    assert resp.status_code == 200
    members = db['teams'].find_one({'_id': team})['members']
    assert len(members) == 1 and members[0]['user_id'] == str(uid) and members[0]['name'] == 'Avery Real'


def test_signup_name_becomes_the_roster_name(admin, db, client):
    team = db['teams'].insert_one({'team_number': '1A', 'members': []}).inserted_id
    uid = db['users'].insert_one({'username': 'jdoe', 'full_name': 'Jane Doe', 'email': 'j@example.com',
                                  'password': b'x', 'role': 'member', 'status': 'pending'}).inserted_id
    admin.post(f'/admin/api/users/{uid}/approve', json={'role': 'member', 'team_id': str(team)})
    assert db['teams'].find_one({'_id': team})['members'][0]['name'] == 'Jane Doe'


def test_roster_link_attaches_a_login(admin, db, make_user):
    user = make_user(username='casey', password='casey-password', email='c@example.com')
    team = db['teams'].insert_one({'team_number': '1A', 'members': [{'member_id': 'm1', 'name': 'Casey', 'user_id': ''}]}).inserted_id
    assert admin.post('/admin/api/roster/link', json={'member_id': 'm1', 'user_id': str(user['_id'])}).status_code == 200
    assert db['teams'].find_one({'_id': team})['members'][0]['user_id'] == str(user['_id'])
    # A card that already has a login is not silently re-linked.
    other = make_user(username='other', password='other-password', email='o@example.com')
    assert admin.post('/admin/api/roster/link', json={'member_id': 'm1', 'user_id': str(other['_id'])}).status_code == 409


def test_pending_accounts_cannot_go_on_rosters_or_change_role(admin, db):
    team = db['teams'].insert_one({'team_number': '1A', 'members': []}).inserted_id
    uid = db['users'].insert_one({'username': 'wait', 'email': 'w@example.com', 'password': b'x',
                                  'role': 'member', 'status': 'pending'}).inserted_id
    assert admin.post('/admin/api/roster/move', json={'user_id': str(uid), 'to_team_id': str(team)}).status_code == 409
    assert admin.post(f'/admin/api/users/{uid}/role', json={'role': 'editor'}).status_code == 409


def test_a_pending_admin_does_not_count_as_another_admin(db, make_user):
    only = make_user(username='only', password='only-password', role='admin')
    db['users'].insert_one({'username': 'p', 'role': 'admin', 'status': 'pending', 'password': b'x'})
    with app_module.app.test_request_context('/'):
        assert app_module._other_admin_exists(only['_id']) is False


# --- Messages and newsletter -------------------------------------------------------------

def _message(db, status='new'):
    return db['contact_messages'].insert_one({'name': 'A', 'email': 'a@example.com', 'message': 'hi',
                                              'status': status, 'created_at': app_module._utcnow()}).inserted_id


def test_message_actions_over_json(admin, db):
    mid = _message(db)
    assert admin.post(f'/admin/api/messages/{mid}', json={'action': 'read'}).get_json()['status'] == 'read'
    assert admin.post(f'/admin/api/messages/{mid}', json={'action': 'new'}).get_json()['status'] == 'new'
    assert admin.post(f'/admin/api/messages/{mid}', json={'action': 'delete'}).get_json()['status'] == 'deleted'
    assert db['contact_messages'].count_documents({}) == 0


def test_bulk_archive(admin, db):
    ids = [str(_message(db)) for _ in range(3)]
    resp = admin.post('/admin/api/messages/bulk', json={'action': 'archive', 'ids': ids + ['junk']})
    assert resp.get_json()['count'] == 3
    assert db['contact_messages'].count_documents({'status': 'archived'}) == 3


def test_message_counts_are_not_capped_by_the_list(admin, db, monkeypatch):
    monkeypatch.setattr(app_module, 'MESSAGES_SHOWN', 2)
    for _ in range(5):
        _message(db)
    page = admin.get('/admin').get_data(as_text=True)
    assert '5 new' in page and 'Showing the newest 2 of 5' in page


def test_subscriber_can_be_removed(admin, db):
    sid = db['newsletter_subscribers'].insert_one({'email': 'fan@example.com', 'unsubscribe_token': 't'}).inserted_id
    assert admin.delete(f'/admin/api/subscribers/{sid}').status_code == 200
    assert db['newsletter_subscribers'].count_documents({}) == 0


def test_export_carries_unsubscribe_links_and_is_logged(admin, db):
    db['newsletter_subscribers'].insert_one({'email': 'fan@example.com', 'unsubscribe_token': 'tok123',
                                             'created_at': app_module._utcnow()})
    csv_text = admin.get('/admin/subscribers.csv').get_data(as_text=True)
    assert 'unsubscribe_url' in csv_text and '/unsubscribe/tok123' in csv_text
    assert db['activities'].find_one({'type': 'subscribers_export'})


# --- Activity log ---------------------------------------------------------------------------

def test_activity_api_filters_and_pages(admin, db, monkeypatch):
    monkeypatch.setattr(app_module, 'ACTIVITY_PAGE', 2)
    now = app_module._utcnow()
    for i, kind in enumerate(['user_approve', 'competition_add', 'user_update', 'roster_move']):
        db['activities'].insert_one({'type': kind, 'description': kind, 'user': 'root',
                                     'timestamp': now - datetime.timedelta(minutes=i)})
    first = admin.get('/admin/api/activity?group=people').get_json()
    assert [a['type'] for a in first['items']] == ['user_approve', 'user_update'] and first['more']
    rest = admin.get(f"/admin/api/activity?group=people&before={first['items'][-1]['timestamp']}").get_json()
    assert [a['type'] for a in rest['items']] == ['roster_move'] and not rest['more']


def test_activity_shows_who_did_it(admin, db):
    admin.post('/admin/api/stats', json={'field': 'hours_built', 'value': 5})
    assert 'root · ' in admin.get('/admin').get_data(as_text=True)


# --- Team editor tools -------------------------------------------------------------------

def test_images_can_be_removed(admin, db, uploads):
    _, deleted = uploads
    team = db['teams'].insert_one({'team_number': '1A', 'hero_image': 'https://blob.example/h.png',
                                   'members': [{'member_id': 'm1', 'name': 'A', 'photo': 'https://blob.example/a.png'}]}).inserted_id
    assert admin.delete(f'/api/team/{team}/image', json={'kind': 'hero_image'}).status_code == 200
    assert admin.delete(f'/api/team/{team}/image', json={'kind': 'member_photo', 'member_id': 'm1'}).status_code == 200
    doc = db['teams'].find_one({'_id': team})
    assert 'hero_image' not in doc and doc['members'][0]['photo'] == ''
    assert sorted(deleted) == ['https://blob.example/a.png', 'https://blob.example/h.png']


def test_editor_uploads_reject_disguised_files(admin, db, uploads):
    keys, _ = uploads
    team = db['teams'].insert_one({'team_number': '1A', 'members': []}).inserted_id
    resp = admin.post(f'/api/team/{team}/image', data={'hero_image': (io.BytesIO(b'<script>'), 'hero.html')},
                      content_type='multipart/form-data')
    assert resp.status_code == 400 and not keys


def test_removing_a_linked_member_keeps_their_card_on_the_account(admin, db, make_user):
    kid = make_user(username='kid', password='kid-password', email='kid@example.com')
    team = db['teams'].insert_one({'team_number': '1A', 'members': [
        {'member_id': 'm1', 'name': 'Kid Real', 'role': 'Driver', 'user_id': str(kid['_id'])}]}).inserted_id
    admin.delete(f'/api/team/{team}/member/m1')
    assert db['users'].find_one({'_id': kid['_id']})['roster_card']['name'] == 'Kid Real'


def test_editors_get_a_team_list(client, db, make_user):
    db['teams'].insert_many([{'team_number': '1A', 'members': []}, {'team_number': '1B', 'members': []}])
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    page = client.get('/my-team').get_data(as_text=True)
    assert 'Team pages' in page and '/manage/team/' in page and page.count('team-picker-number') == 2


def test_quick_team_starts_in_the_current_season(admin, db):
    admin.post('/admin/quick-team', data={'team_number': '1z'})
    assert db['teams'].find_one({'team_number': '1Z'})['season'] == app_module.current_season()


# --- Overview ------------------------------------------------------------------------------

def test_overview_lists_what_needs_attention(admin, db):
    db['users'].insert_one({'username': 'wait', 'email': 'w@example.com', 'password': b'x', 'role': 'member',
                            'status': 'pending'})
    _message(db)
    page = admin.get('/admin').get_data(as_text=True)
    assert '1 sign-up waiting for approval' in page and '1 unread message' in page
    assert 'No upcoming events' in page


@pytest.mark.parametrize('path', ['/admin/api/award-categories', '/admin/api/events/prune', '/admin/api/roster/link',
                                  '/admin/api/messages/bulk', f'/admin/api/teams/{"a" * 24}/new-season'])
def test_new_admin_endpoints_need_admin(client, make_user, path):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    assert client.post(path, json={}).status_code == 403
