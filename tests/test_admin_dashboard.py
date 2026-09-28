"""Admin dashboard: sponsor saves and the page's own markup."""
import io
import re

import pytest

import api.index as app_module


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def uploads(monkeypatch):
    """Capture blob uploads instead of calling Vercel."""
    keys = []

    def _upload(file, key):
        keys.append(key)
        return f'https://blob.example/{key}'

    monkeypatch.setattr(app_module, 'upload_to_vercel_blob', _upload)
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', lambda url: None)
    return keys


# --- Sponsor saves ------------------------------------------------------------

def test_sponsor_create_then_update(admin, db, uploads):
    admin.post('/admin/save-sponsor', data={'name': 'Acme', 'website': 'https://acme.example',
                                            'level': 'Gold'})
    sponsor = db['sponsors'].find_one({'name': 'Acme'})
    assert sponsor['level'] == 'Gold'

    admin.post('/admin/save-sponsor', data={
        'sponsor_id': str(sponsor['_id']), 'name': 'Acme', 'website': 'https://acme.example',
        'level': 'Platinum', 'logo': (io.BytesIO(b'img'), 'logo.png'),
    }, content_type='multipart/form-data')
    assert db['sponsors'].count_documents({}) == 1
    updated = db['sponsors'].find_one({'_id': sponsor['_id']})
    assert updated['level'] == 'Platinum'
    assert updated['logo'].startswith('https://blob.example/sponsors/Acme_')


# --- Dashboard markup -----------------------------------------------------------

def test_dashboard_has_no_inline_script(admin, db):
    db['teams'].insert_one({'team_number': '77628D', 'members': [], 'goals': []})
    db['users'].insert_one({'username': 'bob', 'role': 'member', 'password': b'x'})
    page = admin.get('/admin').get_data(as_text=True)
    assert not re.search(r'\son(click|change|submit|keyup|input)=', page)
    for attributes, body in re.findall(r'<script\b([^>]*)>(.*?)</script>', page, re.S):
        # JSON data islands are inert under CSP; executable inline script is not.
        assert 'src=' in attributes or 'application/json' in attributes or not body.strip()


def test_dashboard_edit_buttons_carry_their_update_urls(admin, db):
    comp = db['competitions'].insert_one({'name': 'Q', 'location': 'L',
                                          'date': app_module._utcnow()}).inserted_id
    page = admin.get('/admin').get_data(as_text=True)
    # Events are edited in place now; each row carries the id its autosave posts to.
    assert f'data-event-id="{comp}"' in page
    assert 'data-update-url="/admin/update-user/' in page


def test_dashboard_controls_are_labelled(admin, db):
    page = admin.get('/admin').get_data(as_text=True)
    assert not re.search(r'<label>', page), 'a <label> without for= remains'
    assert 'aria-live="polite"' in page


def test_admin_js_builds_rows_without_html_strings():
    import pathlib
    source = (pathlib.Path(__file__).resolve().parent.parent / 'static/js/admin.js').read_text(encoding='utf-8')
    # Only the static help copy may be assigned as HTML.
    assignments = re.findall(r'\.innerHTML\s*=\s*([^;\n]+)', source)
    assert assignments == ['html'], assignments


# --- Member photos ------------------------------------------------------------

@pytest.mark.parametrize('stored,expected', [
    ('static/assets/profile/base.png', '/static/assets/other/base.png'),  # never existed
    ('', '/static/assets/other/base.png'),
    (None, '/static/assets/other/base.png'),
    ('static/assets/profile/damon.png', '/static/assets/profile/damon.png'),
    ('https://blob.example/a.png', 'https://blob.example/a.png'),
])
def test_image_urls_fall_back_to_a_real_placeholder(client, stored, expected):
    with app_module.app.test_request_context('/'):
        assert app_module.get_image_url(stored).split('?')[0] == expected
