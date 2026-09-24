import os
import sys

import bcrypt
import mongomock
import pytest
from flask.testing import FlaskClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('MONGO_URI', 'mongodb://tests-use-mongomock')

import api.index as app_module  # noqa: E402


class CsrfClient(FlaskClient):
    """Test client that carries a CSRF token like a real browser session.

    Without this, every non-GET request in the suite would be rejected by the
    app's CSRF hook. Tests that want to *prove* the hook works use the
    `raw_client` fixture instead, which sends nothing.
    """

    def open(self, *args, **kwargs):
        if kwargs.get('method', 'GET').upper() not in ('GET', 'HEAD', 'OPTIONS'):
            headers = dict(kwargs.get('headers') or {})
            headers.setdefault(app_module.CSRF_HEADER, self.csrf_token())
            kwargs['headers'] = headers
        return super().open(*args, **kwargs)

    def csrf_token(self):
        with self.session_transaction() as sess:
            token = sess.get(app_module.CSRF_FIELD)
            if not token:
                token = 'test-csrf-token'
                sess[app_module.CSRF_FIELD] = token
        return token


@pytest.fixture
def db(monkeypatch):
    mock_db = mongomock.MongoClient()['mepham']
    monkeypatch.setattr(app_module, 'get_db', lambda: mock_db)
    monkeypatch.setattr(app_module, '_auth_indexes_ready', False, raising=False)
    monkeypatch.setattr(app_module, '_contact_indexes_ready', False, raising=False)
    monkeypatch.setattr(app_module, '_rate_limit_index_ready', False, raising=False)
    monkeypatch.setattr(app_module, '_newsletter_index_ready', False, raising=False)
    return mock_db


@pytest.fixture
def client(db):
    app_module.app.config['TESTING'] = True
    app_module.app.test_client_class = CsrfClient
    return app_module.app.test_client()


@pytest.fixture
def raw_client(db):
    """A client that never sends a CSRF token."""
    app_module.app.config['TESTING'] = True
    app_module.app.test_client_class = FlaskClient
    try:
        yield app_module.app.test_client()
    finally:
        app_module.app.test_client_class = CsrfClient


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
