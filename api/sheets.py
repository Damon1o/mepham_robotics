"""Member Hub sheets: meeting sign-in/sign-out and volunteer sign-up sheets (bake sales and the like).

Attendance is one row per member per meeting day in the `attendance` collection:

    {user_id, day: 'YYYY-MM-DD', in_at, out_at, by}

`in_at` and `out_at` are naive datetimes in club wall-clock time, like events. `by` is
the username of the editor who wrote the row for someone else, or absent.

A sign-up sheet is one row in `signup_sheets`:

    {title, date, location, details, roles: [{key, name, slots, prompt}],
     signups: {role key: [{user_id, note, at}]}, created_by, created_at, event_id}

`event_id` (and `synced`) are set on a sheet made for a bake sale: the event's id, or
'fundraiser:<start>' for a fundraiser. See bake_sale_sources.

This module is pure: no Flask app, no database. api/index.py wires the routes.
"""
import csv
import datetime
import io
import re

# Members can sign in this long before a meeting starts and out this long after it ends.
OPEN_BEFORE = datetime.timedelta(minutes=60)
CLOSE_AFTER = datetime.timedelta(hours=2)
# Meeting days offered in the editors' day picker.
RECENT_DAYS = 12

TITLE_MAX = 80
LOCATION_MAX = 120
DETAILS_MAX = 400
ROLE_NAME_MAX = 40
PROMPT_MAX = 60
NOTE_MAX = 80
ROLES_MAX = 10
SLOTS_MAX = 50

# A new sheet starts as a bake sale. Prompts ask what each person is bringing or covering.
BAKE_SALE_ROLES = (
    {'name': 'Baker', 'slots': 8, 'prompt': 'What are you bringing?'},
    {'name': 'Seller', 'slots': 4, 'prompt': 'Which shift?'},
    {'name': 'Setup', 'slots': 2, 'prompt': ''},
    {'name': 'Cleanup', 'slots': 2, 'prompt': ''},
)
VOLUNTEER_ROLES = (
    {'name': 'Volunteer', 'slots': 6, 'prompt': 'Which shift can you do?'},
)
# What the admin Events tab can start a sheet as: key -> (label, starting roles).
SHEET_KINDS = {'bake_sale': ('Bake sale', BAKE_SALE_ROLES), 'volunteer': ('Volunteering', VOLUNTEER_ROLES)}
# A bake sale put on the calendar gets a sheet of its own: members sign up to bake or to sell.
EVENT_SHEET_ROLES = BAKE_SALE_ROLES[:2]


# --- Meeting days -----------------------------------------------------------------------

def meeting_bounds(meeting, day):
    """(start, end) datetimes of the meeting on `day`, or None when `day` is not a meeting day."""
    if (day.weekday() + 1) % 7 not in set(meeting.get('days') or ()):
        return None
    (sh, sm), (eh, em) = (map(int, meeting[k].split(':')) for k in ('start', 'end'))
    start = datetime.datetime.combine(day, datetime.time(sh, sm))
    return start, max(start, datetime.datetime.combine(day, datetime.time(eh, em)))


def sign_in_window(meeting, now):
    """{day, start, end, opens, closes} for the meeting members can sign in to right now, or None.

    It opens OPEN_BEFORE the start and closes CLOSE_AFTER the end, so early arrivals
    and late sign-outs still count.
    """
    bounds = meeting_bounds(meeting, now.date())
    if not bounds:
        return None
    start, end = bounds
    opens, closes = start - OPEN_BEFORE, end + CLOSE_AFTER
    if not opens <= now <= closes:
        return None
    return {'day': now.date(), 'start': start, 'end': end, 'opens': opens, 'closes': closes}


def recent_meeting_days(meeting, today, count=RECENT_DAYS):
    """The last `count` meeting days up to and including today, newest first."""
    days, day = [], today
    if not set(meeting.get('days') or ()):
        return days
    while len(days) < count:
        if meeting_bounds(meeting, day):
            days.append(day)
        day -= datetime.timedelta(days=1)
    return days


def parse_day(value):
    try:
        return datetime.date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


# --- Attendance -------------------------------------------------------------------------

