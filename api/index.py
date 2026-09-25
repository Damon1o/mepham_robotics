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
import logging
from functools import wraps
from bson import ObjectId
import bcrypt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, abort
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import requests
import mimetypes

try:  # package import on Vercel, flat import when run from the api/ directory
    from api import robotevents
except ImportError:  # pragma: no cover
    import robotevents

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

@app.template_filter('collapse_ws')
def collapse_whitespace(value):
    """Collapse newlines/indentation from wrapped Jinja block text so it's safe inside a single HTML attribute (og:*, twitter:*, meta description)."""
    return ' '.join(str(value).split())

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

LEADERSHIP_KEYWORDS = ('captain', 'lead', 'president', 'mentor', 'director')


@app.template_filter('member_roles')
def member_roles(member):
    """Every role a member holds. Falls back to the single legacy 'role' string."""
    roles = member.get('roles') or []
    roles = [r.strip() for r in roles if str(r).strip()]
    if not roles and member.get('role'):
        roles = [member['role'].strip()]
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

def seed_team_awards(team_number):
    """Give a newly created team its own copy of every award category, starting at 0."""
    if db['awards'].find_one({'team_number': team_number}):
        return  # already seeded, don't duplicate
    global_awards = list(db['awards'].find({'team_number': {'$exists': False}}))
    if not global_awards:
        return
    new_docs = [
        {
            'team_number': team_number,
            'title': a.get('title'),
            'icon': a.get('icon'),
            'layout': a.get('layout'),
            'border': a.get('border'),
            'shimmer': a.get('shimmer'),
            'count': 0
        }
        for a in global_awards
    ]
    db['awards'].insert_many(new_docs)

def get_activity_icon(activity_type):
    """Get appropriate icon for activity type"""
    icons = {
        'stats_update': '📊',
        'competition_add': '📅',
        'competition_update': '✏️',
        'competition_delete': '🗑️',
        'team_add': '🤖',
        'team_update': '⚙️',
        'team_delete': '🗑️',
        'awards_update': '🏆',
        'user_add': '👤',
        'user_update': '👥',
        'user_delete': '🗑️',
        'sponsor_add': '🤝',
        'sponsor_update': '💼',
        'sponsor_delete': '🗑️',
        'password_reset': '🔑',
        'reset_link_generate': '🔗',
        'message_read': '📬',
        'message_archive': '🗄️',
        'message_delete': '🗑️',
    }
    return icons.get(activity_type, '📝')

def get_activity_title(activity_type):
    """Get human-readable title for activity type"""
    titles = {
        'stats_update': 'Statistics updated',
        'competition_add': 'Event scheduled',
        'competition_update': 'Event updated',
        'competition_delete': 'Event deleted',
        'team_add': 'Team added',
        'team_update': 'Team updated',
        'team_delete': 'Team deleted',
        'awards_update': 'Awards updated',
        'user_add': 'User created',
        'user_update': 'User updated',
        'user_delete': 'User deleted',
        'sponsor_add': 'Sponsor added',
        'sponsor_update': 'Sponsor updated',
        'sponsor_delete': 'Sponsor deleted',
        'password_reset': 'Password reset',
        'reset_link_generate': 'Reset link generated',
        'message_read': 'Message read',
        'message_archive': 'Message archived',
        'message_delete': 'Message deleted',
    }
    return titles.get(activity_type, 'Activity')

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


app.jinja_env.globals['image_manifest'] = _load_image_manifest()

DEFAULT_IMAGE = 'assets/other/base.png'
DEFAULT_MEMBER_PHOTO = 'static/' + DEFAULT_IMAGE


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
    sponsors = []
    for sponsor in db['sponsors'].find():
        sponsor['_id'] = str(sponsor['_id'])
        sponsor['logo_path'] = sponsor.get('logo')
        sponsors.append(sponsor)
    return sponsors


@app.context_processor
def inject_global_data():
    # This runs for every render_template call, including error pages. The
    # nav query only happens if the template iterates nav_teams; awards and
    # sponsors are loaded by the views that show them.
    return dict(
        nav_teams=LazyList(lambda: list(
            db['teams'].find({}, {'team_number': 1}).sort('team_number', 1))),
        get_activity_icon=get_activity_icon,
        get_activity_title=get_activity_title,
        get_image_url=get_image_url,
    )

USER_ROLES = ('member', 'editor', 'admin')

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
    user = db['users'].find_one({'username': session['user']}, {'role': 1, 'session_version': 1})
    if not user or user.get('session_version', 0) != session.get('session_version', 0):
        return None
    return user

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if _current_db_user() is None:
            session.clear()
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
                return _login_redirect()
            db_role = user.get('role', 'member')
            if session.get('role') != db_role:
                session['role'] = db_role
            if db_role != role and db_role != 'admin':
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

