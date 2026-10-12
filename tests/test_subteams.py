"""Sub-teams: one roster per team, and one list of sub-teams (the About page cards) for the whole site."""
import pytest
from bson import ObjectId

from api import site_content


def default_cards():
    return [dict(c) for c in site_content.field_for('about.subteams')[1].default]


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def team(db):
    return db['teams'].insert_one({
        'team_number': '77628A', 'season': '2025-26', 'specs': {}, 'goals': [],
        'members': [
            {'member_id': 'm1', 'name': 'Bo Diaz', 'role': 'Builder', 'subteam': 'Mechanical'},
            {'member_id': 'm2', 'name': 'Ada Lovelace', 'role': 'Captain', 'subteam': 'Programming'},
            {'member_id': 'm3', 'name': 'Cy Young', 'role': 'Scout'},
        ]}).inserted_id


def members(db, team_id):
    return {m['member_id']: m for m in db['teams'].find_one({'_id': team_id})['members']}


def test_roster_is_one_grid_with_subteam_on_each_card(client, team):
    body = client.get('/team/77628A').get_data(as_text=True)
    roster = body.split('id="team"', 1)[1].split('</section>', 1)[0]
    assert roster.count('class="roster-grid"') == 1
    assert 'roster-group' not in roster
    assert '<p class="roster-subteam">Mechanical</p>' in roster
    assert '<p class="roster-subteam">Programming</p>' in roster
    # Leadership still leads.
    assert roster.index('Ada Lovelace') < roster.index('Bo Diaz') < roster.index('Cy Young')


def test_editor_offers_the_about_page_cards(admin, team):
    cards = default_cards() + [{'icon': 'star', 'title': 'Strategy', 'text': ''}]
    assert admin.post('/admin/api/site', json={'key': 'about.subteams', 'value': cards}).status_code == 200
    body = admin.get(f'/manage/team/{team}').get_data(as_text=True)
    assert '<option value="Strategy"' in body


def test_member_can_join_a_new_card_in_its_spelling(admin, db, team):
    cards = default_cards() + [{'icon': 'star', 'title': 'Strategy', 'text': ''}]
    admin.post('/admin/api/site', json={'key': 'about.subteams', 'value': cards})
    resp = admin.post(f'/api/team/{team}/member/m3', json={'field': 'subteam', 'value': 'strategy'})
    assert resp.status_code == 200
    assert members(db, team)['m3']['subteam'] == 'Strategy'


def test_unlisted_subteam_is_refused(admin, db, team):
    resp = admin.post(f'/api/team/{team}/member/m3', json={'field': 'subteam', 'value': 'Snacks'})
    assert resp.status_code == 400
    assert 'subteam' not in members(db, team)['m3']


def test_renaming_a_card_moves_its_members(admin, db, team):
    cards = default_cards()
    cards[0]['title'] = 'Build'  # was Mechanical
    admin.post('/admin/api/site', json={'key': 'about.subteams', 'value': cards})
    now = members(db, team)
    assert now['m1']['subteam'] == 'Build'
    assert now['m2']['subteam'] == 'Programming'


def test_reordering_cards_moves_nobody(admin, db, team):
    cards = default_cards()
    cards[0], cards[2] = cards[2], cards[0]
    admin.post('/admin/api/site', json={'key': 'about.subteams', 'value': cards})
    now = members(db, team)
    assert now['m1']['subteam'] == 'Mechanical'
    assert now['m2']['subteam'] == 'Programming'


def test_removed_card_stays_on_its_members_until_changed(admin, db, team):
    cards = [c for c in default_cards() if c['title'] != 'Mechanical']
    admin.post('/admin/api/site', json={'key': 'about.subteams', 'value': cards})
    assert members(db, team)['m1']['subteam'] == 'Mechanical'
    body = admin.get(f'/manage/team/{team}').get_data(as_text=True)
    assert 'Mechanical (no longer listed)' in body
    assert admin.post(f'/api/team/{team}/member/m1',
                      json={'field': 'subteam', 'value': 'Mechanical'}).status_code == 200
