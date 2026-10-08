"""The events page: one calendar built from events, fundraisers and weekly meetings.

Every source becomes the same item dict, so the month grid, the "Coming up" list,
Google Calendar links and the iCalendar feed treat them alike:

    {source, id, kind, label, icon, name, start, end, location, link, link_label, details}

`start` and `end` are naive datetimes in club wall-clock time, like the rest of the site.

This module is pure: no Flask app, no database. api/index.py wires the routes.
"""
import calendar
import datetime
from urllib.parse import urlencode

# Kinds an admin can give an event: key -> (name, lucide icon).
KINDS = {
    'competition': ('Competition', 'trophy'),
    'scrimmage': ('Scrimmage', 'swords'),
    'outreach': ('Outreach', 'megaphone'),
    'club': ('Club event', 'party-popper'),
}
DEFAULT_KIND = 'competition'
# Kinds the homepage countdown, the Member Hub and the competition log count as competitions.
COMPETITIVE_KINDS = ('competition', 'scrimmage')
# Every kind the calendar shows, in filter-chip order.
ALL_KINDS = dict(KINDS, fundraiser=('Fundraiser', 'piggy-bank'), meeting=('Meeting', 'calendar-clock'))
# Events store only a start time; tournaments run all day, the rest are an afternoon.
DURATION_HOURS = {'competition': 8, 'scrimmage': 6, 'outreach': 2, 'club': 2}
DETAILS_MAX = 300


def competitive_query():
    """Mongo filter for competitive events. Rows saved before kinds existed are competitions."""
    return {'kind': {'$in': [None, *COMPETITIVE_KINDS]}}


def kind_of(event):
    kind = event.get('kind')
    return kind if kind in KINDS else DEFAULT_KIND


def _item(source, kind, name, start, end, **extra):
    label, icon = ALL_KINDS[kind]
    item = {'source': source, 'id': '', 'kind': kind, 'label': label, 'icon': icon, 'name': name,
            'start': start, 'end': end, 'location': '', 'link': '', 'link_label': '', 'details': '',
            'all_day': False}
    item.update({k: v or '' for k, v in extra.items()})
    return item


def event_item(event):
    """A row from the competitions collection, or None when it has no date."""
    start = event.get('date')
    if not isinstance(start, datetime.datetime) or not event.get('name'):
        return None
    start = start.replace(tzinfo=None)
    kind = kind_of(event)
    return _item('event', kind, event['name'], start, start + datetime.timedelta(hours=DURATION_HOURS[kind]),
                 id=str(event.get('_id') or ''), location=event.get('location'), link=event.get('link'),
                 details=event.get('details'))


def _moment(value):
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M') if value else None
    except (TypeError, ValueError):
        return None


def fundraiser_items(entries):
    """Published fundraisers from Site settings. One without an end runs to the end of its first day."""
    items = []
    for n, entry in enumerate(entries or ()):
        start = _moment(entry.get('starts'))
        if entry.get('hidden') or not entry.get('name') or not start:
            continue
        end = _moment(entry.get('ends'))
        if not end or end < start:
            end = start.replace(hour=23, minute=59)
        items.append(_item('fundraiser', 'fundraiser', entry['name'], start, end, id=f'fundraiser-{n}',
                           location=entry.get('location'), link=entry.get('link_url'),
                           link_label=entry.get('link_label'), details=entry.get('description')))
    return items


def history_items(history):
    """Past fundraisers typed in by date only: all-day items."""
    items = []
    for n, row in enumerate(history or ()):
        start = _moment(f"{row.get('date')}T00:00")
        if not row.get('name') or not start:
            continue
        item = _item('fundraiser', 'fundraiser', row['name'], start, start.replace(hour=23, minute=59),
                     id=f'past-fundraiser-{n}', details=row.get('description'))
        item['all_day'] = True
        items.append(item)
    return items


def meeting_items(meeting, first, last, name='Club meeting'):
    """One item per meeting day from `first` to `last` (dates, inclusive).

    DAY_NAMES in site_content starts on Sunday and Python's weekday() on Monday, hence the shift.
    """
    days = set(meeting.get('days') or ())
    if not days:
        return []
    (sh, sm), (eh, em) = (map(int, meeting[k].split(':')) for k in ('start', 'end'))
    items, day = [], first
    while day <= last:
        if (day.weekday() + 1) % 7 in days:
            start = datetime.datetime.combine(day, datetime.time(sh, sm))
            end = datetime.datetime.combine(day, datetime.time(eh, em))
            items.append(_item('meeting', 'meeting', name, start, max(end, start),
                               id=f'meeting-{day.isoformat()}', location=meeting.get('room')))
        day += datetime.timedelta(days=1)
    return items


def sort_items(items):
    return sorted(items, key=lambda i: (i['start'], i['name'].lower()))


# --- Month grid ---------------------------------------------------------------------

def parse_month(value, today):
    """(year, month) from '2026-10', or today's month when missing or out of range."""
    try:
        year, month = (int(p) for p in (value or '').split('-'))
        if 2000 <= year <= 2100 and 1 <= month <= 12:
            return year, month
    except ValueError:
        pass
    return today.year, today.month


def shift_month(year, month, by):
    index = year * 12 + month - 1 + by
    return index // 12, index % 12 + 1


def grid_bounds(year, month):
    """First and last date shown on the month grid: whole weeks, Sunday first."""
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
    return weeks[0][0], weeks[-1][-1]


