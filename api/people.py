"""Member pages (/people/<id>): what a member writes about themselves, checked and shaped.

The page is the member's own: an about blurb and skills, links, a list of honors
(awards, leadership, outreach hours, certifications) they can point a college at,
a photo wall, and drafts of the Common App activity lines. Everything a member
sends comes through clean_section(), which trims, caps and drops what does not
fit, so the stored `profile` dict on the user is always safe to render.

Team history, team awards and events come from the club's own records (rosters,
award counters, RSVPs) in api/index.py; this module never invents those.
"""
import datetime
import re

# Who can open a member's page. Members are mostly minors, so a page starts
# visible to signed-in club members only; the member can make it public to
# share the link (a college application, a résumé).
VISIBILITY = ('members', 'public')
DEFAULT_VISIBILITY = 'members'

HEADLINE_MAX = 80
BIO_MAX = 800
SKILL_MAX = 30
SKILLS_MAX = 12
LINK_LABEL_MAX = 30
URL_MAX = 300
LINKS_MAX = 6
HONOR_TITLE_MAX = 100
HONOR_TEXT_MAX = 100
HONOR_WHEN_MAX = 30
HONOR_TEAM_MAX = 40
HONOR_NOTE_MAX = 240
HONORS_MAX = 40
HONOR_HOURS_MAX = 5000
PINNED_MAX = 3
PHOTOS_MAX = 12
CAPTION_MAX = 120
# The Common App's own limits for an activity's position and description.
POSITION_MAX = 50
ACTIVITY_MAX = 150

# kind -> (label, Lucide icon). Order is the order the page lists them in.
HONOR_KINDS = {
    'award': ('Awards', 'trophy'),
    'leadership': ('Leadership', 'flag'),
    'outreach': ('Outreach & service', 'heart-handshake'),
    'certification': ('Certifications', 'badge-check'),
    'other': ('Other honors', 'star'),
}

SKILL_SUGGESTIONS = ('CAD', 'Programming', 'Driving', 'Building', 'Strategy', 'Scouting', 'Notebook',
                     'Electronics', 'Photography', 'Video editing', 'Outreach', 'Fundraising',
                     'Public speaking', 'Graphic design', 'Leadership')

# Hostname fragment -> Lucide icon for a link. Anything else gets a globe.
LINK_ICONS = (('github.', 'github'), ('gitlab.', 'code'), ('linkedin.', 'linkedin'),
              ('youtube.', 'youtube'), ('youtu.be', 'youtube'), ('instagram.', 'instagram'),
              ('twitter.', 'twitter'), ('x.com', 'twitter'), ('docs.google.', 'notebook-pen'),
              ('drive.google.', 'folder'), ('onshape.', 'drafting-compass'))

GRAD_YEAR_RANGE = (2000, 2100)


class ProfileError(ValueError):
    """A message for the member about what they sent; safe to show."""


def _text(value, limit, label, required=False):
    text = ' '.join(value.split()) if isinstance(value, str) else ''
    if required and not text:
        raise ProfileError(f'{label} cannot be empty.')
    if len(text) > limit:
        raise ProfileError(f'{label} must be {limit} characters or fewer.')
    return text


def _paragraphs(value, limit, label):
    """Free text that keeps its line breaks (at most one blank line between paragraphs)."""
    text = value.replace('\r\n', '\n').strip() if isinstance(value, str) else ''
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(' '.join(line.split()) for line in text.split('\n')))
    if len(text) > limit:
        raise ProfileError(f'{label} must be {limit} characters or fewer.')
    return text


def _url(value, label):
    text = _text(value, URL_MAX, label)
    if text and not re.match(r'https?://[^\s/]+\.[^\s]+', text, re.IGNORECASE):
        raise ProfileError(f'{label} must be a full web address starting with https://.')
    return text


def _list(value, label, most):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileError(f'{label} must be a list.')
    if len(value) > most:
        raise ProfileError(f'Keep {label.lower()} to {most} or fewer.')
    return value


def _grad_year(value):
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    if not text.isdigit() or not GRAD_YEAR_RANGE[0] <= int(text) <= GRAD_YEAR_RANGE[1]:
        raise ProfileError('Class of must be a four-digit year.')
    return int(text)


def _hours(value):
    text = str(value if value is not None else '').strip()
    if not text:
        return 0
    try:
        hours = float(text)
    except ValueError:
        raise ProfileError('Hours must be a number.') from None
    if not 0 <= hours <= HONOR_HOURS_MAX:
        raise ProfileError(f'Hours must be between 0 and {HONOR_HOURS_MAX}.')
    # Half hours are as fine as anyone logs them.
    return round(hours * 2) / 2


