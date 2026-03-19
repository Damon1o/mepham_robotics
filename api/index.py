import os
import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-key')

@app.route('/')
def index():
    return 'Step 1 OK - Flask + werkzeug imports work!', 200
