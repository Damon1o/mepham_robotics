import os
import datetime
from functools import wraps
from bson import ObjectId

import bcrypt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient

load_dotenv()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-key')

app.config['UPLOAD_FOLDER'] = os.path.join('../static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'stl'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- MongoDB Connection (Defensive) ---
try:
    mongo_uri = os.getenv('MONGO_URI')
    if mongo_uri:
        client = MongoClient(mongo_uri)
        db = client['mepham']
        users_collection = db['users']
    else:
        print("MONGO_URI not found in environment!")
        db = None
        users_collection = None
except Exception as e:
    print(f"CRITICAL MONGODB ERROR: {e}")
    db = None
    users_collection = None


# --- Diagnostic Route ---
@app.route('/health')
def health_check():
    return "App is Running! If you see this, the routing works. Check your MongoDB Env Vars next.", 200

@app.context_processor
def inject_global_data():
    nav_teams, awards_list, sponsors_list = [], [], []
    if db is not None:
        try:
            nav_teams = list(db['teams'].find({}, {'team_number': 1}).sort('team_number', 1))
            awards_list = list(db['awards'].find())
            sponsors_list = list(db['sponsors'].find())
            for s in sponsors_list:
                s['_id'] = str(s['_id'])
        except Exception as e:
            print(f"Database Query Error: {e}")
            
    return dict(nav_teams=nav_teams, awards=awards_list, sponsors=sponsors_list)


# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            if session.get('role') != role and session.get('role') != 'admin':
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# --- Public Pages ---

@app.route('/')
def index():
    # Fetch Stats
    stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {
        'teams_count': 0, 'members_count': 0, 'awards_count': 0, 'hours_built': 0
    }
    
    # Fetch all future competitions
    now = datetime.datetime.now()
    upcoming_events = list(db['competitions'].find({'date': {'$gte': now}}).sort('date', 1))
    
    # Pre-format dates for the template
    for event in upcoming_events:
        event['month'] = event['date'].strftime('%b').upper()
        event['day'] = event['date'].strftime('%d')
        event['time'] = event['date'].strftime('%I:%M %p')

    # The countdown uses the very next one
    competition = upcoming_events[0] if upcoming_events else None
    
    return render_template('index.html', 
                           active_page='index', 
                           stats=stats, 
                           competition=competition,
                           upcoming_events=upcoming_events)


@app.route('/about')
def about():
    return render_template('about.html', active_page='about')


@app.route('/achievements')
def achievements():
    awards = list(db['awards'].find())
    return render_template('achievements.html', 
                           active_page='achievements', 
                           awards=awards)


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
    # Ensure ID is string for any template usage
    team['_id'] = str(team['_id'])
    return render_template('team.html', team=team, active_page=team_number)


@app.route('/safety-quiz')
def safety_quiz():
    return render_template('safety_quiz.html', active_page='safety_quiz')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html', active_page='privacy')


@app.route('/credits')
def credits_page():
    return render_template('credits.html', active_page='credits')


# --- Auth-Gated Pages ---

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


# --- Login / Logout ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Look up user by username or email
        user = users_collection.find_one({
            '$or': [
                {'username': username},
                {'email': username}
            ]
        })

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            session['user'] = user['username']
            session['role'] = user.get('role', 'member')
            return redirect(url_for('index'))

        return render_template('login.html', active_page='login', error='Invalid credentials. Please try again.')

    return render_template('login.html', active_page='login')


@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return redirect(url_for('index'))


# --- Admin Dashboard ---

@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    stats = db['site_metadata'].find_one({'_id': 'global_stats'}) or {}
    if '_id' in stats and not isinstance(stats['_id'], str):
        stats['_id'] = str(stats['_id'])
    awards_raw = list(db['awards'].find())
    awards = []
    for a in awards_raw:
        a['_id'] = str(a['_id'])
        awards.append(a)

    competitions_raw = list(db['competitions'].find().sort('date', 1))
    competitions = []
    for c in competitions_raw:
        c['_id'] = str(c['_id'])
        if 'date' in c:
            c['date_str'] = c['date'].strftime('%Y-%m-%dT%H:%M')
            c['display_date'] = c['date'].strftime('%b %d, %Y @ %I:%M %p')
        competitions.append(c)

    users = []
    for u in db['users'].find({}, {'username': 1}):
        u['_id'] = str(u['_id'])
        users.append(u)
    
    teams = []
    for t in db['teams'].find().sort('team_number', 1):
        t['_id'] = str(t['_id'])
        # Also convert user_ids in members if they exist
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
    
    sponsors = list(db['sponsors'].find())
    for s in sponsors:
        s['_id'] = str(s['_id'])

    return render_template('admin.html', 
                           stats=stats, 
                           competitions=competitions, 
                           awards=awards,
                           teams=teams,
                           users=users,
                           sponsors=sponsors)


@app.route('/admin/update-stats', methods=['POST'])
@role_required('admin')
def admin_update_stats():
    # ... logic stays same ...
    try:
        data = {
            'teams_count': int(request.form.get('teams_count', 0)),
            'members_count': int(request.form.get('members_count', 0)),
            'awards_count': int(request.form.get('awards_count', 0)),
            'hours_built': int(request.form.get('hours_built', 0))
        }
        db['site_metadata'].update_one(
            {'_id': 'global_stats'},
            {'$set': data},
            upsert=True
        )
        flash('Statistics updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating statistics: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/add-competition', methods=['POST'])
@role_required('admin')
def admin_add_competition():
    try:
        name = request.form.get('comp_name')
        location = request.form.get('comp_location')
        date_str = request.form.get('comp_date')
        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        
        db['competitions'].insert_one({
            'name': name,
            'location': location,
            'date': date_obj
        })
        flash('New competition added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding competition: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update-competition/<id>', methods=['POST'])
@role_required('admin')
def admin_edit_competition(id):
    try:
        name = request.form.get('comp_name')
        location = request.form.get('comp_location')
        date_str = request.form.get('comp_date')
        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        
        db['competitions'].update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'name': name,
                'location': location,
                'date': date_obj
            }}
        )
        flash('Event updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating event: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-competition/<comp_id>', methods=['POST'])
