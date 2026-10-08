"""Security regressions: CSRF, response headers, upload validation, limits."""
import datetime
import io

import pytest

import api.index as app_module

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 16


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


def _signed_in(c):
    """GET /login bounces a signed-in visitor and shows the form to everyone else."""
    return c.get('/login').status_code == 302


def test_signed_out_cookie_cannot_be_replayed(client, make_user):
    """A copy of the session cookie taken before sign-out must stop working."""
    make_user(username='bob', password='bob-password')
    client.post('/login', data={'username': 'bob', 'password': 'bob-password'})
    with client.session_transaction() as sess:
        stolen = dict(sess)
    client.post('/logout')
    with client.session_transaction() as sess:
        sess.update(stolen)
    assert not _signed_in(client)


def test_signing_out_one_device_keeps_the_other(client, make_user):
    make_user(username='bob', password='bob-password')
    phone = app_module.app.test_client()
    for c in (client, phone):
        c.post('/login', data={'username': 'bob', 'password': 'bob-password'})
    client.post('/logout')
    assert _signed_in(phone)


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


def test_admin_csp_is_strict_too(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    csp = client.get('/admin').headers['Content-Security-Policy']
    assert "'unsafe-inline'" not in csp.split('script-src')[1]


# --- Upload validation ----------------------------------------------------

def test_blob_path_strips_traversal():
    assert app_module.blob_path('../../etc', 'pass wd') == 'etc/pass_wd'


def test_blob_path_never_returns_empty_segment():
    assert app_module.blob_path('../', '..') == 'file/file'


@pytest.mark.parametrize('filename,ok', [
    ('robot.png', True),
    ('robot.PNG', True),
    ('robot.svg', False),
    ('robot.php', False),
    ('robot', False),
    ('robot.png.html', False),
])
def test_image_extension_check(filename, ok):
    assert (app_module.file_extension(filename) in app_module.IMAGE_EXTENSIONS) is ok


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
        stream = io.BytesIO(PNG)

    captured = {}
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda file, key: captured.setdefault('key', key))
    app_module.checked_upload(Fake(), 'teams', '../77628', stem='he/ro',
                              allowed=app_module.IMAGE_EXTENSIONS)
    assert captured['key'].startswith('teams/77628/he_ro_')
    assert captured['key'].endswith('.png')
    assert '..' not in captured['key']


def test_checked_upload_refuses_a_renamed_file(monkeypatch):
    """An HTML page renamed to .png must not reach Blob."""
    class Fake:
        filename = 'photo.png'
        stream = io.BytesIO(b'<html><script>alert(1)</script>')

    monkeypatch.setattr(app_module, 'upload_to_vercel_blob',
                        lambda *a, **k: pytest.fail('should not upload'))
    with pytest.raises(app_module.UserFacingError):
        app_module.checked_upload(Fake(), 'teams', '1', allowed=app_module.IMAGE_EXTENSIONS)


@pytest.mark.parametrize('name,head,ok', [
    ('a.png', PNG, True),
    ('a.jpg', b'\xff\xd8\xff\xe0' + b'0' * 8, True),
    ('a.gif', b'GIF89a' + b'0' * 6, True),
    ('a.webp', b'RIFF\x00\x00\x00\x00WEBP', True),
    ('a.webp', b'RIFF\x00\x00\x00\x00WAVE', False),
    ('a.jpg', PNG, False),
    ('a.stl', b'solid robot', True),
])
def test_content_signature_check(name, head, ok):
    class Fake:
        filename = name
        stream = io.BytesIO(head)

    assert app_module._content_matches(Fake(), app_module.file_extension(name)) is ok
    assert Fake.stream.tell() == 0


def test_blob_upload_ignores_the_browser_content_type(monkeypatch):
    """The stored type follows the extension, whatever the browser claimed."""
    sent = {}

    class Response:
        status_code = 200

        def json(self):
            return {'url': 'https://x.public.blob.vercel-storage.com/a.png'}

    def fake_put(url, headers, data, timeout):
        sent.update(headers=headers, timeout=timeout)
        return Response()

    class Fake:
        filename = 'a.png'
        content_type = 'text/html'

        def read(self):
            return PNG

    monkeypatch.setattr(app_module, 'BLOB_READ_WRITE_TOKEN', 'token')
    monkeypatch.setattr(app_module.requests, 'put', fake_put)
    app_module.upload_to_vercel_blob(Fake(), 'teams/1/a.png')
    assert sent['headers']['Content-Type'] == 'image/png'
    assert sent['timeout']


def test_blob_delete_has_a_timeout(monkeypatch):
    sent = {}

    class Response:
        status_code = 200

    def fake_delete(url, headers, timeout):
        sent['timeout'] = timeout
        return Response()

    monkeypatch.setattr(app_module, 'BLOB_READ_WRITE_TOKEN', 'token')
    monkeypatch.setattr(app_module.requests, 'delete', fake_delete)
    app_module.delete_from_vercel_blob('https://x.public.blob.vercel-storage.com/a.png')
    assert sent['timeout']


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
    # A view that queries the database directly, so the failure propagates.
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


def test_csp_lets_the_stl_viewer_fetch_from_blob(client):
    csp = client.get('/contact').headers['Content-Security-Policy']
    connect_src = csp.split('connect-src')[1].split(';')[0]
    assert "'self'" in connect_src
    assert 'https://*.public.blob.vercel-storage.com' in connect_src
    # Nothing broader than the Blob store.
    assert connect_src.split() == ["'self'", 'https://*.public.blob.vercel-storage.com']


@pytest.mark.parametrize('path', ['/notebook', '/resources', '/glossary'])
def test_member_pages_run_the_strict_csp(client, make_user, path):
    make_user(username='mem', password='mem-password', role='member')
    client.post('/login', data={'username': 'mem', 'password': 'mem-password'})
    csp = client.get(path).headers['Content-Security-Policy']
    assert "'unsafe-inline'" not in csp.split('script-src')[1]
