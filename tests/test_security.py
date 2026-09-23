"""Security regressions: CSRF, response headers, upload validation, limits."""
import datetime

import pytest

import api.index as app_module


# --- CSRF -----------------------------------------------------------------

def test_post_without_csrf_token_is_rejected(raw_client):
    resp = raw_client.post('/api/contact', json={
        'name': 'Mallory', 'email': 'm@example.com', 'message': 'hi'})
    assert resp.status_code == 400
    assert resp.get_json()['error']


def test_html_post_without_csrf_token_renders_400_page(raw_client):
    resp = raw_client.post('/login', data={'username': 'a', 'password': 'b'})
    assert resp.status_code == 400
    assert b'400' in resp.data


def test_post_with_wrong_csrf_token_is_rejected(client):
    resp = client.post('/api/contact',
                       headers={app_module.CSRF_HEADER: 'not-the-token'},
                       json={'name': 'Mallory', 'email': 'm@example.com', 'message': 'hi'})
    assert resp.status_code == 400


def test_csrf_token_is_rendered_into_pages(client):
    page = client.get('/contact').get_data(as_text=True)
    assert 'name="csrf-token"' in page


def test_form_field_carries_csrf_token(client, db):
    page = client.get('/login').get_data(as_text=True)
    assert 'name="_csrf_token"' in page


def test_logout_rejects_get(client):
    assert client.get('/logout').status_code == 405


def test_logout_clears_session_on_post(client, make_user):
    make_user(username='bob', password='bob-password')
    client.post('/login', data={'username': 'bob', 'password': 'bob-password'})
    client.post('/logout')
    with client.session_transaction() as sess:
        assert 'user' not in sess


# --- Response headers -----------------------------------------------------

@pytest.mark.parametrize('header,expected', [
    ('X-Content-Type-Options', 'nosniff'),
    ('X-Frame-Options', 'DENY'),
    ('Referrer-Policy', 'strict-origin-when-cross-origin'),
])
def test_security_headers_present(client, header, expected):
    assert client.get('/contact').headers[header] == expected


def test_public_csp_forbids_inline_script(client):
    csp = client.get('/contact').headers['Content-Security-Policy']
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split('script-src')[1]
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_admin_csp_allows_its_inline_handlers(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    csp = client.get('/admin').headers['Content-Security-Policy']
    assert "'unsafe-inline'" in csp.split('script-src')[1]


# --- Upload validation ----------------------------------------------------

def test_blob_path_strips_traversal():
    assert app_module.blob_path('../../etc', 'pass wd') == 'etc/pass_wd'


def test_blob_path_never_returns_empty_segment():
    assert app_module.blob_path('../', '..') == 'file/file'


@pytest.mark.parametrize('filename,ok', [
    ('robot.png', True),
    ('robot.PNG', True),
    ('robot.svg', True),
    ('robot.php', False),
    ('robot', False),
    ('robot.png.html', False),
])
def test_allowed_file(filename, ok):
    assert app_module.allowed_file(filename, app_module.IMAGE_EXTENSIONS) is ok


def test_checked_upload_rejects_bad_extension(monkeypatch):
    class Fake:
        filename = 'payload.html'

    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda *a, **k: pytest.fail('should not upload'))
    with pytest.raises(ValueError):
        app_module.checked_upload(Fake(), 'teams', '77628',
                                  allowed=app_module.IMAGE_EXTENSIONS)


def test_checked_upload_uses_a_safe_key(monkeypatch):
    class Fake:
        filename = 'hero.PNG'

    captured = {}
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda file, key: captured.setdefault('key', key))
    app_module.checked_upload(Fake(), 'teams', '../77628', stem='he/ro',
                              allowed=app_module.IMAGE_EXTENSIONS)
    assert captured['key'].startswith('teams/77628/he_ro_')
    assert captured['key'].endswith('.png')
    assert '..' not in captured['key']


def test_upload_size_is_capped():
    assert app_module.app.config['MAX_CONTENT_LENGTH'] == app_module.MAX_UPLOAD_BYTES


# --- Login lockout --------------------------------------------------------

def test_account_locks_across_rotating_ips(client, make_user):
    make_user(username='carol', password='carol-password')
    for i in range(app_module.LOGIN_MAX_ACCOUNT_ATTEMPTS):
        client.post('/login', data={'username': 'carol', 'password': 'wrong'},
                    headers={'X-Forwarded-For': f'10.0.0.{i}'})
    # A fresh address still gets the lockout, and even the right password fails.
    resp = client.post('/login', data={'username': 'carol', 'password': 'carol-password'},
                       headers={'X-Forwarded-For': '10.9.9.9'})
    assert resp.status_code == 429


def test_single_ip_still_locks_quickly(client, make_user):
    make_user(username='dave', password='dave-password')
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS):
        client.post('/login', data={'username': 'dave', 'password': 'wrong'},
                    headers={'X-Forwarded-For': '10.1.1.1'})
    resp = client.post('/login', data={'username': 'dave', 'password': 'dave-password'},
                       headers={'X-Forwarded-For': '10.1.1.1'})
    assert resp.status_code == 429


# --- Rate limiter ---------------------------------------------------------

def test_rate_limit_allows_then_blocks(client, db):
    window = datetime.timedelta(minutes=5)
    with app_module.app.test_request_context('/'):
        assert app_module.rate_limit('t', '1.2.3.4', 2, window) == 0
        assert app_module.rate_limit('t', '1.2.3.4', 2, window) == 0
        assert app_module.rate_limit('t', '1.2.3.4', 2, window) > 0
        # A different address has its own budget.
        assert app_module.rate_limit('t', '5.6.7.8', 2, window) == 0


# --- Error handling -------------------------------------------------------

def test_unexpected_error_returns_500_status(client, monkeypatch):
    monkeypatch.setattr(app_module, 'get_db',
                        lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.get('/contact?crash=1')
    # /contact itself needs no database, so force the failure through a view
    # that does.
    resp = client.get('/team/77628')
    assert resp.status_code == 500


def test_404_still_returns_404(client):
    assert client.get('/definitely-not-a-page').status_code == 404


def test_healthz_reports_up(client):
    body = client.get('/healthz').get_json()
    assert body['status'] == 'ok'


def test_csp_allows_the_contact_map_embed(client):
    csp = client.get('/contact').headers['Content-Security-Policy']
    frame_src = csp.split('frame-src')[1].split(';')[0]
    assert 'https://www.google.com' in frame_src
    assert 'https://givebutter.com' in frame_src


@pytest.mark.parametrize('path', ['/notebook', '/resources', '/glossary'])
def test_member_pages_run_the_strict_csp(client, make_user, path):
    make_user(username='mem', password='mem-password', role='member')
    client.post('/login', data={'username': 'mem', 'password': 'mem-password'})
    csp = client.get(path).headers['Content-Security-Policy']
    assert "'unsafe-inline'" not in csp.split('script-src')[1]