def clean_about(data):
    skills, seen = [], set()
    for raw in _list(data.get('skills'), 'Skills', SKILLS_MAX):
        skill = _text(raw, SKILL_MAX, 'A skill')
        if skill and skill.lower() not in seen:
            seen.add(skill.lower())
            skills.append(skill)
    visibility = data.get('visibility', DEFAULT_VISIBILITY)
    if visibility not in VISIBILITY:
        raise ProfileError('Pick who can see your page.')
    return {'headline': _text(data.get('headline'), HEADLINE_MAX, 'Headline'),
            'bio': _paragraphs(data.get('bio'), BIO_MAX, 'About me'),
            'grad_year': _grad_year(data.get('grad_year')),
            'skills': skills, 'visibility': visibility}


def clean_links(data):
    links = []
    for row in _list(data.get('links'), 'Links', LINKS_MAX):
        row = row if isinstance(row, dict) else {}
        url = _url(row.get('url'), 'Each link')
        label = _text(row.get('label'), LINK_LABEL_MAX, 'A link name')
        if url:
            links.append({'label': label, 'url': url})
    return {'links': links}


def clean_honors(data):
    honors = []
    for row in _list(data.get('honors'), 'Honors', HONORS_MAX):
        row = row if isinstance(row, dict) else {}
        title = _text(row.get('title'), HONOR_TITLE_MAX, 'Each honor name')
        if not title:
            continue  # a row left blank is just skipped
        kind = row.get('kind') if row.get('kind') in HONOR_KINDS else 'other'
        honors.append({'kind': kind, 'title': title,
                       'event': _text(row.get('event'), HONOR_TEXT_MAX, 'Event or organisation'),
                       'when': _text(row.get('when'), HONOR_WHEN_MAX, 'When'),
                       'team': _text(row.get('team'), HONOR_TEAM_MAX, 'Team'),
                       'hours': _hours(row.get('hours')),
                       'link': _url(row.get('link'), 'Proof link'),
                       'note': _text(row.get('note'), HONOR_NOTE_MAX, 'Note'),
                       'pinned': bool(row.get('pinned'))})
    if sum(h['pinned'] for h in honors) > PINNED_MAX:
        raise ProfileError(f'Pin up to {PINNED_MAX} highlights.')
    return {'honors': honors}


def clean_activity(data):
    return {'position': _text(data.get('position'), POSITION_MAX, 'Position'),
            'activity': _text(data.get('activity'), ACTIVITY_MAX, 'Description')}


def clean_photos(data, stored):
    """Captions and order for photos already on the page. Paths the page does not
    hold are ignored, so this can never point the page at someone else's file."""
    have = {p['path'] for p in stored}
    photos, seen = [], set()
    for row in _list(data.get('photos'), 'Photos', PHOTOS_MAX):
        row = row if isinstance(row, dict) else {}
        path = row.get('path')
        if path in have and path not in seen:
            seen.add(path)
            photos.append({'path': path, 'caption': _text(row.get('caption'), CAPTION_MAX, 'A caption')})
    # A photo missing from the request (an older tab, say) stays rather than vanishing.
    photos += [p for p in stored if p['path'] not in seen]
    return {'photos': photos}


SECTIONS = {'about': clean_about, 'links': clean_links, 'honors': clean_honors, 'activity': clean_activity}


def clean_section(section, data, stored_profile):
    """Fields to save for one section of the page, or ProfileError."""
    if not isinstance(data, dict):
        raise ProfileError('That request could not be understood.')
    if section == 'photos':
        return clean_photos(data, profile_view(stored_profile)['photos'])
    if section not in SECTIONS:
        raise ProfileError('That part of the page does not exist.')
    return SECTIONS[section](data)


def profile_view(profile):
    """A stored profile with every field present, whatever an older version saved."""
    p = profile if isinstance(profile, dict) else {}
    honors = [{'kind': h.get('kind') if h.get('kind') in HONOR_KINDS else 'other', 'title': str(h['title']),
               **{k: str(h.get(k) or '') for k in ('event', 'when', 'team', 'link', 'note')},
               'hours': h.get('hours') if isinstance(h.get('hours'), (int, float)) else 0,
               'pinned': bool(h.get('pinned'))}
              for h in p.get('honors') or [] if isinstance(h, dict) and h.get('title')]
    return {
        'headline': p.get('headline') or '', 'bio': p.get('bio') or '',
        'grad_year': p.get('grad_year'), 'skills': list(p.get('skills') or []),
        'visibility': p.get('visibility') if p.get('visibility') in VISIBILITY else DEFAULT_VISIBILITY,
        'links': [dict(link, icon=link_icon(link.get('url')))
                  for link in p.get('links') or [] if isinstance(link, dict) and link.get('url')],
        'honors': honors,
        'photos': [ph for ph in p.get('photos') or [] if isinstance(ph, dict) and ph.get('path')],
        'position': p.get('position') or '', 'activity': p.get('activity') or '',
    }