def _build_reset_link(token):
    """Build the absolute reset-password link for a freshly issued token."""
    public_base = os.getenv('PUBLIC_BASE_URL', '')
    if public_base:
        return public_base.rstrip('/') + url_for('reset_password', token=token)
    return url_for('reset_password', token=token, _external=True)

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
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Your session expired. Refresh the page and try again.'}), 400
        abort(400)
    return None


@app.errorhandler(400)
def bad_request(e):
    return render_template('400.html'), 400


@app.errorhandler(413)
def payload_too_large(e):
    megabytes = MAX_UPLOAD_BYTES // (1024 * 1024)
    if request.path.startswith('/api/'):
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
CLUB_TIMEZONE = os.getenv('CLUB_TIMEZONE', 'America/New_York')


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
    stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {
        'teams_count': 0, 'members_count': 0, 'awards_count': 0, 'hours_built': 0
    }
    upcoming_events = list(db['competitions'].find(
        {'date': {'$gte': club_now()}}).sort('date', 1).limit(UPCOMING_EVENTS_LIMIT))
    for event in upcoming_events:
        event['month'] = event['date'].strftime('%b').upper()
        event['day'] = event['date'].strftime('%d')
        event['time'] = event['date'].strftime('%I:%M %p')
    competition = upcoming_events[0] if upcoming_events else None
    return render_template('index.html', active_page='index', stats=stats,
                           competition=competition, upcoming_events=upcoming_events)

@app.route('/about')
def about():
    return render_template('about.html', active_page='about')

@app.route('/achievements')
def achievements():
    global_awards = list(db['awards'].find({'team_number': {'$exists': False}}).sort('_id', 1))
    return render_template('achievements.html', active_page='achievements',
                           global_awards=global_awards)

@app.route('/contact')
def contact():
    return render_template('contact.html', active_page='contact')

CONTACT_EMAIL = os.getenv('CONTACT_EMAIL', 'mephamrobotics@gmail.com')


@app.route('/donate')
def donate():
    # The embed only renders once a campaign id is configured; until then the
    # template shows an email fallback instead of a broken Givebutter frame.
    return render_template('donate.html', active_page='donate',
                           givebutter_campaign_id=os.getenv('GIVEBUTTER_CAMPAIGN_ID', ''),
                           contact_email=CONTACT_EMAIL, sponsors=load_sponsors())

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

    team_awards = list(db['awards'].find({'team_number': team_number}).sort('_id', 1))
    return render_template('team.html', team=team, team_awards=team_awards,
                           event_photos=event_photos, robot_photos=robot_photos,
                           seasons=seasons, active_season=team.get('season'),
                           live_enabled=bool(os.environ.get('ROBOTEVENTS_TOKEN')),
                           active_page=team_number)

@app.route('/api/team/<team_number>/live')
def team_live_data(team_number):
    """Live RobotEvents data for the team page's skills, scoreboard and results panels.

    204 when there is no token, no matching RobotEvents team, or nothing to show.
    The page renders without these panels in that case, so this never fails hard.
    """
    team = db['teams'].find_one({'team_number': team_number})
    if not team:
        return Response(status=204)

    lookup_number = team.get('robotevents_number') or team_number
    try:
        summary = robotevents.team_summary(db, lookup_number)
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

def monthly_stat_changes(since):
    """Net change this month in each dashboard stat, from the activity log.

    Grouped in the database: the old version loaded every activity since the
    first of the month into memory, and the log is never pruned.
    """
    def total(field):
        return {'$sum': {'$ifNull': [f'$details.{field}', 0]}}

    rows = db['activities'].aggregate([
        {'$match': {'timestamp': {'$gte': since}}},
        {'$group': {
            '_id': '$type',
            'count': {'$sum': 1},
            'teams_change': total('teams_change'),
            'members_change': total('members_change'),
            'awards_change': total('awards_change'),
            'members_count': total('members_count'),
            'count_change': {'$sum': {'$ifNull': [
                '$details.count_change', {'$ifNull': ['$details.total_change', 0]}]}},
        }},
    ])
    by_type = {row['_id']: row for row in rows}

    def get(kind, field):
        return by_type.get(kind, {}).get(field, 0)

    return {
        'teams_change': (get('stats_update', 'teams_change')
                         + get('team_add', 'count') - get('team_delete', 'count')),
        'members_change': (get('stats_update', 'members_change')
                           + get('team_add', 'members_count')
                           - get('team_delete', 'members_count')
                           + get('team_update', 'members_change')),
        'awards_change': (get('stats_update', 'awards_change')
                          + get('awards_update', 'count_change')),
        'events_change': get('competition_add', 'count') - get('competition_delete', 'count'),
    }


