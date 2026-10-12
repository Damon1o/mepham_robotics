"""About page: each sub-team card lists the current members on that sub-team."""
import re

import pytest

import api.index as app_module


@pytest.fixture
def rosters(db):
    db['teams'].insert_many([
        {'team_number': '77628A', 'season': '2026-27', 'members': [
            {'member_id': 'a1', 'name': 'Bo Diaz', 'role': 'Builder', 'subteam': 'Mechanical'},
            {'member_id': 'a2', 'name': 'Ada Lovelace', 'role': 'Captain', 'subteam': 'mechanical '},
            {'member_id': 'a3', 'name': 'Cy Young', 'role': 'Programmer', 'subteam': 'Programming'},
            {'member_id': 'a4', 'name': 'No Team Yet', 'role': 'Member'},
        ]},
        # Last season's roster: not current, so not listed.
        {'team_number': '77628A', 'season': '2025-26', 'members': [
            {'member_id': 'o1', 'name': 'Old Timer', 'subteam': 'Mechanical'}]},
        # Hidden teams stay off the About page too.
        {'team_number': '77628Z', 'season': '2026-27', 'hidden': True, 'members': [
            {'member_id': 'z1', 'name': 'Secret Member', 'subteam': 'Mechanical'}]},
    ])


def test_people_are_grouped_by_subteam_leads_first(client, rosters):
    with app_module.app.test_request_context():
        people = app_module.subteam_people()
    assert [p['full_name'] for p in people['mechanical']] == ['Ada Lovelace', 'Bo Diaz']
    assert [p['full_name'] for p in people['programming']] == ['Cy Young']
    assert set(people) == {'mechanical', 'programming'}


def test_cards_list_their_members(client, rosters):
    html = client.get('/about').get_data(as_text=True)
    mech = html.split('<h3>Mechanical</h3>', 1)[1].split('about-subteam-card', 1)[0]
    assert '2 members' in mech
    assert 'Ada Lovelace' in mech and 'Bo Diaz' in mech
    assert '77628A · Captain' in mech
    assert 'href="/team/77628A"' in mech
    assert 'Old Timer' not in html and 'Secret Member' not in html


def test_cards_without_members_show_no_list(client, rosters):
    html = client.get('/about').get_data(as_text=True)
    electrical = html.split('<h3>Electrical</h3>', 1)[1].split('about-subteam-card', 1)[0]
    assert 'about-subteam-people' not in electrical
    assert len(re.findall(r'class="about-subteam-people"', html)) == 2