@role_required('admin')
def admin_delete_competition(comp_id):
    try:
        db['competitions'].delete_one({'_id': ObjectId(comp_id)})
        flash('Competition removed.', 'success')
    except Exception as e:
        flash(f'Error deleting competition: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/save-team', methods=['POST'])
@role_required('admin')
def admin_save_team():
    try:
        team_id = request.form.get('team_id') # If present, we're editing
        team_number = request.form.get('team_number')
        
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

        # Handle Hero Image Upload
        hero_img = request.files.get('hero_image')
        if hero_img and allowed_file(hero_img.filename):
            filename = secure_filename(f"hero_{team_number}_{hero_img.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'teams', filename)
            hero_img.save(path)
            team_data['hero_image'] = path.replace('\\', '/')

        # Handle STL Upload
        stl_file = request.files.get('stl_file')
        if stl_file and allowed_file(stl_file.filename):
            filename = secure_filename(f"robot_{team_number}.stl")
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'teams', filename)
            stl_file.save(path)
            team_data['stl_path'] = path.replace('\\', '/')

        # Handle Members and Goals (Simplified parsing from dynamic form fields)
        # This part assumes we use fields like member_name_0, member_role_0, etc.
        members = []
        i = 0
        while f'member_name_{i}' in request.form:
            member = {
                'name': request.form.get(f'member_name_{i}'),
                'role': request.form.get(f'member_role_{i}'),
                'user_id': request.form.get(f'member_user_{i}'),
                'photo': request.form.get(f'member_photo_path_{i}', 'static/assets/profile/base.png')
            }
            # Handle Member Photo Upload
            m_photo = request.files.get(f'member_photo_{i}')
            if m_photo and allowed_file(m_photo.filename):
                m_filename = secure_filename(f"member_{team_number}_{i}_{m_photo.filename}")
                m_path = os.path.join(app.config['UPLOAD_FOLDER'], 'teams', m_filename)
                m_photo.save(m_path)
                member['photo'] = m_path.replace('\\', '/')
            
            members.append(member)
            i += 1
        team_data['members'] = members

        goals = []
        j = 0
        while f'goal_name_{j}' in request.form:
            goals.append({
                'name': request.form.get(f'goal_name_{j}'),
                'progress': int(request.form.get(f'goal_progress_{j}', 0))
            })
            j += 1
        team_data['goals'] = goals

        if team_id and len(team_id) == 24:
            db['teams'].update_one({'_id': ObjectId(team_id)}, {'$set': team_data})
            flash(f'Team {team_number} updated!', 'success')
        else:
            db['teams'].insert_one(team_data)
            flash(f'Team {team_number} created!', 'success')

    except Exception as e:
        flash(f'Error saving team: {e}', 'error')
    
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-team/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_team(id):
    try:
        db['teams'].delete_one({'_id': ObjectId(id)})
        flash('Team removed.', 'success')
    except Exception as e:
        flash(f'Error deleting team: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update-awards', methods=['POST'])
