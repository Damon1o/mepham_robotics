"""Achievements page: season chips on the competition log, per-team bars, award share buttons."""
import datetime
import re

import pytest

import api.index as app_module


@pytest.fixture
def seeded(db):
    db['teams'].insert_many([{'team_number': '77628A', 'season': '2026-27'},
                             {'team_number': '77628B', 'season': '2026-27'}])
    excellence = db['awards'].insert_one({'title': 'Excellence Award', 'count': 3, 'icon': 'exellence_award.png',
                                          'sort': 0}).inserted_id
    db['awards'].insert_many([
        {'team_number': '77628A', 'title': 'Excellence Award', 'count': 2, 'category_id': str(excellence)},
        {'team_number': '77628B', 'title': 'Excellence Award', 'count': 1, 'category_id': str(excellence)},
    ])
    now = app_module.club_now()
    db['competitions'].insert_many([
        {'name': 'Fall Qualifier', 'date': now.replace(year=now.year - 1, month=10, day=12)},
        {'name': 'Winter Classic', 'date': now.replace(year=now.year - 2, month=12, day=3)},
    ])
    return excellence


def test_season_chips_list_each_season_in_the_log(client, seeded):
    html = client.get('/achievements').get_data(as_text=True)
    chips = re.findall(r'class="ach-season-chip[^"]*" data-season="([^"]+)"', html)
    assert chips[0] == 'all' and len(chips) == 3
    for season in chips[1:]:
        assert f'class="ach-season" data-season="{season}"' in html


def test_one_season_gets_no_chips(client, seeded, db):
    db['competitions'].delete_one({'name': 'Winter Classic'})
    assert 'ach-season-filter' not in client.get('/achievements').get_data(as_text=True)


def test_team_rows_carry_a_bar_against_the_top_team(client, seeded):
    html = client.get('/achievements').get_data(as_text=True)
    bars = re.findall(r'class="ach-roll-bar ach-team-bar" value="(\d+)" max="(\d+)"', html)
    assert bars == [('2', '2'), ('1', '2')]


def test_each_award_has_a_share_link_target(client, seeded):
    html = client.get('/achievements').get_data(as_text=True)
    assert f'id="award-{seeded}"' in html
    assert f'data-share="award-{seeded}"' in html
    assert 'has won the Excellence Award 3 times.' in html
