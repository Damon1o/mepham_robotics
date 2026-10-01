import os
import json
import re
import datetime
import urllib.parse
import hashlib
import hmac
import time
import threading
import csv
from io import StringIO
import math
import secrets
import string
import logging
from functools import wraps
from bson import ObjectId
import bcrypt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, abort, g, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import requests
import mimetypes

try:  # package import on Vercel, flat import when run from the api/ directory
    from api import robotevents, site_content
except ImportError:  # pragma: no cover
    import robotevents
    import site_content

load_dotenv()

logger = logging.getLogger(__name__)

# Vercel Blob configuration
BLOB_READ_WRITE_TOKEN = os.getenv('BLOB_READ_WRITE_TOKEN')
BLOB_BASE_URL = 'https://blob.vercel-storage.com'

def upload_to_vercel_blob(file, filename=None):
    """Upload a file to Vercel Blob storage"""
    if not BLOB_READ_WRITE_TOKEN:
        raise ValueError("BLOB_READ_WRITE_TOKEN environment variable is not set")

    if filename is None:
        filename = secure_filename(file.filename)

    # Get file content type
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # Read file data
    file_data = file.read()

    # Upload to Vercel Blob using PUT request
    # Format: PUT https://blob.vercel-storage.com/{filename}
    headers = {
        'Authorization': f'Bearer {BLOB_READ_WRITE_TOKEN}',
        'Content-Type': content_type,
    }

    response = requests.put(
        f'{BLOB_BASE_URL}/{filename}',
        headers=headers,
        data=file_data
    )

    if response.status_code == 200:
        result = response.json()
        return result.get('url')
    else:
        # The response body is logged, not raised: it lands in an admin flash
        # message otherwise, and Blob error bodies can echo request details.
        logger.error('Vercel Blob upload failed: %s %s', response.status_code, response.text[:500])
        raise RuntimeError(f'Blob upload failed with status {response.status_code}')

def delete_from_vercel_blob(url):
    """Delete a file from Vercel Blob storage"""
    if not BLOB_READ_WRITE_TOKEN:
        raise ValueError("BLOB_READ_WRITE_TOKEN environment variable is not set")

    # Extract blob ID from URL
    # Vercel Blob URLs are like: https://<bucket>.public.blob.vercel-storage.com/<filename>-<random>
    # We need to extract the full blob ID (filename with random suffix)
    blob_id = url.split('/')[-1]

    headers = {
        'Authorization': f'Bearer {BLOB_READ_WRITE_TOKEN}',
    }

    # Delete from Vercel Blob using DELETE request
    response = requests.delete(
        f'{BLOB_BASE_URL}/{blob_id}',
        headers=headers
    )

    if response.status_code != 200:
        logger.warning('Failed to delete blob %s: %s %s', url, response.status_code, response.text[:500])

# Resolve absolute paths so Vercel can find templates/static regardless of working directory
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_root, 'templates'),
            static_folder=os.path.join(_root, 'static'))
_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    if os.getenv('VERCEL'):
        raise RuntimeError(
            'SECRET_KEY environment variable is not set. Refusing to start on Vercel '
            'with the insecure dev fallback key.'
        )
    _secret_key = 'dev-fallback-key'
app.secret_key = _secret_key
if os.getenv('VERCEL') and not os.getenv('MONGO_URI'):
    # Fail the deploy loudly instead of returning a 500 from every request.
    raise RuntimeError('MONGO_URI environment variable is not set.')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.getenv('VERCEL')),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=30),
)
# Refuse oversized request bodies before they are buffered into memory.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES
# Event times and the meeting schedule are club wall-clock time.
CLUB_TIMEZONE = os.getenv('CLUB_TIMEZONE', 'America/New_York')

@app.template_filter('collapse_ws')
def collapse_whitespace(value):
    """Collapse newlines/indentation from wrapped Jinja block text so it's safe inside a single HTML attribute (og:*, twitter:*, meta description)."""
    return ' '.join(str(value).split())

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

LEADERSHIP_KEYWORDS = ('captain', 'lead', 'president', 'mentor', 'director')


@app.template_filter('member_roles')
def member_roles(member):
    """Every role a member holds: the main 'role' first, then the other 'roles', no repeats."""
    roles, seen = [], set()
    for role in [member.get('role') or '', *(member.get('roles') or [])]:
        role = str(role).strip()
        if role and role.lower() not in seen:
            seen.add(role.lower())
            roles.append(role)
    return roles


def _is_leadership(member):
    text = ' '.join(member_roles(member)).lower()
    return any(word in text for word in LEADERSHIP_KEYWORDS)


@app.template_filter('roster_groups')
def roster_groups(members):
    """Members grouped by sub-team, leadership first inside each group.

    Groups keep the order the sub-teams first appear in, and members with no
    sub-team fall into a single trailing group with an empty name, so a team
    that never filled the field still renders as one plain grid.
    """
    order, grouped = [], {}
    for member in members or []:
        key = (member.get('subteam') or '').strip()
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(member)

    order.sort(key=lambda k: (k == '', k))
    return [(key, sorted(grouped[key], key=lambda m: not _is_leadership(m))) for key in order]


# Members saved before this revamp carry a default photo path that was never a real
# file (the placeholder actually lives at assets/other/base.png), so those rows are
# treated as having no photo and fall through to the initials avatar.
PLACEHOLDER_PHOTOS = ('assets/profile/base.png', 'assets/other/base.png')


@app.template_filter('real_photo')
def real_photo(path):
    if not path:
        return ''
    return '' if any(p in path for p in PLACEHOLDER_PHOTOS) else path


@app.template_filter('initials')
def initials(name):
    parts = [p for p in str(name or '').split() if p]
    if not parts:
        return '?'
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper()


ROMAN_NUMERALS = ((10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'))


@app.template_filter('roman')
def roman(number):
    """An award count as the Honor Plaque engraves it: I to XX, then plain digits."""
    number = int(number or 0)
    if not 0 < number <= 20:
        return str(number)
    out = ''
    for value, letters in ROMAN_NUMERALS:
        while number >= value:
            out += letters
            number -= value
    return out


def file_extension(filename):
    """Lowercase extension without the dot, or '' when there isn't one."""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def blob_path(*segments):
    """Build a Vercel Blob key from untrusted segments.

    Every segment is run through secure_filename so a crafted team number,
    member name or sponsor name cannot escape its folder (``../``) or inject
    extra path separators into the blob key.
    """
    safe = [secure_filename(str(seg)) or 'file' for seg in segments]
    return '/'.join(safe)

class UserFacingError(ValueError):
    """An error whose message is written for the admin and safe to show."""


def checked_upload(file, *segments, allowed, stem='file'):
    """Validate an uploaded file's extension, then store it under a safe key.

    Raises ValueError for a rejected extension so the caller's error handling
    surfaces it to the admin instead of writing an attacker-named blob.
    """
    ext = file_extension(file.filename or '')
    if ext not in allowed:
        raise UserFacingError(
            f'"{file.filename}" is not an accepted file type '
            f'({", ".join(sorted(allowed))}).')
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return upload_to_vercel_blob(file, blob_path(*segments, f'{stem}_{stamp}.{ext}'))

def get_time_ago(timestamp):
    """Convert timestamp to human-readable time ago string"""
    now = _utcnow()
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    diff = now - timestamp
    if diff.total_seconds() < 0:
        return "Just now"

    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"

def log_activity(activity_type, description, user=None, details=None):
    """Log an activity to the database"""
    try:
        activity = {
            'type': activity_type,
            'description': description,
            'user': user or (session.get('user') if 'user' in session else 'System'),
            'timestamp': _utcnow(),
            'details': details or {}
        }
        db['activities'].insert_one(activity)
    except Exception:
        logger.exception('Failed to log activity %s', activity_type)

AWARD_STYLE_KEYS = ('title', 'icon', 'layout', 'border', 'shimmer', 'sort')
AWARD_ORDER = [('sort', 1), ('_id', 1)]


def _award_copy(category, team_number):
    """A team's counter for one global award category, starting at 0."""
    doc = {k: category.get(k) for k in AWARD_STYLE_KEYS}
    doc.update(team_number=team_number, category_id=str(category['_id']), count=0)
    return doc


def link_team_award_categories():
    """Point team award rows at their global category (matched by title) so renames reach them.

    Rows made before categories were editable carry only a copy of the title.
    Cheap to repeat: it only touches rows that still lack a category_id.
    """
    unlinked = list(db['awards'].find({'team_number': {'$exists': True}, 'category_id': {'$exists': False}},
                                      {'title': 1}))
    if not unlinked:
        return
    by_title = {a.get('title'): str(a['_id']) for a in db['awards'].find({'team_number': {'$exists': False}},
                                                                          {'title': 1})}
    for row in unlinked:
        if row.get('title') in by_title:
            db['awards'].update_one({'_id': row['_id']}, {'$set': {'category_id': by_title[row['title']]}})


def seed_team_awards(team_number):
    """Give a team its own counter for every award category it is missing, starting at 0."""
    link_team_award_categories()
    have = {a.get('category_id') for a in db['awards'].find({'team_number': team_number}, {'category_id': 1})}
    new_docs = [_award_copy(a, team_number)
                for a in db['awards'].find({'team_number': {'$exists': False}})
                if str(a['_id']) not in have]
    if new_docs:
        db['awards'].insert_many(new_docs)

# type -> (icon, title, filter group). The group drives the Activity tab's filter chips.
ACTIVITY_TYPES = {
    'stats_update': ('📊', 'Statistics updated', 'site'),
    'competition_add': ('📅', 'Event scheduled', 'events'),
    'competition_update': ('✏️', 'Event updated', 'events'),
    'competition_delete': ('🗑️', 'Event deleted', 'events'),
    'team_add': ('🤖', 'Team added', 'teams'),
    'team_update': ('⚙️', 'Team updated', 'teams'),
    'team_delete': ('🗑️', 'Team deleted', 'teams'),
    'season_add': ('🗓️', 'New season started', 'teams'),
    'team_edit': ('✏️', 'Team page edited', 'teams'),
    'awards_update': ('🏆', 'Awards updated', 'awards'),
    'award_category_add': ('🏅', 'Award category added', 'awards'),
    'award_category_update': ('🏅', 'Award category changed', 'awards'),
    'award_category_delete': ('🗑️', 'Award category deleted', 'awards'),
    'user_add': ('👤', 'User created', 'people'),
    'user_update': ('👥', 'User updated', 'people'),
    'user_delete': ('🗑️', 'User deleted', 'people'),
    'password_reset': ('🔑', 'Password reset', 'people'),
    'reset_link_generate': ('🔗', 'Reset link generated', 'people'),
    'user_signup': ('🙋', 'Account requested', 'people'),
    'user_approve': ('✅', 'Account approved', 'people'),
    'user_reject': ('🚫', 'Account request rejected', 'people'),
    'roster_move': ('🔀', 'Roster changed', 'people'),
    'roster_link': ('🔗', 'Login linked to roster', 'people'),
    'sponsor_add': ('🤝', 'Sponsor added', 'sponsors'),
    'sponsor_update': ('💼', 'Sponsor updated', 'sponsors'),
    'sponsor_delete': ('🗑️', 'Sponsor deleted', 'sponsors'),
    'message_read': ('📬', 'Message read', 'messages'),
    'message_new': ('📩', 'Message marked unread', 'messages'),
    'message_archive': ('🗄️', 'Message archived', 'messages'),
    'message_delete': ('🗑️', 'Message deleted', 'messages'),
    'subscriber_remove': ('📭', 'Subscriber removed', 'messages'),
    'subscribers_export': ('📤', 'Subscriber list exported', 'messages'),
    'site_edit': ('🖊️', 'Site content edited', 'site'),
    'fundraiser_edit': ('💰', 'Fundraisers edited', 'events'),
}
ACTIVITY_GROUPS = (('people', 'People'), ('teams', 'Teams'), ('events', 'Events'), ('awards', 'Awards'),
                   ('sponsors', 'Sponsors'), ('messages', 'Messages'), ('site', 'Site'))


def get_activity_icon(activity_type):
    return ACTIVITY_TYPES.get(activity_type, ('📝',))[0]


def get_activity_title(activity_type):
    return ACTIVITY_TYPES.get(activity_type, (None, 'Activity'))[1]


def activity_types_in(group):
    return [t for t, (_, _, g) in ACTIVITY_TYPES.items() if g == group]

# --- MongoDB Connection (lazy) ---
_client = None
_db = None
_db_lock = threading.Lock()


def _ensure_core_indexes(database):
    """Indexes for the queries every page view makes.

    Each is created on its own so one failure (for example a unique index
    over data that already has duplicates) is logged without taking the site
    down or skipping the rest.
    """
    # A unique index on team_number alone predates seasons, and would reject
    # the second season's document for a team. Drop it if an earlier deploy
    # built it; this removes only the index, never data.
    try:
        existing = database['teams'].index_information().get('team_number_1')
        if existing and existing.get('unique'):
            database['teams'].drop_index('team_number_1')
            logger.warning('Dropped the pre-season unique index teams.team_number_1')
    except Exception:
        logger.exception('Could not inspect or drop teams.team_number_1')

    specs = [
        ('users', 'username', {'unique': True}),
        ('users', 'email', {}),
        # One profile per team per season.
        ('teams', [('team_number', 1), ('season', 1)], {'unique': True}),
        ('awards', 'team_number', {}),
        ('competitions', 'date', {}),
        ('activities', 'timestamp', {}),
        ('newsletter_subscribers', 'unsubscribe_token', {}),
    ]
    for collection, key, options in specs:
        try:
            database[collection].create_index(key, **options)
        except Exception:
            logger.exception('Could not create index %s.%s', collection, key)


def get_db():
    global _client, _db
    if _db is None:
        with _db_lock:
            if _db is None:
                mongo_uri = os.getenv('MONGO_URI')
                if not mongo_uri:
                    raise RuntimeError("MONGO_URI environment variable is not set.")
                # serverSelectionTimeoutMS only bounds picking a server. Without
                # socket and connect timeouts a stalled read hangs until the
                # platform kills the function. A small pool keeps many warm
                # instances from exhausting the cluster's connection limit.
                client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000,
                                     connectTimeoutMS=5000, socketTimeoutMS=10000,
                                     maxPoolSize=10)
                database = client['mepham']
                _ensure_core_indexes(database)
                _client, _db = client, database
    return _db

class _DbProxy:
    def __getitem__(self, name):
        return get_db()[name]
    def __getattr__(self, name):
        return getattr(get_db(), name)

db = _DbProxy()

def _load_image_manifest():
    """Pixel sizes and WebP variants written by scripts/optimize_images.py."""
    path = os.path.join(app.static_folder, 'assets', 'image-manifest.json')
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        logger.exception('Could not read %s', path)
        return {}


image_manifest = _load_image_manifest()
app.jinja_env.globals['image_manifest'] = image_manifest

DEFAULT_IMAGE = 'assets/other/base.png'


def get_image_url(image_path, external=False):
    """URL for a stored image: a Vercel Blob URL as-is, or a local static file.

    A local path that does not exist falls back to the placeholder. Member
    rows used to default to `static/assets/profile/base.png`, which was never
    in the repo, so every member without an upload rendered a broken image.
    """
    if image_path and image_path.startswith(('http://', 'https://')):
        return image_path

    clean_path = (image_path or '').replace('\\', '/').removeprefix('/').removeprefix('static/')
    if not clean_path or not os.path.isfile(os.path.join(app.static_folder, clean_path)):
        clean_path = DEFAULT_IMAGE
    return url_for('static', filename=clean_path, _external=external)

class LazyList:
    """A list that runs its loader on first use and never raises.

    A failed load is logged and behaves as empty, so a database outage
    degrades the navigation instead of turning every page into a 500.
    """

    def __init__(self, loader):
        self._loader = loader
        self._items = None

    def _load(self):
        if self._items is None:
            try:
                self._items = self._loader()
            except Exception:
                logger.exception('LazyList: loader failed')
                self._items = []
        return self._items

    def __iter__(self):
        return iter(self._load())

    def __len__(self):
        return len(self._load())

    def __bool__(self):
        return bool(self._load())


def load_sponsors():
    """Every sponsor, highest tier first, then by name."""
    sponsors = []
    for sponsor in db['sponsors'].find():
        sponsor['_id'] = str(sponsor['_id'])
        sponsor['logo_path'] = sponsor.get('logo')
        sponsors.append(sponsor)
    return sorted(sponsors, key=sponsor_sort_key)


# A team document is a robot team unless `kind` says it is a group: a non-competing
# crew like Media or Fundraising, named by `title`, whose `team_number` is its URL slug.
GROUP_KIND = 'group'
ROBOT_TEAMS = {'kind': {'$ne': GROUP_KIND}}


def is_group(team):
    return (team or {}).get('kind') == GROUP_KIND


app.jinja_env.tests['group'] = is_group


def team_sort_key(team):
    """Robot teams by number, then groups by title."""
    name = (team.get('title') if is_group(team) else None) or team.get('team_number') or ''
    return is_group(team), name.lower()


def listed_teams():
    """One entry per team for the nav, sitemap and search, skipping teams hidden in their editor."""
    return sorted((t for t in _newest_season_docs().values() if not t.get('hidden')), key=team_sort_key)


@app.context_processor
def inject_global_data():
    # This runs for every render_template call, including error pages. The
    # nav query only happens if the template iterates nav_teams; awards and
    # sponsors are loaded by the views that show them.
    return dict(
        nav_teams=LazyList(listed_teams),
        site=site(),
        get_activity_icon=get_activity_icon,
        get_activity_title=get_activity_title,
        get_image_url=get_image_url,
    )


# --- Site content (api/site_content.py) ---------------------------------------------
# One stored document of overrides; templates read `site.<section>.<field>`.

SITE_CONTENT_ID = 'site_content'


def _site_overrides():
    doc = db['site_metadata'].find_one({'_id': SITE_CONTENT_ID}, {'values': 1}) or {}
    return doc.get('values') or {}


def site():
    """This request's site content, read at most once and only if a template uses it."""
    if 'site_content' not in g:
        g.site_content = site_content.SiteContent(
            _site_overrides, on_error=lambda: logger.exception('Site content unavailable; using defaults'))
    return g.site_content


app.jinja_env.filters['rich'] = site_content.rich
app.jinja_env.filters['rich_inline'] = lambda text: site_content.rich(text, paragraphs=False)
app.jinja_env.filters['nl_lines'] = lambda text: [line.strip() for line in (text or '').splitlines() if line.strip()]
app.jinja_env.filters['css_url'] = site_content.css_url
app.jinja_env.filters['short_hash'] = lambda text: hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:12]

# Site search (static/js/script.js). Team pages come from the nav list the page already loaded.
SEARCH_PAGES = [
    ('Home', 'index', 'Welcome to Mepham Robotics — VEX V5 team homepage, timeline, and stats',
     'home robotics vex v5 team homepage mepham', False),
    ('About Us', 'about', 'Our mission, values, history, and team culture',
     'about mission values history team culture sub-teams diversity', False),
    ('Achievements', 'achievements', 'Awards, competition results, and season highlights',
     'awards achievements competitions results trophies seasons', False),
    ('Donate', 'donate', 'Support our team through sponsorship and donations',
     'donate sponsor support fundraising givebutter tiers', False),
    ('Contact', 'contact', 'Get in touch — contact form, meeting schedule, and FAQ',
     'contact email form meeting schedule faq questions', False),
    ('Glossary', 'glossary', 'Robotics terms and definitions from A to Z',
     'glossary terms definitions dictionary pid autonomous drivetrain', True),
    ('Branding Guide', 'branding', 'Official team colors, fonts, and logo usage',
     'branding colors fonts logo maroon gold style guide', True),
    ('Design Standards', 'standards', 'Build standards, code style, and naming conventions',
     'standards design build code style naming conventions', True),
    ('Member Resources', 'resources', 'Guides, links, and tooling for team members',
     'resources guides links tools members downloads', True),
    ('Safety Quiz', 'safety_quiz', 'Interactive safety quiz — test your workshop knowledge',
     'safety quiz test workshop lab rules ppe', False),
    ('Engineering Notebook', 'notebook', 'Public engineering notebook — design process and logs',
     'notebook engineering design process testing iteration', True),
    ('Privacy Policy', 'privacy', 'How we handle your data and privacy', 'privacy policy data cookies', False),
    ('Site Credits', 'credits_page', 'Website credits and acknowledgments',
     'credits site acknowledgments technologies', False),
]


