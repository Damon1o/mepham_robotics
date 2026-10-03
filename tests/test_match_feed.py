"""The achievements page match feed: robotevents.match_feed and /api/matches."""
import pytest

import api.index as app_module
from api import robotevents as re

SEASONS = [{'id': 204, 'name': 'VEX V5 Robotics Competition 2026-2027: Override'},
           {'id': 197, 'name': 'VEX V5 Robotics Competition 2025-2026: Push Back'},
           {'id': 190, 'name': 'VEX V5 Robotics Competition 2024-2025: High Stakes'}]


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    monkeypatch.setattr(re, '_now', lambda: re.datetime.datetime(2026, 10, 2, tzinfo=re.datetime.timezone.utc))
    app_module._matches_cache.clear()


@pytest.fixture
def upstream(monkeypatch):
    """Canned payloads keyed by (path, season id); season None matches any."""
    calls = []
    responses = {}

    def fake_fetch(path, params):
        calls.append((path, dict(params or {})))
        season = (params or {}).get('season[]')
        rows = responses.get((path, season), responses.get((path, None)))
        return None if rows is None else {'meta': {'total': len(rows)}, 'data': rows}

    monkeypatch.setattr(re, '_fetch', fake_fetch)
    responses[('/seasons', None)] = SEASONS
    responses[('/teams', None)] = [{'id': 7, 'number': '77628A', 'team_name': 'Mepham A'},
                                   {'id': 8, 'number': '77628B', 'team_name': 'Mepham B'}]
    return type('Upstream', (), {'calls': calls, 'responses': responses})()


def team(number):
    return {'team': {'name': number}, 'sitting': False}


def match(match_id, name, red, blue, red_score, blue_score, started, event_id=1, round_no=2):
    return {
        'id': match_id, 'name': name, 'round': round_no, 'field': 'Field 1', 'started': started,
        'scheduled': started, 'event': {'id': event_id, 'name': f'Event {event_id}', 'code': f'RE-{event_id}'},
        'alliances': [{'color': 'red', 'score': red_score, 'teams': [team(t) for t in red]},
                      {'color': 'blue', 'score': blue_score, 'teams': [team(t) for t in blue]}],
    }


def test_feed_falls_back_to_the_newest_season_with_matches(db, upstream):
    upstream.responses[('/teams/7/matches', 204)] = []
    upstream.responses[('/teams/8/matches', 204)] = []
    upstream.responses[('/teams/7/matches', 197)] = [
        match(1, 'Q1', ['77628A', '1A'], ['2A', '3A'], 40, 20, '2026-01-24T10:00:00-05:00'),
    ]
    upstream.responses[('/teams/8/matches', 197)] = []

    feed = re.match_feed(db, {'77628A', '77628B'})

    assert feed['season'] == {'label': '2025-26', 'game': 'Push Back'}
    assert [t['number'] for t in feed['teams']] == ['77628A'], 'teams with no matches are left out'
    assert feed['events'][0]['matches'][0]['ours'] == [{'number': '77628A', 'color': 'red', 'result': 'win'}]


def test_feed_groups_sorts_and_scores(db, upstream):
    upstream.responses[('/teams/7/matches', None)] = [
        match(1, 'Q1', ['77628A', '1A'], ['2A', '3A'], 40, 20, '2025-11-15T10:00:00-05:00', event_id=1),
        match(3, 'Q9', ['2A', '3A'], ['77628A', '1A'], 50, 30, '2026-01-24T11:00:00-05:00', event_id=2),
        match(2, 'Q2', ['77628A', '1A'], ['77628B', '3A'], 25, 25, '2026-01-24T10:00:00-05:00', event_id=2),
        match(4, 'Practice', ['77628A', '1A'], ['2A', '3A'], 0, 0, '2026-01-24T08:00:00-05:00', event_id=2,
              round_no=1),
        match(5, 'SF 1-1', ['77628A', '1A'], ['2A', '3A'], 0, 0, None, event_id=2, round_no=4),
    ]
    upstream.responses[('/teams/8/matches', None)] = [
        match(2, 'Q2', ['77628A', '1A'], ['77628B', '3A'], 25, 25, '2026-01-24T10:00:00-05:00', event_id=2),
    ]
    upstream.responses[('/teams/7/skills', None)] = [
        {'type': 'driver', 'score': 30, 'rank': 4, 'event': {'id': 2}},
        {'type': 'programming', 'score': 12, 'rank': 6, 'event': {'id': 2}},
        {'type': 'driver', 'score': 35, 'rank': 9, 'event': {'id': 1}},
    ]
    upstream.responses[('/teams/7/rankings', None)] = [
        {'event': {'id': 2}, 'rank': 3, 'wins': 4, 'losses': 1, 'ties': 1, 'wp': 9, 'ap': 20, 'sp': 100,
         'high_score': 50, 'average_points': 30.5},
    ]

    feed = re.match_feed(db, {'77628A', '77628B'})

    assert [e['id'] for e in feed['events']] == [2, 1], 'newest event first'
    newest = feed['events'][0]
    assert [m['name'] for m in newest['matches']] == ['Q9', 'Q2', 'SF 1-1'], 'practice dropped, newest first'
    upcoming = newest['matches'][-1]
    assert upcoming['played'] is False and upcoming['winner'] is None and upcoming['elimination'] is True
    tie = newest['matches'][1]
    assert tie['winner'] == 'tie' and {s['result'] for s in tie['ours']} == {'tie'}

    a = next(t for t in feed['teams'] if t['number'] == '77628A')
    assert (a['wins'], a['losses'], a['ties'], a['played']) == (1, 1, 1, 3)
    assert a['high_score'] == 40 and a['win_rate'] == 33
    assert a['best_rank'] == 3 and a['events'] == 2
    # Best combined is per event (30 + 12), not best driver plus best programming.
    assert a['skills'] == {'best_driver': 35, 'best_programming': 12, 'best_combined': 42, 'best_rank': 4}

    at_event = newest['teams']['77628A']
    assert at_event['ranking']['rank'] == 3 and at_event['skills']['combined'] == 42
    assert (at_event['wins'], at_event['losses'], at_event['ties']) == (0, 1, 1)
    assert newest['teams']['77628B']['ties'] == 1


