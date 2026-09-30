import pytest

from api import robotevents as re


@pytest.fixture
def team(db):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2025-26'})


@pytest.fixture
def upstream(monkeypatch):
    responses = {}
    monkeypatch.setattr(re, '_fetch', lambda path, params: responses.get(path))
    return responses


def envelope(rows):
    return {'meta': {'total': len(rows)}, 'data': rows}


def seed_full(responses):
    responses['/seasons'] = envelope([{'id': 197, 'name': 'VEX V5 Robotics Competition 2025-2026: Push Back'},
                                      {'id': 190, 'name': 'VEX V5 Robotics Competition 2024-2025: High Stakes'}])
    responses['/teams'] = envelope([{'id': 7, 'number': '77628A'}])
    responses['/teams/7/skills'] = envelope([
        {'type': 'driver', 'score': 70, 'rank': 42},
        {'type': 'programming', 'score': 80, 'rank': 42},
    ])
    responses['/teams/7/events'] = envelope([
        {'name': 'States', 'start': '2026-03-01', 'level': 'State'},
    ])
    responses['/teams/7/awards'] = envelope([
        {'title': 'Excellence Award', 'event': {'name': 'States'}},
    ])
    responses['/teams/7/rankings'] = envelope([
        {'event': {'name': 'States'}, 'rank': 3, 'wins': 8, 'losses': 2, 'ties': 0},
    ])


def test_no_token_returns_204(client, team, monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_TOKEN', raising=False)
    assert client.get('/api/team/77628A/live').status_code == 204


def test_unknown_team_returns_204(client, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    assert client.get('/api/team/nope/live').status_code == 204


def test_returns_live_payload(client, team, upstream, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    seed_full(upstream)

    resp = client.get('/api/team/77628A/live')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['skills']['combined'] == 150
    assert body['scoreboard']['competitions'] == 1
    assert body['events'][0]['record']['wins'] == 8
    assert body['stale'] is False


def test_upstream_failure_never_500s(client, team, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')

    def boom(path, params):
        raise RuntimeError('upstream exploded')

    monkeypatch.setattr(re, '_fetch', boom)
    assert client.get('/api/team/77628A/live').status_code == 204


def test_second_request_is_served_from_cache(client, team, upstream, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    seed_full(upstream)

    calls = []
    original = re._fetch

    def counting(path, params):
        calls.append(path)
        return original(path, params)

    monkeypatch.setattr(re, '_fetch', counting)

    client.get('/api/team/77628A/live')
    before = len(calls)
    client.get('/api/team/77628A/live')

    assert len(calls) == before, 'repeat visits must not hit the API again'


def test_robotevents_number_override_is_used(client, db, upstream, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    db['teams'].insert_one({'team_number': 'MEPHAM-A', 'season': '2025-26', 'robotevents_number': '77628A'})
    seed_full(upstream)

    resp = client.get('/api/team/MEPHAM-A/live')

    assert resp.status_code == 200
    assert '77628A' in resp.get_json()['profile_url']
    assert resp.get_json()['profile_url'].startswith('https://events.vex.com/')


# --- season scoping ------------------------------------------------------------

def recording(monkeypatch, responses):
    """Like `upstream`, but also records the params of each call."""
    calls = []

    def fetch(path, params):
        calls.append((path, dict(params or {})))
        return responses.get(path)

    monkeypatch.setattr(re, '_fetch', fetch)
    return calls


def test_live_data_is_scoped_to_the_viewed_season(client, db, monkeypatch):
    # Without a season filter "This Season" showed a team's whole RobotEvents history.
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    db['teams'].insert_many([{'team_number': '77628A', 'season': '2024-25'},
                             {'team_number': '77628A', 'season': '2025-26'}])
    responses = {}
    seed_full(responses)
    calls = recording(monkeypatch, responses)

    assert client.get('/api/team/77628A/live').status_code == 200  # newest season by default
    assert ('/teams/7/events', {'season[]': 197}) in calls

    assert client.get('/api/team/77628A/live?season=2024-25').status_code == 200
    assert ('/teams/7/events', {'season[]': 190}) in calls


def test_season_robotevents_does_not_know_returns_204(client, db, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    db['teams'].insert_one({'team_number': '77628A', 'season': '2030-31'})
    responses = {}
    seed_full(responses)
    calls = recording(monkeypatch, responses)
    assert client.get('/api/team/77628A/live').status_code == 204
    assert not any(path.startswith('/teams/7/') for path, _ in calls)


def test_team_page_asks_for_its_own_season(client, db, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    db['teams'].insert_many([{'team_number': '77628A', 'season': '2024-25'},
                             {'team_number': '77628A', 'season': '2025-26'}])
    body = client.get('/team/77628A?season=2024-25').get_data(as_text=True)
    assert 'data-live-url="/api/team/77628A/live?season=2024-25"' in body


def test_season_id_matches_robotevents_names(db, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_API_KEY', 'test-key')
    responses = {}
    seed_full(responses)
    recording(monkeypatch, responses)
    assert re.season_id(db, '2025-26') == 197
    assert re.season_id(db, '2024-25') == 190
    assert re.season_id(db, '1999-00') is None
    assert re.season_id(db, None) is None
