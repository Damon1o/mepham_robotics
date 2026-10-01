"""Competition Awards designs: each team page layout comes with its own awards style."""
import os
import re

import pytest

from api import site_content


@pytest.fixture
def team(db):
    db['teams'].insert_one({'team_number': '77628L', 'season': '2025-26', 'specs': {},
                            'members': [{'member_id': 'm1', 'name': 'Alice'}]})
    db['awards'].insert_many([
        {'team_number': '77628L', 'title': 'Judges Award', 'icon': 'judges_award.png', 'count': 0, 'sort': 1},
        {'team_number': '77628L', 'title': 'Think Award', 'icon': 'design_award.png', 'count': 1, 'sort': 2},
        {'team_number': '77628L', 'title': 'Design Award', 'icon': 'design_award.png', 'count': 2, 'sort': 3},
        {'team_number': '77628L', 'title': 'Excellence Award', 'icon': 'exellence_award.png', 'count': 3,
         'sort': 4},
    ])


def page(client, db, layout):
    db['teams'].update_one({'team_number': '77628L'}, {'$set': {'layout': layout}})
    return client.get('/team/77628L').data.decode()


def boxes(body):
    """(classes, title) for each award box, in page order."""
    return re.findall(r'class="award-box ([^"]*)">.*?class="award-title">([^<]+)<', body, re.S)


def test_every_paired_style_has_a_template_and_stylesheet():
    for layout, style in site_content.LAYOUT_AWARD_STYLES.items():
        assert layout in site_content.TEAM_LAYOUTS, layout
        assert os.path.exists(f'templates/partials/awards/{style}.html'), style
        assert os.path.exists(f'static/css/pages/awards/{style}.css'), style


@pytest.mark.parametrize('layout', list(site_content.TEAM_LAYOUTS))
def test_every_layout_shows_every_award(client, db, team, layout):
    body = page(client, db, layout)
    assert 'Competition Awards' in body
    titles = [title for _, title in boxes(body)]
    assert sorted(titles) == ['Design Award', 'Excellence Award', 'Judges Award', 'Think Award']


@pytest.mark.parametrize('layout', list(site_content.TEAM_LAYOUTS))
def test_awards_not_won_yet_are_greyed_out(client, db, team, layout):
    greyed = [title for classes, title in boxes(page(client, db, layout)) if 'is-zero' in classes.split()]
    assert greyed == ['Judges Award']


def test_classic_keeps_the_tile_grid(client, db, team):
    body = page(client, db, 'classic')
    assert 'css/pages/awards/' not in body
    assert 'awards-mosaic' not in body
    assert [title for _, title in boxes(body)] == ['Judges Award', 'Think Award', 'Design Award',
                                                   'Excellence Award']


@pytest.mark.parametrize('layout', ['meet', 'tabs', 'bento'])
def test_mosaic_sizes_tiles_by_wins(client, db, team, layout):
    body = page(client, db, layout)
    assert 'css/pages/awards/mosaic.css' in body
    tiles = boxes(body)
    # Admin sort order, with awards not won yet moved to the end.
    assert [title for _, title in tiles] == ['Think Award', 'Design Award', 'Excellence Award', 'Judges Award']
    sizes = {title: classes.split() for classes, title in tiles}
    assert 'award-box--feature' in sizes['Excellence Award']
    assert 'award-box--double' in sizes['Design Award']
    assert not {'award-box--feature', 'award-box--double'} & set(sizes['Think Award'] + sizes['Judges Award'])


def test_mosaic_feature_needs_a_repeat_win(client, db, team):
    db['awards'].update_many({'count': {'$gt': 1}}, {'$set': {'count': 1}})
    body = page(client, db, 'meet')
    assert 'award-box--feature' not in body and 'award-box--double' not in body


def test_mosaic_feature_tie_goes_to_sort_order(client, db, team):
    db['awards'].update_one({'title': 'Design Award'}, {'$set': {'count': 3}})
    sizes = {title: classes.split() for classes, title in boxes(page(client, db, 'meet'))}
    assert 'award-box--feature' in sizes['Design Award']
    assert 'award-box--double' in sizes['Excellence Award']


def test_mosaic_with_no_awards(client, db, team):
    db['awards'].delete_many({})
    body = page(client, db, 'meet')
    assert 'No awards recorded for this team yet' in body


def test_groups_get_no_awards_section(client, db):
    db['teams'].insert_one({'kind': 'group', 'team_number': 'media', 'title': 'Media',
                            'members': [{'member_id': 'm1', 'name': 'Alice'}]})
    body = client.get('/team/media').data.decode()
    assert 'Competition Awards' not in body
