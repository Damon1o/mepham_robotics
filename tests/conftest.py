import os
import sys

import bcrypt
import mongomock
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('MONGO_URI', 'mongodb://tests-use-mongomock')

import api.index as app_module  # noqa: E402


@pytest.fixture
def db(monkeypatch):
    mock_db = mongomock.MongoClient()['mepham']
    monkeypatch.setattr(app_module, 'get_db', lambda: mock_db)
    monkeypatch.setattr(app_module, '_auth_indexes_ready', False, raising=False)
    return mock_db


@pytest.fixture
def client(db):
    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


@pytest.fixture
def make_user(db):
    def _make(username='alice', password='correct-horse', email='alice@example.com', role='member'):
        doc = {
            'username': username,
            'email': email,
            'password': bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(4)),
            'role': role,
        }
        doc['_id'] = db['users'].insert_one(doc).inserted_id
        return doc
    return _make