def link_icon(url):
    host = re.sub(r'^https?://(www\.)?', '', str(url or '').lower()).split('/')[0]
    return next((icon for fragment, icon in LINK_ICONS if fragment in host), 'globe')


def link_label(link):
    """What a link shows: its name, else the bare host."""
    return link.get('label') or re.sub(r'^https?://(www\.)?', '', link['url']).split('/')[0]


def honor_groups(honors):
    """[(kind, label, icon, honors)] in HONOR_KINDS order, empty kinds left out."""
    return [(kind, label, icon, [h for h in honors if h['kind'] == kind])
            for kind, (label, icon) in HONOR_KINDS.items() if any(h['kind'] == kind for h in honors)]


def season_start(label):
    """2025 for '2025-26'; None for a blank or odd label."""
    head = str(label or '')[:4]
    return int(head) if head.isdigit() else None


def tenure(seasons):
    """(first season's start year, number of seasons) from account_history seasons."""
    years = [y for y in (season_start(s['season']) for s in seasons) if y]
    return (min(years) if years else None), len([s for s in seasons if s['season']])


def team_moves(seasons):
    """Mark each season whose robot team differs from the season before it.

    seasons come newest first; a season gets `moved_from` (the earlier team's label)
    and `moved_to` (the team they joined) when the person's robot team changed going
    into it. Timelines show that as a transfer, so a switch of teams reads as a story.
    """
    previous = None
    for s in reversed(seasons):
        robots = [t['label'] for t in s['teams'] if not t['group']]
        moved = bool(robots and previous and previous not in robots)
        s['moved_from'] = previous if moved else None
        s['moved_to'] = robots[0] if moved else None
        if robots:
            previous = robots[0]
    return seasons


def _clip(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(' ', 1)[0].rstrip(',;:·-– ')
    return cut + '…'


def activity_draft(club_name, history, profile):
    """A first draft of the Common App activity lines, from the member's own records.

    position (≤50): newest roles and team, e.g. "Captain & Programmer, Team 77628B".
    activity (≤150): seasons, teams and the honors they pinned or listed first.
    The member edits these; a saved version always wins over the draft.
    """
    seasons = [s for s in history['seasons'] if s['teams']]
    roles, team = [], ''
    for s in seasons:
        for t in s['teams']:
            if not t['group'] and not team:
                team = t['label']
            roles += [r for r in t['roles'] if r not in roles]
        if roles:
            break
    who = ' & '.join(roles[:2]) or 'Member'
    position = _clip(f'{who}, Team {team}' if team else f'{who}, {club_name}', POSITION_MAX)

    first, count = tenure(history['seasons'])
    honors = profile['honors']
    picked = [h['title'] for h in honors if h['pinned']] or [h['title'] for h in honors if h['kind'] == 'award']
    hours = sum(h['hours'] for h in honors)
    parts = [f'Competed in VEX Robotics for {count} season{"s" if count != 1 else ""}' if count
             else 'VEX Robotics team member']
    if hours:
        parts.append(f'{hours:g} outreach hours')
    if picked:
        parts.append('won ' + ', '.join(picked[:2]))
    return {'position': position, 'activity': _clip('; '.join(parts) + '.', ACTIVITY_MAX), 'since': first}


def stats(history, profile, show_events):
    """The hero's number strip. Events only for signed-in viewers (RSVPs are members-only)."""
    first, count = tenure(history['seasons'])
    honors = profile['honors']
    rows = [('Seasons', count), ('Teams', history['team_count']),
            ('Honors', len(honors))]
    hours = sum(h['hours'] for h in honors)
    if hours:
        rows.append(('Hours', f'{hours:g}'))
    if show_events:
        rows.append(('Events', history['went_total']))
    return rows


def years_in(first_year, now=None):
    """'3rd year' style label for how long someone has been in the club."""
    if not first_year:
        return ''
    now = now or datetime.date.today()
    # Seasons start in late spring, as elsewhere on the site.
    current = now.year - (now.month < 5)
    n = max(1, current - first_year + 1)
    suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix} year'
