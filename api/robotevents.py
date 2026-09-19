"""RobotEvents v2 client for the team page's live sections.

Everything here is optional by design. With no ROBOTEVENTS_TOKEN, with the API
down, or with a response we don't recognise, every public function returns None
and the team page simply renders without its live sections.

Responses are cached in the `re_cache` collection so a traffic spike costs one
upstream call per freshness window, not one per visitor. On an upstream failure
a stale cache entry is served in preference to nothing, flagged so the page can
say how old it is.

ENDPOINT ASSUMPTIONS
--------------------
The official docs at https://www.robotevents.com/api/v2 require a token to read,
so the paths below follow the widely-used community wrappers rather than a doc
page we could open. Every parser uses .get() and tolerates missing keys, and
`python -m api.robotevents probe <team_number>` prints the real payload shapes
once a token is available. Confirm with the probe before trusting field names.

    GET /teams?number[]=&program[]=      -> {"data": [{"id", "number", ...}]}
    GET /teams/{id}/events?season[]=     -> {"data": [{"id", "sku", "name", "start", "level"}]}
    GET /teams/{id}/awards?season[]=     -> {"data": [{"title", "event": {"name"}, ...}]}
    GET /teams/{id}/rankings?season[]=   -> {"data": [{"rank", "wins", "losses", "ties", "event"}]}
    GET /teams/{id}/skills?season[]=     -> {"data": [{"type": "driver"|"programming", "score", "rank", "event"}]}
"""

import datetime
import logging
import os

import requests

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.robotevents.com/api/v2'
PROGRAM_V5RC = 1
REQUEST_TIMEOUT = 2.5

# How long a cached payload counts as fresh.
FRESHNESS = {
    'skills': datetime.timedelta(minutes=30),
    'events': datetime.timedelta(hours=6),
    'awards': datetime.timedelta(hours=6),
    'rankings': datetime.timedelta(hours=6),
    'team': datetime.timedelta(days=7),
}
DEFAULT_FRESHNESS = datetime.timedelta(hours=6)

# Event levels RobotEvents reports, mapped to the three buckets the scoreboard shows.
LEVEL_BUCKETS = {
    'World': 'championship',
    'National': 'championship',
    'Signature': 'signature',
    'State': 'signature',
    'Regional': 'signature',
    'Other': 'local',
}

TRIPLE_CROWN_AWARDS = ('tournament champion', 'excellence award', 'robot skills champion')


def get_token():
    """The API token, or None when the deployment has not been given one."""
    token = os.environ.get('ROBOTEVENTS_TOKEN')
    return token.strip() or None if token else None


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _cache_key(path, params):
    parts = []
    for key in sorted(params or {}):
        value = params[key]
        if isinstance(value, (list, tuple)):
            value = ','.join(str(v) for v in value)
        parts.append(f'{key}={value}')
    return path + ('?' + '&'.join(parts) if parts else '')


def _kind(path):
    for kind in FRESHNESS:
        if path.rstrip('/').endswith(kind) or path.strip('/') == kind:
            return kind
    return 'other'


def _fetch(path, params):
    """One upstream GET. Returns the decoded body, or None on any failure."""
    token = get_token()
    if not token:
        return None
    try:
        resp = requests.get(
            BASE_URL + path,
            params=params,
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning('RobotEvents %s returned HTTP %s', path, resp.status_code)
            return None
        return resp.json()
    except Exception as exc:  # network error, timeout, bad JSON - all non-fatal
        logger.warning('RobotEvents %s failed: %s', path, exc.__class__.__name__)
        return None


def get_cached(db, path, params=None):
    """Cached GET. Returns (payload, fetched_at, stale) or (None, None, False).

    A fresh cache entry is returned without touching the network. A stale entry
    is refreshed, and kept as the answer if the refresh fails.
    """
    if not get_token():
        return None, None, False

    key = _cache_key(path, params)
    window = FRESHNESS.get(_kind(path), DEFAULT_FRESHNESS)
    cached = db['re_cache'].find_one({'_id': key})

    if cached:
        fetched_at = cached.get('fetched_at')
        if isinstance(fetched_at, datetime.datetime):
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=datetime.timezone.utc)
            if _now() - fetched_at < window:
                return cached.get('payload'), fetched_at, False

    payload = _fetch(path, params)
    if payload is None:
        if cached:
            return cached.get('payload'), cached.get('fetched_at'), True
        return None, None, False

    now = _now()
    db['re_cache'].update_one(
        {'_id': key},
        {'$set': {'payload': payload, 'fetched_at': now}},
        upsert=True,
    )
    return payload, now, False


def _rows(payload):
    if isinstance(payload, dict):
        data = payload.get('data')
        if isinstance(data, list):
            return data
    return []


def get_team_id(db, team_number):
    payload, _, _ = get_cached(db, '/teams', {'number[]': team_number,
                                              'program[]': PROGRAM_V5RC})
    for row in _rows(payload):
        if str(row.get('number', '')).upper() == str(team_number).upper():
            return row.get('id')
    return None


def _event_name(row):
    event = row.get('event')
    if isinstance(event, dict):
        return event.get('name')
    return None


def parse_skills(payload):
    """Season-best driver and programming scores, plus the best rank seen."""
    best = {'driver': 0, 'programming': 0}
    rank = None
    for row in _rows(payload):
        kind = str(row.get('type', '')).lower()
        if kind not in best:
            continue
        score = row.get('score') or 0
        try:
            score = int(score)
        except (TypeError, ValueError):
            continue
        best[kind] = max(best[kind], score)
        row_rank = row.get('rank')
        if isinstance(row_rank, int) and row_rank > 0:
            rank = row_rank if rank is None else min(rank, row_rank)

    if not best['driver'] and not best['programming']:
        return None
    return {
        'driver': best['driver'],
        'programming': best['programming'],
        'combined': best['driver'] + best['programming'],
        'rank': rank,
    }


