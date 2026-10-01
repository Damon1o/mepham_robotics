"""Competition Awards designs: each team page layout comes with its own awards style."""
import os
import re

import pytest

import api.index as app_module

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
    return re.findall(r'class="(?:award-box|plaque-line|trophy) ([^"]*)">.*?class="(?:award-title|plaque-title|trophy-title)">([^<]+)<',
                      body, re.S)


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


# --- Honor Plaque -------------------------------------------------------------

@pytest.mark.parametrize('number, numeral', [(1, 'I'), (3, 'III'), (4, 'IV'), (9, 'IX'), (14, 'XIV'), (19, 'XIX'),
                                             (20, 'XX'), (21, '21'), (0, '0'), (None, '0')])
def test_roman(number, numeral):
    assert app_module.roman(number) == numeral


@pytest.mark.parametrize('layout', ['dossier', 'compact'])
def test_plaque_engraves_counts(client, db, team, layout):
    body = page(client, db, layout)
    assert 'css/pages/awards/plaque.css' in body and 'family=Cinzel' in body
    assert 'awards-grid' not in body
    lines = boxes(body)
    assert [title for _, title in lines] == ['Think Award', 'Design Award', 'Excellence Award', 'Judges Award']
    counts = re.findall(r'class="plaque-count" aria-label="([^"]+)">([^<]+)<', body)
    assert counts == [('won 1 time', 'I'), ('won 2 times', 'II'), ('won 3 times', 'III'),
                      ('won 0 times', '&mdash;')]
    assert 'Team 77628L &middot; 2025-26' in body
    assert '6 awards won' in body


def test_plaque_with_no_awards(client, db, team):
    db['awards'].delete_many({})
    body = page(client, db, 'dossier')
    assert 'No awards recorded for this team yet' in body and 'class="plaque"' not in body


def test_plaque_shimmer_only_on_won_awards(client, db, team):
    db['awards'].update_many({}, {'$set': {'shimmer': True}})
    lines = dict((title, classes.split()) for classes, title in boxes(page(client, db, 'dossier')))
    assert 'plaque-line--shimmer' in lines['Excellence Award']
    assert 'plaque-line--shimmer' not in lines['Judges Award']


# --- Trophy Shelf -------------------------------------------------------------

@pytest.mark.parametrize('layout', ['spotlight', 'magazine'])
def test_shelf_puts_trophies_on_shelves(client, db, team, layout):
    body = page(client, db, layout)
    assert 'css/pages/awards/shelf.css' in body and 'class="trophy-case"' in body
    assert 'awards-grid' not in body
    assert [title for _, title in boxes(body)] == ['Think Award', 'Design Award', 'Excellence Award', 'Judges Award']
    plates = re.findall(r'class="trophy-plate" aria-label="([^"]+)">([^<]+)<', body)
    assert plates == [('won 1 time', '×1'), ('won 2 times', '×2'), ('won 3 times', '×3'),
                      ('won 0 times', '&mdash;')]


def test_shelf_spotlight_only_on_won_awards(client, db, team):
    db['awards'].update_many({}, {'$set': {'shimmer': True, 'border': 'gold'}})
    trophies = {title: classes.split() for classes, title in boxes(page(client, db, 'magazine'))}
    assert 'trophy--spotlit' in trophies['Excellence Award'] and 'trophy--gold' in trophies['Excellence Award']
    assert 'trophy--spotlit' not in trophies['Judges Award']


def test_shelf_with_no_awards(client, db, team):
    db['awards'].delete_many({})
    body = page(client, db, 'magazine')
    assert 'No awards recorded for this team yet' in body and 'class="trophy-case"' not in body
