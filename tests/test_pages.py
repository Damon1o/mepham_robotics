"""Every page renders, and the site-wide chrome is actually wired up."""
import re

import pytest

PUBLIC_PAGES = ['/', '/about', '/achievements', '/contact', '/donate',
                '/safety-quiz', '/privacy', '/credits']
MEMBER_PAGES = ['/resources', '/glossary', '/branding', '/standards', '/notebook']


@pytest.fixture
def signed_in(client, make_user):
    def _sign_in(role='member'):
        make_user(username='pat', password='pat-password', role=role)
        client.post('/login', data={'username': 'pat', 'password': 'pat-password'})
        return client
    return _sign_in


@pytest.mark.parametrize('path', PUBLIC_PAGES)
def test_public_page_renders(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize('path', MEMBER_PAGES)
def test_member_page_renders_for_members(signed_in, path):
    assert signed_in('member').get(path).status_code == 200


@pytest.mark.parametrize('path', MEMBER_PAGES)
def test_member_page_redirects_anonymous(client, path):
    resp = client.get(path)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_admin_dashboard_renders(signed_in):
    assert signed_in('admin').get('/admin').status_code == 200


def test_every_page_has_the_skip_link_and_main_landmark(client):
    page = client.get('/').get_data(as_text=True)
    assert 'class="skip-link"' in page
    assert 'id="main-content"' in page


def test_no_inline_event_handlers_on_public_pages(client):
    """Public pages run under a CSP with no 'unsafe-inline' script source, so
    an onclick= attribute here would silently stop working."""
    for path in PUBLIC_PAGES:
        page = client.get(path).get_data(as_text=True)
        for attribute in ('onclick=', 'onsubmit=', 'onchange=', 'onerror='):
            assert attribute not in page, f'{attribute} found on {path}'


def test_no_inline_script_blocks_on_public_pages(client, db):
    """Same reason: an inline <script> would be dropped by the CSP."""
    db['teams'].insert_one({'team_number': '77628D', 'members': [], 'goals': []})
    for path in PUBLIC_PAGES + ['/login', '/team/77628D']:
        page = client.get(path).get_data(as_text=True)
        for block in re.findall(r'<script\b([^>]*)>(.*?)</script>', page, re.S):
            attributes, body = block
            assert 'src=' in attributes or not body.strip(), \
                f'inline script on {path}: {body.strip()[:60]}'


def test_theme_toggle_is_present(client):
    page = client.get('/').get_data(as_text=True)
    assert 'data-theme-toggle' in page
    assert 'js/theme.js' in page


def test_newsletter_form_posts_to_the_site(client):
    page = client.get('/').get_data(as_text=True)
    assert 'footer-newsletter-form' in page
    assert 'docs.google.com/forms' not in page


def test_sitemap_lists_public_pages(client, db):
    db['teams'].insert_one({'team_number': '77628D'})
    body = client.get('/sitemap.xml').get_data(as_text=True)
    for path in ('/about', '/contact', '/safety-quiz', '/team/77628D'):
        assert path in body


def test_robots_blocks_private_areas(client):
    body = client.get('/robots.txt').get_data(as_text=True)
    for rule in ('Disallow: /admin', 'Disallow: /api/', 'Disallow: /unsubscribe/'):
        assert rule in body


def test_static_assets_are_cached_hard(client):
    resp = client.get('/static/js/theme.js')
    assert resp.status_code == 200
    assert 'immutable' in resp.headers['Cache-Control']


def test_static_urls_carry_a_version(client):
    """`immutable` caching is only safe if the URL changes when the file does."""
    page = client.get('/').get_data(as_text=True)
    stylesheets = re.findall(r'href="(/static/css/[^"]+)"', page)
    assert stylesheets
    for href in stylesheets:
        assert '?v=' in href, href


def test_static_version_changes_with_the_file(tmp_path, monkeypatch):
    import api.index as module
    module._static_versions.clear()
    first = module._static_version('js/theme.js')
    module._static_versions.clear()
    monkeypatch.setattr(module.os.path, 'getmtime', lambda p: 1234567890)
    assert module._static_version('js/theme.js') != first


def test_missing_static_file_still_builds_a_url(client):
    import api.index as module
    module._static_versions.clear()
    assert module._static_version('does/not/exist.css') == '0'


# --- Runtime-injected handlers --------------------------------------------
# The inline-handler checks above only see server-rendered HTML. A handler
# written into an innerHTML template string in the JS bundle is blocked by the
# CSP just the same, which is how the safety quiz's buttons died unnoticed.
JS_BUNDLES_UNDER_STRICT_CSP = ['static/js/script.js', 'static/js/login.js',
                               'static/js/theme.js', 'static/js/admin.js',
                               'static/js/team-editor.js']


@pytest.mark.parametrize('bundle', JS_BUNDLES_UNDER_STRICT_CSP)
def test_js_bundles_inject_no_inline_handlers(bundle):
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    source = (root / bundle).read_text(encoding='utf-8')
    hits = re.findall(r'\son(?:click|change|submit|input|keyup|keydown|load|error)\s*=\s*["\']', source)
    assert not hits, f'{bundle} injects inline handlers: {hits}'


@pytest.mark.parametrize('path', MEMBER_PAGES)
def test_member_pages_have_no_inline_script(signed_in, path):
    page = signed_in('member').get(path).get_data(as_text=True)
    for attribute in ('onclick=', 'onsubmit=', 'onchange=', 'onerror='):
        assert attribute not in page, f'{attribute} found on {path}'
    for attributes, body in re.findall(r'<script\b([^>]*)>(.*?)</script>', page, re.S):
        assert 'src=' in attributes or not body.strip(), f'inline script on {path}'


def test_safety_quiz_breadcrumb_stays_public(client):
    page = client.get('/safety-quiz').get_data(as_text=True)
    assert 'href="/resources' not in page


def test_notebook_faq_is_accessible(signed_in):
    page = signed_in('member').get('/notebook').get_data(as_text=True)
    assert 'aria-controls="notebook-template-answer"' in page
    assert 'id="notebook-template-answer"' in page


def test_side_nav_has_no_theme_or_search_controls(client):
    page = client.get('/').get_data(as_text=True)
    nav = page[page.index('id="mySidenav"'):page.index('class="search-overlay"')]
    assert 'data-theme-toggle' not in nav
    assert 'nav-search-btn' not in nav


def test_theme_toggle_lives_in_the_footer(client):
    page = client.get('/').get_data(as_text=True)
    footer = page[page.index('<footer'):page.index('</footer>')]
    assert 'data-theme-toggle' in footer
