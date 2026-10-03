"""RobotEvents v2 client for the team page's live sections.

Everything here is optional by design. With no ROBOTEVENTS_API_KEY, with the API
down, or with a response we don't recognise, every public function returns None
and the team page simply renders without its live sections.

Responses are cached in the `re_cache` collection so a traffic spike costs one
upstream call per freshness window, not one per visitor. On an upstream failure
a stale cache entry is served in preference to nothing, flagged so the page can
say how old it is.

ENDPOINT ASSUMPTIONS
--------------------
The official docs at https://events.vex.com/api/v2 require a token to read,
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

# RobotEvents moved to events.vex.com in May 2026; every robotevents.com/api/v2
# path now answers 404, even without a token. The API itself is unchanged.
SITE_URL = 'https://events.vex.com'
BASE_URL = SITE_URL + '/api/v2'
PROGRAM_V5RC = 1
REQUEST_TIMEOUT = 2.5


def team_url(team_number):
    """The team's public profile page. Needs no API key."""
    return f'{SITE_URL}/teams/V5RC/{team_number}'

# How long a cached payload counts as fresh.
FRESHNESS = {
    'matches': datetime.timedelta(minutes=5),
    'skills': datetime.timedelta(minutes=30),
    'events': datetime.timedelta(hours=6),
    'awards': datetime.timedelta(hours=6),
    'rankings': datetime.timedelta(minutes=30),
    'team': datetime.timedelta(days=7),
}
DEFAULT_FRESHNESS = datetime.timedelta(hours=6)

# After an upstream failure, serve what we have (or nothing) for this long
# before trying again. Without it, an outage costs every page view up to four
# timed-out calls.
RETRY_BACKOFF = datetime.timedelta(minutes=5)

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


TOKEN_ENV_VARS = ('ROBOTEVENTS_API_KEY', 'ROBOTEVENTS_TOKEN')


def get_token():
    """The API token, or None when the deployment has not been given one.

    ROBOTEVENTS_API_KEY is the name the deployment uses; ROBOTEVENTS_TOKEN is the
    older name, still read so existing setups keep working.
    """
    for name in TOKEN_ENV_VARS:
        token = (os.environ.get(name) or '').strip()
        if token:
            return token
    return None


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


def _aware(value):
    """A stored datetime as timezone-aware UTC, or None."""
    if not isinstance(value, datetime.datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)


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

    def fallback():
        # A back-off marker can exist without a payload; that means "nothing".
        if cached and cached.get('payload') is not None:
            return cached.get('payload'), cached.get('fetched_at'), True
        return None, None, False

    if cached:
        fetched_at = _aware(cached.get('fetched_at'))
        if fetched_at and cached.get('payload') is not None and _now() - fetched_at < window:
            return cached.get('payload'), fetched_at, False
        failed_at = _aware(cached.get('failed_at'))
        if failed_at and _now() - failed_at < RETRY_BACKOFF:
            return fallback()

    payload = _fetch(path, params)
    if payload is None:
        db['re_cache'].update_one({'_id': key}, {'$set': {'failed_at': _now()}}, upsert=True)
        return fallback()

    now = _now()
    db['re_cache'].update_one(
        {'_id': key},
        {'$set': {'payload': payload, 'fetched_at': now}, '$unset': {'failed_at': ''}},
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


def season_id(db, label):
    """The RobotEvents season id for a site season label such as '2025-26', or None.

    RobotEvents names seasons like 'VEX V5 Robotics Competition 2025-2026: Push Back'.
    """
    try:
        start = int(str(label)[:4])
    except (TypeError, ValueError):
        return None
    payload, _, _ = get_cached(db, '/seasons', {'program[]': PROGRAM_V5RC})
    needle = f'{start}-{start + 1}'
    for row in _rows(payload):
        if needle in str(row.get('name', '')):
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
    """Record today's standing, one sample per UTC day, keeping the last 60.

    This runs on every live-panel request. Pushing a sample each time meant a
    busy day pushed every older sample out of the 60-slot window, so the 24h
    trend never found a baseline and always read "new".
    """
    if rank is None:
        return
    now = _now()
    entry = {'date': now, 'rank': rank, 'score': score}
    samples = (db['re_history'].find_one({'_id': team_number}, {'samples': 1}) or {}).get('samples') or []
    last_date = _aware(samples[-1].get('date')) if samples else None
    if last_date and last_date.date() == now.date():
        # Same day: keep the newest reading without adding a sample.
        db['re_history'].update_one(
            {'_id': team_number},
            {'$set': {f'samples.{len(samples) - 1}': entry}},
        )
        return
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
        'profile_url': team_url(team_number),
    }


# --- Match feed (achievements page) ---------------------------------------------------
# One season of matches for every robot team, grouped by event, newest first.
# RobotEvents lists a team's matches in no useful order, so everything is
# sorted here by the time the match started (or was scheduled).

FEED_SEASONS_TO_TRY = 3
TEAM_FEED_SEASONS_TO_TRY = 5
FEED_EVENT_LIMIT = 6
PER_PAGE_MAX = 250

