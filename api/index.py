import os
import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import bcrypt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-key')

@app.route('/')
def index():
    return 'Step 2 OK - bcrypt + dotenv imports work!', 200
