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

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        mongo_uri = os.getenv('MONGO_URI')
        if not mongo_uri:
            raise RuntimeError("MONGO_URI is not set!")
        _client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        _db = _client['mepham']
    return _db

@app.route('/')
def index():
    try:
        db = get_db()
        # Just ping the DB to confirm connection
        db.client.admin.command('ping')
        return 'Step 4 OK - MongoDB connected!', 200
    except Exception as e:
        return f'Step 4 FAILED - MongoDB error: {str(e)}', 500