ROUND_NAMES = {1: 'Practice', 2: 'Qualification', 3: 'Quarterfinal', 4: 'Semifinal',
               5: 'Final', 6: 'Round of 16', 7: 'Round of 32'}


def _season_start(row):
    """2025 for 'VEX V5 Robotics Competition 2025-2026: Push Back', else None."""
    name = str(row.get('name', ''))
    for i in range(len(name) - 8):
        chunk = name[i:i + 9]
        if chunk[:4].isdigit() and chunk[4] == '-' and chunk[5:].isdigit():
            return int(chunk[:4])
    return None


def recent_seasons(db, count=FEED_SEASONS_TO_TRY):
    """The newest seasons that have started, newest first, as {'id', 'name', 'label'}."""
    payload, _, _ = get_cached(db, '/seasons', {'program[]': PROGRAM_V5RC})
    this_year = _now().year
    seasons = []
    for row in _rows(payload):
        start = _season_start(row)
        if start is None or start > this_year or not row.get('id'):
            continue
        game = str(row.get('name', '')).rpartition(':')[2].strip()
        seasons.append({'id': row['id'], 'start': start, 'game': game,
                        'label': f'{start}-{(start + 1) % 100:02d}'})
    seasons.sort(key=lambda s: s['start'], reverse=True)
    return seasons[:count]


def _team_rows(db, numbers):
    payload, _, _ = get_cached(db, '/teams', {'number[]': sorted(numbers), 'program[]': PROGRAM_V5RC})
    wanted = {n.upper() for n in numbers}
    return [row for row in _rows(payload) if str(row.get('number', '')).upper() in wanted and row.get('id')]


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _match_time(row):
    return row.get('started') or row.get('scheduled') or ''


def _ts(value):
    """Sortable seconds for an ISO time string; RobotEvents mixes UTC offsets."""
    try:
        return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return 0.0


def parse_match(row, ours):
    """One match as the feed shows it, or None for practice and malformed rows.

    `ours` is the set of our team numbers, upper-cased.
    """
    round_no = _int(row.get('round'))
    if round_no == 1:
        return None
    sides = {}
    for alliance in row.get('alliances') or []:
        color = alliance.get('color')
        if color not in ('red', 'blue'):
            continue
        teams = []
        for entry in alliance.get('teams') or []:
            name = str(((entry or {}).get('team') or {}).get('name') or '')
            if name:
                teams.append({'number': name, 'ours': name.upper() in ours,
                              'sitting': bool(entry.get('sitting'))})
        sides[color] = {'score': _int(alliance.get('score')), 'teams': teams}
    if set(sides) != {'red', 'blue'}:
        return None

    red, blue = sides['red']['score'], sides['blue']['score']
    played = red is not None and blue is not None and (bool(row.get('started')) or red or blue or row.get('scored'))
    winner = None
    if played:
        winner = 'tie' if red == blue else ('red' if red > blue else 'blue')

    our_sides = []
    for color in ('red', 'blue'):
        for team in sides[color]['teams']:
            if team['ours']:
                result = None
                if winner:
                    result = 'tie' if winner == 'tie' else ('win' if winner == color else 'loss')
                our_sides.append({'number': team['number'], 'color': color, 'result': result})

    return {
        'id': row.get('id'),
        'name': row.get('name') or ROUND_NAMES.get(round_no, 'Match'),
        'round': ROUND_NAMES.get(round_no, 'Elimination'),
        'elimination': bool(round_no and round_no > 2),
        'field': row.get('field') or None,
        'time': _match_time(row) or None,
        'played': bool(played),
        'winner': winner,
        'red': sides['red'],
        'blue': sides['blue'],
        'ours': our_sides,
    }


def _skills_by_event(payload):
    """{event_id: {'driver', 'programming', 'combined', 'rank'}} for one team."""
    events = {}
    for row in _rows(payload):
        kind = str(row.get('type', '')).lower()
        event_id = (row.get('event') or {}).get('id')
        score = _int(row.get('score'))
        if kind not in ('driver', 'programming') or event_id is None or score is None:
            continue
        entry = events.setdefault(event_id, {'driver': 0, 'programming': 0, 'rank': None})
        entry[kind] = max(entry[kind], score)
        rank = _int(row.get('rank'))
        if rank:
            entry['rank'] = rank if entry['rank'] is None else min(entry['rank'], rank)
    for entry in events.values():
        entry['combined'] = entry['driver'] + entry['programming']
    return events


def _rankings_by_event(payload):
    keys = ('rank', 'wins', 'losses', 'ties', 'wp', 'ap', 'sp', 'high_score', 'average_points')
    return {(row.get('event') or {}).get('id'): {k: row.get(k) for k in keys}
            for row in _rows(payload) if (row.get('event') or {}).get('id') is not None}


