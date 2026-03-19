import os
import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import bcrypt
from dotenv import load_dotenv
from bson import ObjectId
from pymongo import MongoClient

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-fallback-key')

@app.route('/')
def index():
    return 'Step 3 OK - pymongo + bson imports work!', 200