def minutes_present(row, meeting_end, now):
    """Whole minutes between signing in and out.

    No sign-out yet counts up to now while the meeting runs, and up to the meeting's
    end once it is over (a forgotten sign-out never earns more than the meeting).
    """
    start = row.get('in_at')
    if not isinstance(start, datetime.datetime):
        return 0
    end = row.get('out_at')
    if not isinstance(end, datetime.datetime):
        end = min(now, meeting_end) if meeting_end else now
    return max(0, int((end - start).total_seconds() // 60))


def fmt_minutes(minutes):
    hours, mins = divmod(int(minutes), 60)
    if not hours:
        return f'{mins}m'
    return f'{hours}h {mins:02d}m' if mins else f'{hours}h'


def sheet_rows(rows, names, meeting_end, now):
    """Attendance rows for one day, ready to draw: here now first, then signed out, by sign-in time.

    `names` maps user id -> display name; rows for deleted accounts are skipped.
    """
    out = []
    for row in rows:
        uid = row.get('user_id')
        if uid not in names:
            continue
        here = not isinstance(row.get('out_at'), datetime.datetime)
        out.append({'user_id': uid, 'name': names[uid], 'in_at': row.get('in_at'), 'out_at': row.get('out_at'),
                    'here': here, 'forgot': here and meeting_end is not None and now > meeting_end,
                    'minutes': minutes_present(row, meeting_end, now), 'by': row.get('by') or ''})
    out.sort(key=lambda r: (not r['here'] or r['forgot'], r['in_at'] or datetime.datetime.min))
    return out


def member_totals(rows, meeting, now):
    """(meetings attended, total minutes) over a member's attendance rows."""
    days, minutes = set(), 0
    for row in rows:
        day = parse_day(row.get('day'))
        if not day:
            continue
        bounds = meeting_bounds(meeting, day)
        days.add(day)
        minutes += minutes_present(row, bounds[1] if bounds else None, now)
    return len(days), minutes


def attendance_csv(rows, names, meeting, now):
    """Every attendance row as CSV: day, name, in, out, minutes. Newest day first."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Day', 'Name', 'Signed in', 'Signed out', 'Minutes', 'Recorded by'])
    for row in sorted(rows, key=lambda r: (r.get('day') or '', names.get(r.get('user_id'), '')), reverse=True):
        if row.get('user_id') not in names:
            continue
        day = parse_day(row.get('day'))
        bounds = meeting_bounds(meeting, day) if day else None
        stamp = lambda v: v.strftime('%H:%M') if isinstance(v, datetime.datetime) else ''
        writer.writerow([row.get('day'), _csv_safe(names[row['user_id']]), stamp(row.get('in_at')),
                         stamp(row.get('out_at')), minutes_present(row, bounds[1] if bounds else None, now),
                         _csv_safe(row.get('by') or '')])
    return buffer.getvalue()


def _csv_safe(value):
    """Spreadsheets run cells that start with = + - @ as formulas; a leading quote stops that."""
    value = str(value)
    return "'" + value if value[:1] in ('=', '+', '-', '@') else value


# --- Sign-up sheets ---------------------------------------------------------------------

def _clean_text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _role_key(name, taken):
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'role'
    key, n = base, 2
    while key in taken:
        key, n = f'{base}-{n}', n + 1
    return key


def clean_sheet(body, old_roles=()):
    """(sheet fields, error) from a create/edit form body.

    Roles keep the key they were sent with when it belongs to `old_roles`, so editing a
    sheet keeps everyone signed up for a role that was only renamed.
    """
    title = _clean_text(body.get('title'), TITLE_MAX)
    if not title:
        return None, 'Give the sheet a title.'
    try:
        date = datetime.datetime.strptime(str(body.get('date') or ''), '%Y-%m-%dT%H:%M')
    except ValueError:
        return None, 'Pick a date and time.'
    raw_roles = body.get('roles') if isinstance(body.get('roles'), list) else []
    old_keys = {r['key'] for r in old_roles}
    roles, taken = [], set()
    for raw in raw_roles[:ROLES_MAX]:
        if not isinstance(raw, dict):
            continue
        name = _clean_text(raw.get('name'), ROLE_NAME_MAX)
        if not name:
            continue
        try:
            slots = int(raw.get('slots') or 0)
        except (TypeError, ValueError):
            slots = 0
        if not 1 <= slots <= SLOTS_MAX:
            return None, f'{name} needs between 1 and {SLOTS_MAX} spots.'
        key = str(raw.get('key') or '')
        if key not in old_keys or key in taken:
            key = _role_key(name, taken | old_keys)
        taken.add(key)
        roles.append({'key': key, 'name': name, 'slots': slots, 'prompt': _clean_text(raw.get('prompt'), PROMPT_MAX)})
    if not roles:
        return None, 'Add at least one role, like Baker or Seller.'
    details = str(body.get('details') or '').replace('\r\n', '\n').strip()[:DETAILS_MAX]
    return {'title': title, 'date': date, 'location': _clean_text(body.get('location'), LOCATION_MAX),
            'details': details, 'roles': roles}, None


# Anything named like a bake sale counts, whatever type it was scheduled as.
BAKE_SALE_NAME = re.compile(r'\bbake[\s-]*sales?\b', re.I)


def is_bake_sale(kind, name):
    return kind == 'bake_sale' or bool(BAKE_SALE_NAME.search(name or ''))


def _when(value):
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M') if value else None
    except (TypeError, ValueError):
        return None


def bake_sale_sources(event_rows, fundraiser_entries, since):
    """{source key: {title, date, location, details}} for every bake sale from `since` on.

    A bake sale is a calendar event of the Bake sale type (or named like one), or a
    fundraiser named like one. Events are keyed by their id, fundraisers (which have no
    id) by 'fundraiser:' and their start time.
    """
    sources = {}
    for row in event_rows:
        date = row.get('date')
        if isinstance(date, datetime.datetime) and date >= since and is_bake_sale(row.get('kind'), row.get('name')):
            sources[str(row['_id'])] = _source(row.get('name'), date, row.get('location'), row.get('details'))
    for entry in fundraiser_entries or ():
        start = _when(entry.get('starts'))
        end = _when(entry.get('ends')) or start
        if start and not entry.get('hidden') and max(start, end) >= since and is_bake_sale(None, entry.get('name')):
            sources[f"fundraiser:{entry['starts']}"] = _source(entry['name'], start, entry.get('location'),
                                                               entry.get('description'))
    return sources


def _source(name, date, location, details):
    return {'title': _clean_text(name, TITLE_MAX), 'date': date.replace(tzinfo=None),
            'location': _clean_text(location, LOCATION_MAX),
            'details': str(details or '').replace('\r\n', '\n').strip()[:DETAILS_MAX]}


def new_event_sheet(source, key):
    """A fresh sheet for a bake sale, with its Baker and Seller roles and nobody on them yet.

    `synced` remembers what the sheet last took from its bake sale, so the sheet only
    follows the bake sale when that changes, and an editor's own changes stick otherwise.
    """
    taken, roles = set(), []
    for role in EVENT_SHEET_ROLES:
        role_key = _role_key(role['name'], taken)
        taken.add(role_key)
        roles.append(dict(role, key=role_key))
    return dict(source, roles=roles, signups={}, event_id=key, synced=source)


def reconcile_bake_sales(sources, sheets, dismissed):
    """(new sheets, {sheet _id: fields to set}, sheet _ids to delete) to match `sheets` to `sources`.

    `sheets` are the upcoming sheets made for a bake sale; `dismissed` are source keys whose
    sheet an editor deleted, which are never made again. A sheet whose bake sale is gone
    is deleted while nobody is on it, and kept otherwise.
    """
    by_key = {s['event_id']: s for s in sheets}
    new, updates, deletes = [], {}, []
    for key, source in sources.items():
        sheet = by_key.pop(key, None)
        if sheet is None:
            if key not in dismissed:
                new.append(new_event_sheet(source, key))
        elif sheet.get('synced') != source:
            old = sheet.get('synced') or {}
            changed = {f: v for f, v in source.items() if old.get(f) != v}
            updates[sheet['_id']] = dict(changed, synced=source)
    for sheet in by_key.values():
        if not signup_user_ids([sheet]):
            deletes.append(sheet['_id'])
    return new, updates, deletes


def is_open(sheet, now):
    """Sign-ups stay open until the end of the sheet's day."""
    return isinstance(sheet.get('date'), datetime.datetime) and sheet['date'].date() >= now.date()


def role_view(sheet, names, viewer_id):
    """Each role with who signed up: [{key, name, slots, prompt, people, taken, full, mine}]."""
    signups = sheet.get('signups') or {}
    roles = []
    for role in sheet.get('roles') or ():
        people = [{'user_id': s['user_id'], 'name': names[s['user_id']], 'note': s.get('note') or ''}
                  for s in signups.get(role['key']) or () if s.get('user_id') in names]
        mine = next((p for p in people if p['user_id'] == viewer_id), None)
        roles.append(dict(role, people=people, taken=len(people), full=len(people) >= role['slots'],
                          mine=mine, open_slots=max(0, role['slots'] - len(people))))
    return roles


def fill(roles):
    """(spots taken, spots total) over a sheet's roles."""
    return sum(min(r['taken'], r['slots']) for r in roles), sum(r['slots'] for r in roles)


def signup_user_ids(sheets):
    """Every user id signed up on these sheets, for one name lookup."""
    return {s.get('user_id') for sheet in sheets for rows in (sheet.get('signups') or {}).values() for s in rows}


def at_clock(day, value):
    """`day` at 'HH:MM', or None when `value` is empty. Raises ValueError on a bad time."""
    value = str(value or '').strip()
    if not value:
        return None
    return datetime.datetime.combine(day, datetime.datetime.strptime(value, '%H:%M').time())