@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {}
    if '_id' in stats and not isinstance(stats['_id'], str):
        stats['_id'] = str(stats['_id'])
    all_awards = [dict(a, _id=str(a['_id'])) for a in db['awards'].find()]
    global_awards = [a for a in all_awards if 'team_number' not in a]
    team_awards_list = [a for a in all_awards if 'team_number' in a]
    
    competitions_raw = list(db['competitions'].find().sort('date', 1))
    competitions = []
    for c in competitions_raw:
        c['_id'] = str(c['_id'])
        if 'date' in c:
            c['date_str'] = c['date'].strftime('%Y-%m-%dT%H:%M')
            c['display_date'] = c['date'].strftime('%b %d, %Y @ %I:%M %p')
        competitions.append(c)
    users = [dict(u, _id=str(u['_id']), role=u.get('role', 'member'), email=u.get('email', ''))
             for u in db['users'].find({}, {'username': 1, 'email': 1, 'role': 1}).sort('username', 1)]
    teams = []
    for t in db['teams'].find().sort('team_number', 1):
        t['_id'] = str(t['_id'])
        if 'members' in t:
            for m in t['members']:
                if 'user_id' in m and m['user_id']:
                    m['user_id'] = str(m['user_id'])
                if 'photo' in m:
                    m['photo'] = m['photo'].replace('\\', '/')
        if 'hero_image' in t and t['hero_image']:
            t['hero_image'] = t['hero_image'].replace('\\', '/')
        if 'stl_path' in t and t['stl_path']:
            t['stl_path'] = t['stl_path'].replace('\\', '/')
        teams.append(t)
    sponsors = load_sponsors()

    # Get recent activities
    activities = []
    monthly_changes = {
        'teams_change': 0,
        'members_change': 0,
        'awards_change': 0,
        'events_change': 0
    }

    for a in db['activities'].find().sort('timestamp', -1).limit(10):
        a['_id'] = str(a['_id'])
        if 'timestamp' in a:
            a['display_time'] = get_time_ago(a['timestamp'])
        activities.append(a)

    first_of_month = _utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_changes.update(monthly_stat_changes(first_of_month))

    reset_link = session.pop('_generated_reset_link', None)
    reset_link_user = session.pop('_generated_reset_link_user', None)

    messages = []
    for m in db['contact_messages'].find().sort('created_at', -1).limit(200):
        m['_id'] = str(m['_id'])
        created = m.get('created_at')
        m['display_date'] = created.strftime('%b %d, %Y @ %I:%M %p') if created else ''
        m['status'] = m.get('status', 'new')
        messages.append(m)
    unread_messages = sum(1 for m in messages if m['status'] == 'new')
    subscriber_count = db['newsletter_subscribers'].count_documents({})

    return render_template('admin.html', stats=stats, competitions=competitions,
                           awards=global_awards, team_awards=team_awards_list,
                           teams=teams, users=users, sponsors=sponsors,
                           activities=activities, monthly_changes=monthly_changes,
                           reset_link=reset_link, reset_link_user=reset_link_user,
                           messages=messages, unread_messages=unread_messages,
                           subscriber_count=subscriber_count)