@role_required('admin')
def admin_update_awards():
    try:
        # Iterate through all form fields to find award counts
        for key, value in request.form.items():
            if key.startswith('award_'):
                award_id = key.replace('award_', '')
                count = int(value)
                db['awards'].update_one(
                    {'_id': ObjectId(award_id)},
                    {'$set': {'count': count}}
                )
        flash('Award inventory updated!', 'success')
    except Exception as e:
        flash(f'Error updating awards: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/create-user', methods=['POST'])
@role_required('admin')
def admin_create_user():
    try:
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'member').strip()

        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('admin_dashboard'))

        # Check if user already exists
        if users_collection.find_one({'username': username}):
            flash('Username already exists.', 'error')
            return redirect(url_for('admin_dashboard'))

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed,
            'role': role
        })
        flash(f'User "{username}" created successfully as {role}!', 'success')
    except Exception as e:
        flash(f'Error creating user: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/save-sponsor', methods=['POST'])
@role_required('admin')
def admin_save_sponsor():
    try:
        sponsor_id = request.form.get('sponsor_id')
        name = request.form.get('name')
        website = request.form.get('website', '')
        level = request.form.get('level', 'Bronze')
        
        sponsor_data = {
            'name': name,
            'website': website,
            'level': level
        }

        # Handle Logo Upload
        logo_file = request.files.get('logo')
        if logo_file and allowed_file(logo_file.filename):
            # Ensure directory exists
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'sponsors'), exist_ok=True)
            filename = secure_filename(f"sponsor_{name.replace(' ', '_')}_{logo_file.filename}")
            path = os.path.join('static/uploads/sponsors', filename)
            abs_path = os.path.join(app.root_path, path)
            logo_file.save(abs_path)
            sponsor_data['logo_path'] = path.replace('\\', '/')

        if sponsor_id and len(sponsor_id) == 24:
            db['sponsors'].update_one({'_id': ObjectId(sponsor_id)}, {'$set': sponsor_data})
            flash(f'Sponsor "{name}" updated!', 'success')
        else:
            db['sponsors'].insert_one(sponsor_data)
            flash(f'Sponsor "{name}" added!', 'success')

    except Exception as e:
        flash(f'Error saving sponsor: {e}', 'error')
    
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-sponsor/<id>', methods=['POST'])
@role_required('admin')
def admin_delete_sponsor(id):
    try:
        db['sponsors'].delete_one({'_id': ObjectId(id)})
        flash('Sponsor removed.', 'success')
    except Exception as e:
        flash(f'Error deleting sponsor: {e}', 'error')
    return redirect(url_for('admin_dashboard'))


# --- API Routes ---
@app.route('/api/chat', methods=['POST'])
def api_chat():
    import requests
    
    data = request.get_json()
    user_message = data.get('message')
    
    if not user_message:
        return {'error': 'No message provided'}, 400

    api_key = os.getenv('CHATBOT_API_KEY')
    url = os.getenv('CHATBOT_API_URL', "https://ai.hackclub.com/proxy/v1/chat/completions")
    model = os.getenv('CHATBOT_MODEL', "gpt-4o-mini")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Add a system prompt to give the AI context about Mepham Robotics
    system_prompt = (
        "You are Steven, the official AI assistant for the Mepham Robotics Club (VEX V5 Team 77628). "
        "Be helpful, enthusiastic about robotics, and concise."
    )
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        reply = result['choices'][0]['message']['content']
        return {'reply': reply}
    except Exception as e:
        print(f"Chat API Error: {e}")
        return {'error': 'Failed to process request'}, 500


# --- Inject user into all templates ---
@app.context_processor
def inject_user():
    return dict(current_user=session.get('user'))


# --- CLI: Seed initial user ---
@app.cli.command('seed-user')
def seed_user():
    """Create or update the default admin user."""
    username = 'damon'
    email = 'damon@mephamrobotics.com'
    password = '131265614'
    role = 'admin'

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    users_collection.update_one(
        {'username': username},
        {'$set': {
            'username': username,
            'email': email,
            'password': hashed,
            'role': role
        }},
        upsert=True
    )
    print(f'User "{username}" seeded successfully as {role}.')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)