def test_feed_is_empty_without_teams_or_matches(db, upstream):
    assert re.match_feed(db, set())['events'] == []
    assert re.match_feed(db, {'77628A'})['events'] == [], 'no matches in any recent season'


def test_endpoint_is_empty_without_a_key(client, monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_API_KEY', raising=False)
    assert client.get('/api/matches').get_json() == {'season': None, 'teams': [], 'events': []}


def test_endpoint_follows_the_database_links_pages_and_caches(client, db, upstream):
    db['teams'].insert_one({'team_number': '77628A', 'robotevents_number': '77628B', 'members': []})
    upstream.responses[('/teams/8/matches', None)] = [
        match(1, 'Q1', ['77628B', '1A'], ['2A', '3A'], 40, 20, '2026-01-24T10:00:00-05:00'),
    ]

    body = client.get('/api/matches').get_json()
    teams_call = next(params for path, params in upstream.calls if path == '/teams')
    assert teams_call['number[]'] == ['77628B'], 'the RobotEvents number override is used'
    assert body['teams'][0]['number'] == '77628B'
    assert body['teams'][0]['page'] == '77628A', 'cards link to the site team page'

    count = len(upstream.calls)
    client.get('/api/matches')
    assert len(upstream.calls) == count, 'second request is served from cache'


def test_endpoint_narrows_to_one_team_and_season(client, db, upstream):
    db['teams'].insert_many([
        {'team_number': '77628A', 'season': '2024-25', 'members': [], 'hidden': True},
        {'team_number': '77628B', 'season': '2025-26', 'members': []},
    ])
    upstream.responses[('/teams/7/matches', 190)] = [
        match(1, 'Q1', ['77628A', '1A'], ['2A', '3A'], 40, 20, '2025-01-24T10:00:00-05:00'),
    ]

    body = client.get('/api/matches?team=77628a&season=2024-25').get_json()
    teams_call = next(params for path, params in upstream.calls if path == '/teams')
    assert teams_call['number[]'] == ['77628A'], 'only the asked-for team, even when hidden'
    assert body['season']['label'] == '2024-25'
    assert [t['number'] for t in body['teams']] == ['77628A']
    match_seasons = {params['season[]'] for path, params in upstream.calls if path.endswith('/matches')}
    assert match_seasons == {190}, 'an explicit season is the only one tried'

    assert client.get('/api/matches?team=99999Z').get_json()['events'] == []
    assert client.get('/api/matches?team=77628A&season=bogus').status_code == 200


def _team_page(client, db, values=None, layout=None):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2025-26', 'members': [],
                            **({'layout': layout} if layout else {})})
    if values:
        db['site_metadata'].insert_one({'_id': app_module.SITE_CONTENT_ID, 'values': values})
    return client.get('/team/77628A').get_data(as_text=True)


def test_team_page_shows_match_results_by_default(client, db):
    html = _team_page(client, db)
    assert 'id="match-feed"' in html and 'data-team="77628A"' in html
    assert 'data-season=' not in html, 'the newest season falls back to the latest one with matches'
    assert 'js/match-feed.js' in html and 'css/match-feed.css' in html
    assert 'Match Results' in html


def test_team_page_match_results_toggle(client, db):
    html = _team_page(client, db, {'teams': {'show_matches': False}})
    assert 'id="match-feed"' not in html and 'js/match-feed.js' not in html


def test_team_page_match_results_need_the_key(client, db, monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_API_KEY', raising=False)
    assert 'id="match-feed"' not in _team_page(client, db)


def test_compact_layout_shows_match_results_by_default(client, db):
    assert 'id="match-feed"' in _team_page(client, db, layout='compact')


def test_compact_layout_has_its_own_toggle(client, db):
    html = _team_page(client, db, {'teams': {'matches_compact': False}}, layout='compact')
    assert 'id="match-feed"' not in html and 'js/match-feed.js' not in html


def test_compact_toggle_leaves_other_layouts_alone(client, db):
    assert 'id="match-feed"' in _team_page(client, db, {'teams': {'matches_compact': False}})


def test_team_page_pins_an_older_season(client, db):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2024-25', 'members': []})
    _team_page(client, db)  # adds the 2025-26 season
    html = client.get('/team/77628A?season=2024-25').get_data(as_text=True)
    assert 'data-season="2024-25"' in html


def test_team_feed_looks_further_back(client, db, upstream):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2026-27', 'members': []})
    upstream.responses[('/seasons', None)] = SEASONS + [
        {'id': 181, 'name': 'VEX V5 Robotics Competition 2023-2024: Over Under'}]
    for season in (204, 197, 190):
        upstream.responses[('/teams/7/matches', season)] = []
    upstream.responses[('/teams/7/matches', 181)] = [
        match(1, 'Q1', ['77628A', '1A'], ['2A', '3A'], 40, 20, '2024-01-24T10:00:00-05:00'),
    ]
    body = client.get('/api/matches?team=77628A').get_json()
    assert body['season']['label'] == '2023-24'
    assert client.get('/api/matches').get_json()['events'] == [], 'the club-wide feed stays recent'
