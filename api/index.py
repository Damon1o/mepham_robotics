from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return 'Flask is working on Vercel!', 200

@app.route('/test')
def test():
    return 'Test route working!', 200
