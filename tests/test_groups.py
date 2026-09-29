"""Groups: non-competing crews (Media, Fundraising, ...) that live alongside robot teams.

A person is on at most one robot team but can be in any number of groups.
"""
import pytest
from bson import ObjectId

import api.index as app_module


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def club(db, make_user):
    """Robot teams D and P, a Media group, and Casey (with a login) on team D."""
    casey = make_user(username='casey', email='casey@example.com')
    uid = str(casey['_id'])
    d = db['teams'].insert_one({'team_number': '77628D', 'season': '2026-27', 'members': [
        {'member_id': 'md', 'name': 'Casey', 'role': 'Driver', 'user_id': uid, 'photo': ''},
        {'member_id': 'mx', 'name': 'Avery', 'role': 'Builder', 'user_id': '', 'photo': ''},
    ]}).inserted_id
    p = db['teams'].insert_one({'team_number': '77628P', 'season': '2026-27', 'members': []}).inserted_id
    media = db['teams'].insert_one({'kind': 'group', 'team_number': 'media', 'title': 'Media',
                                    'season': '2026-27', 'members': []}).inserted_id
    return {'d': str(d), 'p': str(p), 'media': str(media), 'casey': casey, 'uid': uid}


def members(db, team_id):
    return db['teams'].find_one({'_id': ObjectId(team_id)})['members']


def move(client, **body):
    return client.post('/admin/api/roster/move', json=body)


# --- Creating groups ----------------------------------------------------------------

def test_create_group_from_a_title(admin, db):
    resp = admin.post('/admin/quick-group', data={'title': 'Media & Outreach'})
    assert resp.status_code == 302 and '/manage/team/' in resp.headers['Location']
    group = db['teams'].find_one({'kind': 'group'})
    assert group['title'] == 'Media & Outreach'
    assert group['team_number'] == 'media-outreach'
    assert db['awards'].count_documents({'team_number': 'media-outreach'}) == 0


def test_group_names_must_be_unique(admin, db, club):
    admin.post('/admin/quick-group', data={'title': 'media'})
    assert db['teams'].count_documents({'kind': 'group'}) == 1


def test_group_needs_a_usable_name(admin, db):
    admin.post('/admin/quick-group', data={'title': '!!!'})
    assert db['teams'].count_documents({}) == 0


def test_new_award_categories_skip_groups(admin, db, club):
    resp = admin.post('/admin/api/award-categories', json={'title': 'Think Award', 'icon': app_module.AWARD_ICONS[0]})
    assert resp.status_code == 200
    assert db['awards'].count_documents({'team_number': 'media'}) == 0
    assert db['awards'].count_documents({'team_number': '77628D'}) == 1


# --- Public site ----------------------------------------------------------------------

def test_nav_lists_groups_after_teams(client, db, club):
    page = client.get('/').get_data(as_text=True)
    menu = page[page.index('id="teamDropdown"'):]
    menu = menu[:menu.index('</div>')]
    assert menu.index('77628P') < menu.index('Groups') < menu.index('>Media</a>')


def test_group_page_has_no_robot_sections(client, db, club):
    page = client.get('/team/media').get_data(as_text=True)
    assert '<h1>Media</h1>' in page
    assert 'Meet the Group' in page
    assert 'robot-showcase' not in page and 'Engineering Notebook' not in page
    assert 'Team media' not in page


def test_group_has_no_live_robotevents_data(client, db, club):
    assert client.get('/api/team/media/live').status_code == 204


def test_stats_count_teams_not_groups_and_people_once(db, club):
    media = ObjectId(club['media'])
    db['teams'].update_one({'_id': media}, {'$push': {'members': {
        'member_id': 'mm', 'name': 'Casey', 'user_id': club['uid']}}})
    stats = app_module.compute_auto_stats()
    assert stats['teams_count'] == 2
    assert stats['members_count'] == 2  # Casey (on D and in Media) and Avery


# --- Roster board -----------------------------------------------------------------------

def test_board_shows_group_column(admin, db, club):
    page = admin.get('/admin').get_data(as_text=True)
    assert 'data-kind="group"' in page
    assert 'Also add to group' in page


def test_drop_on_group_adds_and_keeps_the_team(admin, db, club):
    resp = move(admin, member_id='md', to_team_id=club['media'])
    body = resp.get_json()
    assert resp.status_code == 200 and body['mode'] == 'add'
    assert [m['member_id'] for m in members(db, club['d'])] == ['md', 'mx']
    added = members(db, club['media'])
    assert len(added) == 1 and added[0]['user_id'] == club['uid'] and added[0]['member_id'] != 'md'
    assert body['member']['member_id'] == added[0]['member_id']


def test_cannot_join_the_same_group_twice(admin, db, club):
    move(admin, member_id='md', to_team_id=club['media'])
    resp = move(admin, member_id='md', to_team_id=club['media'])
    assert resp.status_code == 409
    assert len(members(db, club['media'])) == 1


def test_moving_teams_keeps_groups(admin, db, club):
    move(admin, member_id='md', to_team_id=club['media'])
    resp = move(admin, member_id='md', to_team_id=club['p'])
    assert resp.get_json()['mode'] == 'move'
    assert [m['member_id'] for m in members(db, club['p'])] == ['md']
    assert [m['user_id'] for m in members(db, club['media'])] == [club['uid']]


