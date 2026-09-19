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
    db['teams'].insert_one({'team_number': 'MEPHAM-A', 'robotevents_number': '77628A'})
    seed_full(upstream)

    resp = client.get('/api/team/MEPHAM-A/live')

    assert resp.status_code == 200
    assert '77628A' in resp.get_json()['profile_url']