def month_weeks(year, month, items, today):
    """The month as weeks of day cells: {date, in_month, today, past, items}.

    An item that spans several days (a weekend fundraiser) sits on each of them.
    """
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
    by_day = {}
    for item in sort_items(items):
        day, last = item['start'].date(), max(item['end'], item['start']).date()
        while day <= last:
            by_day.setdefault(day, []).append(item)
            day += datetime.timedelta(days=1)
    return [[{'date': d, 'in_month': d.month == month, 'today': d == today, 'past': d < today,
              'items': by_day.get(d, [])} for d in week] for week in weeks]


def by_month(items):
    """[(first day of month, items)] in date order, for the "Coming up" list."""
    groups = []
    for item in sort_items(items):
        key = item['start'].date().replace(day=1)
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(item)
    return groups


PLURALS = {'competition': 'Competitions', 'scrimmage': 'Scrimmages', 'outreach': 'Outreach',
           'club': 'Club events', 'fundraiser': 'Fundraisers', 'meeting': 'Meetings'}


def kinds_present(items):
    """[(kind, name, icon, plural)] for the kinds among `items`, in ALL_KINDS order: chips and key."""
    present = {item['kind'] for item in items}
    return [(kind, *ALL_KINDS[kind], PLURALS[kind]) for kind in ALL_KINDS if kind in present]


# --- Calendar apps ------------------------------------------------------------------

def _stamp(moment):
    return moment.strftime('%Y%m%dT%H%M%S')


def google_url(item, timezone):
    """A Google Calendar "add event" link, in club time."""
    if item['all_day']:
        dates = f"{item['start']:%Y%m%d}/{item['end'].date() + datetime.timedelta(days=1):%Y%m%d}"
    else:
        dates = f"{_stamp(item['start'])}/{_stamp(item['end'])}"
    params = {'action': 'TEMPLATE', 'text': item['name'], 'dates': dates, 'ctz': timezone}
    details = '\n\n'.join(p for p in (item['details'], item['link']) if p)
    if details:
        params['details'] = details
    if item['location']:
        params['location'] = item['location']
    return 'https://calendar.google.com/calendar/render?' + urlencode(params)


def maps_url(location):
    return 'https://www.google.com/maps/search/?' + urlencode({'api': 1, 'query': location}) if location else ''


def _ics_text(value):
    return (str(value).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\n').replace('\n', '\\n'))


def _fold(line):
    """Lines longer than 75 octets continue on the next line after a space (RFC 5545 §3.1)."""
    raw = line.encode('utf-8')
    if len(raw) <= 75:
        return line
    parts, chunk = [], b''
    for char in line:
        encoded = char.encode('utf-8')
        if len(chunk) + len(encoded) > (75 if not parts else 74):
            parts.append(chunk.decode('utf-8'))
            chunk = b''
        chunk += encoded
    parts.append(chunk.decode('utf-8'))
    return '\r\n '.join(parts)


def _vevent(item, uid, timezone, now, rrule=None):
    if item['all_day']:
        # DTEND of an all-day event is the day after (exclusive).
        when = [f'DTSTART;VALUE=DATE:{item["start"]:%Y%m%d}',
                f'DTEND;VALUE=DATE:{item["end"].date() + datetime.timedelta(days=1):%Y%m%d}']
    else:
        when = [f'DTSTART;TZID={timezone}:{_stamp(item["start"])}', f'DTEND;TZID={timezone}:{_stamp(item["end"])}']
    lines = ['BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{now.strftime("%Y%m%dT%H%M%SZ")}', *when,
             f'SUMMARY:{_ics_text(item["name"])}',
             f'CATEGORIES:{_ics_text(item["label"])}']
    if rrule:
        lines.append(f'RRULE:{rrule}')
    if item['location']:
        lines.append(f'LOCATION:{_ics_text(item["location"])}')
    if item['details']:
        lines.append(f'DESCRIPTION:{_ics_text(item["details"])}')
    if item['link'] and item['link'].startswith('http'):
        lines.append(f'URL:{item["link"]}')
    return lines + ['END:VEVENT']


ICS_DAYS = ('SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA')


def ics_calendar(name, items, host, timezone, now_utc, meeting=None, meeting_name='Club meeting',
                 meeting_from=None):
    """An iCalendar (RFC 5545) document.

    Times carry the club's IANA time zone name, which Google, Apple and Outlook all
    resolve. With `meeting`, the weekly meetings are one repeating event starting
    on `meeting_from` (a date), instead of hundreds of copies.
    """
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', f'PRODID:-//{_ics_text(host)}//Events//EN', 'CALSCALE:GREGORIAN',
             'METHOD:PUBLISH', f'X-WR-CALNAME:{_ics_text(name)}', f'X-WR-TIMEZONE:{timezone}',
             'REFRESH-INTERVAL;VALUE=DURATION:PT12H', 'X-PUBLISHED-TTL:PT12H']
    for item in sort_items(items):
        lines += _vevent(item, f'{item["id"] or _stamp(item["start"])}@{host}', timezone, now_utc)
    days = sorted(set((meeting or {}).get('days') or ()))
    if days and meeting_from:
        # The first meeting day on or after meeting_from anchors the rule.
        first = next(meeting_from + datetime.timedelta(days=n) for n in range(7)
                     if ((meeting_from + datetime.timedelta(days=n)).weekday() + 1) % 7 in days)
        item = meeting_items(meeting, first, first, meeting_name)[0]
        rule = 'FREQ=WEEKLY;BYDAY=' + ','.join(ICS_DAYS[d] for d in days)
        lines += _vevent(item, f'weekly-meeting@{host}', timezone, now_utc, rrule=rule)
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'