def test_group_card_onto_a_team_moves_their_team_card(admin, db, club):
    """Dropping Casey's Media card on P moves Casey from D to P; the Media card stays."""
    group_card = move(admin, member_id='md', to_team_id=club['media']).get_json()['member']['member_id']
    resp = move(admin, member_id=group_card, to_team_id=club['p'])
    body = resp.get_json()
    assert body['mode'] == 'move' and body['member']['member_id'] == 'md'
    assert body['from_team_id'] == club['d']
    assert [m['member_id'] for m in members(db, club['p'])] == ['md']
    assert [m['member_id'] for m in members(db, club['media'])] == [group_card]


def test_group_card_onto_own_team_is_refused(admin, db, club):
    group_card = move(admin, member_id='md', to_team_id=club['media']).get_json()['member']['member_id']
    assert move(admin, member_id=group_card, to_team_id=club['d']).status_code == 409


def test_group_only_person_can_join_a_team(admin, db, club, make_user):
    sam = make_user(username='sam', email='sam@example.com')
    resp = move(admin, user_id=str(sam['_id']), to_team_id=club['media'])
    assert resp.get_json()['mode'] == 'add'
    card = members(db, club['media'])[0]['member_id']
    resp = move(admin, member_id=card, to_team_id=club['p'])
    assert resp.get_json()['mode'] == 'add'
    assert [m['user_id'] for m in members(db, club['p'])] == [str(sam['_id'])]
    assert [m['member_id'] for m in members(db, club['media'])] == [card]


def test_account_can_be_only_in_a_group(admin, db, club, make_user):
    sam = make_user(username='sam', email='sam@example.com')
    move(admin, user_id=str(sam['_id']), to_team_id=club['media'])
    page = admin.get('/admin').get_data(as_text=True)
    unassigned = page[page.index('roster-col--unassigned'):]
    assert '@sam' not in unassigned[:unassigned.index('</section>')]


def test_leaving_a_group_keeps_the_team(admin, db, club):
    card = move(admin, member_id='md', to_team_id=club['media']).get_json()['member']['member_id']
    resp = move(admin, member_id=card, to_team_id=None)
    assert resp.status_code == 200 and resp.get_json()['unassigned'] is False
    assert members(db, club['media']) == []
    assert [m['member_id'] for m in members(db, club['d'])] == ['md', 'mx']
    assert 'roster_card' not in db['users'].find_one({'_id': club['casey']['_id']})


def test_leaving_the_only_group_unassigns(admin, db, club, make_user):
    sam = make_user(username='sam', email='sam@example.com')
    card = move(admin, user_id=str(sam['_id']), to_team_id=club['media']).get_json()['member']['member_id']
    assert move(admin, member_id=card, to_team_id=None).get_json()['unassigned'] is True


def test_no_login_card_copies_to_group_and_undo_removes_it(admin, db, club):
    card = move(admin, member_id='mx', to_team_id=club['media']).get_json()['member']['member_id']
    assert [m['name'] for m in members(db, club['media'])] == ['Avery']
    assert move(admin, member_id=card, to_team_id=None).status_code == 400
    assert move(admin, member_id=card, to_team_id=None, remove=True).status_code == 200
    assert members(db, club['media']) == []
    assert [m['member_id'] for m in members(db, club['d'])] == ['md', 'mx']


def test_linking_a_login_in_a_group_keeps_the_team(admin, db, club, make_user):
    """Linking removes the account from other robot teams only, never from its team for a group card."""
    db['teams'].update_one({'_id': ObjectId(club['media'])}, {'$push': {'members': {
        'member_id': 'mg', 'name': 'Casey', 'user_id': ''}}})
    resp = admin.post('/admin/api/roster/link', json={'member_id': 'mg', 'user_id': club['uid']})
    assert resp.status_code == 200
    assert [m['user_id'] for m in members(db, club['d']) if m['member_id'] == 'md'] == [club['uid']]


# --- Editors -----------------------------------------------------------------------------

def test_group_editor_hides_robot_fields(admin, db, club):
    page = admin.get(f"/manage/team/{club['media']}").get_data(as_text=True)
    assert 'data-autosave="title"' in page
    assert 'data-autosave="nickname"' not in page and 'specs.drive_train' not in page
    assert 'data-autosave="division"' not in page


def test_group_fields(admin, db, club):
    api = f"/api/team/{club['media']}/field"
    assert admin.post(api, json={'field': 'title', 'value': 'Media Crew'}).status_code == 200
    assert admin.post(api, json={'field': 'nickname', 'value': 'x'}).status_code == 400
    assert admin.post(api, json={'field': 'team_number', 'value': 'Media Crew'}).status_code == 400
    assert admin.post(api, json={'field': 'team_number', 'value': 'media-crew'}).get_json()['value'] == 'media-crew'
    assert admin.post(f"/api/team/{club['d']}/field", json={'field': 'title', 'value': 'x'}).status_code == 400
    group = db['teams'].find_one({'_id': ObjectId(club['media'])})
    assert (group['title'], group['team_number']) == ('Media Crew', 'media-crew')


def test_member_on_team_and_group_picks_which_page(client, db, club):
    db['teams'].update_one({'_id': ObjectId(club['media'])}, {'$push': {'members': {
        'member_id': 'mm', 'name': 'Casey', 'user_id': club['uid']}}})
    db['users'].update_one({'_id': club['casey']['_id']},
                           {'$set': {'password': app_module.bcrypt.hashpw(b'casey-password',
                                                                          app_module.bcrypt.gensalt(4))}})
    client.post('/login', data={'username': 'casey', 'password': 'casey-password'})
    page = client.get('/my-team').get_data(as_text=True)
    assert page.count('team-picker-card') == 2
    assert 'Your team' in page and 'Your group' in page
    assert client.get(f"/manage/team/{club['media']}").status_code == 200
