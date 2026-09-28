"""Team profile fields saved through the shared editor's JSON API (editors and admins)."""
import pytest

import api.index as app_module


@pytest.fixture
def admin_client(client, make_user):
    make_user(username='root', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'correct-horse'})
    return client


@pytest.fixture
def team(db):
    return str(db['teams'].insert_one({'team_number': '77628A', 'nickname': 'Hydra', 'members': [],
                                       'specs': {}}).inserted_id)


def field(client, team_id, name, value):
    return client.post(f'/api/team/{team_id}/field', json={'field': name, 'value': value})


def test_profile_fields_persist(admin_client, db, team):
    for name, value in [('season', '2025-26'), ('division', 'High School'), ('since', '2019'),
                        ('worlds_appearances', '2'), ('robotevents_number', '77628a')]:
        assert field(admin_client, team, name, value).status_code == 200
    doc = db['teams'].find_one({'team_number': '77628A'})
    assert doc['season'] == '2025-26'
    assert doc['division'] == 'High School'
    assert doc['since'] == 2019
    assert doc['worlds_appearances'] == 2
    assert doc['robotevents_number'] == '77628A'


def test_blank_optional_fields_are_removed(admin_client, db, team):
    field(admin_client, team, 'season', '2025-26')
    field(admin_client, team, 'season', '')
    assert 'season' not in db['teams'].find_one({'team_number': '77628A'})


def test_non_numeric_year_is_rejected(admin_client, db, team):
    assert field(admin_client, team, 'since', 'not-a-year').status_code == 400
    assert 'since' not in db['teams'].find_one({'team_number': '77628A'})


@pytest.mark.parametrize('name,value', [('team_number', 'A/B C'), ('season', 'banana'),
                                        ('robotevents_number', 'bad number!')])
def test_malformed_numbers_and_seasons_are_rejected(admin_client, db, team, name, value):
    resp = field(admin_client, team, name, value)
    assert resp.status_code == 400 and resp.is_json


def test_renaming_onto_an_existing_profile_is_a_clean_409(admin_client, db, team):
    """This used to raise DuplicateKeyError (an HTML 500) after the awards had already moved."""
    app_module._ensure_core_indexes(db)
    other = str(db['teams'].insert_one({'team_number': '77628B', 'members': []}).inserted_id)
    db['awards'].insert_one({'team_number': '77628B', 'title': 'Design Award', 'count': 3})
    resp = field(admin_client, other, 'team_number', '77628A')
    assert resp.status_code == 409 and resp.is_json
    assert db['awards'].find_one({'team_number': '77628B'})['count'] == 3


def test_rename_carries_the_award_counts(admin_client, db, team):
    db['awards'].insert_one({'team_number': '77628A', 'title': 'Design Award', 'count': 2})
    assert field(admin_client, team, 'team_number', '77628c').status_code == 200
    assert db['awards'].find_one({'team_number': '77628C'})['count'] == 2
    assert not db['awards'].find_one({'team_number': '77628A'})


def test_journey_milestones_persist(admin_client, db, team):
    admin_client.post(f'/api/team/{team}/list/journey',
                      json={'items': [{'date': '2019', 'title': 'Team founded', 'description': 'First season.'}]})
    journey = db['teams'].find_one({'team_number': '77628A'})['journey']
    assert journey == [{'date': '2019', 'title': 'Team founded', 'description': 'First season.'}]


def test_unknown_list_kind_is_json(admin_client, team):
    resp = admin_client.post(f'/api/team/{team}/list/nope', json={'items': []})
    assert resp.status_code == 404 and resp.is_json


def test_hidden_teams_leave_the_menu(admin_client, db, team, client):
    field(admin_client, team, 'hidden', True)
    assert db['teams'].find_one({'team_number': '77628A'})['hidden'] is True
    assert '/team/77628A' not in admin_client.get('/about').get_data(as_text=True)
    field(admin_client, team, 'hidden', False)
    assert 'hidden' not in db['teams'].find_one({'team_number': '77628A'})