def search_index(teams):
    """Pages the search box offers; member-only pages only to signed-in visitors."""
    signed_in = 'user' in session
    pages = [{'title': title, 'url': url_for(endpoint), 'desc': desc, 'keywords': keywords, 'members': members}
             for title, endpoint, desc, keywords, members in SEARCH_PAGES if signed_in or not members]
    pages[5:5] = [_search_entry(t) for t in teams]
    return pages


def _search_entry(t):
    url = url_for('team_page', team_number=t['team_number'])
    if is_group(t):
        title = t.get('title') or t['team_number']
        return {'title': title, 'url': url, 'desc': f'The {title} group: members, goals and journey',
                'keywords': f"{title} {t['team_number']} group crew", 'members': False}
    return {'title': f"{t['team_number']} Team", 'url': url,
            'desc': f"Team {t['team_number']}" + (f" · {t['nickname']}" if t.get('nickname') else '')
            + ' robot details and competition info',
            'keywords': f"{t['team_number']} {t.get('nickname') or ''} robot team", 'members': False}


app.jinja_env.globals['search_index'] = search_index
app.jinja_env.globals.update(
    fmt_time=site_content.fmt_time, fmt_schedule=site_content.fmt_schedule,
    social_links=site_content.social_links, announcement_live=site_content.announcement_live,
    club_now=lambda: club_now(), club_timezone=CLUB_TIMEZONE)

USER_ROLES = ('member', 'editor', 'admin')
# Each role can do everything the roles before it can.
ROLE_RANK = {role: rank for rank, role in enumerate(USER_ROLES)}


def role_at_least(role, needed):
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[needed]


def _wants_json():
    return '/api/' in request.path

def _safe_next(target):
    """Only allow same-site relative paths as post-login redirects."""
    if (target and target.startswith('/') and not target.startswith(('//', '/\\'))
            and not any(ord(c) < 0x21 or c == '\\' for c in target)):
        parsed = urllib.parse.urlsplit(target)
        if not parsed.scheme and not parsed.netloc:
            return target
    return url_for('index')

def _login_redirect():
    return redirect(url_for('login', next=request.full_path.rstrip('?')))

def _current_db_user():
    """Look up the DB user backing the current session.

    Returns the user doc (role, session_version) or None if there is no
    session, the user no longer exists, or the session predates a password
    reset / role change / deletion (session_version mismatch). Missing
    session_version on either side is treated as 0, so existing users and
    sessions keep working without a migration.
    """
    if 'user' not in session:
        return None
    user = db['users'].find_one({'username': session['user']},
                                {'role': 1, 'session_version': 1, 'status': 1})
    if not user or user.get('session_version', 0) != session.get('session_version', 0):
        return None
    # Accounts made before sign-up existed have no status and count as active.
    if user.get('status', 'active') != 'active':
        return None
    return user

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if _current_db_user() is None:
            session.clear()
            if _wants_json():
                return jsonify({'error': 'Please sign in again.'}), 401
            return _login_redirect()
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = _current_db_user()
            if user is None:
                session.clear()
                if _wants_json():
                    return jsonify({'error': 'Please sign in again.'}), 401
                return _login_redirect()
            db_role = user.get('role', 'member')
            if session.get('role') != db_role:
                session['role'] = db_role
            if not role_at_least(db_role, role):
                if _wants_json():
                    return jsonify({'error': 'You do not have permission to do that.'}), 403
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# --- Auth helpers: rate limiting, reset tokens, email ---
LOGIN_MAX_ATTEMPTS = 5
# A botnet can rotate IPs, so an account also locks after this many failures
# across *all* addresses inside the same window.
LOGIN_MAX_ACCOUNT_ATTEMPTS = 20
LOGIN_WINDOW = datetime.timedelta(minutes=15)
PASSWORD_MIN_LENGTH = 8
RESET_TOKEN_TTL = datetime.timedelta(hours=1)
_auth_indexes_ready = False

def _utcnow():
    """Naive UTC now; MongoDB TTL indexes compare against UTC."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

def _client_ip():
    # Trusted: Vercel overwrites X-Forwarded-For with the real client IP (spoofable if hosted elsewhere).
    forwarded = request.headers.get('X-Forwarded-For', '')
    return forwarded.split(',')[0].strip() or request.remote_addr or ''

def _ensure_auth_indexes():
    global _auth_indexes_ready
    if _auth_indexes_ready:
        return
    db['login_attempts'].create_index('created_at', expireAfterSeconds=int(LOGIN_WINDOW.total_seconds()))
    db['login_attempts'].create_index([('key', 1), ('ip', 1), ('created_at', 1)])
    db['password_resets'].create_index('created_at', expireAfterSeconds=int(RESET_TOKEN_TTL.total_seconds()))
    db['password_resets'].create_index('token_hash', unique=True)
    _auth_indexes_ready = True

def _window_lockout(query, limit):
    """Minutes until the oldest attempt in the window ages out, or 0."""
    since = _utcnow() - LOGIN_WINDOW
    attempts = list(db['login_attempts'].find(
        dict(query, created_at={'$gte': since})).sort('created_at', 1).limit(limit))
    if len(attempts) < limit:
        return 0
    unlock_at = attempts[0]['created_at'] + LOGIN_WINDOW
    return max(1, math.ceil((unlock_at - _utcnow()).total_seconds() / 60))


def _lockout_minutes(key, ip):
    """Minutes until this account may try again from this IP, or 0.

    Two limits apply: a tight one for this (account, IP) pair, and a looser
    account-wide one so rotating source addresses does not reset the counter.
    """
    return max(
        _window_lockout({'key': key, 'ip': ip}, LOGIN_MAX_ATTEMPTS),
        _window_lockout({'key': key}, LOGIN_MAX_ACCOUNT_ATTEMPTS),
    )

def _record_attempt(key, ip):
    _ensure_auth_indexes()
    db['login_attempts'].insert_one({'key': key, 'ip': ip, 'created_at': _utcnow()})

def _clear_attempts(key, ip=None):
    query = {'key': key}
    if ip is not None:
        query['ip'] = ip
    db['login_attempts'].delete_many(query)

# --- Generic per-IP rate limiting for public JSON endpoints ---
RATE_LIMIT_TTL = datetime.timedelta(hours=1)
_rate_limit_index_ready = False


def _ensure_rate_limit_index():
    global _rate_limit_index_ready
    if _rate_limit_index_ready:
        return
    db['rate_limits'].create_index('created_at',
                                   expireAfterSeconds=int(RATE_LIMIT_TTL.total_seconds()))
    db['rate_limits'].create_index([('bucket', 1), ('ip', 1), ('created_at', 1)])
    _rate_limit_index_ready = True


def rate_limit(bucket, ip, limit, window):
    """Record a hit and report whether this IP is over the limit.

    Returns the number of seconds until the caller may retry, or 0 when the
    request is allowed. The hit is recorded either way, so hammering a locked
    bucket keeps it locked.
    """
    _ensure_rate_limit_index()
    now = _utcnow()
    db['rate_limits'].insert_one({'bucket': bucket, 'ip': ip, 'created_at': now})
    hits = list(db['rate_limits'].find(
        {'bucket': bucket, 'ip': ip, 'created_at': {'$gte': now - window}}
    ).sort('created_at', 1).limit(limit + 1))
    if len(hits) <= limit:
        return 0
    return max(1, int((hits[0]['created_at'] + window - now).total_seconds()))


# --- Contact form helpers ---
CONTACT_MAX_ATTEMPTS = 3
CONTACT_WINDOW = datetime.timedelta(minutes=15)
CONTACT_NAME_MAX = 100
CONTACT_EMAIL_MAX = 254
CONTACT_MESSAGE_MAX = 4000
# Topics the contact form offers. Anything else is stored as 'general'.
CONTACT_TOPICS = ('join', 'sponsor', 'general')
_contact_indexes_ready = False

def _ensure_contact_indexes():
    global _contact_indexes_ready
    if _contact_indexes_ready:
        return
    db['contact_attempts'].create_index('created_at', expireAfterSeconds=int(CONTACT_WINDOW.total_seconds()))
    db['contact_attempts'].create_index([('key', 1), ('ip', 1)])
    db['contact_messages'].create_index([('created_at', -1)])
    _contact_indexes_ready = True

def _contact_lockout_minutes(ip):
    """Minutes until this IP may send another message, or 0 if not limited."""
    since = _utcnow() - CONTACT_WINDOW
    attempts = list(db['contact_attempts'].find(
        {'key': 'contact', 'ip': ip, 'created_at': {'$gte': since}}).sort('created_at', 1))
    if len(attempts) < CONTACT_MAX_ATTEMPTS:
        return 0
    unlock_at = attempts[0]['created_at'] + CONTACT_WINDOW
    return max(1, math.ceil((unlock_at - _utcnow()).total_seconds() / 60))

def _record_contact_attempt(ip):
    _ensure_contact_indexes()
    db['contact_attempts'].insert_one({'key': 'contact', 'ip': ip, 'created_at': _utcnow()})

def _looks_like_email(email):
    local, _, domain = email.partition('@')
    return bool(local) and '.' in domain and not domain.startswith('.') and not domain.endswith('.')


def _validate_contact(payload):
    """Return (cleaned, error). cleaned is None when error is set."""
    def _text(value):
        return value.strip() if isinstance(value, str) else ''

    name = _text(payload.get('name'))
    email = _text(payload.get('email')).lower()
    message = _text(payload.get('message'))
    topic = _text(payload.get('topic')).lower()
    if topic not in CONTACT_TOPICS:
        topic = 'general'

    if not name:
        return None, 'Please enter your name.'
    if len(name) > CONTACT_NAME_MAX:
        return None, f'Name must be {CONTACT_NAME_MAX} characters or fewer.'
    if not email:
        return None, 'Please enter your email address.'
    if len(email) > CONTACT_EMAIL_MAX:
        return None, f'Email must be {CONTACT_EMAIL_MAX} characters or fewer.'
    if not _looks_like_email(email):
        return None, 'Please enter a valid email address.'
    if not message:
        return None, 'Please enter a message.'
    if len(message) > CONTACT_MESSAGE_MAX:
        return None, f'Message must be {CONTACT_MESSAGE_MAX} characters or fewer.'

    return {'name': name, 'email': email, 'message': message, 'topic': topic}, None

def _hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def _public_url(endpoint, **values):
    """An absolute link for use outside the site (emails, exports), honouring PUBLIC_BASE_URL."""
    public_base = os.getenv('PUBLIC_BASE_URL', '')
    if public_base:
        return public_base.rstrip('/') + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def _build_reset_link(token):
    """Build the absolute reset-password link for a freshly issued token."""
    return _public_url('reset_password', token=token)

def _find_reset(token):
    _ensure_auth_indexes()
    doc = db['password_resets'].find_one({'token_hash': _hash_token(token)})
    if not doc or _utcnow() - doc['created_at'] > RESET_TOKEN_TTL:
        return None
    return doc

def _no_referrer(rv):
    """Wrap a view return value and set Referrer-Policy: no-referrer (keeps reset tokens out of Referer)."""
    resp = app.make_response(rv)
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return resp

# --- CSRF protection -------------------------------------------------------
# Every state-changing request must echo a per-session token. The check is a
# before_request hook rather than a per-view decorator so new routes are
# protected by default instead of by remembering to opt in.
CSRF_FIELD = '_csrf_token'
CSRF_HEADER = 'X-CSRF-Token'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}


def csrf_token():
    token = session.get(CSRF_FIELD)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_FIELD] = token
    return token


app.jinja_env.globals['csrf_token'] = csrf_token


def _submitted_csrf_token():
    if request.form.get(CSRF_FIELD):
        return request.form[CSRF_FIELD]
    if request.headers.get(CSRF_HEADER):
        return request.headers[CSRF_HEADER]
    if request.is_json:
        return (request.get_json(silent=True) or {}).get(CSRF_FIELD, '')
    return ''


@app.before_request
def verify_csrf():
    if request.method in SAFE_METHODS or app.config.get('WTF_CSRF_DISABLED'):
        return None
    expected = session.get(CSRF_FIELD, '')
    submitted = _submitted_csrf_token()
    if not expected or not submitted or not hmac.compare_digest(str(submitted), expected):
        if _wants_json():
            return jsonify({'error': 'Your session expired. Refresh the page and try again.'}), 400
        abort(400)
    return None


@app.errorhandler(400)
def bad_request(e):
    if _wants_json():
        return jsonify({'error': 'That request could not be understood.'}), 400
    return render_template('400.html'), 400


@app.errorhandler(413)
def payload_too_large(e):
    megabytes = MAX_UPLOAD_BYTES // (1024 * 1024)
    if _wants_json():
        return jsonify({'error': f'File too large (max {megabytes} MB).'}), 413
    flash(f'That file is too large. The limit is {megabytes} MB.', 'error')
    return redirect(request.referrer or url_for('index')), 302


# --- Security headers ------------------------------------------------------
# One policy for every page: no inline script anywhere, including the admin
# dashboard, whose controls are wired through delegated listeners.
_SCRIPT_CDNS = "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com"
_BASE_CSP = [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' https://fonts.gstatic.com data:",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    # The team page's 3D viewer fetches the uploaded .stl from Vercel Blob.
    "connect-src 'self' https://*.public.blob.vercel-storage.com",
    # The donation page embeds a Givebutter widget; the contact page loads a
    # Google Maps embed on request.
    "frame-src https://givebutter.com https://www.google.com",
]


def _csp_for(path):
    return '; '.join(_BASE_CSP + [f"script-src 'self' {_SCRIPT_CDNS}"])


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault(
        'Permissions-Policy', 'geolocation=(), microphone=(), camera=(), interest-cohort=()')
    response.headers.setdefault('Content-Security-Policy', _csp_for(request.path))
    if os.getenv('VERCEL'):
        response.headers.setdefault(
            'Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


# --- Static asset versioning ----------------------------------------------
# Static files are served with `immutable` and a one-year max-age, so a URL
# without a version can pin a stale stylesheet in a browser for a year. This
# stamps every url_for('static', ...) with the file's modification time, which
# makes the aggressive caching safe and removes the hand-maintained ?v=N.
_static_versions = {}


def _static_version(filename):
    if filename not in _static_versions:
        try:
            mtime = os.path.getmtime(os.path.join(app.static_folder, filename))
        except OSError:
            mtime = 0
        _static_versions[filename] = format(int(mtime) & 0xFFFFFFF, 'x')
    return _static_versions[filename]


@app.url_defaults
def add_static_version(endpoint, values):
    if endpoint == 'static' and values.get('filename'):
        values.setdefault('v', _static_version(values['filename']))


@app.route('/healthz')
def healthz():
    """Liveness probe that also confirms the database answers."""
    try:
        get_db().command('ping')
        return jsonify({'status': 'ok', 'database': 'up'})
    except Exception:
        logger.exception('healthz: database ping failed')
        return jsonify({'status': 'degraded', 'database': 'down'}), 503


UPCOMING_EVENTS_LIMIT = 12


def club_now():
    """Naive wall-clock time where the club is.

    Admins enter event times as local wall-clock time in a datetime-local
    input, and they are stored without a zone. Comparing them against the
    server clock (UTC on Vercel) made events leave the homepage four or five
    hours before they started.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(CLUB_TIMEZONE)).replace(tzinfo=None)
    except Exception:
        return datetime.datetime.now()


@app.route('/')
def index():
    stats = public_stats(db['site_metadata'].find_one({'_id': 'global_stats'}))
    upcoming_events = list(db['competitions'].find(
        {'date': {'$gte': club_now()}}).sort('date', 1).limit(UPCOMING_EVENTS_LIMIT))
    for event in upcoming_events:
        event['month'] = event['date'].strftime('%b').upper()
        event['day'] = event['date'].strftime('%d')
        event['time'] = event['date'].strftime('%I:%M %p')
    competition = upcoming_events[0] if upcoming_events else None
    settings = site().fundraisers
    fundraisers = (site_content.fundraiser_cards(settings.entries, club_now(), settings.max_shown)
                   if settings.mode != 'never' else [])
    return render_template('index.html', active_page='index', stats=stats,
                           competition=competition, upcoming_events=upcoming_events, fundraisers=fundraisers)

@app.route('/about')
def about():
    return render_template('about.html', active_page='about')

def achievements_view():
    """Everything the achievements page shows, built from award rows, teams and past events.

    Club-wide category rows carry the headline counts; each team's own counters add the
    per-team breakdown. Team rows made before categories were linked match by title.
    """
    rows = list(db['awards'].find().sort(AWARD_ORDER))
    categories = [a for a in rows if 'team_number' not in a]
    by_title = {a.get('title'): str(a['_id']) for a in categories}
    teams = [t for t in listed_teams() if not is_group(t)]
    team_rows = {t['team_number']: [] for t in teams}
    winners = {}
    for row in rows:
        count = int(row.get('count') or 0)
        if row.get('team_number') in team_rows and count > 0:
            team_rows[row['team_number']].append(dict(row, count=count, icon=row.get('icon') or AWARD_ICONS[0]))
            key = row.get('category_id') or by_title.get(row.get('title'))
            winners.setdefault(key, []).append({'team_number': row['team_number'], 'count': count})

    total = sum(int(a.get('count') or 0) for a in categories)
    earned, unearned = [], []
    for a in categories:
        a['count'] = int(a.get('count') or 0)
        a['icon'] = a.get('icon') or AWARD_ICONS[0]
        a['featured'] = a.get('border') == 'gold' or bool(a.get('shimmer'))
        a['share'] = round(100 * a['count'] / total) if total else 0
        a['teams'] = sorted(winners.get(str(a['_id']), []), key=lambda w: -w['count'])
        (earned if a['count'] else unearned).append(a)

    team_cards = [{'number': t['team_number'], 'nickname': t.get('nickname') or '',
                   'total': sum(r['count'] for r in team_rows[t['team_number']]),
                   'awards': team_rows[t['team_number']]} for t in teams]
    team_cards.sort(key=lambda c: -c['total'])

    limit = site().achievements.history_limit or 12
    events = list(db['competitions'].find({'date': {'$lt': club_now()}}).sort('date', -1).limit(limit + 1))
    more_events = len(events) > limit
    events = events[:limit]
    for event in events:
        # VEX seasons start in late spring: an April event belongs to the season that began last year.
        start = event['date'].year - (event['date'].month < 5)
        event['season'] = f'{start}–{str(start + 1)[-2:]}'
    return {
        'earned': earned, 'unearned': unearned, 'has_awards': bool(categories),
        'featured': [a for a in earned if a['featured']],
        'total': total, 'team_cards': team_cards, 'past_events': events, 'more_events': more_events,
        'top_count': max((a['count'] for a in earned), default=0),
    }


@app.route('/achievements')
def achievements():
    return render_template('achievements.html', active_page='achievements', **achievements_view(),
                           live_results=bool(robotevents.get_token()) and site().achievements.show_live)

@app.route('/contact')
def contact():
    return render_template('contact.html', active_page='contact')

CONTACT_EMAIL = os.getenv('CONTACT_EMAIL', 'mephamrobotics@gmail.com')


