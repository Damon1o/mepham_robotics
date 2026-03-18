import os
from functools import wraps

import bcrypt
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-key')

# --- MongoDB Connection ---
client = MongoClient(os.getenv('MONGO_URI'))
db = client['mepham']
users_collection = db['users']


# --- Auth Decorator ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# --- Public Pages ---

@app.route('/')
def index():
    return render_template('index.html', active_page='index')


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


@app.route('/team/77628D')
def team_77628D():
    return render_template('77628D.html', active_page='77628D')


@app.route('/team/77628P')
def team_77628P():
    return render_template('77628P.html', active_page='77628P')


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
@login_required
def resources():
    return render_template('resources.html', active_page='resources')


@app.route('/glossary')
@login_required
def glossary():
    return render_template('glossary.html', active_page='glossary')


@app.route('/branding')
@login_required
def branding():
    return render_template('branding.html', active_page='branding')


@app.route('/standards')
@login_required
def standards():
    return render_template('standards.html', active_page='standards')


@app.route('/notebook')
@login_required
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
            return redirect(url_for('resources'))

        return render_template('login.html', active_page='login', error='Invalid credentials. Please try again.')

    return render_template('login.html', active_page='login')


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


# --- API Routes ---
@app.route('/api/chat', methods=['POST'])
def api_chat():
    import requests
    
    data = request.get_json()
    user_message = data.get('message')
    
    if not user_message:
        return {'error': 'No message provided'}, 400

    api_key = ""
    url = "https://ai.hackclub.com/proxy/v1/chat/completions"
    
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
        "model": "qwen/qwen3-32b",
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

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    users_collection.update_one(
        {'username': username},
        {'$set': {
            'username': username,
            'email': email,
            'password': hashed
        }},
        upsert=True
    )
    print(f'✅ User "{username}" seeded successfully.')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)
