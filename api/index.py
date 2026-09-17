import os
import datetime
import urllib.parse
import hashlib
import html
import math
import re
import secrets
import logging
from functools import wraps
from bson import ObjectId
import bcrypt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import requests
import mimetypes

load_dotenv()

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
        raise Exception(f"Failed to upload to Vercel Blob: {response.status_code} - {response.text}")

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
        print(f"Warning: Failed to delete blob {url}: {response.status_code} - {response.text}")

# Resolve absolute paths so Vercel can find templates/static regardless of working directory
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_root, 'templates'),
            static_folder=os.path.join(_root, 'static'))
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-key')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.getenv('VERCEL')),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=30),
)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

@app.template_filter('collapse_ws')
def collapse_whitespace(value):
    """Collapse newlines/indentation from wrapped Jinja block text so it's safe inside a single HTML attribute (og:*, twitter:*, meta description)."""
    return ' '.join(str(value).split())

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'stl'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_time_ago(timestamp):
    """Convert timestamp to human-readable time ago string"""
    now = datetime.datetime.now()
    diff = now - timestamp

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
            'user': user or (session.get('username') if 'username' in session else 'System'),
            'timestamp': datetime.datetime.now(),
            'details': details or {}
        }
        db['activities'].insert_one(activity)
    except Exception as e:
        print(f"Failed to log activity: {e}")

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
    }
    return titles.get(activity_type, 'Activity')

# --- MongoDB Connection (lazy) ---
_client = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        mongo_uri = os.getenv('MONGO_URI')
        if not mongo_uri:
            raise RuntimeError("MONGO_URI environment variable is not set.")
        _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        _db = _client['mepham']
    return _db

class _DbProxy:
    def __getitem__(self, name):
        return get_db()[name]
    def __getattr__(self, name):
        return getattr(get_db(), name)

db = _DbProxy()

def get_image_url(image_path, external=False):
    """Helper function to get proper image URL for both local static files and Vercel Blob URLs"""
    if not image_path:
        return url_for('static', filename='assets/other/base.png', _external=external)

    # If it's already a full URL (http/https), use it directly
    if image_path.startswith(('http://', 'https://')):
        return image_path

    # Otherwise, treat it as a local static file path
    # Clean up the path by removing 'static/' prefix if present
    clean_path = image_path.replace('\\', '/').replace('static/', '')
    return url_for('static', filename=clean_path, _external=external)