@app.route('/donate')
def donate():
    # The embed only renders once a campaign id is configured; until then the
    # template shows an email fallback instead of a broken Givebutter frame.
    content = site()
    # The contact page has always shown its own address; the donation fallback
    # used CONTACT_EMAIL. Once an admin sets the club email, both use it.
    email = content.general.contact_email if content.is_custom('general.contact_email') else CONTACT_EMAIL
    return render_template('donate.html', active_page='donate',
                           givebutter_campaign_id=content.donate.givebutter_id,
                           contact_email=email, sponsors=load_sponsors())

# Journey dates are free text; these are the shapes people type into that box.
LOOSE_DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%B %d %Y',
                      '%b %Y', '%B %Y', '%Y')


def parse_loose_date(text):
    """A journey date like 'Sep 2025', 'January 12, 2026' or '2024' as a datetime, else None."""
    text = re.sub(r'\bSept\b', 'Sep', ' '.join(str(text or '').replace('.', '').split()), flags=re.I)
    for fmt in LOOSE_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def team_timeline(team):
    """Journey milestones and the team's own events as one dated list (Season Timeline layout).

    Milestones keep the order they were written in: one whose date does not parse
    takes the date of the milestone before it. Events are the team's photo galleries,
    dated (and placed) by the club competition of the same name in that season.
    Events with no matching competition close the list. Built from stored data
    only; team.js adds RobotEvents results to it when a key is configured.
    """
    season = str(team.get('season') or '')
    start_year = int(season[:4]) if season[:4].isdigit() else None
    competitions = {}
    for comp in db['competitions'].find({}, {'name': 1, 'date': 1, 'location': 1}).sort('date', 1):
        when = comp.get('date')
        if not comp.get('name') or not isinstance(when, datetime.datetime):
            continue
        # VEX seasons start in late spring, as on the achievements page.
        if start_year is not None and when.year - (when.month < 5) != start_year:
            continue
        competitions.setdefault(comp['name'].strip().lower(), comp)

    items, last = [], None
    for order, milestone in enumerate(team.get('journey') or []):
        last = parse_loose_date(milestone.get('date')) or last
        items.append({'kind': 'milestone', 'when': last, 'order': order, 'label': milestone.get('date') or '',
                      'title': milestone.get('title') or '', 'text': milestone.get('description') or ''})
    for order, event in enumerate(team.get('events') or []):
        name = (event.get('name') or '').strip()
        if not name:
            continue
        comp = competitions.get(name.lower())
        when = comp['date'].replace(tzinfo=None) if comp else None
        items.append({'kind': 'event', 'when': when, 'order': 10_000 + order, 'title': name,
                      'label': f'{when:%b} {when.day}, {when.year}' if when else '',
                      'where': (comp or {}).get('location') or '', 'photos': event.get('photos') or []})

    def key(item):
        if item['when'] is not None:
            return (1, item['when'], item['order'])
        # Undated milestones before any dated one open the list; undated events close it.
        return (0 if item['kind'] == 'milestone' else 2, datetime.datetime.min, item['order'])
    return sorted(items, key=key)


MOSAIC_SIZES = (9, 7, 5, 4)


def team_mosaic(team):
    """Photos for the Magazine layout's mosaic, as (path, event name) pairs, plus how many
    more the team has.

    Taken one event at a time in turn, so the mosaic is not nine shots of one day. The
    count is trimmed to a size the mosaic's grid fills with no holes (9, 7, 5 or 4); a
    team with fewer than 4 photos gets no mosaic.
    """
    queues = [[(p, e['name']) for p in e.get('photos') or []]
              for e in team.get('events') or [] if e.get('name') and e.get('photos')]
    photos = []
    while any(queues):
        for queue in queues:
            if queue:
                photos.append(queue.pop(0))
    size = next((n for n in MOSAIC_SIZES if len(photos) >= n), 0)
    return photos[:size], len(photos) - size if size else 0


def team_layout(team):
    """The layout this team season renders with: its own pick, else the site default.

    Groups always use Classic until they get layouts of their own. A stored key that
    is no longer offered falls back too, so removing a layout never breaks a page.
    """
    if is_group(team):
        return site_content.DEFAULT_TEAM_LAYOUT
    for key in (team.get('layout'), site().teams.layout):
        if key in site_content.TEAM_LAYOUTS:
            return key
    return site_content.DEFAULT_TEAM_LAYOUT


@app.route('/team/<team_number>')
def team_page(team_number):
    docs = list(db['teams'].find({'team_number': team_number}))
    if not docs:
        flash(f"Team {team_number} not found.", "error")
        return redirect(url_for('index'))

    # One document per (team_number, season). Newest season wins unless ?season= names
    # an existing one. Documents predating seasons have no 'season' key and sort last.
    seasons = sorted({d['season'] for d in docs if d.get('season')}, reverse=True)
    requested = request.args.get('season')
    team = next((d for d in docs if d.get('season') == requested), None)
    if team is None:
        team = next((d for d in docs if d.get('season') == seasons[0]), docs[0]) if seasons else docs[0]

    team['_id'] = str(team['_id'])
    # Older or hand-made team documents can lack these; the template reads
    # straight into them, and a missing one turned the page into a 500.
    # setdefault leaves an explicit null in place, so normalise with `or`.
    team['specs'] = team.get('specs') or {}
    for key in ('members', 'goals', 'journey', 'events'):
        team[key] = team.get(key) or []

    # Photo strips are keyed by event name so team.js can attach them to the
    # matching RobotEvents row without a second lookup.
    raw_photos = {e.get('name'): e.get('photos') or []
                  for e in team['events'] if e.get('name') and e.get('photos')}
    # team.js sets these as img src directly, so resolve them here: a raw
    # `static/...` path would resolve against /team/<n>/ and break.
    event_photos = {name: [get_image_url(p) for p in photos] for name, photos in raw_photos.items()}

    # Fallback for the robot showcase when no CAD model has been uploaded.
    # Kept as stored paths: the template resolves each with get_image_url.
    robot_photos = [p for photos in raw_photos.values() for p in photos][:6]

    team_awards = [] if is_group(team) else list(db['awards'].find({'team_number': team_number}).sort(AWARD_ORDER))
    for award in team_awards:
        # The awards grid builds the icon path from this; a row missing it used to 500 the page.
        award['icon'] = award.get('icon') or AWARD_ICONS[0]
    layout = team_layout(team)
    mosaic, mosaic_more = team_mosaic(team) if layout == 'magazine' else ([], 0)
    return render_template('team.html', team=team, team_awards=team_awards,
                           event_photos=event_photos, robot_photos=robot_photos,
                           layout=layout, award_style=site_content.LAYOUT_AWARD_STYLES.get(layout, 'classic'),
                           timeline=team_timeline(team) if layout == 'timeline' else [],
                           mosaic=mosaic, mosaic_more=mosaic_more,
                           robotevents_url=None if is_group(team) else robotevents.team_url(team_number),
                           seasons=seasons, active_season=team.get('season'),
                           live_enabled=bool(robotevents.get_token()) and not is_group(team),
                           active_page=team_number)

@app.route('/api/team/<team_number>/live')
def team_live_data(team_number):
    """Live RobotEvents data for the team page's skills, scoreboard and results panels.

    Scoped to one season (?season=, else the team's newest), so "This Season"
    never shows a team's whole history. 204 when there is no token, no matching
    RobotEvents team or season, or nothing to show. The page renders without
    these panels in that case, so this never fails hard.
    """
    docs = list(db['teams'].find({'team_number': team_number}))
    if not docs or is_group(docs[0]):
        return Response(status=204)
    label = request.args.get('season') or max((d['season'] for d in docs if d.get('season')), default=None)
    team = next((d for d in docs if d.get('season') == label), docs[0])
    if not label or not robotevents.get_token():
        return Response(status=204)

    lookup_number = team.get('robotevents_number') or team_number
    try:
        season = robotevents.season_id(db, label)
        if not season:
            return Response(status=204)
        summary = robotevents.team_summary(db, lookup_number, season_id=season)
    except Exception:
        app.logger.exception('Live team data failed for %s', team_number)
        return Response(status=204)

    if not summary:
        return Response(status=204)
    return jsonify(summary)


@app.route('/safety-quiz')
def safety_quiz():
    return render_template('safety_quiz.html', active_page='safety_quiz')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', active_page='privacy')

@app.route('/credits')
def credits_page():
    return render_template('credits.html', active_page='credits')

@app.route('/resources')
@role_required('member')
def resources():
    return render_template('resources.html', active_page='resources')

@app.route('/glossary')
@role_required('member')
def glossary():
    return render_template('glossary.html', active_page='glossary')

@app.route('/branding')
@role_required('member')
def branding():
    return render_template('branding.html', active_page='branding')

@app.route('/standards')
@role_required('member')
def standards():
    return render_template('standards.html', active_page='standards')

@app.route('/notebook')
@role_required('member')
def notebook():
    return render_template('notebook.html', active_page='notebook')

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = _safe_next(request.values.get('next'))
    if _current_db_user() is not None:
        return redirect(next_url)
    session.clear()

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        attempt_key = identifier.lower()
        ip = _client_ip()

        wait = _lockout_minutes(attempt_key, ip)
        if wait:
            error = f'Too many attempts. Try again in {wait} minute{"s" if wait != 1 else ""}.'
            return render_template('login.html', active_page='login', error=error,
                                   next=next_url, username=identifier), 429

        user = db['users'].find_one({'$or': [{'username': identifier}, {'email': identifier}]})
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            _clear_attempts(attempt_key, ip)
            # Only someone who knows the password learns the account is waiting.
            if user.get('status', 'active') == 'pending':
                return render_template('login.html', active_page='login', next=next_url,
                                       username=identifier,
                                       error='Your account is waiting for an admin to approve it.'), 403
            session.clear()
            session['user'] = user['username']
            session['role'] = user.get('role', 'member')
            session['session_version'] = user.get('session_version', 0)
            session.permanent = bool(request.form.get('remember'))
            return redirect(next_url)

        _record_attempt(attempt_key, ip)
        return render_template('login.html', active_page='login',
                               error='Invalid credentials. Please try again.',
                               next=next_url, username=identifier), 401

    return render_template('login.html', active_page='login', next=next_url)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset = _find_reset(token)
    user = db['users'].find_one({'_id': reset['user_id']}) if reset else None
    if not user:
        resp = render_template('reset_password.html', active_page='login', invalid=True), 400
        return _no_referrer(resp)

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        error = None
        if len(password) < PASSWORD_MIN_LENGTH:
            error = f'Password must be at least {PASSWORD_MIN_LENGTH} characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        if error:
            resp = render_template('reset_password.html', active_page='login', invalid=False, error=error), 400
            return _no_referrer(resp)

        # Atomically consume the token so two concurrent POSTs can't both apply it.
        consumed = db['password_resets'].find_one_and_delete(
            {'token_hash': _hash_token(token), 'created_at': {'$gte': _utcnow() - RESET_TOKEN_TTL}})
        if not consumed:
            resp = render_template('reset_password.html', active_page='login', invalid=True), 400
            return _no_referrer(resp)

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        db['users'].update_one({'_id': user['_id']},
                               {'$set': {'password': hashed}, '$inc': {'session_version': 1}})
        db['password_resets'].delete_many({'user_id': user['_id']})
        _clear_attempts(user['username'].lower())
        if user.get('email'):
            _clear_attempts(user['email'].lower())
        log_activity('password_reset', f'Password reset for {user["username"]}',
                     user=user['username'], details={'username': user['username']})
        flash('Password updated. Sign in with your new password.', 'success')
        return redirect(url_for('login'))

    return _no_referrer(render_template('reset_password.html', active_page='login', invalid=False))

USERNAME_RE = re.compile(r'[A-Za-z0-9_.-]{3,32}')
SIGNUP_RATE_LIMIT = 5
SIGNUP_RATE_WINDOW = datetime.timedelta(hours=1)


def _team_choices():
    """(id, label) for every team, then every group, for the sign-up and approval team pickers."""
    teams = db['teams'].find({}, {'team_number': 1, 'nickname': 1, 'season': 1, 'kind': 1, 'title': 1})
    return [(str(t['_id']), ' '.join(filter(None, [t.get('title') if is_group(t) else t.get('team_number'),
                                                   None if is_group(t) else t.get('nickname'),
                                                   f"({t['season']})" if t.get('season') else None])))
            for t in sorted(teams, key=team_sort_key)]


def _find_by_id(collection, doc_id):
    """The document for a string id, or None for anything malformed or missing."""
    if not doc_id or not ObjectId.is_valid(str(doc_id)):
        return None
    return db[collection].find_one({'_id': ObjectId(str(doc_id))})


def _find_team(team_id):
    return _find_by_id('teams', team_id)


FULL_NAME_MAX = 100


def _validate_account(username, email, password, confirm=None, existing=None, require_email=True,
                      require_password=True):
    """The first problem with these account details, or None. Shared by sign-up and the admin forms.

    When editing (`existing` is the stored user) only changed fields are
    re-checked, so an older account whose name predates the rules can still
    have its email or role changed.
    """
    name_changed = existing is None or username != existing.get('username')
    email_changed = existing is None or email != (existing.get('email') or '').lower()
    if name_changed and not USERNAME_RE.fullmatch(username):
        return 'Pick a username of 3-32 letters, numbers, dots, dashes or underscores.'
    if email_changed and (email or require_email):
        if not _looks_like_email(email) or len(email) > CONTACT_EMAIL_MAX:
            return 'Please enter a valid email address.'
    if password or require_password:
        if len(password) < PASSWORD_MIN_LENGTH:
            return f'Password must be at least {PASSWORD_MIN_LENGTH} characters.'
        if confirm is not None and password != confirm:
            return 'Passwords do not match.'
    clash = []
    if name_changed:
        clash.append({'username': re.compile(f'^{re.escape(username)}$', re.IGNORECASE)})
    if email and email_changed:
        clash.append({'email': email})
    if clash:
        query = {'$or': clash}
        if existing is not None:
            query['_id'] = {'$ne': existing['_id']}
        if db['users'].find_one(query):
            return 'That username or email is already registered.'
    return None


def _validate_signup(form):
    if len(form.get('full_name', '').strip()) > FULL_NAME_MAX:
        return f'Your name must be {FULL_NAME_MAX} characters or fewer.'
    return _validate_account(form.get('username', '').strip(), form.get('email', '').strip().lower(),
                             form.get('password', ''), form.get('confirm_password', ''))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if _current_db_user() is not None:
        return redirect(url_for('index'))
    teams = _team_choices()
    if request.method == 'GET':
        return render_template('signup.html', active_page='login', teams=teams, form={})

    if rate_limit('signup', _client_ip(), SIGNUP_RATE_LIMIT, SIGNUP_RATE_WINDOW):
        return render_template('signup.html', active_page='login', teams=teams, form=request.form,
                               error='Too many sign-ups from this network. Try again later.'), 429
    error = _validate_signup(request.form)
    if error:
        return render_template('signup.html', active_page='login', teams=teams, form=request.form,
                               error=error), 400

    username = request.form['username'].strip()
    user = {
        'username': username,
        'email': request.form['email'].strip().lower(),
        'password': bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt()),
        'role': 'member',
        'status': 'pending',
        'created_at': _utcnow(),
    }
    full_name = collapse_whitespace(request.form.get('full_name', ''))
    if full_name:
        user['full_name'] = full_name
    requested = _find_team(request.form.get('requested_team'))
    if requested:
        user['requested_team'] = str(requested['_id'])
    db['users'].insert_one(user)
    log_activity('user_signup', f'{username} requested an account', user=username,
                 details={'username': username})
    return render_template('signup.html', active_page='login', submitted=True, teams=teams, form={})


# --- Club numbers ---------------------------------------------------------------
# The homepage shows four numbers. Each of the first three can be typed in
# ("manual") or follow the database ("auto"). The live counts are cached on
# the global_stats document, so the homepage still reads a single document.

STAT_FIELDS = ('teams_count', 'members_count', 'awards_count', 'hours_built')
AUTO_STAT_FIELDS = ('teams_count', 'members_count', 'awards_count')
STAT_LIMITS = {'teams_count': 999, 'members_count': 9_999, 'awards_count': 9_999, 'hours_built': 1_000_000}
STAT_LABELS = {'teams_count': 'Teams', 'members_count': 'Members', 'awards_count': 'Awards',
               'hours_built': 'Hours built'}


def _newest_season_docs(query=None):
    """One team document per team number: the newest season (a missing season sorts oldest)."""
    newest = {}
    for team in db['teams'].find(query or {}, {'team_number': 1, 'season': 1, 'members': 1, 'nickname': 1,
                                               'hidden': 1, 'kind': 1, 'title': 1}):
        number = team.get('team_number')
        if number and (number not in newest
                       or (team.get('season') or '') > (newest[number].get('season') or '')):
            newest[number] = team
    return newest


def compute_auto_stats():
    """Live club numbers: listed robot teams, people on current rosters, and club award totals.

    Groups aren't teams, but their people count; someone on a team and in Media counts once.
    """
    current = _newest_season_docs({'hidden': {'$ne': True}})
    awards = db['awards'].find({'team_number': {'$exists': False}}, {'count': 1})
    people = {str(m.get('user_id') or '') or m.get('member_id') or id(m)
              for t in current.values() for m in t.get('members') or []}
    return {
        'teams_count': sum(not is_group(t) for t in current.values()),
        'members_count': len(people),
        'awards_count': sum(int(a.get('count') or 0) for a in awards),
    }


def refresh_auto_stats():
    """Recount the live numbers after anything that changes teams, rosters or awards."""
    try:
        auto = compute_auto_stats()
        db['site_metadata'].update_one({'_id': 'global_stats'}, {'$set': {'auto': auto}}, upsert=True)
        return auto
    except Exception:
        logger.exception('Could not refresh the automatic club numbers')
        return None


def public_stats(doc):
    """The homepage numbers: typed-in values, or the live count for fields set to auto."""
    doc = doc or {}
    modes, auto = doc.get('modes') or {}, doc.get('auto') or {}
    return {f: int((auto if modes.get(f) == 'auto' else doc).get(f) or 0) for f in STAT_FIELDS}


def monthly_stat_changes(current, today=None):
    """How far each live number moved since the first dashboard visit this month.

    The first visit of a month stores a snapshot; later visits compare against
    it. Summing the activity log instead double-counted any change an admin
    also typed into the stats by hand.
    """
    today = today or _utcnow()
    key = f"stats_snapshot_{today:%Y-%m}"
    db['site_metadata'].update_one({'_id': key}, {'$setOnInsert': dict(current)}, upsert=True)
    snapshot = db['site_metadata'].find_one({'_id': key}) or {}
    return {f: current.get(f, 0) - snapshot.get(f, current.get(f, 0)) for f in current}


MESSAGES_SHOWN = 200
SUBSCRIBERS_SHOWN = 500


def _message_counts():
    counts = {'new': 0, 'read': 0, 'archived': 0}
    for row in db['contact_messages'].aggregate([{'$group': {'_id': {'$ifNull': ['$status', 'new']},
                                                             'n': {'$sum': 1}}}]):
        counts[row['_id']] = counts.get(row['_id'], 0) + row['n']
    counts['total'] = sum(counts.values())
    return counts