def _season_record(number, matches):
    """Win/loss record and scoring for one of our teams across parsed matches."""
    record = {'wins': 0, 'losses': 0, 'ties': 0}
    scores = []
    for match in matches:
        for side in match['ours']:
            if side['number'] != number or not side['result']:
                continue
            record[{'win': 'wins', 'loss': 'losses', 'tie': 'ties'}[side['result']]] += 1
            scores.append(match[side['color']]['score'])
    played = sum(record.values())
    return {
        **record,
        'played': played,
        'win_rate': round(100 * record['wins'] / played) if played else None,
        'high_score': max(scores) if scores else None,
        'average_score': round(sum(scores) / len(scores), 1) if scores else None,
    }


def match_feed(db, numbers, season_label=None, seasons_to_try=FEED_SEASONS_TO_TRY):
    """Season match feed for our robot teams.

    Tries the newest seasons in turn and uses the first one where any of the
    teams has played, so the page keeps showing last season's results until
    the first event of the new one. With `season_label` ('2025-26') only that
    season is used, as a team page showing an older season wants. Returns
    {'season', 'teams', 'events'}; both lists are empty when there is nothing
    to show.
    """
    empty = {'season': None, 'teams': [], 'events': []}
    if not get_token() or not numbers:
        return empty
    team_rows = _team_rows(db, numbers)
    if not team_rows:
        return empty
    ours = {str(row['number']).upper() for row in team_rows}

    season, raw = None, {}
    if season_label:
        candidates = [c for c in recent_seasons(db, count=None) if c['label'] == season_label]
    else:
        candidates = recent_seasons(db, count=seasons_to_try)
    for candidate in candidates:
        raw = {}
        for row in team_rows:
            payload, _, _ = get_cached(db, f"/teams/{row['id']}/matches",
                                       {'season[]': candidate['id'], 'per_page': PER_PAGE_MAX})
            raw[row['id']] = _rows(payload)
        if any(raw.values()):
            season = candidate
            break
    if not season:
        return empty

    matches, events = {}, {}
    for rows in raw.values():
        for row in rows:
            event = row.get('event') or {}
            match = parse_match(row, ours)
            if not match or match['id'] in matches or event.get('id') is None:
                continue
            matches[match['id']] = match
            entry = events.setdefault(event['id'], {'id': event['id'], 'name': event.get('name') or 'Event',
                                                    'code': event.get('code'), 'matches': [], 'teams': {}})
            entry['matches'].append(match)

    teams = []
    for row in sorted(team_rows, key=lambda r: str(r['number'])):
        number = str(row['number'])
        team_id = row['id']
        if not raw.get(team_id):
            continue
        season_params = {'season[]': season['id'], 'per_page': PER_PAGE_MAX}
        skills_payload, _, _ = get_cached(db, f'/teams/{team_id}/skills', season_params)
        rankings_payload, _, _ = get_cached(db, f'/teams/{team_id}/rankings', season_params)
        skills = _skills_by_event(skills_payload)
        rankings = _rankings_by_event(rankings_payload)

        team_matches = [m for m in matches.values() if any(s['number'] == number for s in m['ours'])]
        event_ids = {(r.get('event') or {}).get('id') for r in raw[team_id]}
        for event_id in event_ids & set(events):
            event_matches = [m for m in events[event_id]['matches'] if any(s['number'] == number for s in m['ours'])]
            events[event_id]['teams'][number] = {
                **_season_record(number, event_matches),
                'ranking': rankings.get(event_id),
                'skills': skills.get(event_id),
            }

        best_skills = max(skills.values(), key=lambda s: s['combined'], default=None)
        ranks = [r['rank'] for r in rankings.values() if _int(r.get('rank'))]
        teams.append({
            'number': number,
            'name': row.get('team_name') or '',
            'profile_url': team_url(number),
            'events': len(event_ids),
            'best_rank': min(ranks) if ranks else None,
            'skills': {
                'best_driver': max((s['driver'] for s in skills.values()), default=0),
                'best_programming': max((s['programming'] for s in skills.values()), default=0),
                'best_combined': best_skills['combined'] if best_skills else 0,
                'best_rank': min((s['rank'] for s in skills.values() if s['rank']), default=None),
            } if skills else None,
            **_season_record(number, team_matches),
        })

    ordered = []
    for entry in events.values():
        entry['matches'].sort(key=lambda m: _ts(m['time']), reverse=True)
        times = sorted((m['time'] for m in entry['matches'] if m['time']), key=_ts)
        entry['start'] = times[0] if times else None
        entry['end'] = times[-1] if times else None
        ordered.append(entry)
    # Newest event first; events with no times fall back to RobotEvents' id order.
    ordered.sort(key=lambda e: (_ts(e['end']), e['id']), reverse=True)

    return {
        'season': {'label': season['label'], 'game': season['game']},
        'teams': teams,
        'events': ordered[:FEED_EVENT_LIMIT],
    }


def _probe(team_number):  # pragma: no cover - operator tool, needs a real token
    """Print the real payload shapes. Run once a token exists:

        python -m api.robotevents probe 77628A
    """
    import json
    if not get_token():
        print('ROBOTEVENTS_API_KEY is not set; nothing to probe.')
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