@app.context_processor
def inject_global_data():
    try:
        nav_teams = list(db['teams'].find({}, {'team_number': 1}).sort('team_number', 1))
        awards_list = list(db['awards'].find({'team_number': {'$exists': False}}).sort('_id', 1))
        sponsors_list = list(db['sponsors'].find())
    except Exception:
        logger.exception("inject_global_data: failed to load nav/footer data")
        nav_teams, awards_list, sponsors_list = [], [], []
    for s in sponsors_list:
        s['_id'] = str(s['_id'])
        # Ensure sponsors have logo_path field for backward compatibility with templates
        if 'logo' in s:
            s['logo_path'] = s['logo']
        else:
            s['logo_path'] = None
    return dict(
        nav_teams=nav_teams,
        global_awards=awards_list,
        sponsors=sponsors_list,
        get_activity_icon=get_activity_icon,
        get_activity_title=get_activity_title,
        get_image_url=get_image_url,
        abs=abs
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

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return _login_redirect()
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user' not in session:
                return _login_redirect()
            if session.get('role') != role and session.get('role') != 'admin':
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# --- Auth helpers: rate limiting, reset tokens, email ---
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW = datetime.timedelta(minutes=15)
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
    db['login_attempts'].create_index([('key', 1), ('ip', 1)])
    db['password_resets'].create_index('created_at', expireAfterSeconds=int(RESET_TOKEN_TTL.total_seconds()))
    db['password_resets'].create_index('token_hash', unique=True)
    _auth_indexes_ready = True

def _lockout_minutes(key, ip):
    """Minutes until (key, ip) may try again, or 0 if not locked out."""
    since = _utcnow() - LOGIN_WINDOW
    attempts = list(db['login_attempts'].find(
        {'key': key, 'ip': ip, 'created_at': {'$gte': since}}).sort('created_at', 1))
    if len(attempts) < LOGIN_MAX_ATTEMPTS:
        return 0
    unlock_at = attempts[0]['created_at'] + LOGIN_WINDOW
    return max(1, math.ceil((unlock_at - _utcnow()).total_seconds() / 60))

def _record_attempt(key, ip):
    _ensure_auth_indexes()
    db['login_attempts'].insert_one({'key': key, 'ip': ip, 'created_at': _utcnow()})

def _clear_attempts(key, ip=None):
    query = {'key': key}
    if ip is not None:
        query['ip'] = ip
    db['login_attempts'].delete_many(query)

def _hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def send_email(to, subject, text, html_body):
    """Send one email through Resend. Returns False instead of raising."""
    api_key = os.getenv('RESEND_API_KEY')
    sender = os.getenv('RESEND_FROM')
    if not api_key or not sender:
        app.logger.error('send_email: RESEND_API_KEY or RESEND_FROM is not set')
        return False
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {api_key}'},
            json={'from': sender, 'to': [to], 'subject': subject, 'text': text, 'html': html_body},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        app.logger.exception('send_email: Resend request failed')
        return False

def _reset_email_bodies(username, link):
    text = (
        f"Hi {username},\n\n"
        f"Someone asked to reset your Mepham Robotics password. Use this link within 1 hour:\n\n"
        f"{link}\n\n"
        f"If you didn't ask for this, you can ignore this email."
    )
    safe_name = html.escape(username)
    safe_link = html.escape(link, quote=True)
    html_body = (
        f"<p>Hi {safe_name},</p>"
        f"<p>Someone asked to reset your Mepham Robotics password. This link works for 1 hour:</p>"
        f"<p><a href=\"{safe_link}\" style=\"display:inline-block;padding:12px 20px;background:#800000;"
        f"color:#ffffff;text-decoration:none;border-radius:8px;font-weight:bold;\">Reset password</a></p>"
        f"<p>If you didn't ask for this, you can ignore this email.</p>"
    )
    return text, html_body

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

@app.route('/')
def index():
    stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {
        'teams_count': 0, 'members_count': 0, 'awards_count': 0, 'hours_built': 0
    }
    now = datetime.datetime.now()
    upcoming_events = list(db['competitions'].find({'date': {'$gte': now}}).sort('date', 1))
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
    return render_template('achievements.html', active_page='achievements')

@app.route('/contact')
def contact():
    return render_template('contact.html', active_page='contact')

@app.route('/donate')
def donate():
    return render_template('donate.html', active_page='donate')

@app.route('/team/<team_number>')
def team_page(team_number):
    team = db['teams'].find_one({'team_number': team_number})
    if not team:
        flash(f"Team {team_number} not found.", "error")
        return redirect(url_for('index'))
    team['_id'] = str(team['_id'])
    team_awards = list(db['awards'].find({'team_number': team_number}).sort('_id', 1))  # ← FIXED
    return render_template('team.html', team=team, team_awards=team_awards, active_page=team_number)

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
    if 'user' in session:
        return redirect(next_url)

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
            session.permanent = bool(request.form.get('remember'))
            return redirect(next_url)

        _record_attempt(attempt_key, ip)
        return render_template('login.html', active_page='login',
                               error='Invalid credentials. Please try again.',
                               next=next_url, username=identifier), 401

    return render_template('login.html', active_page='login', next=next_url)

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        ip = _client_ip()
        key = f'reset:{email}'
        if email and not _lockout_minutes(key, ip):
            _record_attempt(key, ip)
            user = db['users'].find_one({'email': {'$regex': f'^{re.escape(email)}$', '$options': 'i'}})
            if user and user.get('email'):
                token = secrets.token_urlsafe(32)
                db['password_resets'].delete_many({'user_id': user['_id']})
                db['password_resets'].insert_one({
                    'user_id': user['_id'],
                    'token_hash': _hash_token(token),
                    'created_at': _utcnow(),
                })
                public_base = os.getenv('PUBLIC_BASE_URL', '')
                if public_base:
                    link = public_base.rstrip('/') + url_for('reset_password', token=token)
                else:
                    link = url_for('reset_password', token=token, _external=True)
                text, html_body = _reset_email_bodies(user['username'], link)
                # Result ignored deliberately so the response doesn't reveal whether the email matched.
                send_email(user['email'], 'Reset your Mepham Robotics password', text, html_body)
        return render_template('forgot_password.html', active_page='login', sent=True)
    return render_template('forgot_password.html', active_page='login', sent=False)

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
        if len(password) < 8:
            error = 'Password must be at least 8 characters.'
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
        db['users'].update_one({'_id': user['_id']}, {'$set': {'password': hashed}})
        db['password_resets'].delete_many({'user_id': user['_id']})
        _clear_attempts(user['username'].lower())
        if user.get('email'):
            _clear_attempts(user['email'].lower())
        log_activity('password_reset', f'Password reset for {user["username"]}',
                     user=user['username'], details={'username': user['username']})
        flash('Password updated. Sign in with your new password.', 'success')
        return redirect(url_for('login'))

    return _no_referrer(render_template('reset_password.html', active_page='login', invalid=False))

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
    sponsors = [dict(s, _id=str(s['_id'])) for s in db['sponsors'].find()]

    # Get recent activities
    activities = []
    monthly_changes = {
        'teams_change': 0,
        'members_change': 0,
        'awards_change': 0,
        'events_change': 0
    }

    if 'activities' in db.list_collection_names():
        # Get activities for display
        activities_raw = list(db['activities'].find().sort('timestamp', -1).limit(10))
        for a in activities_raw:
            a['_id'] = str(a['_id'])
            if 'timestamp' in a:
                a['display_time'] = get_time_ago(a['timestamp'])
            activities.append(a)

        # Calculate monthly changes
        first_of_month = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_activities = list(db['activities'].find({'timestamp': {'$gte': first_of_month}}))

        for activity in monthly_activities:
            activity_type = activity.get('type', '')
            details = activity.get('details', {})

            if activity_type == 'stats_update':
                # Use the change details from stats updates
                monthly_changes['teams_change'] += details.get('teams_change', 0)
                monthly_changes['members_change'] += details.get('members_change', 0)
                monthly_changes['awards_change'] += details.get('awards_change', 0)
            elif activity_type == 'team_add':
                monthly_changes['teams_change'] += 1
                monthly_changes['members_change'] += details.get('members_count', 0)
            elif activity_type == 'team_delete':
                monthly_changes['teams_change'] -= 1
                monthly_changes['members_change'] -= details.get('members_count', 0)
            elif activity_type == 'team_update':
                # Team updates might include member changes
                if 'members_change' in details:
                    monthly_changes['members_change'] += details.get('members_change', 0)
            elif activity_type == 'awards_update':
                if 'count_change' in details:
                    monthly_changes['awards_change'] += details.get('count_change', 0)
                elif 'total_change' in details:
                    monthly_changes['awards_change'] += details.get('total_change', 0)
            elif activity_type == 'competition_add':
                monthly_changes['events_change'] += 1
            elif activity_type == 'competition_delete':
                monthly_changes['events_change'] -= 1
            elif activity_type == 'sponsor_add':
                # Sponsors don't affect the main stats shown
                pass
            elif activity_type == 'sponsor_delete':
                # Sponsors don't affect the main stats shown
                pass
            elif activity_type == 'user_add':
                # Users don't affect the main stats shown
                pass

    return render_template('admin.html', stats=stats, competitions=competitions,
                           awards=global_awards, team_awards=team_awards_list,
                           teams=teams, users=users, sponsors=sponsors,
                           activities=activities, monthly_changes=monthly_changes)

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
        db['site_metadata'].update_one({'_id': 'global_stats'}, {'$set': data}, upsert=True)
        flash('Statistics updated successfully!', 'success')

        # Log activity with change calculations
        # Get previous stats to calculate changes
        prev_stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {}
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
    except Exception as e:
        flash(f'Error updating statistics: {e}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add-competition', methods=['POST'])
@role_required('admin')
def admin_add_competition():
    try:
        date_obj = datetime.datetime.strptime(request.form.get('comp_date'), '%Y-%m-%dT%H:%M')
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
    except Exception as e:
        flash(f'Error adding competition: {e}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update-competition/<id>', methods=['POST'])
@role_required('admin')
def admin_edit_competition(id):
    try:
        date_obj = datetime.datetime.strptime(request.form.get('comp_date'), '%Y-%m-%dT%H:%M')
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
    except Exception as e:
        flash(f'Error updating event: {e}', 'error')
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
    except Exception as e:
        flash(f'Error deleting competition: {e}', 'error')
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
            hero_image_file = request.files['hero_image']
            hero_image_url = upload_to_vercel_blob(
                hero_image_file,
                f'teams/{team_number}/hero_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.{hero_image_file.filename.split(".")[-1]}'
            )

        # Upload STL file if provided
        if 'stl_file' in request.files and request.files['stl_file'].filename:
            stl_file = request.files['stl_file']
            stl_file_url = upload_to_vercel_blob(
                stl_file,
                f'teams/{team_number}/model_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.stl'
            )

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

        # Add file URLs if uploaded
        if hero_image_url:
            team_data['hero_image'] = hero_image_url
        if stl_file_url:
            team_data['stl_path'] = stl_file_url

        # Handle member photos
        members = []
        i = 0
        while f'member_name_{i}' in request.form:
            member_photo_url = None

            # Check if a new photo was uploaded for this member
            member_photo_key = f'member_photo_{i}'
            if member_photo_key in request.files and request.files[member_photo_key].filename:
                member_photo_file = request.files[member_photo_key]
                member_photo_url = upload_to_vercel_blob(
                    member_photo_file,
                    f'teams/{team_number}/members/{request.form.get(f"member_name_{i}").replace(" ", "_")}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.{member_photo_file.filename.split(".")[-1]}'
                )
            else:
                # Use existing photo path from hidden field
                member_photo_url = request.form.get(f'member_photo_path_{i}', 'static/assets/profile/base.png')

            members.append({
                'name': request.form.get(f'member_name_{i}'),
                'role': request.form.get(f'member_role_{i}'),
                'user_id': request.form.get(f'member_user_{i}'),
                'photo': member_photo_url
            })
            i += 1

        team_data['members'] = members

        goals = []
        j = 0
        while f'goal_name_{j}' in request.form:
            goals.append({'name': request.form.get(f'goal_name_{j}'),
                          'progress': int(request.form.get(f'goal_progress_{j}', 0))})
            j += 1
        team_data['goals'] = goals

        if team_id and len(team_id) == 24:
            # Update existing team - handle old file deletion
            prev_team = db['teams'].find_one({'_id': ObjectId(team_id)})

            # Delete old files from blob if they're being replaced
            if prev_team:
                if hero_image_url and 'hero_image' in prev_team and prev_team['hero_image'].startswith('http'):
                    try:
                        delete_from_vercel_blob(prev_team['hero_image'])
                    except Exception as e:
                        print(f"Error deleting old hero image: {e}")

                if stl_file_url and 'stl_path' in prev_team and prev_team['stl_path'].startswith('http'):
                    try:
                        delete_from_vercel_blob(prev_team['stl_path'])
                    except Exception as e:
                        print(f"Error deleting old STL file: {e}")

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
    except Exception as e:
        flash(f'Error saving team: {e}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-team/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_team(id):
    try:
        # Get team info before deleting for logging
        team = db['teams'].find_one({'_id': ObjectId(id)})
        db['teams'].delete_one({'_id': ObjectId(id)})
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
    except Exception as e:
        flash(f'Error deleting team: {e}', 'error')
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
                        'name': prev_award.get('name', 'Unknown') if prev_award else 'Unknown',
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
    except Exception as e:
        flash(f'Error updating awards: {e}', 'error')
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
                        'award': prev_award.get('name', 'Unknown') if prev_award else 'Unknown',
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
    except Exception as e:
        flash(f'Error updating team awards: {e}', 'error')
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
    except Exception as e:
        flash(f'Error creating user: {e}', 'error')
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
        db['users'].update_one({'_id': user['_id']}, {'$set': updates})

        # Keep the current session in sync when admins edit themselves
        if session.get('user') == user['username']:
            session['user'] = username
            session['role'] = role

        flash(f'User "{username}" updated!', 'success')
        changes = [f for f in ('username', 'email', 'role') if user.get(f, '') != updates[f]]
        if password:
            changes.append('password')
        log_activity(
            'user_update',
            f'Updated user: {username}',
            details={'username': username, 'role': role, 'changes': changes}
        )
    except Exception as e:
        flash(f'Error updating user: {e}', 'error')
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
    except Exception as e:
        flash(f'Error deleting user: {e}', 'error')
    return redirect(url_for('admin_dashboard', _anchor='users'))

@app.route('/admin/save-sponsor', methods=['POST'])
@role_required('admin')
def admin_save_sponsor():
    try:
        sponsor_id = request.form.get('sponsor_id')
        name = request.form.get('name')

        # Handle logo upload
        logo_url = None
        if 'logo' in request.files and request.files['logo'].filename:
            logo_file = request.files['logo']
            logo_url = upload_to_vercel_blob(
                logo_file,
                f'sponsors/{name.replace(" ", "_")}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.{logo_file.filename.split(".")[-1]}'
            )

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
                except Exception as e:
                    print(f"Error deleting old sponsor logo: {e}")

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
    except Exception as e:
        flash(f'Error saving sponsor: {e}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-sponsor/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_sponsor(id):
    try:
        # Get sponsor info before deleting for logging
        sponsor = db['sponsors'].find_one({'_id': ObjectId(id)})
        db['sponsors'].delete_one({'_id': ObjectId(id)})
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
    except Exception as e:
        flash(f'Error deleting sponsor: {e}', 'error')
    return redirect(url_for('admin_dashboard'))

ROBOTEVENTS_TEAM_NUMBERS = ['77628D', '77628P']

@app.route('/api/matches')
def api_matches():
    """Proxy RobotEvents match data so the API key never reaches the browser."""
    api_key = os.getenv('ROBOTEVENTS_API_KEY')
    if not api_key:
        return jsonify({'matches': []})

    headers = {'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}

    def fetch(endpoint):
        try:
            resp = requests.get(f'https://www.robotevents.com/api/v2/{endpoint}', headers=headers, timeout=8)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"RobotEvents fetch error: {e}")
            return None

    number_qs = '&'.join(f'number[]={n}' for n in ROBOTEVENTS_TEAM_NUMBERS)
    teams_data = fetch(f'teams?{number_qs}')
    if not teams_data or not teams_data.get('data'):
        return jsonify({'matches': []})

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

    return jsonify({'matches': results})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json()
    user_message = data.get('message')
    if not user_message:
        return {'error': 'No message provided'}, 400
    try:
        response = requests.post(
            os.getenv('CHATBOT_API_URL', "https://ai.hackclub.com/proxy/v1/chat/completions"),
            headers={"Authorization": f"Bearer {os.getenv('CHATBOT_API_KEY')}", "Content-Type": "application/json"},
            json={"model": os.getenv('CHATBOT_MODEL', "gpt-4o-mini"),
                  "messages": [{"role": "system", "content": "You are Steven, the official AI assistant for the Mepham Robotics Club (VEX V5 Team 77628). Be helpful, enthusiastic about robotics, and concise."},
                                {"role": "user", "content": user_message}]})
        response.raise_for_status()
        return {'reply': response.json()['choices'][0]['message']['content']}
    except Exception:
        return {'error': 'Failed to process request'}, 500

@app.context_processor
def inject_user():
    return dict(current_user=session.get('user'))

STATIC_PUBLIC_PAGES = [
    ('index', 1.0, 'daily'),
    ('about', 0.8, 'monthly'),
    ('achievements', 0.8, 'weekly'),
    ('donate', 0.7, 'monthly'),
    ('contact', 0.6, 'monthly'),
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

logger = logging.getLogger(__name__)

@app.errorhandler(500)
def internal_server_error(e):
    logger.exception("Internal server error: %s", e)
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.exception("Unhandled exception: %s", e)
    return render_template('500.html'), 500

@app.after_request
def add_static_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

if __name__ == '__main__':
    app.run(debug=True)