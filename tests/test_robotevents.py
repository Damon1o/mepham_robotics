import datetime

import pytest

from api import robotevents as re


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')


@pytest.fixture
def no_token(monkeypatch):
    monkeypatch.delenv('ROBOTEVENTS_TOKEN', raising=False)


@pytest.fixture
def upstream(monkeypatch):
    """Records calls and replays canned payloads keyed by path."""
    calls = []
    responses = {}

    def fake_fetch(path, params):
        calls.append(path)
        value = responses.get(path)
        if isinstance(value, Exception):
            return None
        return value

    monkeypatch.setattr(re, '_fetch', fake_fetch)
    return type('Upstream', (), {'calls': calls, 'responses': responses})()


def envelope(rows):
    return {'meta': {'total': len(rows)}, 'data': rows}


# --- token handling --------------------------------------------------------

def test_no_token_returns_none(no_token, db):
    assert re.get_token() is None
    assert re.get_cached(db, '/teams', {}) == (None, None, False)
    assert re.team_summary(db, '77628A') is None


def test_blank_token_treated_as_absent(monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', '   ')
    assert re.get_token() is None


# --- caching ---------------------------------------------------------------

def test_fresh_cache_skips_upstream(token, db, upstream):
    upstream.responses['/teams'] = envelope([{'id': 1, 'number': '77628A'}])

    first = re.get_cached(db, '/teams', {'number[]': '77628A'})
    second = re.get_cached(db, '/teams', {'number[]': '77628A'})

    assert first[0] == second[0]
    assert upstream.calls == ['/teams'], 'second read should come from the cache'


def test_expired_cache_refetches(token, db, upstream):
    path = '/teams/1/skills'
    upstream.responses[path] = envelope([{'type': 'driver', 'score': 50}])
    re.get_cached(db, path, {})

    stale_at = re._now() - datetime.timedelta(hours=3)
    db['re_cache'].update_one({'_id': path}, {'$set': {'fetched_at': stale_at}})

    upstream.responses[path] = envelope([{'type': 'driver', 'score': 99}])
    payload, _, stale = re.get_cached(db, path, {})

    assert payload['data'][0]['score'] == 99
    assert stale is False
    assert upstream.calls.count(path) == 2


def test_upstream_failure_serves_stale_cache(token, db, upstream):
    path = '/teams/1/skills'
    upstream.responses[path] = envelope([{'type': 'driver', 'score': 50}])
    re.get_cached(db, path, {})

    db['re_cache'].update_one({'_id': path},
                              {'$set': {'fetched_at': re._now() - datetime.timedelta(hours=3)}})
    upstream.responses[path] = None  # upstream now failing

    payload, fetched_at, stale = re.get_cached(db, path, {})

    assert payload['data'][0]['score'] == 50
    assert stale is True
    assert fetched_at is not None


def test_upstream_failure_without_cache_returns_none(token, db, upstream):
    assert re.get_cached(db, '/teams/1/skills', {}) == (None, None, False)


def test_cache_key_is_order_independent(token, db, upstream):
    upstream.responses['/teams'] = envelope([])
    re.get_cached(db, '/teams', {'a': 1, 'b': 2})
    re.get_cached(db, '/teams', {'b': 2, 'a': 1})
    assert upstream.calls.count('/teams') == 1


# --- parsers ---------------------------------------------------------------

def test_parse_skills_takes_season_best_per_type():
    payload = envelope([
        {'type': 'driver', 'score': 40, 'rank': 300},
        {'type': 'driver', 'score': 72, 'rank': 120},
        {'type': 'programming', 'score': 88, 'rank': 90},
    ])
    skills = re.parse_skills(payload)
    assert skills == {'driver': 72, 'programming': 88, 'combined': 160, 'rank': 90}


def test_parse_skills_returns_none_when_empty():
    assert re.parse_skills(envelope([])) is None
    assert re.parse_skills(None) is None


def test_parse_skills_ignores_garbage_scores():
    skills = re.parse_skills(envelope([
        {'type': 'driver', 'score': 'not-a-number'},
        {'type': 'driver', 'score': 30},
        {'type': 'mystery', 'score': 999},
    ]))
    assert skills['driver'] == 30
    assert skills['programming'] == 0


def test_parse_events_buckets_and_sorts():
    events = re.parse_events(envelope([
        {'name': 'League Night', 'start': '2025-11-01', 'level': 'Other'},
        {'name': 'Worlds', 'start': '2026-05-01', 'level': 'World'},
        {'name': 'States', 'start': '2026-03-01', 'level': 'State'},
    ]))
    assert [e['name'] for e in events] == ['Worlds', 'States', 'League Night']
    assert [e['bucket'] for e in events] == ['championship', 'signature', 'local']


def test_parse_awards_skips_untitled_rows():
    awards = re.parse_awards(envelope([
        {'title': 'Excellence Award', 'event': {'name': 'States'}},
        {'event': {'name': 'States'}},
    ]))
    assert awards == [{'title': 'Excellence Award', 'event': 'States'}]


def test_build_scoreboard_counts_triple_crown():
    events = re.parse_events(envelope([{'name': 'States', 'start': '2026-03-01', 'level': 'State'}]))
    awards = [
        {'title': 'Tournament Champion', 'event': 'States'},
        {'title': 'Excellence Award', 'event': 'States'},
        {'title': 'Robot Skills Champion', 'event': 'States'},
    ]
    board = re.build_scoreboard(events, awards)
    assert board['competitions'] == 1
    assert board['signature'] == 1
    assert board['awards'] == 3
    assert board['triple_crowns'] == 1


def test_build_scoreboard_partial_sweep_is_not_a_triple_crown():
    events = re.parse_events(envelope([{'name': 'States', 'start': '2026-03-01', 'level': 'State'}]))
    awards = [{'title': 'Excellence Award', 'event': 'States'}]
    assert re.build_scoreboard(events, awards)['triple_crowns'] == 0


# --- rank trend ------------------------------------------------------------

def test_rank_trend_new_without_history(db):
    assert re.rank_trend(db, '77628A', 120) == {'direction': 'new', 'delta': 0}


def _seed_history(db, rank, hours_ago):
    db['re_history'].update_one(
        {'_id': '77628A'},
        {'$push': {'samples': {'date': re._now() - datetime.timedelta(hours=hours_ago),
                               'rank': rank, 'score': 100}}},
        upsert=True,
    )


def test_rank_trend_up(db):
    _seed_history(db, rank=200, hours_ago=30)
    assert re.rank_trend(db, '77628A', 150) == {'direction': 'up', 'delta': 50}


def test_rank_trend_down(db):
    _seed_history(db, rank=100, hours_ago=30)
    assert re.rank_trend(db, '77628A', 140) == {'direction': 'down', 'delta': 40}


def test_rank_trend_flat(db):
    _seed_history(db, rank=100, hours_ago=30)
    assert re.rank_trend(db, '77628A', 100) == {'direction': 'flat', 'delta': 0}


def test_rank_trend_ignores_samples_inside_24h(db):
    _seed_history(db, rank=200, hours_ago=2)
    assert re.rank_trend(db, '77628A', 150)['direction'] == 'new'


def test_history_is_capped(db):
    for i in range(70):
        re.record_skills_history(db, '77628A', rank=i + 1, score=100)
    samples = db['re_history'].find_one({'_id': '77628A'})['samples']
    assert len(samples) == 60


# --- summary ---------------------------------------------------------------

def test_team_summary_assembles_live_data(token, db, upstream):
    upstream.responses['/teams'] = envelope([{'id': 7, 'number': '77628A'}])
    upstream.responses['/teams/7/skills'] = envelope([
        {'type': 'driver', 'score': 70, 'rank': 42},
        {'type': 'programming', 'score': 80, 'rank': 42},
    ])
    upstream.responses['/teams/7/events'] = envelope([
        {'name': 'States', 'start': '2026-03-01', 'level': 'State', 'sku': 'RE-V5RC-1'},
    ])
    upstream.responses['/teams/7/awards'] = envelope([
        {'title': 'Excellence Award', 'event': {'name': 'States'}},
    ])
    upstream.responses['/teams/7/rankings'] = envelope([
        {'event': {'name': 'States'}, 'rank': 3, 'wins': 8, 'losses': 2, 'ties': 0},
    ])

    summary = re.team_summary(db, '77628A')

    assert summary['skills']['combined'] == 150
    assert summary['scoreboard']['awards'] == 1
    assert summary['events'][0]['record']['wins'] == 8
    assert summary['events'][0]['awards'] == ['Excellence Award']
    assert summary['trend']['direction'] == 'new'
    assert summary['stale'] is False
    assert '77628A' in summary['profile_url']


def test_team_summary_none_when_team_unknown(token, db, upstream):
    upstream.responses['/teams'] = envelope([])
    assert re.team_summary(db, '77628A') is None


def test_team_summary_none_when_team_has_no_data(token, db, upstream):
    upstream.responses['/teams'] = envelope([{'id': 7, 'number': '77628A'}])
    for path in ('skills', 'events', 'awards', 'rankings'):
        upstream.responses[f'/teams/7/{path}'] = envelope([])
    assert re.team_summary(db, '77628A') is None


def test_team_summary_survives_unexpected_payload_shape(token, db, upstream):
    upstream.responses['/teams'] = {'unexpected': True}
    assert re.team_summary(db, '77628A') is None