def _attention_items(pending, counts, past_events, upcoming, teams, stats_doc, auto):
    """Short to-do list for the Overview tab: each item says what is off and where to fix it."""
    items = []

    def add(icon, text, tab, action, tone='info', target=''):
        items.append({'icon': icon, 'text': text, 'tab': tab, 'action': action, 'tone': tone, 'target': target})

    def plural(n, word):
        return f'{n} {word}{"s" if n != 1 else ""}'

    def names(numbers):
        return ', '.join(numbers[:3]) + (' and more' if len(numbers) > 3 else '')

    if pending:
        add('user-check', f'{plural(len(pending), "sign-up")} waiting for approval', 'users', 'Review', 'alert',
            'approvals')
    if counts.get('new'):
        add('mail', f'{plural(counts["new"], "unread message")}', 'messages', 'Read', 'alert')
    if not upcoming:
        add('calendar-plus', 'No upcoming events, so the homepage countdown says TBD', 'events', 'Add one',
            target='event_form')
    if past_events:
        add('calendar-x', f'{plural(len(past_events), "past event")} still stored', 'events', 'Tidy up',
            target='past-events')
    unnamed = [t['team_number'] for t in teams if not t.get('nickname')]
    if unnamed:
        add('bot', f'{names(unnamed)} {"has" if len(unnamed) == 1 else "have"} no nickname yet', 'teams', 'Edit')
    empty = [t['team_number'] for t in teams if not t.get('members')]
    if empty:
        add('users', f'{names(empty)} {"has" if len(empty) == 1 else "have"} an empty roster', 'users',
            'Add people', target='roster')
    modes = stats_doc.get('modes') or {}
    drift = [STAT_LABELS[f].lower() for f in AUTO_STAT_FIELDS
             if modes.get(f) != 'auto' and auto and stats_doc.get(f, 0) != auto.get(f, 0)]
    if drift:
        listed = drift[0] if len(drift) == 1 else ', '.join(drift[:-1]) + ' and ' + drift[-1]
        add('hash', f'Homepage {listed} {"differs" if len(drift) == 1 else "differ"} from the live count',
            'overview', 'Check',
            target='homepage-numbers')
    return items


@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    _ensure_member_ids()
    _ensure_award_order()
    auto = refresh_auto_stats() or {}
    stats_doc = db['site_metadata'].find_one({'_id': 'global_stats'}) or {}
    stats = public_stats(stats_doc)
    modes = stats_doc.get('modes') or {}

    # Events: upcoming first (soonest first), past newest first. Undated rows count as past.
    now = club_now()
    upcoming, past = [], []
    for c in db['competitions'].find().sort('date', 1):
        c['_id'] = str(c['_id'])
        if isinstance(c.get('date'), datetime.datetime):
            c['date_str'] = c['date'].strftime('%Y-%m-%dT%H:%M')
            c['display_date'] = c['date'].strftime('%a %b %d, %Y · %I:%M %p')
            c['days_away'] = (c['date'].date() - now.date()).days
            (upcoming if c['date'] >= now else past).append(c)
        else:
            c['date_str'], c['display_date'] = '', 'No date'
            past.append(c)
    past.reverse()

    live = dict(auto, events_count=len(upcoming))
    monthly_changes = monthly_stat_changes(live)

    all_users = [dict(u, _id=str(u['_id']), role=u.get('role', 'member'), email=u.get('email', ''),
                      status=u.get('status', 'active'))
                 for u in db['users'].find({}, {'username': 1, 'email': 1, 'role': 1, 'status': 1, 'full_name': 1,
                                                'requested_team': 1, 'created_at': 1}).sort('username', 1)]
    users = [u for u in all_users if u['status'] == 'active']
    pending_users = [u for u in all_users if u['status'] == 'pending']
    for u in pending_users:
        created = u.get('created_at')
        u['requested_ago'] = get_time_ago(created) if created else ''

    teams = []
    for t in db['teams'].find().sort([('team_number', 1), ('season', -1)]):
        t['_id'] = str(t['_id'])
        t['members'] = t.get('members') or []
        for m in t['members']:
            if m.get('user_id'):
                m['user_id'] = str(m['user_id'])
        teams.append(t)
    current_ids = {str(t['_id']) for t in _newest_season_docs().values()}
    for t in teams:
        t['is_current'] = t['_id'] in current_ids
    current_teams = sorted((t for t in teams if t['is_current']), key=team_sort_key)
    current_robot_teams = [t for t in current_teams if not is_group(t)]

    # Roster board: one column per team's current season, then every active account not on a roster.
    usernames = {u['_id']: u['username'] for u in users}
    rostered = {str(m.get('user_id')) for t in teams for m in t['members'] if m.get('user_id')}
    board, claimable = [], []
    for t in current_teams:
        cards = []
        for m in t['members']:
            card = _card(m)
            card['username'] = usernames.get(card['user_id'], '')
            cards.append(card)
            if not card['user_id']:
                claimable.append((card['member_id'], f"{_team_label(t)} · {card['name']}"))
        board.append({'_id': t['_id'], 'label': _team_label(t), 'group': is_group(t),
                      'nickname': '' if is_group(t) else t.get('nickname') or '',
                      'hidden': bool(t.get('hidden')), 'cards': cards})
    unassigned = [u for u in users if u['_id'] not in rostered]
    team_choices = [(b['_id'], b['label']) for b in board if not b['group']]
    group_choices = [(b['_id'], b['label']) for b in board if b['group']]
    # For the Move-to menus: which groups each person is already in, and their robot team.
    group_members = {b['_id']: {c['user_id'] for c in b['cards'] if c['user_id']} for b in board if b['group']}
    robot_team_of = {c['user_id']: b['_id'] for b in board if not b['group'] for c in b['cards'] if c['user_id']}

    link_team_award_categories()
    all_awards = [dict(a, _id=str(a['_id'])) for a in db['awards'].find().sort(AWARD_ORDER)]
    global_awards = [a for a in all_awards if 'team_number' not in a]
    team_awards = [{k: a.get(k) for k in ('_id', 'team_number', 'title', 'icon', 'count')}
                   for a in all_awards if 'team_number' in a]

    messages = []
    for m in db['contact_messages'].find().sort('created_at', -1).limit(MESSAGES_SHOWN):
        m['_id'] = str(m['_id'])
        created = m.get('created_at')
        m['display_date'] = created.strftime('%b %d, %Y @ %I:%M %p') if created else ''
        m['ago'] = get_time_ago(created) if created else ''
        m['status'] = m.get('status', 'new')
        messages.append(m)
    message_counts = _message_counts()
    subscriber_count = db['newsletter_subscribers'].count_documents({})
    subscribers = [dict(s, _id=str(s['_id'])) for s in db['newsletter_subscribers'].find(
        {}, {'email': 1, 'created_at': 1}).sort('created_at', -1).limit(SUBSCRIBERS_SHOWN)]

    activities, more_activity = activity_page()
    overrides = _site_overrides()
    site_summary = [{'key': sec.key, 'title': sec.title, 'icon': sec.icon, 'blurb': sec.blurb, 'page': sec.page,
                     'custom': len(overrides.get(sec.key) or {})} for sec in site_content.SECTIONS]
    announcement = site_content.merged(overrides)['announcement']
    reset_link = session.pop('_generated_reset_link', None)
    reset_link_user = session.pop('_generated_reset_link_user', None)

    return render_template(
        'admin.html', active_page='admin',
        stats=stats, stats_doc=stats_doc, modes=modes, auto=auto, live=live, monthly_changes=monthly_changes,
        stat_fields=STAT_FIELDS, auto_stat_fields=AUTO_STAT_FIELDS, stat_labels=STAT_LABELS,
        stat_limits=STAT_LIMITS,
        upcoming=upcoming, past_events=past,
        attention=_attention_items(pending_users, message_counts, past, upcoming, current_robot_teams,
                                   stats_doc, auto),
        users=users, pending_users=pending_users, board=board, unassigned=unassigned,
        team_choices=team_choices, group_choices=group_choices, group_members=group_members,
        robot_team_of=robot_team_of, claimable=claimable,
        teams=teams, current_teams=current_teams, next_season=season_options()[0],
        awards=global_awards, team_awards=team_awards, award_icons=AWARD_ICONS, award_borders=AWARD_BORDERS,
        award_icon_label=award_icon_label,
        sponsors=load_sponsors(), sponsor_tiers=SPONSOR_TIERS,
        messages=messages, message_counts=message_counts, messages_shown=MESSAGES_SHOWN,
        subscriber_count=subscriber_count, subscribers=subscribers, subscribers_shown=SUBSCRIBERS_SHOWN,
        activities=activities, more_activity=more_activity, activity_groups=ACTIVITY_GROUPS,
        site_summary=site_summary, announcement=announcement,
        announcement_on=site_content.announcement_live(announcement, club_now()),
        reset_link=reset_link, reset_link_user=reset_link_user,
        event_locations=sorted({c['location'] for c in db['competitions'].find(
            {'location': {'$nin': [None, '']}}, {'location': 1})}),
        team_number_suggestions=next_team_numbers(t.get('team_number') for t in teams if not is_group(t)))


def next_team_numbers(numbers):
    """The next free letter for each club number in use: 77628A and 77628B suggest 77628C."""
    taken = {str(n).upper() for n in numbers if n}
    suggestions = []
    for prefix in sorted({re.sub(r'[A-Z]+$', '', n) for n in taken} - {''}):
        free = next((prefix + c for c in string.ascii_uppercase if prefix + c not in taken), None)
        if free:
            suggestions.append(free)
    return suggestions

def parse_event_date(value):
    try:
        return datetime.datetime.strptime((value or '').strip(), '%Y-%m-%dT%H:%M')
    except ValueError:
        raise UserFacingError('Enter a valid event date and time.') from None


EVENT_TEXT_MAX = 200


def _admin_redirect(tab):
    return redirect(url_for('admin_dashboard', _anchor=tab))


@app.route('/admin/add-competition', methods=['POST'])
@role_required('admin')
def admin_add_competition():
    try:
        event = {
            'name': _clean_text(request.form.get('comp_name'), EVENT_TEXT_MAX, 'Event name', required=True),
            'location': _clean_text(request.form.get('comp_location'), EVENT_TEXT_MAX, 'Location'),
            'date': parse_event_date(request.form.get('comp_date')),
        }
        link = _clean_url(request.form.get('comp_link'), 'Event link')
        if link:
            event['link'] = link
        db['competitions'].insert_one(event)
        flash(f'Added {event["name"]}.', 'success')
        log_activity('competition_add', f'Added new competition: {event["name"]}',
                     details={'name': event['name'], 'location': event['location'],
                              'date': event['date'].strftime('%Y-%m-%d %H:%M')})
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error adding competition')
        flash('Error adding competition. The details were logged for the site maintainer.', 'error')
    return _admin_redirect('events')


@app.route('/admin/delete-competition/<comp_id>', methods=['POST'])
@role_required('admin')
def admin_delete_competition(comp_id):
    competition = _find_by_id('competitions', comp_id)
    if not competition:
        flash('That event no longer exists.', 'error')
        return _admin_redirect('events')
    db['competitions'].delete_one({'_id': competition['_id']})
    flash(f'Removed {competition.get("name") or "the event"}.', 'success')
    log_activity('competition_delete', f'Deleted competition: {competition.get("name", "Unknown")}',
                 details={'name': competition.get('name', 'Unknown'),
                          'location': competition.get('location', 'Unknown')})
    return _admin_redirect('events')


def _clamp_percent(value):
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _team_blob_urls(team):
    """Every Vercel Blob URL a team document points at."""
    urls = [team.get('hero_image'), team.get('stl_path')]
    urls += [m.get('photo') for m in team.get('members', [])]
    return [u for u in urls if isinstance(u, str) and u.startswith('http')]


def _blob_still_used(url):
    """True when another team document (another season, say) still shows this file."""
    return bool(db['teams'].find_one({'$or': [{'hero_image': url}, {'stl_path': url}, {'members.photo': url}]},
                                     {'_id': 1}))


def _delete_blobs(urls, why):
    for url in urls:
        if _blob_still_used(url):
            continue
        try:
            delete_from_vercel_blob(url)
        except Exception:
            logger.exception('Failed to delete blob %s for %s', url, why)


def _park_roster_card(member, keep_photo=True):
    """Keep a linked member's card on their account, so putting them back restores it."""
    uid = str(member.get('user_id') or '')
    if ObjectId.is_valid(uid):
        card = dict(member) if keep_photo else dict(member, photo='')
        db['users'].update_one({'_id': ObjectId(uid)}, {'$set': {'roster_card': card}})


@app.route('/admin/delete-team/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_team(id):
    team = _find_team(id)
    if not team:
        flash('That team no longer exists.', 'error')
        return _admin_redirect('teams')
    number = team.get('team_number', 'Unknown')
    db['teams'].delete_one({'_id': team['_id']})
    # Award counters are keyed by team number and shared by every season of it.
    other_season = db['teams'].find_one({'team_number': number}, {'_id': 1})
    if not other_season:
        db['awards'].delete_many({'team_number': number})
    for member in team.get('members', []):
        _park_roster_card(member, keep_photo=False)
    _delete_blobs(_team_blob_urls(team), 'a deleted team')
    refresh_auto_stats()
    label = _team_label(team)
    flash(f'Removed {label}.' + (' Its award counts were kept for the other season.' if other_season else ''),
          'success')
    log_activity('team_delete', f'Deleted team {label}: {team.get("nickname", "")}',
                 details={'team_number': number, 'nickname': team.get('nickname', ''),
                          'members_count': len(team.get('members', []))})
    return _admin_redirect('teams')


@app.route('/admin/create-user', methods=['POST'])
@role_required('admin')
def admin_create_user():
    form = request.form
    username = form.get('username', '').strip()
    email = form.get('email', '').strip().lower()
    password = form.get('password', '')
    role = form.get('role', 'member')
    full_name = collapse_whitespace(form.get('full_name', ''))
    error = ('Pick a valid role.' if role not in USER_ROLES else
             f'Names must be {FULL_NAME_MAX} characters or fewer.' if len(full_name) > FULL_NAME_MAX else
             _validate_account(username, email, password, form.get('confirm_password'), require_email=False))
    if error:
        flash(error, 'error')
        return _admin_redirect('users')
    user = {'username': username, 'email': email, 'role': role, 'status': 'active', 'created_at': _utcnow(),
            'password': bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())}
    if full_name:
        user['full_name'] = full_name
    db['users'].insert_one(user)
    flash(f'Account "{username}" created. Put them on a team from the roster board.', 'success')
    log_activity('user_add', f'Created new user: {username}', details={'username': username, 'role': role})
    return _admin_redirect('users')


def _other_admin_exists(user_id):
    """Another admin who can actually sign in (a pending request does not count)."""
    return db['users'].count_documents({'role': 'admin', '_id': {'$ne': user_id},
                                        'status': {'$nin': ['pending']}}, limit=1) > 0


@app.route('/admin/update-user/<id>', methods=['POST'])
@role_required('admin')
def admin_update_user(id):
    user = _find_by_id('users', id)
    if not user:
        flash('That account no longer exists.', 'error')
        return _admin_redirect('users')
    form = request.form
    username = form.get('username', '').strip()
    email = form.get('email', '').strip().lower()
    password = form.get('password', '')
    role = form.get('role', 'member')
    full_name = collapse_whitespace(form.get('full_name', ''))
    error = ('Pick a valid role.' if role not in USER_ROLES else
             f'Names must be {FULL_NAME_MAX} characters or fewer.' if len(full_name) > FULL_NAME_MAX else
             _validate_account(username, email, password, form.get('confirm_password') if password else None,
                               existing=user, require_email=False, require_password=False))
    if not error and user.get('role') == 'admin' and role != 'admin' and not _other_admin_exists(user['_id']):
        error = 'Cannot remove the last admin.'
    if error:
        flash(error, 'error')
        return _admin_redirect('users')

    updates = {'username': username, 'email': email, 'role': role, 'full_name': full_name}
    changes = [f for f in updates if (user.get(f) or '') != updates[f]]
    if password:
        updates['password'] = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        changes.append('password')
    # Any change that could let an existing session act as someone else
    # (or with a role/password it shouldn't have) invalidates that session.
    security_relevant = any(c in ('username', 'role', 'password') for c in changes)
    update_ops = {'$set': updates}
    if security_relevant:
        update_ops['$inc'] = {'session_version': 1}
    db['users'].update_one({'_id': user['_id']}, update_ops)

    # Keep the current session in sync when admins edit themselves
    if session.get('user') == user['username']:
        session['user'] = username
        session['role'] = role
        if security_relevant:
            session['session_version'] = user.get('session_version', 0) + 1

    flash(f'Saved {username}.' if changes else 'Nothing changed.', 'success')
    if changes:
        log_activity('user_update', f'Updated user: {username}',
                     details={'username': username, 'role': role, 'changes': changes})
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    return _admin_redirect('users')