def parse_events(payload):
    events = []
    for row in _rows(payload):
        level = row.get('level') or 'Other'
        events.append({
            'name': row.get('name'),
            'sku': row.get('sku'),
            'start': row.get('start'),
            'level': level,
            'bucket': LEVEL_BUCKETS.get(level, 'local'),
        })
    events.sort(key=lambda e: e.get('start') or '', reverse=True)
    return events


def parse_awards(payload):
    awards = []
    for row in _rows(payload):
        title = row.get('title')
        if not title:
            continue
        awards.append({'title': title, 'event': _event_name(row)})
    return awards


def parse_rankings(payload):
    records = {}
    for row in _rows(payload):
        event = _event_name(row)
        if not event:
            continue
        records[event] = {
            'rank': row.get('rank'),
            'wins': row.get('wins'),
            'losses': row.get('losses'),
            'ties': row.get('ties'),
        }
    return records


def build_scoreboard(events, awards):
    buckets = {'local': 0, 'signature': 0, 'championship': 0}
    for event in events:
        buckets[event.get('bucket', 'local')] = buckets.get(event.get('bucket', 'local'), 0) + 1

    by_event = {}
    for award in awards:
        by_event.setdefault(award.get('event'), set()).add(str(award.get('title', '')).lower())

    triple_crowns = 0
    for titles in by_event.values():
        if all(any(needle in title for title in titles) for needle in TRIPLE_CROWN_AWARDS):
            triple_crowns += 1

    return {
        'competitions': len(events),
        'local': buckets['local'],
        'signature': buckets['signature'],
        'championship': buckets['championship'],
        'awards': len(awards),
        'triple_crowns': triple_crowns,
    }


def record_skills_history(db, team_number, rank, score):
    """Append today's standing, keeping the last 60 samples for trend maths."""
    if rank is None:
        return
    entry = {'date': _now(), 'rank': rank, 'score': score}
    db['re_history'].update_one(
        {'_id': team_number},
        {'$push': {'samples': {'$each': [entry], '$slice': -60}}},
        upsert=True,
    )


def rank_trend(db, team_number, current_rank):
    """Compare against the newest sample older than 24h."""
    if current_rank is None:
        return None
    doc = db['re_history'].find_one({'_id': team_number}) or {}
    cutoff = _now() - datetime.timedelta(hours=24)

    previous = None
    for sample in doc.get('samples', []):
        date = sample.get('date')
        if isinstance(date, datetime.datetime):
            if date.tzinfo is None:
                date = date.replace(tzinfo=datetime.timezone.utc)
            if date <= cutoff:
                previous = sample
    if previous is None:
        return {'direction': 'new', 'delta': 0}

    delta = previous['rank'] - current_rank
    if delta > 0:
        return {'direction': 'up', 'delta': delta}
    if delta < 0:
        return {'direction': 'down', 'delta': -delta}
    return {'direction': 'flat', 'delta': 0}


def team_summary(db, team_number, season_id=None):
    """Everything the live panels need, or None when there is nothing to show."""
    if not get_token():
        return None

    team_id = get_team_id(db, team_number)
    if not team_id:
        return None

    season = {'season[]': season_id} if season_id else {}
    skills_payload, skills_at, skills_stale = get_cached(db, f'/teams/{team_id}/skills', season)
    events_payload, events_at, events_stale = get_cached(db, f'/teams/{team_id}/events', season)
    awards_payload, _, awards_stale = get_cached(db, f'/teams/{team_id}/awards', season)
    rankings_payload, _, _ = get_cached(db, f'/teams/{team_id}/rankings', season)

    skills = parse_skills(skills_payload)
    events = parse_events(events_payload)
    awards = parse_awards(awards_payload)
    rankings = parse_rankings(rankings_payload)

    if not skills and not events and not awards:
        return None

    trend = None
    if skills:
        record_skills_history(db, team_number, skills.get('rank'), skills.get('combined'))
        trend = rank_trend(db, team_number, skills.get('rank'))

    for event in events:
        event['record'] = rankings.get(event['name'])
        event['awards'] = [a['title'] for a in awards if a.get('event') == event['name']]

    fetched_at = skills_at or events_at
    return {
        'team_id': team_id,
        'skills': skills,
        'trend': trend,
        'scoreboard': build_scoreboard(events, awards),
        'events': events,
        'awards': awards,
        'fetched_at': fetched_at.isoformat() if fetched_at else None,
        'stale': bool(skills_stale or events_stale or awards_stale),
        'profile_url': f'https://www.robotevents.com/teams/V5RC/{team_number}',
    }


def _probe(team_number):  # pragma: no cover - operator tool, needs a real token
    """Print the real payload shapes. Run once a token exists:

        python -m api.robotevents probe 77628A
    """
    import json
    if not get_token():
        print('ROBOTEVENTS_TOKEN is not set; nothing to probe.')
        return
    teams = _fetch('/teams', {'number[]': team_number, 'program[]': PROGRAM_V5RC})
    print('TEAMS:', json.dumps(teams, indent=2)[:2000])
    rows = _rows(teams)
    if not rows:
        return
    team_id = rows[0].get('id')
    for path in ('skills', 'events', 'awards', 'rankings'):
        body = _fetch(f'/teams/{team_id}/{path}', {})
        sample = _rows(body)[:1]
        print(f'\n{path.upper()} keys:', sorted(sample[0].keys()) if sample else '(empty)')
        print(json.dumps(sample, indent=2)[:1500])


if __name__ == '__main__':  # pragma: no cover
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == 'probe':
        _probe(sys.argv[2])
    else:
        print(__doc__)