@app.route('/admin/update-stats', methods=['POST'])
@role_required('admin')
def admin_update_stats():
    try:
        data = {
            'teams_count': int(request.form.get('teams_count', 0)),
            'members_count': int(request.form.get('members_count', 0)),
            'awards_count': int(request.form.get('awards_count', 0)),
            'hours_built': int(request.form.get('hours_built', 0))
        }
        # Read the old numbers *before* writing, otherwise every delta is zero.
        prev_stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {}
        db['site_metadata'].update_one({'_id': 'global_stats'}, {'$set': data}, upsert=True)
        flash('Statistics updated successfully!', 'success')
        changes = {
            'teams_change': data['teams_count'] - prev_stats.get('teams_count', 0),
            'members_change': data['members_count'] - prev_stats.get('members_count', 0),
            'awards_change': data['awards_count'] - prev_stats.get('awards_count', 0),
            'hours_change': data['hours_built'] - prev_stats.get('hours_built', 0)
        }

        log_activity(
            'stats_update',
            'Updated site statistics',
            details={
                'teams_count': data['teams_count'],
                'members_count': data['members_count'],
                'awards_count': data['awards_count'],
                'hours_built': data['hours_built'],
                'teams_change': changes['teams_change'],
                'members_change': changes['members_change'],
                'awards_change': changes['awards_change'],
                'hours_change': changes['hours_change']
            }
        )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error updating statistics')
        flash('Error updating statistics. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

def parse_event_date(value):
    try:
        return datetime.datetime.strptime((value or '').strip(), '%Y-%m-%dT%H:%M')
    except ValueError:
        raise UserFacingError('Enter a valid event date and time.') from None


@app.route('/admin/add-competition', methods=['POST'])
@role_required('admin')
def admin_add_competition():
    try:
        date_obj = parse_event_date(request.form.get('comp_date'))
        competition_data = {
            'name': request.form.get('comp_name'),
            'location': request.form.get('comp_location'),
            'date': date_obj
        }
        db['competitions'].insert_one(competition_data)
        flash('New competition added successfully!', 'success')

        # Log activity
        log_activity(
            'competition_add',
            f'Added new competition: {competition_data["name"]}',
            details={'name': competition_data['name'], 'location': competition_data['location'],
                    'date': competition_data['date'].strftime('%Y-%m-%d %H:%M')}
        )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error adding competition')
        flash('Error adding competition. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-competition/<id>', methods=['POST'])
@role_required('admin')
def admin_edit_competition(id):
    try:
        date_obj = parse_event_date(request.form.get('comp_date'))
        competition_data = {
            'name': request.form.get('comp_name'),
            'location': request.form.get('comp_location'),
            'date': date_obj
        }
        db['competitions'].update_one({'_id': ObjectId(id)}, {'$set': competition_data})
        flash('Event updated successfully!', 'success')

        # Log activity
        log_activity(
            'competition_update',
            f'Updated competition: {competition_data["name"]}',
            details={'name': competition_data['name'], 'location': competition_data['location'],
                    'date': competition_data['date'].strftime('%Y-%m-%d %H:%M')}
        )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error updating event')
        flash('Error updating event. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-competition/<comp_id>', methods=['POST'])
@role_required('admin')
def admin_delete_competition(comp_id):
    try:
        # Get competition info before deleting for logging
        competition = db['competitions'].find_one({'_id': ObjectId(comp_id)})
        db['competitions'].delete_one({'_id': ObjectId(comp_id)})
        flash('Competition removed.', 'success')

        # Log activity
        if competition:
            log_activity(
                'competition_delete',
                f'Deleted competition: {competition.get("name", "Unknown")}',
                details={'name': competition.get('name', 'Unknown'),
                        'location': competition.get('location', 'Unknown')}
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error deleting competition')
        flash('Error deleting competition. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/save-team', methods=['POST'])
@role_required('admin')
def admin_save_team():
    try:
        team_id = request.form.get('team_id')
        team_number = request.form.get('team_number')

        # Handle file uploads
        hero_image_url = None
        stl_file_url = None

        # Upload hero image if provided
        if 'hero_image' in request.files and request.files['hero_image'].filename:
            hero_image_url = checked_upload(
                request.files['hero_image'], 'teams', team_number,
                allowed=IMAGE_EXTENSIONS, stem='hero')

        # Upload STL file if provided
        if 'stl_file' in request.files and request.files['stl_file'].filename:
            stl_file_url = checked_upload(
                request.files['stl_file'], 'teams', team_number,
                allowed={'stl'}, stem='model')

        team_data = {
            'team_number': team_number,
            'nickname': request.form.get('nickname'),
            'tagline': request.form.get('tagline'),
            'specs': {
                'drive_train': request.form.get('drive_train'),
                'lift_system': request.form.get('lift_system'),
                'intake': request.form.get('intake'),
                'auton_consistency': request.form.get('auton_consistency')
            },
            'notebook_link': request.form.get('notebook_link', '#')
        }

        # Optional profile fields. A blank input stores nothing rather than an empty
        # string or a misleading 0, so the team page can hide what was never filled in.
        for field in ('season', 'division', 'robotevents_number'):
            value = (request.form.get(field) or '').strip()
            if value:
                team_data[field] = value
        for field in ('since', 'worlds_appearances'):
            value = (request.form.get(field) or '').strip()
            if value:
                try:
                    team_data[field] = int(value)
                except ValueError:
                    pass

        # Add file URLs if uploaded
        if hero_image_url:
            team_data['hero_image'] = hero_image_url
        if stl_file_url:
            team_data['stl_path'] = stl_file_url

        # Handle member photos
        members = []
        for i in form_row_indexes('member_name'):
            member_photo_url = None

            # Check if a new photo was uploaded for this member
            member_photo_key = f'member_photo_{i}'
            if member_photo_key in request.files and request.files[member_photo_key].filename:
                member_photo_url = checked_upload(
                    request.files[member_photo_key],
                    'teams', team_number, 'members',
                    allowed=IMAGE_EXTENSIONS,
                    stem=request.form.get(f'member_name_{i}') or 'member')
            else:
                # Use existing photo path from hidden field
                member_photo_url = request.form.get(f'member_photo_path_{i}') or DEFAULT_MEMBER_PHOTO

            member = {
                'name': request.form.get(f'member_name_{i}'),
                'role': request.form.get(f'member_role_{i}'),
                'user_id': request.form.get(f'member_user_{i}'),
                'photo': member_photo_url
            }

            roles = [r.strip() for r in (request.form.get(f'member_roles_{i}') or '').split(',') if r.strip()]
            if roles:
                member['roles'] = roles
            subteam = (request.form.get(f'member_subteam_{i}') or '').strip()
            if subteam:
                member['subteam'] = subteam
            since = (request.form.get(f'member_since_{i}') or '').strip()
            if since:
                try:
                    member['since'] = int(since)
                except ValueError:
                    pass

            members.append(member)

        team_data['members'] = members
        team_data['goals'] = [
            {'name': request.form.get(f'goal_name_{j}'),
             'progress': _clamp_percent(request.form.get(f'goal_progress_{j}', 0))}
            for j in form_row_indexes('goal_name')
        ]

        team_data['journey'] = [
            {'date': request.form.get(f'journey_date_{k}', ''),
             'title': request.form.get(f'journey_title_{k}', ''),
             'description': request.form.get(f'journey_description_{k}', '')}
            for k in form_row_indexes('journey_title')
        ]

        if team_id and len(team_id) == 24:
            # Update existing team - handle old file deletion
            prev_team = db['teams'].find_one({'_id': ObjectId(team_id)})

            # Delete old files from blob if they're being replaced
            if prev_team:
                if hero_image_url and 'hero_image' in prev_team and prev_team['hero_image'].startswith('http'):
                    try:
                        delete_from_vercel_blob(prev_team['hero_image'])
                    except Exception:
                        logger.exception('Error deleting old hero image')

                if stl_file_url and 'stl_path' in prev_team and prev_team['stl_path'].startswith('http'):
                    try:
                        delete_from_vercel_blob(prev_team['stl_path'])
                    except Exception:
                        logger.exception('Error deleting old STL file')

            db['teams'].update_one({'_id': ObjectId(team_id)}, {'$set': team_data})
            flash(f'Team {team_number} updated!', 'success')

            # Log activity for team update
            prev_member_count = len(prev_team.get('members', [])) if prev_team else 0
            new_member_count = len(team_data.get('members', []))
            members_change = new_member_count - prev_member_count

            log_activity(
                'team_update',
                f'Updated team {team_number}: {team_data.get("nickname", "")}',
                details={
                    'team_number': team_number,
                    'nickname': team_data.get('nickname', ''),
                    'members_change': members_change
                }
            )
        else:
            # Create new team
            db['teams'].insert_one(team_data)
            seed_team_awards(team_number)
            flash(f'Team {team_number} created!', 'success')

            # Log activity for new team
            log_activity(
                'team_add',
                f'Added new team {team_number}: {team_data.get("nickname", "")}',
                details={
                    'team_number': team_number,
                    'nickname': team_data.get('nickname', ''),
                    'members_count': len(team_data.get('members', []))
                }
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error saving team')
        flash('Error saving team. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

def form_row_indexes(prefix):
    """Sorted row numbers present in the form for `<prefix>_<n>` fields.

    The dashboard numbers member and goal rows as it creates them, and deleting
    a row leaves a gap. Reading `0, 1, 2, ...` until the first missing number
    silently dropped every row after a deleted one, so collect what is there.
    """
    pattern = re.compile(rf'{re.escape(prefix)}_(\d+)')
    found = {int(m.group(1)) for key in request.form
             if (m := pattern.fullmatch(key))}
    return sorted(found)


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


@app.route('/admin/delete-team/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_team(id):
    try:
        # Get team info before deleting for logging
        team = db['teams'].find_one({'_id': ObjectId(id)})
        db['teams'].delete_one({'_id': ObjectId(id)})
        if team:
            # Drop the team's own award counters and blobs so nothing is orphaned.
            db['awards'].delete_many({'team_number': team.get('team_number')})
            for url in _team_blob_urls(team):
                try:
                    delete_from_vercel_blob(url)
                except Exception:
                    logger.exception('Failed to delete blob %s for deleted team', url)
        flash('Team removed.', 'success')

        # Log activity
        if team:
            log_activity(
                'team_delete',
                f'Deleted team {team.get("team_number", "Unknown")}: {team.get("nickname", "")}',
                details={
                    'team_number': team.get('team_number', 'Unknown'),
                    'nickname': team.get('nickname', ''),
                    'members_count': len(team.get('members', []))
                }
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error deleting team')
        flash('Error deleting team. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-awards', methods=['POST'])
@role_required('admin')
def admin_update_awards():
    try:
        total_change = 0
        award_changes = []

        for key, value in request.form.items():
            if key.startswith('award_'):
                award_id = key.replace('award_', '')
                new_count = int(value)

                # Get previous count
                prev_award = db['awards'].find_one({'_id': ObjectId(award_id)})
                prev_count = prev_award.get('count', 0) if prev_award else 0
                count_change = new_count - prev_count

                # Update award
                db['awards'].update_one({'_id': ObjectId(award_id)},
                                        {'$set': {'count': new_count}})

                if count_change != 0:
                    total_change += count_change
                    award_changes.append({
                        'name': prev_award.get('title', 'Unknown') if prev_award else 'Unknown',
                        'change': count_change
                    })

        flash('Award inventory updated!', 'success')

        # Log activity if there were changes
        if total_change != 0:
            description = f'Updated awards inventory'
            if len(award_changes) == 1:
                award = award_changes[0]
                direction = "increased" if award['change'] > 0 else "decreased"
                description = f'"{award["name"]}" count {direction} by {abs(award["change"])}'
            elif len(award_changes) > 1:
                description = f'Updated {len(award_changes)} awards, net change: {total_change}'

            log_activity(
                'awards_update',
                description,
                details={
                    'total_change': total_change,
                    'award_changes': award_changes,
                    'count_change': total_change  # For monthly change calculation
                }
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error updating awards')
        flash('Error updating awards. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-team-awards', methods=['POST'])
@role_required('admin')
def admin_update_team_awards():
    try:
        total_change = 0
        team_award_changes = []

        for key, value in request.form.items():
            if key.startswith('team_award_'):
                award_id = key.replace('team_award_', '')
                new_count = int(value)

                # Get previous count and team info
                prev_award = db['awards'].find_one({'_id': ObjectId(award_id)})
                prev_count = prev_award.get('count', 0) if prev_award else 0
                count_change = new_count - prev_count

                # Update award
                db['awards'].update_one({'_id': ObjectId(award_id)},
                                        {'$set': {'count': new_count}})

                if count_change != 0:
                    total_change += count_change
                    team_award_changes.append({
                        'team': prev_award.get('team_number', 'Unknown') if prev_award else 'Unknown',
                        'award': prev_award.get('title', 'Unknown') if prev_award else 'Unknown',
                        'change': count_change
                    })

        flash('Team awards updated successfully!', 'success')

        # Log activity if there were changes
        if total_change != 0:
            description = f'Updated team awards'
            if len(team_award_changes) == 1:
                change = team_award_changes[0]
                direction = "increased" if change['change'] > 0 else "decreased"
                description = f'Team {change["team"]} "{change["award"]}" {direction} by {abs(change["change"])}'
            elif len(team_award_changes) > 1:
                description = f'Updated {len(team_award_changes)} team awards, net change: {total_change}'

            log_activity(
                'awards_update',
                description,
                details={
                    'total_change': total_change,
                    'team_award_changes': team_award_changes,
                    'count_change': total_change  # For monthly change calculation
                }
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error updating team awards')
        flash('Error updating team awards. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/create-user', methods=['POST'])
@role_required('admin')
def admin_create_user():
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        if len(password) < PASSWORD_MIN_LENGTH:
            flash(f'Password must be at least {PASSWORD_MIN_LENGTH} characters.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        if db['users'].find_one({'username': username}):
            flash('Username already exists.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        role = request.form.get('role', 'member')
        if role not in USER_ROLES:
            flash('Invalid role.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        user_data = {
            'username': username,
            'email': request.form.get('email', '').strip(),
            'password': hashed,
            'role': role
        }
        db['users'].insert_one(user_data)
        flash(f'User "{username}" created successfully!', 'success')

        # Log activity
        log_activity(
            'user_add',
            f'Created new user: {username}',
            details={
                'username': username,
                'role': user_data['role']
            }
        )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error creating user')
        flash('Error creating user. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard', _anchor='users'))

def _other_admin_exists(user_id):
    return db['users'].count_documents({'role': 'admin', '_id': {'$ne': user_id}}, limit=1) > 0

@app.route('/admin/update-user/<id>', methods=['POST'])
@role_required('admin')
def admin_update_user(id):
    try:
        user = db['users'].find_one({'_id': ObjectId(id)})
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'member')
        if not username:
            flash('Username is required.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        if password and len(password) < PASSWORD_MIN_LENGTH:
            flash(f'Password must be at least {PASSWORD_MIN_LENGTH} characters.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        if role not in USER_ROLES:
            flash('Invalid role.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        if db['users'].find_one({'username': username, '_id': {'$ne': user['_id']}}):
            flash('Username already exists.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))
        if user.get('role') == 'admin' and role != 'admin' and not _other_admin_exists(user['_id']):
            flash('Cannot remove the last admin.', 'error')
            return redirect(url_for('admin_dashboard', _anchor='users'))

        updates = {
            'username': username,
            'email': request.form.get('email', '').strip(),
            'role': role
        }
        if password:
            updates['password'] = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        changes = [f for f in ('username', 'email', 'role') if user.get(f, '') != updates[f]]
        if password:
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

        flash(f'User "{username}" updated!', 'success')
        log_activity(
            'user_update',
            f'Updated user: {username}',
            details={'username': username, 'role': role, 'changes': changes}
        )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error updating user')
        flash('Error updating user. The details were logged for the site maintainer.', 'error')
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    return redirect(url_for('admin_dashboard', _anchor='users'))

@app.route('/admin/delete-user/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_user(id):
    try:
        user = db['users'].find_one({'_id': ObjectId(id)})
        if not user:
            flash('User not found.', 'error')
        elif user['username'] == session.get('user'):
            flash('You cannot delete your own account.', 'error')
        elif user.get('role') == 'admin' and not _other_admin_exists(user['_id']):
            flash('Cannot delete the last admin.', 'error')
        else:
            db['users'].delete_one({'_id': user['_id']})
            # Unlink the account from any team member entries
            for team in db['teams'].find({'members.user_id': id}):
                members = [dict(mem, user_id='') if mem.get('user_id') == id else mem
                           for mem in team['members']]
                db['teams'].update_one({'_id': team['_id']}, {'$set': {'members': members}})
            flash(f'User "{user["username"]}" deleted.', 'success')
            log_activity(
                'user_delete',
                f'Deleted user: {user["username"]}',
                details={'username': user['username'], 'role': user.get('role', 'member')}
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error deleting user')
        flash('Error deleting user. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard', _anchor='users'))

@app.route('/admin/generate-reset-link/<id>', methods=['POST'])
@role_required('admin')
def admin_generate_reset_link(id):
    try:
        user = db['users'].find_one({'_id': ObjectId(id)})
        if not user:
            flash('User not found.', 'error')
        else:
            _ensure_auth_indexes()
            token = secrets.token_urlsafe(32)
            db['password_resets'].delete_many({'user_id': user['_id']})
            db['password_resets'].insert_one({
                'user_id': user['_id'],
                'token_hash': _hash_token(token),
                'created_at': _utcnow(),
            })
            session['_generated_reset_link'] = _build_reset_link(token)
            session['_generated_reset_link_user'] = user['username']
            flash(f'Reset link generated for {user["username"]}. Copy it below.', 'success')
            log_activity(
                'reset_link_generate',
                f'Generated reset link for {user["username"]}',
                details={'username': user['username']}
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error generating reset link')
        flash('Error generating reset link. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard', _anchor='users'))

@app.route('/admin/messages/<id>/<action>', methods=['POST'])
@role_required('admin')
def admin_message_action(id, action):
    """Mark a contact message read, archive it, or delete it."""
    if action not in ('read', 'archive', 'delete'):
        flash('Unknown message action.', 'error')
        return redirect(url_for('admin_dashboard', _anchor='messages'))
    try:
        message = db['contact_messages'].find_one({'_id': ObjectId(id)})
        if not message:
            flash('Message not found.', 'error')
        elif action == 'delete':
            db['contact_messages'].delete_one({'_id': message['_id']})
            flash('Message deleted.', 'success')
            # Log the sender only - never the message body.
            log_activity('message_delete', f'Deleted message from {message.get("email", "unknown")}',
                         details={'message_id': str(message['_id'])})
        else:
            status = 'read' if action == 'read' else 'archived'
            db['contact_messages'].update_one({'_id': message['_id']}, {'$set': {'status': status}})
            flash(f'Message marked {status}.', 'success')
            log_activity(f'message_{action}', f'Message from {message.get("email", "unknown")} marked {status}',
                         details={'message_id': str(message['_id'])})
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error updating message')
        flash('Error updating message. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard', _anchor='messages'))

@app.route('/admin/save-sponsor', methods=['POST'])
@role_required('admin')
def admin_save_sponsor():
    try:
        sponsor_id = request.form.get('sponsor_id')
        name = request.form.get('name')

        # Handle logo upload
        logo_url = None
        if 'logo' in request.files and request.files['logo'].filename:
            logo_url = checked_upload(
                request.files['logo'], 'sponsors',
                allowed=IMAGE_EXTENSIONS, stem=name or 'sponsor')

        sponsor_data = {
            'name': name,
            'website': request.form.get('website', ''),
            'level': request.form.get('level', 'Bronze')
        }

        # Add logo URL if uploaded
        if logo_url:
            sponsor_data['logo'] = logo_url

        if sponsor_id and len(sponsor_id) == 24:
            # Update existing sponsor - handle old logo deletion
            prev_sponsor = db['sponsors'].find_one({'_id': ObjectId(sponsor_id)})

            # Delete old logo from blob if it's being replaced
            if prev_sponsor and logo_url and 'logo' in prev_sponsor and prev_sponsor['logo'].startswith('http'):
                try:
                    delete_from_vercel_blob(prev_sponsor['logo'])
                except Exception:
                    logger.exception('Error deleting old sponsor logo')

            db['sponsors'].update_one({'_id': ObjectId(sponsor_id)}, {'$set': sponsor_data})
            flash(f'Sponsor "{name}" updated!', 'success')

            # Log activity
            log_activity(
                'sponsor_update',
                f'Updated sponsor: {name}',
                details={
                    'name': name,
                    'level': sponsor_data['level']
                }
            )
        else:
            # Create new sponsor
            db['sponsors'].insert_one(sponsor_data)
            flash(f'Sponsor "{name}" added!', 'success')

            # Log activity
            log_activity(
                'sponsor_add',
                f'Added new sponsor: {name}',
                details={
                    'name': name,
                    'level': sponsor_data['level']
                }
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error saving sponsor')
        flash('Error saving sponsor. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-sponsor/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_sponsor(id):
    try:
        # Get sponsor info before deleting for logging
        sponsor = db['sponsors'].find_one({'_id': ObjectId(id)})
        db['sponsors'].delete_one({'_id': ObjectId(id)})
        logo = (sponsor or {}).get('logo')
        if isinstance(logo, str) and logo.startswith('http'):
            try:
                delete_from_vercel_blob(logo)
            except Exception:
                logger.exception('Failed to delete logo blob %s for deleted sponsor', logo)
        flash('Sponsor removed.', 'success')

        # Log activity
        if sponsor:
            log_activity(
                'sponsor_delete',
                f'Deleted sponsor: {sponsor.get("name", "Unknown")}',
                details={
                    'name': sponsor.get('name', 'Unknown'),
                    'level': sponsor.get('level', 'Unknown')
                }
            )
    except UserFacingError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Error deleting sponsor')
        flash('Error deleting sponsor. The details were logged for the site maintainer.', 'error')
    return redirect(url_for('admin_dashboard'))

ROBOTEVENTS_TEAM_NUMBERS = ['77628D', '77628P']
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
    api_key = os.getenv('ROBOTEVENTS_API_KEY')
    if not api_key:
        return {'matches': []}

    headers = {'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}

    def fetch(endpoint):
        try:
            resp = requests.get(f'https://www.robotevents.com/api/v2/{endpoint}', headers=headers, timeout=8)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning('RobotEvents fetch failed for %s', endpoint, exc_info=True)
            return None

    number_qs = '&'.join(f'number[]={n}' for n in ROBOTEVENTS_TEAM_NUMBERS)
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
    writer.writerow(['email', 'subscribed_at'])
    for sub in db['newsletter_subscribers'].find().sort('created_at', -1):
        created = sub.get('created_at')
        writer.writerow([csv_safe(sub.get('email', '')),
                         csv_safe(created.strftime('%Y-%m-%d %H:%M') if created else '')])
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
                  "messages": [{"role": "system", "content": CHAT_SYSTEM_PROMPT},
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

@app.route('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
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
    for team in db['teams'].find({}, {'team_number': 1}):
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

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.exception("Internal server error: %s", e)
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # Let Flask's own HTTP errors (404, 400, 413, ...) keep their status and
    # their dedicated handlers instead of collapsing everything into a 500.
    if isinstance(e, HTTPException):
        return e
    logger.exception("Unhandled exception: %s", e)
    return render_template('500.html'), 500

@app.after_request
def add_static_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

if __name__ == '__main__':
    # The Werkzeug debugger executes code from the browser; only opt in.
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')