@app.route('/admin/delete-user/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_user(id):
    user = _find_by_id('users', id)
    if not user:
        flash('That account no longer exists.', 'error')
    elif user['username'] == session.get('user'):
        flash('You cannot delete your own account.', 'error')
    elif user.get('role') == 'admin' and not _other_admin_exists(user['_id']):
        flash('Cannot delete the last admin.', 'error')
    else:
        db['users'].delete_one({'_id': user['_id']})
        # Keep their roster card (it is still a real person), just without the login.
        for team in db['teams'].find({'members.user_id': id}):
            members = [dict(mem, user_id='') if mem.get('user_id') == id else mem
                       for mem in team['members']]
            db['teams'].update_one({'_id': team['_id']}, {'$set': {'members': members}})
        flash(f'Account "{user["username"]}" deleted. Their roster card stays, without a login.', 'success')
        log_activity('user_delete', f'Deleted user: {user["username"]}',
                     details={'username': user['username'], 'role': user.get('role', 'member')})
    return _admin_redirect('users')


@app.route('/admin/generate-reset-link/<id>', methods=['POST'])
@role_required('admin')
def admin_generate_reset_link(id):
    user = _find_by_id('users', id)
    if not user:
        flash('That account no longer exists.', 'error')
        return _admin_redirect('users')
    _ensure_auth_indexes()
    token = secrets.token_urlsafe(32)
    db['password_resets'].delete_many({'user_id': user['_id']})
    db['password_resets'].insert_one({'user_id': user['_id'], 'token_hash': _hash_token(token),
                                      'created_at': _utcnow()})
    session['_generated_reset_link'] = _build_reset_link(token)
    session['_generated_reset_link_user'] = user['username']
    flash(f'Reset link generated for {user["username"]}. Copy it below.', 'success')
    log_activity('reset_link_generate', f'Generated reset link for {user["username"]}',
                 details={'username': user['username']})
    return _admin_redirect('users')


MESSAGE_STATUSES = {'read': 'read', 'archive': 'archived', 'new': 'new'}


def _apply_message_action(message, action):
    """Mark read/unread, archive or delete one contact message. Returns the new status or 'deleted'."""
    if action == 'delete':
        db['contact_messages'].delete_one({'_id': message['_id']})
        # Log the sender only - never the message body.
        log_activity('message_delete', f'Deleted message from {message.get("email", "unknown")}',
                     details={'message_id': str(message['_id'])})
        return 'deleted'
    status = MESSAGE_STATUSES[action]
    db['contact_messages'].update_one({'_id': message['_id']}, {'$set': {'status': status}})
    log_activity(f'message_{action}', f'Message from {message.get("email", "unknown")} marked {status}',
                 details={'message_id': str(message['_id'])})
    return status


@app.route('/admin/messages/<id>/<action>', methods=['POST'])
@role_required('admin')
def admin_message_action(id, action):
    """Mark a contact message read, archive it, or delete it (no-JavaScript fallback)."""
    if action not in MESSAGE_STATUSES and action != 'delete':
        flash('Unknown message action.', 'error')
        return _admin_redirect('messages')
    message = _find_by_id('contact_messages', id)
    if not message:
        flash('Message not found.', 'error')
    else:
        result = _apply_message_action(message, action)
        flash('Message deleted.' if result == 'deleted' else f'Message marked {result}.', 'success')
    return _admin_redirect('messages')


SPONSOR_TIERS = ('Platinum', 'Gold', 'Silver', 'Bronze')
SPONSOR_NAME_MAX = 100


def sponsor_sort_key(sponsor):
    level = sponsor.get('level')
    rank = SPONSOR_TIERS.index(level) if level in SPONSOR_TIERS else len(SPONSOR_TIERS)
    return (rank, (sponsor.get('name') or '').lower())


@app.route('/admin/save-sponsor', methods=['POST'])
@role_required('admin')
def admin_save_sponsor():
    form = request.form
    sponsor_id = form.get('sponsor_id', '').strip()
    previous = None
    try:
        if sponsor_id:
            previous = _find_by_id('sponsors', sponsor_id)
            if not previous:
                raise UserFacingError('That sponsor no longer exists. Reload the page and try again.')
        name = _clean_text(form.get('name'), SPONSOR_NAME_MAX, 'Sponsor name', required=True)
        website = _clean_url(form.get('website'), 'Website')
        level = form.get('level', 'Bronze')
        if level not in SPONSOR_TIERS:
            raise UserFacingError('Pick a sponsorship level.')
        data = {'name': name, 'website': website, 'level': level}
        logo = request.files.get('logo')
        if logo and logo.filename:
            data['logo'] = checked_upload(logo, 'sponsors', allowed=IMAGE_EXTENSIONS, stem=name)
    except UserFacingError as e:
        flash(str(e), 'error')
        return _admin_redirect('sponsors')
    except Exception:
        logger.exception('Error saving sponsor')
        flash('Error saving sponsor. The details were logged for the site maintainer.', 'error')
        return _admin_redirect('sponsors')

    old_logo = (previous or {}).get('logo')
    remove_logo = form.get('remove_logo') == '1' and 'logo' not in data
    if previous:
        update = {'$set': data}
        if remove_logo:
            update['$unset'] = {'logo': ''}
        db['sponsors'].update_one({'_id': previous['_id']}, update)
        flash(f'Sponsor "{name}" updated.', 'success')
        log_activity('sponsor_update', f'Updated sponsor: {name}', details={'name': name, 'level': level})
    else:
        db['sponsors'].insert_one(data)
        flash(f'Sponsor "{name}" added.', 'success')
        log_activity('sponsor_add', f'Added new sponsor: {name}', details={'name': name, 'level': level})
    if isinstance(old_logo, str) and old_logo.startswith('http') and ('logo' in data or remove_logo):
        try:
            delete_from_vercel_blob(old_logo)
        except Exception:
            logger.exception('Error deleting old sponsor logo')
    return _admin_redirect('sponsors')


@app.route('/admin/delete-sponsor/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_sponsor(id):
    sponsor = _find_by_id('sponsors', id)
    if not sponsor:
        flash('That sponsor no longer exists.', 'error')
        return _admin_redirect('sponsors')
    db['sponsors'].delete_one({'_id': sponsor['_id']})
    logo = sponsor.get('logo')
    if isinstance(logo, str) and logo.startswith('http'):
        try:
            delete_from_vercel_blob(logo)
        except Exception:
            logger.exception('Failed to delete logo blob %s for deleted sponsor', logo)
    flash(f'Removed {sponsor.get("name") or "the sponsor"}.', 'success')
    log_activity('sponsor_delete', f'Deleted sponsor: {sponsor.get("name", "Unknown")}',
                 details={'name': sponsor.get('name', 'Unknown'), 'level': sponsor.get('level', 'Unknown')})
    return _admin_redirect('sponsors')


@app.route('/admin/api/sponsor/<id>/logo', methods=['POST'])
@role_required('admin')
def admin_api_sponsor_logo(id):
    """Replace one sponsor's logo: a file dropped or pasted on its row in the list."""
    sponsor = _find_by_id('sponsors', id)
    if not sponsor:
        return _json_error('That sponsor no longer exists. Reload the page and try again.', 404)
    logo = request.files.get('logo')
    if not logo or not logo.filename:
        return _json_error('Choose a logo to upload.')
    name = sponsor.get('name') or 'sponsor'
    try:
        url = checked_upload(logo, 'sponsors', allowed=IMAGE_EXTENSIONS, stem=name)
    except UserFacingError as e:
        return _json_error(str(e))
    except Exception:
        logger.exception('Sponsor logo upload failed')
        return _json_error('Upload failed. Try again in a moment.', 502)
    db['sponsors'].update_one({'_id': sponsor['_id']}, {'$set': {'logo': url}})
    old = sponsor.get('logo')
    if isinstance(old, str) and old.startswith('http') and old != url:
        try:
            delete_from_vercel_blob(old)
        except Exception:
            logger.exception('Error deleting old sponsor logo')
    log_activity('sponsor_update', f'Updated logo for sponsor: {name}', details={'name': name, 'level': sponsor.get('level')})
    return jsonify({'ok': True, 'url': get_image_url(url)})

# --- People, roster board, inline admin edits, and the shared team editor ---
# Everything here speaks JSON to static/js/admin.js and static/js/team-editor.js.
# The CSRF hook covers these routes like any other POST; the browser sends the
# token in the X-CSRF-Token header.

SUBTEAMS = ('Mechanical', 'Electrical', 'Programming', 'Notebook & Outreach')
DIVISIONS = ('High School', 'Middle School')
# Offered as <datalist> suggestions; people can still type anything.
ROLE_SUGGESTIONS = ('Captain', 'Co-Captain', 'Driver', 'Builder', 'Programmer', 'Designer (CAD)',
                    'Notebooker', 'Scout', 'Strategist', 'Outreach', 'Mentor')
GOAL_SUGGESTIONS = ('Qualify for States', 'Qualify for Worlds', 'Win a tournament', 'Win the Excellence Award',
                    'Win the Design Award', 'Top 10 in skills', 'Finish the notebook every week',
                    'Reliable autonomous')
SPEC_SUGGESTIONS = {
    'drive_train': ('6-motor 450 RPM', '6-motor 600 RPM', '8-motor 450 RPM', '4-motor 200 RPM',
                    'X-drive', 'Mecanum'),
    'lift_system': ('4-bar lift', '6-bar lift', 'Double reverse 4-bar', 'Cascade lift', 'Arm', 'None'),
    'intake': ('Side rollers', 'Front rollers', 'Claw', 'Conveyor', 'Flex-wheel intake'),
    'auton_consistency': ('50%', '60%', '70%', '80%', '90%', '95%', '100%'),
}
FIRST_CLUB_YEAR = 2005


def current_season(today=None):
    """VEX seasons run spring to spring; the new game is revealed at Worlds in late April."""
    today = today or _utcnow()
    start = today.year if today.month >= 5 else today.year - 1
    return f'{start}-{(start + 1) % 100:02d}'


def season_options(existing=()):
    """Next season, this one and the eight before it, plus any odd value already stored."""
    start = int(current_season()[:4]) + 1
    seasons = [f'{y}-{(y + 1) % 100:02d}' for y in range(start, start - 10, -1)]
    return seasons + sorted({s for s in existing if s and s not in seasons}, reverse=True)


def year_options():
    return list(range(_utcnow().year + 1, FIRST_CLUB_YEAR - 1, -1))


def month_suggestions():
    """'Mon YYYY' for the last two years and the next one, newest first, for journey dates."""
    now = _utcnow()
    months = []
    for offset in range(12, -25, -1):
        index = now.year * 12 + now.month - 1 + offset
        months.append(datetime.date(index // 12, index % 12 + 1, 1).strftime('%b %Y'))
    return months
# Anyone can reach these, so no SVG (it can carry script).
MEMBER_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
LIST_MAX_ITEMS = 30


def _json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _json_error(message, status=400):
    return jsonify({'error': message}), status


def _new_member_id():
    return secrets.token_hex(8)


def _ensure_member_ids():
    """Give every roster entry a stable member_id so a drag can name one exact person."""
    for team in db['teams'].find({'members': {'$elemMatch': {'member_id': {'$exists': False}}}}):
        members = [m if m.get('member_id') else dict(m, member_id=_new_member_id())
                   for m in team.get('members', [])]
        db['teams'].update_one({'_id': team['_id']}, {'$set': {'members': members}})


def _team_label(team):
    label = (team.get('title') if is_group(team) else None) or team.get('team_number') or 'Team'
    if team.get('season'):
        label += f" ({team['season']})"
    return label


def _card(member):
    """The fields the board and editor need, with the user id as a plain string."""
    return {
        'member_id': member.get('member_id', ''),
        'name': member.get('name') or '',
        'role': member.get('role') or '',
        'user_id': str(member.get('user_id') or ''),
        'photo': real_photo(member.get('photo') or ''),
        'subteam': member.get('subteam') or '',
    }


def _clean_text(value, limit, field_label, required=False):
    text = value.strip() if isinstance(value, str) else ('' if value is None else str(value).strip())
    if required and not text:
        raise UserFacingError(f'{field_label} cannot be empty.')
    if len(text) > limit:
        raise UserFacingError(f'{field_label} must be {limit} characters or fewer.')
    return text


def _clean_year(value, field_label):
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    try:
        year = int(text)
    except ValueError:
        raise UserFacingError(f'{field_label} must be a number.') from None
    if not 0 <= year <= 2100:
        raise UserFacingError(f'{field_label} is out of range.')
    return year


def _clean_url(value, field_label):
    text = _clean_text(value, 500, field_label)
    if text and not re.match(r'https?://', text, re.IGNORECASE):
        raise UserFacingError(f'{field_label} must start with http:// or https://.')
    return text


def _rosters_to_leave(user_id, team):
    """Rosters an account must leave to join `team`: every robot team, or just that group.

    A person is on at most one robot team but can sit in any number of groups
    (Media, Fundraising, ...), with or without a robot team.
    """
    if is_group(team):
        return {'_id': team['_id'], 'members.user_id': user_id}
    return {'members.user_id': user_id, **ROBOT_TEAMS}


def _pull_user_from_rosters(user_id, team):
    db['teams'].update_many(_rosters_to_leave(user_id, team), {'$pull': {'members': {'user_id': user_id}}})


def _on_any_roster(user_id):
    return db['teams'].find_one({'members.user_id': user_id}, {'_id': 1}) is not None


def _card_for_user(user):
    """The roster entry an account gets when placed on a team.

    Taking someone off every roster parks their card on the account, so
    putting them back (or Undo) restores their name, role and photo instead of
    starting over from the username.
    """
    parked = user.get('roster_card')
    if isinstance(parked, dict) and parked.get('member_id'):
        return dict(parked, user_id=str(user['_id']))
    return {'member_id': _new_member_id(), 'name': user.get('full_name') or user.get('username', ''),
            'role': 'Member', 'user_id': str(user['_id']), 'photo': ''}


def _place_user_on_team(user, team):
    """Add an account to a roster (taking it off any other robot team). Returns the new card."""
    _pull_user_from_rosters(str(user['_id']), team)
    member = _card_for_user(user)
    db['teams'].update_one({'_id': team['_id']}, {'$push': {'members': member}})
    db['users'].update_one({'_id': user['_id']}, {'$unset': {'roster_card': ''}})
    return member


# --- Approvals and roles ---

def _is_active(user):
    # Accounts made before sign-up existed have no status and count as active.
    return user.get('status', 'active') == 'active'


def _unlinked_card_team(member_id):
    """The team holding this roster card, if the card has no login linked to it yet."""
    return db['teams'].find_one({'members': {'$elemMatch': {'member_id': member_id,
                                                            'user_id': {'$in': ['', None]}}}})


def _link_card(team, member_id, user):
    """Attach a login to a roster card that had none. The account leaves any other robot team."""
    uid = str(user['_id'])
    _pull_user_from_rosters(uid, team)
    db['teams'].update_one({'_id': team['_id'], 'members.member_id': member_id},
                           {'$set': {'members.$.user_id': uid}})
    db['users'].update_one({'_id': user['_id']}, {'$unset': {'roster_card': ''}})
    team = db['teams'].find_one({'_id': team['_id']})
    return next(m for m in team.get('members', []) if m.get('member_id') == member_id)


@app.route('/admin/api/users/<id>/approve', methods=['POST'])
@role_required('admin')
def admin_api_approve_user(id):
    body = _json_body()
    role = body.get('role', 'member')
    if role not in USER_ROLES:
        return _json_error('Pick a valid role.')
    user = _find_by_id('users', id)
    if not user:
        return _json_error('That account no longer exists.', 404)
    if user.get('status') != 'pending':
        return _json_error('That request was already handled.', 409)
    team, claim = None, str(body.get('member_id') or '')
    if claim:
        team = _unlinked_card_team(claim)
        if not team:
            return _json_error('That roster card is already linked to a login, or was removed.', 409)
    elif body.get('team_id'):
        team = _find_team(body['team_id'])
        if not team:
            return _json_error('That team no longer exists.', 404)

    db['users'].update_one({'_id': user['_id']},
                           {'$set': {'status': 'active', 'role': role},
                            '$unset': {'requested_team': ''}})
    card = None
    if claim:
        card = _card(_link_card(team, claim, user))
    elif team:
        card = _card(_place_user_on_team(user, team))
    refresh_auto_stats()
    log_activity('user_approve', f"Approved {user['username']} as {role}"
                 + (f" on {_team_label(team)}" if team else ''),
                 details={'username': user['username'], 'role': role})
    return jsonify({'ok': True, 'member': card, 'team_id': str(team['_id']) if team else None,
                    'user': {'_id': id, 'username': user['username'], 'role': role}})


@app.route('/admin/api/users/<id>/reject', methods=['POST'])
@role_required('admin')
def admin_api_reject_user(id):
    user = _find_by_id('users', id)
    if not user:
        return _json_error('That account no longer exists.', 404)
    if user.get('status') != 'pending':
        return _json_error('Only pending requests can be rejected.', 409)
    db['users'].delete_one({'_id': user['_id']})
    log_activity('user_reject', f"Rejected account request from {user['username']}",
                 details={'username': user['username']})
    return jsonify({'ok': True})


@app.route('/admin/api/users/<id>/role', methods=['POST'])
@role_required('admin')
def admin_api_user_role(id):
    role = _json_body().get('role')
    if role not in USER_ROLES:
        return _json_error('Pick a valid role.')
    user = _find_by_id('users', id)
    if not user:
        return _json_error('User not found.', 404)
    if not _is_active(user):
        return _json_error('Approve this account first.', 409)
    if user.get('role') == role:
        return jsonify({'ok': True})
    if user.get('role') == 'admin' and not _other_admin_exists(user['_id']):
        return _json_error('Cannot remove the last admin.')
    db['users'].update_one({'_id': user['_id']},
                           {'$set': {'role': role}, '$inc': {'session_version': 1}})
    if session.get('user') == user['username']:
        session['role'] = role
        session['session_version'] = user.get('session_version', 0) + 1
    log_activity('user_update', f"Changed {user['username']} to {role}",
                 details={'username': user['username'], 'role': role, 'changes': ['role']})
    return jsonify({'ok': True, 'self_demoted': session.get('user') == user['username'] and role != 'admin'})


# --- Roster board ---

@app.route('/admin/api/roster/move', methods=['POST'])
@role_required('admin')
def admin_api_roster_move():
    """Put a roster card (or a not-yet-rostered account) on a team or group, or take it off.

    Each person is on at most one robot team, so dropping on a team moves them
    there, keeping their groups. Dropping on a group adds them to it and leaves
    them where they were. `to_team_id` null takes the card off its roster (a card
    with no login only with `remove`, which Undo uses). `mode` in the response is
    "move" when a card changed rosters and "add" when a new card joined one while
    the dragged card stayed put; `from_team_id` is where the card came from, for Undo.
    """
    body = _json_body()
    member_id, user_id, to_id = body.get('member_id'), body.get('user_id'), body.get('to_team_id')
    _ensure_member_ids()

    target = None
    if to_id:
        target = _find_team(to_id)
        if not target:
            return _json_error('That team no longer exists.', 404)

    user = None
    if member_id:
        source = db['teams'].find_one({'members.member_id': member_id})
        if not source:
            return _json_error('That person is no longer on a roster.', 404)
        member = next(m for m in source['members'] if m.get('member_id') == member_id)
    elif user_id:
        user = _find_by_id('users', user_id)
        if not user:
            return _json_error('User not found.', 404)
        if not _is_active(user):
            return _json_error('Approve this account before putting it on a team.', 409)
        source = db['teams'].find_one({'members.user_id': str(user['_id']), **ROBOT_TEAMS})
        member = (next(m for m in source['members'] if m.get('user_id') == str(user['_id'])) if source
                  else _card_for_user(user))
    else:
        return _json_error('Say who to move.')

    linked = str(member.get('user_id') or '')
    name = member.get('name') or 'That person'
    if not target and not linked and not body.get('remove'):
        # Unassigned lists accounts; a card with no login would simply vanish.
        return _json_error('People without a login are removed in the team editor.')
    if target and source and source['_id'] == target['_id']:
        return jsonify({'ok': True, 'mode': 'move', 'member': _card(member), 'from_team_id': str(source['_id']),
                        'to_team_id': str(source['_id'])})

    # A group card dropped on a team stays in its group. If the person already
    # has a team card, that card moves; otherwise they get a new one.
    added = bool(target) and (is_group(target) or (source is not None and is_group(source)))
    if target and not is_group(target) and source and is_group(source):
        robot = db['teams'].find_one({'members.user_id': linked, **ROBOT_TEAMS}) if linked else None
        if robot and robot['_id'] == target['_id']:
            return _json_error(f'{name} is already on {_team_label(target)}.', 409)
        if robot:
            source, added = robot, False
            member = next(m for m in robot['members'] if m.get('user_id') == linked)
        else:
            account = _find_by_id('users', linked) if linked else None
            source, member = None, (_card_for_user(account) if account else _copied_card(member))
    elif target and is_group(target):
        if linked and db['teams'].find_one({'_id': target['_id'], 'members.user_id': linked}, {'_id': 1}):
            return _json_error(f'{name} is already in {_team_label(target)}.', 409)
        member = _copied_card(member)

    from_id = str(source['_id']) if source else None
    if source and not added:
        db['teams'].update_one({'_id': source['_id']},
                               {'$pull': {'members': {'member_id': member['member_id']}}})
    if target:
        if linked:
            _pull_user_from_rosters(linked, target)
        db['teams'].update_one({'_id': target['_id']}, {'$push': {'members': member}})
    if linked and ObjectId.is_valid(linked):
        if target and not is_group(target):
            db['users'].update_one({'_id': ObjectId(linked)}, {'$unset': {'roster_card': ''}})
        elif not target and source and not is_group(source):
            db['users'].update_one({'_id': ObjectId(linked)}, {'$set': {'roster_card': member}})
    refresh_auto_stats()

    who = member.get('name') or 'a member'
    if not target:
        what = f"Took {who} off {_team_label(source) if source else 'every roster'}"
    else:
        what = f"{'Added' if added else 'Moved'} {who} to {_team_label(target)}"
    log_activity('roster_move', what,
                 details={'name': member.get('name'), 'from': from_id,
                          'to': str(target['_id']) if target else None})
    return jsonify({'ok': True, 'mode': 'add' if added else 'move', 'member': _card(member),
                    'from_team_id': from_id, 'to_team_id': str(target['_id']) if target else None,
                    'unassigned': bool(linked) and not target and not _on_any_roster(linked)})


def _copied_card(member):
    """A new roster card for the same person: name, photo and login, but a fresh id and role."""
    return {'member_id': _new_member_id(), 'name': member.get('name') or '', 'role': 'Member',
            'user_id': str(member.get('user_id') or ''), 'photo': member.get('photo') or ''}


@app.route('/admin/api/roster/link', methods=['POST'])
@role_required('admin')
def admin_api_roster_link():
    """Give a roster card with no login an account, or (user_id null) take the login off a card."""
    body = _json_body()
    member_id = str(body.get('member_id') or '')
    team = db['teams'].find_one({'members.member_id': member_id}) if member_id else None
    if not team:
        return _json_error('That person is no longer on a roster.', 404)
    member = next(m for m in team['members'] if m.get('member_id') == member_id)
    if body.get('user_id') is None:
        linked = str(member.get('user_id') or '')
        if not linked:
            return jsonify({'ok': True, 'member': _card(member)})
        db['teams'].update_one({'_id': team['_id'], 'members.member_id': member_id},
                               {'$set': {'members.$.user_id': ''}})
        log_activity('roster_link', f"Unlinked the login from {member.get('name')}'s card on {_team_label(team)}",
                     details={'member_id': member_id})
        return jsonify({'ok': True, 'member': _card(dict(member, user_id=''))})

    user = _find_by_id('users', body.get('user_id'))
    if not user:
        return _json_error('User not found.', 404)
    if not _is_active(user):
        return _json_error('Approve this account first.', 409)
    if member.get('user_id'):
        return _json_error('That card already has a login. Unlink it first.', 409)
    card = _link_card(team, member_id, user)
    refresh_auto_stats()
    log_activity('roster_link', f"Linked {user['username']} to {member.get('name')} on {_team_label(team)}",
                 details={'member_id': member_id, 'username': user['username']})
    return jsonify({'ok': True, 'member': _card(card), 'team_id': str(team['_id'])})


# --- Club numbers, awards, events ---

def _clean_count(value, limit, label='That number'):
    """A whole number from 0 to limit. JSON floats like 3.0 pass; booleans, 3.9 and Infinity do not."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise UserFacingError('Enter a whole number.')
    if value < 0:
        raise UserFacingError(f'{label} cannot be negative.')
    if value > limit:
        raise UserFacingError(f'{label} can be at most {limit:,}.')
    return value


@app.route('/admin/api/stats', methods=['POST'])
@role_required('admin')
def admin_api_stats():
    body = _json_body()
    field = body.get('field')
    if field not in STAT_FIELDS:
        return _json_error('Unknown statistic.')
    label = STAT_LABELS[field]
    if 'mode' in body:
        mode = body.get('mode')
        if field not in AUTO_STAT_FIELDS or mode not in ('auto', 'manual'):
            return _json_error('That number cannot count itself.')
        refresh_auto_stats()
        db['site_metadata'].update_one({'_id': 'global_stats'}, {'$set': {f'modes.{field}': mode}}, upsert=True)
        shown = public_stats(db['site_metadata'].find_one({'_id': 'global_stats'}))[field]
        log_activity('stats_update', f'{label} is now {"counted automatically" if mode == "auto" else "typed in"}',
                     details={'field': field, 'mode': mode})
        return jsonify({'ok': True, 'mode': mode, 'value': shown})
    try:
        value = _clean_count(body.get('value'), STAT_LIMITS[field], label)
    except UserFacingError as e:
        return _json_error(str(e))
    prev = (db['site_metadata'].find_one({'_id': 'global_stats'}) or {}).get(field, 0)
    db['site_metadata'].update_one({'_id': 'global_stats'}, {'$set': {field: value}}, upsert=True)
    change_key = field.replace('_count', '').replace('_built', '') + '_change'
    log_activity('stats_update', f'Set {label.lower()} to {value}', details={field: value, change_key: value - prev})
    return jsonify({'ok': True, 'value': value})


AWARD_COUNT_MAX = 999
AWARD_TITLE_MAX = 80
# The award artwork in static/assets/icons (the other files there are site icons).
AWARD_ICONS = ('exellence_award.png', 'tournament_champions.png', 'tournament_finalists.png',
               'design_award.png', 'judges_award.png', 'innovate_award.png', 'create_award.png',
               'amaze_award.png', 'robot_skills_champion.png', 'sportsmanship.png', 'triple_crown.png',
               'world_championship.png')
AWARD_BORDERS = ('gold', 'purple', 'red', 'green', 'blue', 'yellow', 'grey')


def award_icon_label(filename):
    return filename.rsplit('.', 1)[0].replace('exellence', 'excellence').replace('_', ' ').title()


def _ensure_award_order():
    """Give every club award category a sort position, and every team copy its category's."""
    link_team_award_categories()
    unsorted = list(db['awards'].find({'team_number': {'$exists': False}, 'sort': {'$exists': False}},
                                      {'_id': 1}).sort('_id', 1))
    if unsorted:
        top = max([a.get('sort') or 0 for a in db['awards'].find({'team_number': {'$exists': False},
                                                                  'sort': {'$exists': True}}, {'sort': 1})],
                  default=0)
        for offset, award in enumerate(unsorted, 1):
            db['awards'].update_one({'_id': award['_id']}, {'$set': {'sort': top + offset}})
    for category in db['awards'].find({'team_number': {'$exists': False}}, {'sort': 1}):
        db['awards'].update_many({'category_id': str(category['_id']), 'sort': {'$ne': category.get('sort')}},
                                 {'$set': {'sort': category.get('sort')}})


def _award_category_fields(body, partial=False):
    """Validated style fields for an award category, from a JSON body."""
    out = {}
    if 'title' in body or not partial:
        out['title'] = _clean_text(body.get('title'), AWARD_TITLE_MAX, 'Award name', required=True)
    if 'icon' in body or not partial:
        if body.get('icon') not in AWARD_ICONS:
            raise UserFacingError('Pick an icon for the award.')
        out['icon'] = body['icon']
    if 'border' in body:
        if body['border'] not in ('',) + AWARD_BORDERS:
            raise UserFacingError('Pick a listed border colour.')
        out['border'] = body['border'] or None
    if 'layout' in body:
        if body['layout'] not in ('', 'wide'):
            raise UserFacingError('Pick a listed layout.')
        out['layout'] = body['layout'] or None
    if 'shimmer' in body:
        out['shimmer'] = bool(body['shimmer'])
    return out


def _category_title_taken(title, exclude=None):
    query = {'team_number': {'$exists': False}, 'title': re.compile(f'^{re.escape(title)}$', re.IGNORECASE)}
    if exclude is not None:
        query['_id'] = {'$ne': exclude}
    return bool(db['awards'].find_one(query, {'_id': 1}))


@app.route('/admin/api/award-categories', methods=['POST'])
@role_required('admin')
def admin_api_award_category_add():
    try:
        fields = _award_category_fields(_json_body())
    except UserFacingError as e:
        return _json_error(str(e))
    if _category_title_taken(fields['title']):
        return _json_error(f'There is already an award called "{fields["title"]}".', 409)
    _ensure_award_order()
    top = max([a.get('sort') or 0 for a in db['awards'].find({'team_number': {'$exists': False}}, {'sort': 1})],
              default=0)
    category = dict(fields, count=0, sort=top + 1)
    category['_id'] = db['awards'].insert_one(category).inserted_id
    numbers = sorted({n for n in db['teams'].distinct('team_number', ROBOT_TEAMS) if n})
    if numbers:
        db['awards'].insert_many([_award_copy(category, n) for n in numbers])
    log_activity('award_category_add', f'Added award category "{fields["title"]}"',
                 details={'title': fields['title']})
    flash(f'Added "{fields["title"]}" to the club and to every team.', 'success')
    return jsonify({'ok': True, 'id': str(category['_id'])})


@app.route('/admin/api/award-categories/<id>', methods=['POST', 'DELETE'])
@role_required('admin')
def admin_api_award_category(id):
    category = _find_by_id('awards', id)
    if not category or 'team_number' in category:
        return _json_error('That award category no longer exists.', 404)
    link_team_award_categories()
    if request.method == 'DELETE':
        db['awards'].delete_many({'category_id': str(category['_id'])})
        db['awards'].delete_one({'_id': category['_id']})
        refresh_auto_stats()
        log_activity('award_category_delete', f'Deleted award category "{category.get("title")}"',
                     details={'title': category.get('title')})
        flash(f'Deleted "{category.get("title")}" and every team\'s count of it.', 'success')
        return jsonify({'ok': True})
    try:
        fields = _award_category_fields(_json_body(), partial=True)
    except UserFacingError as e:
        return _json_error(str(e))
    if not fields:
        return _json_error('Nothing to change.')
    if 'title' in fields and _category_title_taken(fields['title'], exclude=category['_id']):
        return _json_error(f'There is already an award called "{fields["title"]}".', 409)
    db['awards'].update_one({'_id': category['_id']}, {'$set': fields})
    db['awards'].update_many({'category_id': str(category['_id'])}, {'$set': fields})
    log_activity('award_category_update', f'Changed award category "{category.get("title")}"',
                 details={'title': category.get('title'), 'fields': sorted(fields)})
    return jsonify({'ok': True, **{k: v for k, v in fields.items()}})


@app.route('/admin/api/award-categories/<id>/move', methods=['POST'])
@role_required('admin')
def admin_api_award_category_move(id):
    step = _json_body().get('step')
    if step not in (-1, 1):
        return _json_error('Move up or down one place.')
    _ensure_award_order()
    ordered = list(db['awards'].find({'team_number': {'$exists': False}}).sort(AWARD_ORDER))
    index = next((i for i, a in enumerate(ordered) if str(a['_id']) == id), None)
    if index is None:
        return _json_error('That award category no longer exists.', 404)
    other = index + step
    if not 0 <= other < len(ordered):
        return jsonify({'ok': True})
    a, b = ordered[index], ordered[other]
    for doc, sort in ((a, b.get('sort')), (b, a.get('sort'))):
        db['awards'].update_one({'_id': doc['_id']}, {'$set': {'sort': sort}})
        db['awards'].update_many({'category_id': str(doc['_id'])}, {'$set': {'sort': sort}})
    return jsonify({'ok': True})


@app.route('/admin/api/awards/<id>', methods=['POST'])
@role_required('admin')
def admin_api_award(id):
    try:
        count = _clean_count(_json_body().get('count'), AWARD_COUNT_MAX, 'Counts')
    except UserFacingError as e:
        return _json_error(str(e))
    award = _find_by_id('awards', id)
    if not award:
        return _json_error('Award not found.', 404)
    change = count - award.get('count', 0)
    db['awards'].update_one({'_id': award['_id']}, {'$set': {'count': count}})
    if change:
        owner = f"Team {award['team_number']} " if award.get('team_number') else ''
        log_activity('awards_update', f'{owner}"{award.get("title", "Award")}" set to {count}',
                     details={'title': award.get('title'), 'team_number': award.get('team_number'),
                              'count_change': change})
        if not award.get('team_number'):
            refresh_auto_stats()
    return jsonify({'ok': True, 'count': count})


EVENT_FIELDS = ('name', 'location', 'date', 'link')


@app.route('/admin/api/events/<id>', methods=['POST'])
@role_required('admin')
def admin_api_event(id):
    body = _json_body()
    field = body.get('field')
    event = _find_by_id('competitions', id)
    if not event:
        return _json_error('Event not found.', 404)
    if field not in EVENT_FIELDS:
        return _json_error('That field cannot be edited here.')
    try:
        if field == 'name':
            value = _clean_text(body.get('value'), EVENT_TEXT_MAX, 'Event name', required=True)
        elif field == 'location':
            value = _clean_text(body.get('value'), EVENT_TEXT_MAX, 'Location')
        elif field == 'link':
            value = _clean_url(body.get('value'), 'Event link')
        else:
            value = parse_event_date(body.get('value'))
    except UserFacingError as e:
        return _json_error(str(e))
    old = event.get(field)
    db['competitions'].update_one({'_id': event['_id']}, {'$set': {field: value}})
    log_activity('competition_update', f'Updated {field} of {event.get("name", "an event")}',
                 details={'name': event.get('name'), 'field': field,
                          'from': _loggable(old), 'to': _loggable(value)})
    return jsonify({'ok': True})


@app.route('/admin/api/events/prune', methods=['POST'])
@role_required('admin')
def admin_api_events_prune():
    """Delete every event whose start time has passed."""
    result = db['competitions'].delete_many({'date': {'$lt': club_now()}})
    if result.deleted_count:
        log_activity('competition_delete', f'Cleared {result.deleted_count} past event'
                     f'{"s" if result.deleted_count != 1 else ""}', details={'count': result.deleted_count})
    return jsonify({'ok': True, 'deleted': result.deleted_count})


def _loggable(value, limit=200):
    """A short, JSON-safe copy of a value for the activity log."""
    if isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    if isinstance(value, list):
        value = ', '.join(str(v) for v in value)
    text = '' if value is None else str(value)
    return text if len(text) <= limit else text[:limit - 1] + '…'


# --- Teams and seasons ---

TEAM_NUMBER_RE = re.compile(r'[A-Z0-9-]{1,20}')
GROUP_SLUG_RE = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
GROUP_SLUG_MAX, GROUP_TITLE_MAX = 40, 60
SEASON_RE = re.compile(r'\d{4}-\d{2}')


@app.route('/admin/quick-team', methods=['POST'])
@role_required('admin')
def admin_quick_team():
    """Create a team from just its number and go straight to the editor."""
    number = request.form.get('team_number', '').strip().upper()
    if not TEAM_NUMBER_RE.fullmatch(number):
        flash('Enter a team number like 77628D.', 'error')
        return _admin_redirect('teams')
    if db['teams'].find_one({'team_number': number}):
        flash(f'Team {number} already exists. To start its next season, use "New season" on its card.', 'error')
        return _admin_redirect('teams')
    team_id = db['teams'].insert_one({'team_number': number, 'season': current_season(), 'nickname': '',
                                      'tagline': '', 'specs': {}, 'members': [], 'goals': [],
                                      'journey': []}).inserted_id
    seed_team_awards(number)
    refresh_auto_stats()
    log_activity('team_add', f'Added new team {number}', details={'team_number': number, 'members_count': 0})
    flash(f'Team {number} created. Fill in the details below; everything saves as you go.', 'success')
    return redirect(url_for('manage_team', team_id=str(team_id)))


def group_slug(title):
    """The URL slug for a group title: "Media & Outreach" becomes media-outreach."""
    return re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:GROUP_SLUG_MAX].strip('-')


@app.route('/admin/quick-group', methods=['POST'])
@role_required('admin')
def admin_quick_group():
    """Create a group (Media, Fundraising, ...) from just its title and go to its editor."""
    title = collapse_whitespace(request.form.get('title', ''))
    slug = group_slug(title)
    if not slug or len(title) > GROUP_TITLE_MAX:
        flash(f'Give the group a name of up to {GROUP_TITLE_MAX} characters, like Media.', 'error')
        return _admin_redirect('teams')
    clash = db['teams'].find_one({'team_number': {'$in': [slug, slug.upper()]}}, {'kind': 1, 'title': 1})
    if clash:
        flash(f'{_team_label(clash)} already uses that name.', 'error')
        return _admin_redirect('teams')
    team_id = db['teams'].insert_one({'kind': GROUP_KIND, 'team_number': slug, 'title': title,
                                      'season': current_season(), 'tagline': '', 'members': [], 'goals': [],
                                      'journey': []}).inserted_id
    refresh_auto_stats()
    log_activity('team_add', f'Added new group {title}', details={'team_number': slug, 'members_count': 0})
    flash(f'{title} created. Fill in the details below; everything saves as you go.', 'success')
    return redirect(url_for('manage_team', team_id=str(team_id)))


CARRIED_TEAM_FIELDS = ('kind', 'title', 'team_number', 'nickname', 'tagline', 'division', 'since', 'worlds_appearances',
                       'robotevents_number', 'notebook_link', 'hero_image')


@app.route('/admin/api/teams/<id>/new-season', methods=['POST'])
@role_required('admin')
def admin_api_new_season(id):
    """Start a team's next season: same identity and roster, fresh specs, goals and journey.

    Logins move to the new season's cards; last season keeps its roster as
    names only, so each account still sits on exactly one card.
    """
    team = _find_team(id)
    if not team:
        return _json_error('That team no longer exists.', 404)
    season = str(_json_body().get('season') or '').strip()
    if not SEASON_RE.fullmatch(season):
        return _json_error('Pick a season like 2026-27.')
    number = team.get('team_number')
    if db['teams'].find_one({'team_number': number, 'season': season}, {'_id': 1}):
        return _json_error(f'{number} already has a {season} profile.', 409)
    members = team.get('members') or []
    doc = {k: team[k] for k in CARRIED_TEAM_FIELDS if team.get(k) not in (None, '')}
    doc.update(season=season, specs={}, goals=[], journey=[],
               members=[dict(m, member_id=_new_member_id()) for m in members])
    try:
        new_id = db['teams'].insert_one(doc).inserted_id
    except DuplicateKeyError:
        return _json_error(f'{number} already has a {season} profile.', 409)
    if any(m.get('user_id') for m in members):
        db['teams'].update_one({'_id': team['_id']},
                               {'$set': {'members': [dict(m, user_id='') for m in members]}})
    if not is_group(team):
        seed_team_awards(number)
    refresh_auto_stats()
    log_activity('season_add', f'Started {season} for {number}', details={'team_number': number, 'season': season})
    flash(f'{number} {season} is ready. Last season stays on the team page under its season picker.', 'success')
    return jsonify({'ok': True, 'url': url_for('manage_team', team_id=str(new_id))})


# --- Contact messages, newsletter, activity ---

@app.route('/admin/api/messages/<id>', methods=['POST'])
@role_required('admin')
def admin_api_message(id):
    action = _json_body().get('action')
    if action not in MESSAGE_STATUSES and action != 'delete':
        return _json_error('Unknown message action.')
    message = _find_by_id('contact_messages', id)
    if not message:
        return _json_error('That message no longer exists.', 404)
    return jsonify({'ok': True, 'status': _apply_message_action(message, action)})


@app.route('/admin/api/messages/bulk', methods=['POST'])
@role_required('admin')
def admin_api_messages_bulk():
    body = _json_body()
    action, ids = body.get('action'), body.get('ids')
    if action not in MESSAGE_STATUSES and action != 'delete':
        return _json_error('Unknown message action.')
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        return _json_error('Pick up to 500 messages.')
    object_ids = [ObjectId(i) for i in ids if isinstance(i, str) and ObjectId.is_valid(i)]
    query = {'_id': {'$in': object_ids}}
    if action == 'delete':
        done = db['contact_messages'].delete_many(query).deleted_count
    else:
        done = db['contact_messages'].update_many(query, {'$set': {'status': MESSAGE_STATUSES[action]}}).matched_count
    if done:
        verb = 'Deleted' if action == 'delete' else f'Marked {MESSAGE_STATUSES[action]}'
        log_activity('message_delete' if action == 'delete' else f'message_{action}',
                     f'{verb} {done} message{"s" if done != 1 else ""}', details={'count': done})
    return jsonify({'ok': True, 'count': done, 'status': 'deleted' if action == 'delete' else MESSAGE_STATUSES[action]})


@app.route('/admin/api/subscribers/<id>', methods=['DELETE'])
@role_required('admin')
def admin_api_subscriber_delete(id):
    subscriber = _find_by_id('newsletter_subscribers', id)
    if not subscriber:
        return _json_error('That address is no longer on the list.', 404)
    db['newsletter_subscribers'].delete_one({'_id': subscriber['_id']})
    log_activity('subscriber_remove', f'Removed {subscriber.get("email")} from the newsletter',
                 details={'email': subscriber.get('email')})
    return jsonify({'ok': True})


ACTIVITY_PAGE = 30


def _activity_row(a):
    stamp = a.get('timestamp')
    return {'_id': str(a['_id']), 'type': a.get('type'), 'icon': get_activity_icon(a.get('type')),
            'title': get_activity_title(a.get('type')), 'description': a.get('description') or '',
            'user': a.get('user') or '', 'ago': get_time_ago(stamp) if stamp else '',
            'when': stamp.strftime('%b %d, %Y %I:%M %p UTC') if stamp else '',
            'timestamp': stamp.isoformat() if stamp else ''}


def activity_page(group='', before=None, limit=None):
    """Newest activity first; `before` (an ISO timestamp) continues an earlier page."""
    limit = limit or ACTIVITY_PAGE
    query = {}
    if group:
        query['type'] = {'$in': activity_types_in(group)}
    if before:
        query['timestamp'] = {'$lt': before}
    rows = [_activity_row(a) for a in db['activities'].find(query).sort('timestamp', -1).limit(limit + 1)]
    return rows[:limit], len(rows) > limit


@app.route('/admin/api/activity')
@role_required('admin')
def admin_api_activity():
    group = request.args.get('group', '')
    if group and group not in dict(ACTIVITY_GROUPS):
        return _json_error('Unknown filter.')
    before = None
    if request.args.get('before'):
        try:
            before = datetime.datetime.fromisoformat(request.args['before'])
        except ValueError:
            return _json_error('Bad page marker.')
    rows, more = activity_page(group, before)
    return jsonify({'items': rows, 'more': more})


# --- Site content editor ---

def _blob_srcs(value):
    """Uploaded image URLs anywhere inside a stored site-content value."""
    if isinstance(value, dict):
        found = [value['src']] if isinstance(value.get('src'), str) else []
        return found + [s for v in value.values() if isinstance(v, (dict, list)) for s in _blob_srcs(v)]
    if isinstance(value, list):
        return [s for v in value for s in _blob_srcs(v)]
    return []


@app.route('/admin/site')
@role_required('admin')
def admin_site():
    overrides = _site_overrides()
    values = site_content.merged(overrides)
    return render_template('site_editor.html', active_page='admin', sections=site_content.SECTIONS,
                           values=values, overrides=overrides, icons=site_content.ICONS,
                           platforms=site_content.SOCIAL_PLATFORMS, day_names=site_content.DAY_NAMES,
                           gallery_keys=sorted(k for k in image_manifest if k.startswith('photos/carousel')),
                           club_timezone=CLUB_TIMEZONE, group_choices=_group_choices(), can_pick_group=True)


def _site_field(key):
    section, field = site_content.field_for(key)
    if not field:
        raise UserFacingError('That setting does not exist.')
    return section, field


class SiteAccessError(UserFacingError):
    status = 403


def _is_admin(user):
    return bool(user) and role_at_least(user.get('role', 'member'), 'admin')


def _check_site_access(section, field):
    """Admins edit everything. The fundraising group edits its own section, but only
    editors and admins choose which group that is."""
    user = _session_user()
    if _is_admin(user):
        return
    if section.role == 'fundraisers' and can_manage_fundraisers(user):
        if field.key == 'owner_group' and not role_at_least(user.get('role', 'member'), 'editor'):
            raise SiteAccessError('Only editors and admins can change the fundraising group.')
        return
    raise SiteAccessError('You do not have permission to do that.')


def _site_log_type(section):
    return 'fundraiser_edit' if section.key == 'fundraisers' else 'site_edit'


@app.route('/admin/api/site', methods=['POST'])
@login_required
def admin_api_site():
    body = _json_body()
    key = str(body.get('key') or '')
    try:
        section, field = _site_field(key)
        _check_site_access(section, field)
        value = site_content.clean_value(field, body.get('value'))
    except (UserFacingError, site_content.ContentError) as e:
        return _json_error(str(e), getattr(e, 'status', 400))
    if key == 'fundraisers.owner_group' and value not in _group_slugs():
        return _json_error('Pick one of the groups.')
    stored = _site_overrides()
    old = (stored.get(section.key) or {}).get(field.key, field.default)
    path = f'values.{section.key}.{field.key}'
    if value == field.default:
        update = {'$unset': {path: ''}}
    else:
        update = {'$set': {path: value}}
    update.setdefault('$set', {}).update(updated_at=_utcnow(), updated_by=session.get('user'))
    db['site_metadata'].update_one({'_id': SITE_CONTENT_ID}, update, upsert=True)
    gone = set(_blob_srcs(old)) - set(_blob_srcs(value))
    _delete_site_blobs(gone)
    if old != value:
        log_activity(_site_log_type(section), f'Changed "{field.label}" on {section.title}',
                     details={'key': key, 'from': _loggable(old), 'to': _loggable(value)})
    return jsonify({'ok': True, 'value': value, 'custom': value != field.default})


@app.route('/admin/api/site/reset', methods=['POST'])
@login_required
def admin_api_site_reset():
    key = str(_json_body().get('key') or '')
    try:
        section, field = _site_field(key)
        _check_site_access(section, field)
    except UserFacingError as e:
        return _json_error(str(e), getattr(e, 'status', 400))
    old = (_site_overrides().get(section.key) or {}).get(field.key, field.default)
    db['site_metadata'].update_one({'_id': SITE_CONTENT_ID},
                                   {'$unset': {f'values.{section.key}.{field.key}': ''},
                                    '$set': {'updated_at': _utcnow(), 'updated_by': session.get('user')}},
                                   upsert=True)
    _delete_site_blobs(set(_blob_srcs(old)))
    if old != field.default:
        log_activity(_site_log_type(section), f'Reset "{field.label}" on {section.title} to the original',
                     details={'key': key, 'from': _loggable(old)})
    return jsonify({'ok': True, 'value': field.default, 'custom': False})


def _delete_site_blobs(urls):
    """Delete uploaded site images that no setting uses any more."""
    if not urls:
        return
    still_used = set(_blob_srcs(_site_overrides()))
    for url in urls:
        if url in still_used or not url.startswith('https://'):
            continue
        try:
            delete_from_vercel_blob(url)
        except Exception:
            logger.exception('Could not delete site image %s', url)


@app.route('/admin/api/site/image', methods=['POST'])
@login_required
def admin_api_site_image():
    """Store an image for a site setting. The browser sends its pixel size, since
    production has no image library to measure it."""
    user = _session_user()
    if not (_is_admin(user) or can_manage_fundraisers(user)):
        return _json_error('You do not have permission to do that.', 403)
    file = request.files.get('file')
    if not file or not file.filename:
        return _json_error('Choose an image to upload.')
    try:
        width = _clean_count(int(request.form.get('width', 0)), site_content.IMAGE_MAX_SIDE, 'Width')
        height = _clean_count(int(request.form.get('height', 0)), site_content.IMAGE_MAX_SIDE, 'Height')
        if not width or not height:
            raise UserFacingError('Could not read the image size. Try a JPEG or PNG.')
        url = checked_upload(file, 'site', allowed=MEMBER_UPLOAD_EXTENSIONS, stem='image')
    except ValueError as e:
        message = str(e) if isinstance(e, UserFacingError) else 'Could not read the image size.'
        return _json_error(message)
    except Exception:
        logger.exception('Site image upload failed')
        return _json_error('Upload failed. Try again in a moment.', 502)
    return jsonify({'ok': True, 'image': {'src': url, 'width': width, 'height': height}})


def site_image_url(image):
    """URL for a stored site image: a built-in photo key or an uploaded file."""
    if not image:
        return ''
    if image.get('key') in image_manifest:
        return url_for('static', filename=image_manifest[image['key']]['src'])
    return site_content.css_url(image.get('src'))


app.jinja_env.globals['site_image_url'] = site_image_url


# --- Shared team editor ---

# field -> (label, max length) for text a team member may edit on their own team.
MEMBER_TEAM_FIELDS = {
    'nickname': ('Nickname', 80),
    'tagline': ('Tagline', 200),
    'notebook_link': ('Notebook link', 500),
    'specs.drive_train': ('Drive train', 120),
    'specs.lift_system': ('Lift system', 120),
    'specs.intake': ('Intake', 120),
    'specs.auton_consistency': ('Auton consistency', 40),
    'layout': ('Page layout', None),
}
# Editors and admins only. Blank values are removed rather than stored.
ADMIN_TEAM_FIELDS = {
    'team_number': ('Team number', 20),
    'season': ('Season', 20),
    'division': ('Division', 40),
    'robotevents_number': ('RobotEvents number', 20),
    'since': ('Competing since', None),
    'worlds_appearances': ('Worlds appearances', None),
    'hidden': ('Hidden from the site menu', None),
    'title': ('Group name', GROUP_TITLE_MAX),
}
# Fields that only mean something for one kind of team.
ROBOT_ONLY_FIELDS = {'nickname', 'notebook_link', 'division', 'robotevents_number', 'worlds_appearances', 'layout',
                     'specs.drive_train', 'specs.lift_system', 'specs.intake', 'specs.auton_consistency'}
GROUP_ONLY_FIELDS = {'title'}
MEMBER_CARD_FIELDS = {'name': ('Name', 100), 'role': ('Role', 100), 'roles': ('Roles', 200),
                      'subteam': ('Sub-team', 60), 'since': ('Member since', None)}


def _session_user():
    """The full user document for this request, looked up once."""
    if 'session_user' not in g:
        user = _current_db_user()
        g.session_user = db['users'].find_one({'_id': user['_id']}) if user else None
    return g.session_user


def _team_access(team, user):
    """(can_admin, own_member_id, is_member) for this user on this team."""
    can_admin = role_at_least(user.get('role', 'member'), 'editor')
    uid = str(user['_id'])
    own = next((m.get('member_id') for m in team.get('members', []) if str(m.get('user_id') or '') == uid), None)
    return can_admin, own, own is not None


def _load_team_for_edit(team_id):
    """(team, user, can_admin, own_member_id) or a JSON error response."""
    user = _session_user()
    if not user:
        session.clear()
        return None, _json_error('Please sign in again.', 401)
    team = _find_team(team_id)
    if not team:
        return None, _json_error('Team not found.', 404)
    can_admin, own, is_member = _team_access(team, user)
    if not (can_admin or is_member):
        return None, _json_error('You can only edit your own team.', 403)
    return (team, user, can_admin, own), None


def _team_edit_log(team, user, what, old=None, new=None):
    details = {'team_number': team.get('team_number'), 'what': what}
    if old is not None or new is not None:
        details.update({'from': _loggable(old), 'to': _loggable(new)})
    log_activity('team_edit', f"{user['username']} updated {what} on {_team_label(team)}",
                 user=user['username'], details=details)


def _own_rosters():
    """Current-season teams and groups the signed-in user is on: their team first, then groups."""
    if 'own_rosters' not in g:
        user = _current_db_user()
        g.own_rosters = sorted(_newest_season_docs({'members.user_id': str(user['_id'])}).values(),
                               key=team_sort_key) if user else []
    return g.own_rosters


def my_team_url():
    """Link to the signed-in user's team editor, the picker if they are on several, or None."""
    own = _own_rosters()
    if len(own) > 1:
        return url_for('my_team')
    return url_for('manage_team', team_id=str(own[0]['_id'])) if own else None


app.jinja_env.globals['my_team_url'] = my_team_url


def _group_choices():
    """(slug, title) for every group, for the fundraising-group picker."""
    groups = sorted(_newest_season_docs({'kind': GROUP_KIND}).values(), key=team_sort_key)
    return [(g['team_number'], g.get('title') or g['team_number']) for g in groups]


def _group_slugs():
    return {slug for slug, _ in _group_choices()}


def fundraising_group():
    """The current-season group whose members run the fundraisers, or None."""
    slug = site().fundraisers.owner_group
    return _newest_season_docs({'kind': GROUP_KIND, 'team_number': slug}).get(slug)


def can_manage_fundraisers(user=None):
    """Editors and admins, plus everyone on the fundraising group's current roster."""
    user = user if user is not None else _session_user()
    if not user:
        return False
    if role_at_least(user.get('role', 'member'), 'editor'):
        return True
    group = fundraising_group()
    uid = str(user['_id'])
    return bool(group) and any(str(m.get('user_id') or '') == uid for m in group.get('members') or [])


app.jinja_env.globals['can_manage_fundraisers'] = can_manage_fundraisers


@app.route('/manage/fundraisers')
@login_required
def manage_fundraisers():
    user = _session_user()
    if not can_manage_fundraisers(user):
        flash('Only the fundraising group can edit fundraisers.', 'error')
        return redirect(url_for('my_team'))
    section = site_content.SECTION_MAP['fundraisers']
    overrides = _site_overrides()
    return render_template('site_editor.html', active_page='my_team', sections=(section,),
                           values=site_content.merged(overrides), overrides=overrides, icons=site_content.ICONS,
                           platforms=site_content.SOCIAL_PLATFORMS, day_names=site_content.DAY_NAMES,
                           gallery_keys=[], club_timezone=CLUB_TIMEZONE, fundraiser_editor=True,
                           group_choices=_group_choices(),
                           can_pick_group=role_at_least(user.get('role', 'member'), 'editor'))


@app.route('/my-team')
@login_required
def my_team():
    user = _session_user()
    own = _own_rosters()
    own_ids = {t['_id'] for t in own}
    editor = bool(user) and role_at_least(user.get('role', 'member'), 'editor')
    if editor or len(own) > 1:
        # Editors can open any team, and someone on a team and in a group has two pages,
        # so give them a list instead of guessing one.
        teams = sorted(_newest_season_docs().values(), key=team_sort_key) if editor else own
        choices = [{'url': url_for('manage_team', team_id=str(t['_id'])), 'group': is_group(t),
                    'number': (t.get('title') if is_group(t) else t.get('team_number')) or 'Team',
                    'season': t.get('season') or '', 'nickname': t.get('nickname') or '',
                    'members': len(t.get('members') or []), 'own': t['_id'] in own_ids}
                   for t in teams]
        choices.sort(key=lambda c: not c['own'])
        return render_template('my_team.html', active_page='my_team', team_choices=choices, editor=editor)
    if own:
        return redirect(url_for('manage_team', team_id=str(own[0]['_id'])))
    return render_template('my_team.html', active_page='my_team')


@app.route('/manage/team/<team_id>')
@login_required
def manage_team(team_id):
    _ensure_member_ids()
    user = _session_user()
    team = _find_team(team_id)
    if not team:
        abort(404)
    can_admin, own, is_member = _team_access(team, user)
    if not (can_admin or is_member):
        flash('You can only edit your own team.', 'error')
        return render_template('my_team.html', active_page='my_team', forbidden=True), 403
    team['_id'] = str(team['_id'])
    team.setdefault('specs', {})
    other_seasons = [{'label': d.get('season') or 'No season', 'url': url_for('manage_team', team_id=str(d['_id']))}
                     for d in db['teams'].find({'team_number': team.get('team_number'),
                                                '_id': {'$ne': ObjectId(team['_id'])}}, {'season': 1})]
    return render_template('team_editor.html', active_page='my_team', team=team,
                           can_admin=can_admin, own_member_id=own, other_seasons=other_seasons,
                           cards=[_card(m) | {'roles': ', '.join(m.get('roles') or []),
                                              'since': m.get('since') or ''}
                                  for m in team.get('members', [])],
                           subteams=SUBTEAMS, divisions=DIVISIONS, team_layouts=site_content.TEAM_LAYOUTS,
                           seasons=season_options(d.get('season') for d in db['teams'].find({}, {'season': 1})),
                           years=year_options(), months=month_suggestions(),
                           role_suggestions=ROLE_SUGGESTIONS, goal_suggestions=GOAL_SUGGESTIONS,
                           spec_suggestions=SPEC_SUGGESTIONS)


def _clean_team_field(field, value, label, limit):
    if field == 'notebook_link':
        return _clean_url(value, label)
    if field in ('since', 'worlds_appearances'):
        return _clean_year(value, label)
    if field == 'hidden':
        return bool(value) or None
    if field == 'layout':
        # Blank means "use the site default", so it is removed rather than stored.
        if not value:
            return None
        if value not in site_content.TEAM_LAYOUTS:
            raise UserFacingError('Pick one of the listed layouts.')
        return value
    text = _clean_text(value, limit, label, required=(field == 'team_number'))
    if field in ('team_number', 'robotevents_number'):
        text = text.upper()
        if text and not TEAM_NUMBER_RE.fullmatch(text):
            raise UserFacingError(f'{label} can only use letters, digits and dashes, like 77628A.')
    if field == 'season' and text and not SEASON_RE.fullmatch(text):
        raise UserFacingError('Pick a season like 2026-27.')
    if field == 'division' and text and text not in DIVISIONS:
        raise UserFacingError('Pick a listed division.')
    return text


def _clean_group_field(field, value, label, limit):
    text = collapse_whitespace(_clean_text(value, limit, label, required=True))
    if field == 'title':
        return text
    slug = text.lower()
    if len(slug) > GROUP_SLUG_MAX or not GROUP_SLUG_RE.fullmatch(slug):
        raise UserFacingError('Use lowercase letters, digits and single dashes, like media or fundraising.')
    return slug


def _move_team_awards(old, new):
    """Carry award counters from one team number to another (after a rename).

    Counters stay put when another season still uses the old number. When the
    new number already has counters, counts for the same category are added
    together rather than leaving duplicate rows.
    """
    if not old or old == new or db['teams'].find_one({'team_number': old}, {'_id': 1}):
        seed_team_awards(new)
        return
    link_team_award_categories()
    existing = {a.get('category_id') or a.get('title'): a for a in db['awards'].find({'team_number': new})}
    for row in db['awards'].find({'team_number': old}):
        key = row.get('category_id') or row.get('title')
        if key in existing:
            db['awards'].update_one({'_id': existing[key]['_id']}, {'$inc': {'count': int(row.get('count') or 0)}})
            db['awards'].delete_one({'_id': row['_id']})
        else:
            db['awards'].update_one({'_id': row['_id']}, {'$set': {'team_number': new}})
    seed_team_awards(new)


@app.route('/api/team/<team_id>/field', methods=['POST'])
@login_required
def api_team_field(team_id):
    loaded, error = _load_team_for_edit(team_id)
    if error:
        return error
    team, user, can_admin, _ = loaded
    body = _json_body()
    field = body.get('field')

    if field in MEMBER_TEAM_FIELDS:
        label, limit = MEMBER_TEAM_FIELDS[field]
    elif field in ADMIN_TEAM_FIELDS:
        if not can_admin:
            return _json_error('Only editors and admins can change that.', 403)
        label, limit = ADMIN_TEAM_FIELDS[field]
    else:
        return _json_error('That field cannot be edited.' if can_admin else 'You cannot change that.',
                           400 if can_admin else 403)
    if field in (ROBOT_ONLY_FIELDS if is_group(team) else GROUP_ONLY_FIELDS):
        return _json_error(f"{'Groups' if is_group(team) else 'Robot teams'} don't have that field.")

    try:
        if is_group(team) and field in ('team_number', 'title'):
            value = (_clean_group_field(field, body.get('value'), 'Page address', GROUP_SLUG_MAX)
                     if field == 'team_number' else _clean_group_field(field, body.get('value'), label, limit))
        else:
            value = _clean_team_field(field, body.get('value'), label, limit)
    except UserFacingError as e:
        return _json_error(str(e))

    old = team.get('team_number') if field == 'team_number' else (
        team.get('specs', {}).get(field.split('.', 1)[1]) if field.startswith('specs.') else team.get(field))
    if field in ('team_number', 'season'):
        number = value if field == 'team_number' else team.get('team_number')
        season = value if field == 'season' else team.get('season')
        clash = db['teams'].find_one({'team_number': number, 'season': season or None,
                                      '_id': {'$ne': team['_id']}}, {'_id': 1})
        if clash:
            return _json_error(f'Another profile already uses {number} for {season or "no season"}.', 409)

    try:
        if value is None or (field in ADMIN_TEAM_FIELDS and value == ''):
            db['teams'].update_one({'_id': team['_id']}, {'$unset': {field: ''}})
        else:
            db['teams'].update_one({'_id': team['_id']}, {'$set': {field: value}})
    except DuplicateKeyError:
        return _json_error('Another profile already uses that team number and season.', 409)

    if field == 'team_number' and value != old and not is_group(team):
        _move_team_awards(old, value)
    if field == 'team_number' and value != old and is_group(team) and site().fundraisers.owner_group == old:
        db['site_metadata'].update_one({'_id': SITE_CONTENT_ID},
                                       {'$set': {'values.fundraisers.owner_group': value}}, upsert=True)
    if field in ('team_number', 'hidden'):
        refresh_auto_stats()
    _team_edit_log(team, user, label.lower(), old, value)
    return jsonify({'ok': True, 'value': value})


@app.route('/api/team/<team_id>/list/<kind>', methods=['POST'])
@login_required
def api_team_list(team_id, kind):
    if kind not in ('goals', 'journey'):
        return _json_error('Unknown list.', 404)
    loaded, error = _load_team_for_edit(team_id)
    if error:
        return error
    team, user, can_admin, _ = loaded
    if kind == 'journey' and not can_admin:
        return _json_error('Only editors and admins can change the journey.', 403)
    items = _json_body().get('items')
    if not isinstance(items, list) or len(items) > LIST_MAX_ITEMS:
        return _json_error(f'Send up to {LIST_MAX_ITEMS} rows.')
    try:
        if kind == 'goals':
            cleaned = [{'name': _clean_text(i.get('name'), 120, 'Goal name'),
                        'progress': _clamp_percent(i.get('progress'))}
                       for i in items if isinstance(i, dict)]
            cleaned = [g for g in cleaned if g['name']]
        else:
            cleaned = [{'date': _clean_text(i.get('date'), 40, 'Date'),
                        'title': _clean_text(i.get('title'), 120, 'Title'),
                        'description': _clean_text(i.get('description'), 1000, 'Description')}
                       for i in items if isinstance(i, dict)]
            cleaned = [j for j in cleaned if j['title']]
    except UserFacingError as e:
        return _json_error(str(e))
    db['teams'].update_one({'_id': team['_id']}, {'$set': {kind: cleaned}})
    _team_edit_log(team, user, kind)
    return jsonify({'ok': True, 'items': cleaned})


@app.route('/api/team/<team_id>/member/<member_id>', methods=['POST', 'DELETE'])
@login_required
def api_team_member(team_id, member_id):
    loaded, error = _load_team_for_edit(team_id)
    if error:
        return error
    team, user, can_admin, own = loaded
    member = next((m for m in team.get('members', []) if m.get('member_id') == member_id), None)
    if not member:
        return _json_error('That member is no longer on this team.', 404)

    if request.method == 'DELETE':
        if not can_admin:
            return _json_error('Only editors and admins can remove members.', 403)
        db['teams'].update_one({'_id': team['_id']}, {'$pull': {'members': {'member_id': member_id}}})
        _park_roster_card(member)
        if not member.get('user_id'):
            _delete_blobs([u for u in [member.get('photo')] if isinstance(u, str) and u.startswith('http')],
                          'a removed member')
        refresh_auto_stats()
        _team_edit_log(team, user, f"roster (removed {member.get('name')})")
        return jsonify({'ok': True})

    if not can_admin and member_id != own:
        return _json_error('You can only edit your own card.', 403)
    body = _json_body()
    field = body.get('field')
    if field not in MEMBER_CARD_FIELDS:
        return _json_error('That field cannot be edited.')
    label, limit = MEMBER_CARD_FIELDS[field]
    try:
        if field == 'since':
            value = _clean_year(body.get('value'), label)
        elif field == 'roles':
            text = _clean_text(body.get('value'), limit, label)
            value = [r.strip() for r in text.split(',') if r.strip()]
        else:
            value = _clean_text(body.get('value'), limit, label, required=(field == 'name'))
            if field == 'subteam' and value and value not in SUBTEAMS:
                raise UserFacingError('Pick a listed sub-team.')
    except UserFacingError as e:
        return _json_error(str(e))
    db['teams'].update_one({'_id': team['_id'], 'members.member_id': member_id},
                           {'$set': {f'members.$.{field}': value}})
    _team_edit_log(team, user, f"{member.get('name')}'s {label.lower()}", member.get(field), value)
    return jsonify({'ok': True, 'value': value})


@app.route('/api/team/<team_id>/member', methods=['POST'])
@login_required
def api_team_add_member(team_id):
    loaded, error = _load_team_for_edit(team_id)
    if error:
        return error
    team, user, can_admin, _ = loaded
    if not can_admin:
        return _json_error('Only editors and admins can add members.', 403)
    try:
        name = _clean_text(_json_body().get('name'), 100, 'Name', required=True)
    except UserFacingError as e:
        return _json_error(str(e))
    member = {'member_id': _new_member_id(), 'name': name, 'role': 'Member', 'user_id': '', 'photo': ''}
    db['teams'].update_one({'_id': team['_id']}, {'$push': {'members': member}})
    refresh_auto_stats()
    _team_edit_log(team, user, f'roster (added {name})')
    return jsonify({'ok': True, 'member': _card(member)})


TEAM_IMAGE_KINDS = ('hero_image', 'stl_file', 'member_photo')


@app.route('/api/team/<team_id>/image', methods=['POST', 'DELETE'])
@login_required
def api_team_image(team_id):
    loaded, error = _load_team_for_edit(team_id)
    if error:
        return error
    team, user, can_admin, own = loaded

    if request.method == 'DELETE':
        body = _json_body()
        kind, member_id = body.get('kind'), str(body.get('member_id') or '')
        if kind not in TEAM_IMAGE_KINDS:
            return _json_error('Say which image to remove.')
        if kind == 'stl_file' and not can_admin:
            return _json_error('Only editors and admins can remove the CAD model.', 403)
        if kind == 'member_photo':
            member = next((m for m in team.get('members', []) if m.get('member_id') == member_id), None)
            if not member:
                return _json_error('That member is no longer on this team.', 404)
            if not can_admin and member_id != own:
                return _json_error('You can only change your own photo.', 403)
            old = member.get('photo')
            db['teams'].update_one({'_id': team['_id'], 'members.member_id': member_id},
                                   {'$set': {'members.$.photo': ''}})
        else:
            key = 'hero_image' if kind == 'hero_image' else 'stl_path'
            old = team.get(key)
            db['teams'].update_one({'_id': team['_id']}, {'$unset': {key: ''}})
        if isinstance(old, str) and old.startswith('http'):
            _delete_blobs([old], 'a removed image')
        _team_edit_log(team, user, {'hero_image': 'banner photo', 'stl_file': 'CAD model',
                                    'member_photo': 'a photo'}[kind] + ' (removed)')
        return jsonify({'ok': True})

    files = request.files
    try:
        if files.get('hero_image') and files['hero_image'].filename:
            url = checked_upload(files['hero_image'], 'teams', team['team_number'],
                                 allowed=MEMBER_UPLOAD_EXTENSIONS, stem='hero')
            old, update, what = team.get('hero_image'), {'$set': {'hero_image': url}}, 'hero image'
            query = {'_id': team['_id']}
        elif files.get('stl_file') and files['stl_file'].filename:
            if not can_admin:
                return _json_error('Only editors and admins can upload the CAD model.', 403)
            url = checked_upload(files['stl_file'], 'teams', team['team_number'], allowed={'stl'}, stem='model')
            old, update, what = team.get('stl_path'), {'$set': {'stl_path': url}}, 'CAD model'
            query = {'_id': team['_id']}
        elif files.get('member_photo') and files['member_photo'].filename:
            member_id = request.form.get('member_id', '')
            member = next((m for m in team.get('members', []) if m.get('member_id') == member_id), None)
            if not member:
                return _json_error('That member is no longer on this team.', 404)
            if not can_admin and member_id != own:
                return _json_error('You can only change your own photo.', 403)
            url = checked_upload(files['member_photo'], 'teams', team['team_number'], 'members',
                                 allowed=MEMBER_UPLOAD_EXTENSIONS, stem=member.get('name') or 'member')
            old, update, what = member.get('photo'), {'$set': {'members.$.photo': url}}, 'a photo'
            query = {'_id': team['_id'], 'members.member_id': member_id}
        else:
            return _json_error('Choose a file to upload.')
    except UserFacingError as e:
        return _json_error(str(e))
    except Exception:
        logger.exception('Team image upload failed')
        return _json_error('Upload failed. Try again in a moment.', 502)

    db['teams'].update_one(query, update)
    if isinstance(old, str) and old.startswith('http'):
        _delete_blobs([old], 'a replaced image')
    _team_edit_log(team, user, what)
    return jsonify({'ok': True, 'url': get_image_url(url)})


MATCHES_CACHE_SECONDS = 300
_matches_cache = {'expires_at': 0.0, 'payload': None}
_matches_cache_lock = threading.Lock()


@app.route('/api/matches')
def api_matches():
    """Proxy RobotEvents match data so the API key never reaches the browser.

    Results are cached for a few minutes: every visitor hitting this endpoint
    otherwise costs one upstream call per team plus a team lookup.
    """
    with _matches_cache_lock:
        if _matches_cache['payload'] is not None and time.time() < _matches_cache['expires_at']:
            return jsonify(_matches_cache['payload'])

    payload = _fetch_matches()
    with _matches_cache_lock:
        _matches_cache['payload'] = payload
        _matches_cache['expires_at'] = time.time() + MATCHES_CACHE_SECONDS
    return jsonify(payload)


def _fetch_matches():
    api_key = robotevents.get_token()
    if not api_key:
        return {'matches': []}

    headers = {'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}

    def fetch(endpoint):
        try:
            resp = requests.get(f'{robotevents.BASE_URL}/{endpoint}', headers=headers, timeout=8)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning('RobotEvents fetch failed for %s', endpoint, exc_info=True)
            return None

    numbers = sorted({t.get('robotevents_number') or t['team_number'] for t in listed_teams() if not is_group(t)})
    if not numbers:
        return {'matches': []}
    number_qs = '&'.join(f'number[]={urllib.parse.quote(n)}' for n in numbers)
    teams_data = fetch(f'teams?{number_qs}')
    if not teams_data or not teams_data.get('data'):
        return {'matches': []}

    all_matches = []
    for team in teams_data['data']:
        matches_data = fetch(f"teams/{team['id']}/matches?per_page=20")
        if matches_data and matches_data.get('data'):
            all_matches.extend(matches_data['data'])

    seen = {}
    for m in all_matches:
        seen[m['id']] = m
    unique_matches = sorted(seen.values(), key=lambda m: m.get('scheduled') or '', reverse=True)

    displayed = []
    if unique_matches:
        latest_event_id = unique_matches[0]['event']['id']
        same_event = [m for m in unique_matches if m['event']['id'] == latest_event_id]
        displayed = sorted(same_event, key=lambda m: m.get('matchnum', 0), reverse=True)[:5]

    results = []
    for match in displayed:
        red = next((a for a in match['alliances'] if a['color'] == 'red'), None)
        blue = next((a for a in match['alliances'] if a['color'] == 'blue'), None)
        if not red or not blue:
            continue
        results.append({
            'name': match.get('name', ''),
            'red_teams': ', '.join(t['team']['name'] for t in red['teams']),
            'blue_teams': ', '.join(t['team']['name'] for t in blue['teams']),
            'score': f"{red['score']} - {blue['score']}" if red['score'] is not None else None,
        })

    return {'matches': results}

@app.route('/api/contact', methods=['POST'])
def api_contact():
    payload = request.get_json(silent=True) or {}

    # Honeypot: bots fill the hidden field. Look successful, store nothing.
    if (payload.get('website') or '').strip():
        return jsonify({'ok': True})

    ip = _client_ip()
    locked = _contact_lockout_minutes(ip)
    if locked:
        minute_word = 'minute' if locked == 1 else 'minutes'
        return jsonify({'error': f'Too many messages. Try again in {locked} {minute_word}.'}), 429

    cleaned, error = _validate_contact(payload)
    if error:
        return jsonify({'error': error}), 400

    _record_contact_attempt(ip)
    db['contact_messages'].insert_one({
        **cleaned,
        'status': 'new',
        'created_at': _utcnow(),
        'ip': ip,
        'user_agent': request.headers.get('User-Agent', '')[:200],
    })
    return jsonify({'ok': True})

CHAT_MESSAGE_MAX = 1000
CHAT_RATE_LIMIT = 20
CHAT_RATE_WINDOW = datetime.timedelta(minutes=10)
CHAT_TIMEOUT_SECONDS = 20
CHAT_SYSTEM_PROMPT = (
    "You are Steven, the official AI assistant for the Mepham Robotics Club "
    "(VEX V5 Team 77628). Be helpful, enthusiastic about robotics, and concise."
)


def chat_system_prompt():
    """The assistant's instructions plus the facts admins keep current in Site settings."""
    content = site()
    meeting = content.meeting
    facts = [f"The club meets {site_content.fmt_schedule(meeting)} in {meeting['room']} at {meeting['school']}.",
             f"The club email is {content.general.contact_email}."]
    if content.assistant.knowledge:
        facts.append(content.assistant.knowledge)
    return CHAT_SYSTEM_PROMPT + ' Facts you can rely on: ' + ' '.join(facts)


NEWSLETTER_RATE_LIMIT = 5
NEWSLETTER_RATE_WINDOW = datetime.timedelta(hours=1)
_newsletter_index_ready = False


def _ensure_newsletter_index():
    global _newsletter_index_ready
    if _newsletter_index_ready:
        return
    db['newsletter_subscribers'].create_index('email', unique=True)
    db['newsletter_subscribers'].create_index([('created_at', -1)])
    _newsletter_index_ready = True


@app.route('/api/newsletter', methods=['POST'])
def api_newsletter():
    """Store a footer newsletter signup.

    Re-subscribing is idempotent and reports success either way, so the form
    cannot be used to probe whether an address is already on the list.
    """
    payload = request.get_json(silent=True) or {}

    # Honeypot, same as the contact form.
    if (payload.get('website') or '').strip():
        return jsonify({'ok': True})

    email = payload.get('email')
    email = email.strip().lower() if isinstance(email, str) else ''
    if not email or len(email) > CONTACT_EMAIL_MAX or not _looks_like_email(email):
        return jsonify({'error': 'Please enter a valid email address.'}), 400

    retry_after = rate_limit('newsletter', _client_ip(),
                             NEWSLETTER_RATE_LIMIT, NEWSLETTER_RATE_WINDOW)
    if retry_after:
        return jsonify({'error': 'Too many signups from this network. Try again later.'}), 429

    _ensure_newsletter_index()
    db['newsletter_subscribers'].update_one(
        {'email': email},
        {'$setOnInsert': {'email': email,
                          'created_at': _utcnow(),
                          'unsubscribe_token': secrets.token_urlsafe(24)}},
        upsert=True)
    return jsonify({'ok': True, 'message': "You're on the list."})


@app.route('/unsubscribe/<token>')
def unsubscribe(token):
    removed = db['newsletter_subscribers'].delete_one({'unsubscribe_token': token})
    return render_template('unsubscribe.html', active_page='unsubscribe',
                           removed=removed.deleted_count > 0)


# Spreadsheets treat a cell starting with one of these as a formula, so an
# address like `=HYPERLINK("http://evil")@example.com` would execute when an
# admin opens the export. Prefixing a quote keeps the value as text.
CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def csv_safe(value):
    text = '' if value is None else str(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


@app.route('/admin/subscribers.csv')
@role_required('admin')
def admin_subscribers_csv():
    """Download the newsletter list so it can be pasted into a mail tool."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['email', 'subscribed_at', 'unsubscribe_url'])
    rows = 0
    for sub in db['newsletter_subscribers'].find().sort('created_at', -1):
        created = sub.get('created_at')
        token = sub.get('unsubscribe_token')
        writer.writerow([csv_safe(sub.get('email', '')),
                         csv_safe(created.strftime('%Y-%m-%d %H:%M') if created else ''),
                         csv_safe(_public_url('unsubscribe', token=token) if token else '')])
        rows += 1
    log_activity('subscribers_export', f'Exported {rows} newsletter address{"es" if rows != 1 else ""}',
                 details={'count': rows})
    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename="newsletter-subscribers.csv"'})


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Proxy the chatbot upstream. Public, so it is capped and rate limited:
    without both, anyone could drain the API key with a loop."""
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip() if isinstance(data.get('message'), str) else ''
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    if len(user_message) > CHAT_MESSAGE_MAX:
        return jsonify({'error': f'Message must be {CHAT_MESSAGE_MAX} characters or fewer.'}), 400

    retry_after = rate_limit('chat', _client_ip(), CHAT_RATE_LIMIT, CHAT_RATE_WINDOW)
    if retry_after:
        minutes = max(1, math.ceil(retry_after / 60))
        return jsonify({
            'error': f'Steven needs a breather. Try again in {minutes} '
                     f'{"minute" if minutes == 1 else "minutes"}.'
        }), 429

    if not os.getenv('CHATBOT_API_KEY'):
        return jsonify({'error': 'The assistant is offline right now.'}), 503

    try:
        response = requests.post(
            os.getenv('CHATBOT_API_URL', "https://ai.hackclub.com/proxy/v1/chat/completions"),
            headers={"Authorization": f"Bearer {os.getenv('CHATBOT_API_KEY')}",
                     "Content-Type": "application/json"},
            json={"model": os.getenv('CHATBOT_MODEL', "gpt-4o-mini"),
                  "messages": [{"role": "system", "content": chat_system_prompt()},
                               {"role": "user", "content": user_message}]},
            timeout=CHAT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return jsonify({'reply': response.json()['choices'][0]['message']['content']})
    except requests.Timeout:
        logger.warning('api_chat: upstream timed out')
        return jsonify({'error': 'Steven took too long to answer. Try again.'}), 504
    except Exception:
        logger.exception('api_chat: upstream request failed')
        return jsonify({'error': 'Failed to process request'}), 502

@app.context_processor
def inject_user():
    return dict(current_user=session.get('user'))

STATIC_PUBLIC_PAGES = [
    ('index', 1.0, 'daily'),
    ('about', 0.8, 'monthly'),
    ('achievements', 0.8, 'weekly'),
    ('donate', 0.7, 'monthly'),
    ('contact', 0.6, 'monthly'),
    ('safety_quiz', 0.5, 'yearly'),
    ('privacy', 0.3, 'yearly'),
    ('credits_page', 0.3, 'yearly'),
]

GOOGLE_SITE_VERIFICATION = 'googleb1225e3231cfbee0.html'


@app.route(f'/{GOOGLE_SITE_VERIFICATION}')
def google_site_verification():
    # Google Search Console fetches this file from the site root to prove ownership.
    return send_from_directory(_root, GOOGLE_SITE_VERIFICATION, mimetype='text/html')


@app.route('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
        'Disallow: /manage/',
        'Disallow: /login',
        'Disallow: /logout',
        'Disallow: /api/',
        'Disallow: /unsubscribe/',
        f"Sitemap: {url_for('sitemap_xml', _external=True)}",
    ]
    return Response('\n'.join(lines), mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    urls = []
    for endpoint, priority, changefreq in STATIC_PUBLIC_PAGES:
        urls.append({
            'loc': url_for(endpoint, _external=True),
            'priority': priority,
            'changefreq': changefreq,
        })
    for team in listed_teams():
        urls.append({
            'loc': url_for('team_page', team_number=team['team_number'], _external=True),
            'priority': 0.6,
            'changefreq': 'weekly',
        })

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml_parts.append(
            f"<url><loc>{u['loc']}</loc><changefreq>{u['changefreq']}</changefreq>"
            f"<priority>{u['priority']}</priority></url>"
        )
    xml_parts.append('</urlset>')
    return Response('\n'.join(xml_parts), mimetype='application/xml')

SERVER_ERROR_TEXT = 'Something went wrong on the server. Try again in a moment.'


# JSON callers (admin.js, team-editor.js) show the 'error' text; an HTML error
# page there used to surface only as "Save failed (500)."
@app.errorhandler(404)
def page_not_found(e):
    if _wants_json():
        return jsonify({'error': 'Not found.'}), 404
    return render_template('404.html'), 404

@app.errorhandler(405)
def method_not_allowed(e):
    if _wants_json():
        return jsonify({'error': 'That action is not supported here.'}), 405
    return e

@app.errorhandler(500)
def internal_server_error(e):
    logger.exception("Internal server error: %s", e)
    if _wants_json():
        return jsonify({'error': SERVER_ERROR_TEXT}), 500
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # Let Flask's own HTTP errors (404, 400, 413, ...) keep their status and
    # their dedicated handlers instead of collapsing everything into a 500.
    if isinstance(e, HTTPException):
        return e
    logger.exception("Unhandled exception: %s", e)
    if _wants_json():
        return jsonify({'error': SERVER_ERROR_TEXT}), 500
    return render_template('500.html'), 500

@app.after_request
def add_static_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

if __name__ == '__main__':
    # The Werkzeug debugger executes code from the browser; only opt in.
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')