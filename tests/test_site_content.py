"""Admin-editable site content (api/site_content.py and the /admin/site editor)."""
import io

import pytest

import api.index as app_module
from api import site_content


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def save(client, key, value):
    return client.post('/admin/api/site', json={'key': key, 'value': value})


# --- Defaults reproduce the site as it was -------------------------------------------------

@pytest.mark.parametrize('path,expected', [
    ('/', ['Mepham Robotics', 'Build. Code. Compete.', 'Learn More', 'Next Competition In:', 'Team Gallery',
           'Want to Support Us?']),
    ('/about', ['Who We Are', 'student-led robotics club', 'What We Stand For', 'Perseverance', 'Team Moments',
                'Take Safety Quiz']),
    ('/contact', ['Talk to the builders.', 'Tuesday &amp; Friday · 3:00–5:00 PM', 'Room LL01, Wellington C. Mepham HS',
                  'damlin@bmchsd.com', 'How do I join the robotics club?', 'href="/donate"']),
    ('/donate', ['Support Our Mission', 'Bronze Sponsor', 'Logo on robot', 'Buys a VEX motor',
                 'Become a Corporate Sponsor']),
    ('/achievements', ['All-Time VEX V5 Competition Awards']),
])
def test_defaults_match_the_original_copy(client, path, expected):
    page = client.get(path).get_data(as_text=True)
    for text in expected:
        assert text in page, (path, text)


def test_placeholder_social_links_are_gone(client):
    page = client.get('/').get_data(as_text=True)
    assert 'href="https://facebook.com"' not in page and 'href="https://x.com"' not in page
    assert 'https://instagram.com/mephamrobotics' in page


def test_copyright_year_follows_the_clock(client):
    assert f'© {app_module.club_now().year}' in client.get('/').get_data(as_text=True).replace('&copy;', '©')


# --- Editing ---------------------------------------------------------------------------------

def test_saving_changes_the_page_and_marks_it_custom(admin, db):
    resp = save(admin, 'home.hero_title', 'Mepham Robotics 2026')
    assert resp.get_json() == {'ok': True, 'value': 'Mepham Robotics 2026', 'custom': True}
    assert '<h1>Mepham Robotics 2026</h1>' in admin.get('/').get_data(as_text=True)
    assert db['activities'].find_one({'type': 'site_edit'})['details']['to'] == 'Mepham Robotics 2026'


def test_saving_the_default_removes_the_override(admin, db):
    save(admin, 'home.hero_title', 'Changed')
    save(admin, 'home.hero_title', 'Mepham Robotics')
    doc = db['site_metadata'].find_one({'_id': 'site_content'})
    assert 'hero_title' not in (doc['values'].get('home') or {})


def test_reset_puts_the_original_back(admin, db):
    save(admin, 'contact.form_title', 'Say hi')
    resp = admin.post('/admin/api/site/reset', json={'key': 'contact.form_title'})
    assert resp.get_json()['value'] == 'Talk to the builders.'
    assert 'Talk to the builders.' in admin.get('/contact').get_data(as_text=True)


@pytest.mark.parametrize('key,value', [
    ('home.hero_title', ''),                                  # required
    ('home.hero_title', 'x' * 41),                            # too long
    ('home.cta_primary_url', 'javascript:alert(1)'),          # unsafe link
    ('home.countdown_mode', 'sometimes'),                     # not a choice
    ('meeting.start', '25:00'),
    ('meeting.days', [1, 9]),
    ('general.contact_email', 'not-an-email'),
    ('social.links', [{'platform': 'instagram', 'url': 'https://evil.example/x'}]),
    ('social.links', [{'platform': 'myspace', 'url': 'https://myspace.com/x'}]),
    ('home.hero_image', {'src': 'javascript:alert(1)', 'width': 10, 'height': 10}),
    ('home.hero_image', {'src': "https://blob.example/a.png') ; background:url('x", 'width': 10, 'height': 10}),
    ('donate.givebutter_id', 'abc"><script>'),
    ('nope.field', 'x'),
    ('announcement.enabled', 'yes'),
])
def test_bad_values_are_rejected(admin, key, value):
    resp = save(admin, key, value)
    assert resp.status_code == 400 and resp.is_json


def test_editing_needs_an_admin(client, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    assert save(client, 'home.hero_title', 'Hacked').status_code == 403
    assert client.get('/admin/site').status_code == 302


def test_editor_page_renders(admin):
    page = admin.get('/admin/site').get_data(as_text=True)
    assert 'Site editor' in page and 'data-key="announcement.text"' in page and 'data-key="gallery.photos"' in page


# --- Rich text is safe ----------------------------------------------------------------------------

def test_rich_text_escapes_html_and_filters_links():
    html = str(site_content.rich('**Hi** <script>x</script> [ok](/contact) [bad](javascript:alert(1))'))
    assert '<strong>Hi</strong>' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '<a href="/contact">ok</a>' in html
    assert 'javascript:' not in html.split('bad')[0]


def test_external_rich_links_open_safely():
    assert 'rel="noopener"' in str(site_content.rich('[x](https://example.com)'))


# --- Features that ride on it -----------------------------------------------------------------------

def test_announcement_shows_only_inside_its_window(admin, db):
    save(admin, 'announcement.text', 'Tryouts **Tuesday**')
    assert 'site-announcement' not in admin.get('/').get_data(as_text=True)
    save(admin, 'announcement.enabled', True)
    page = admin.get('/about').get_data(as_text=True)
    assert 'site-announcement--info' in page and '<strong>Tuesday</strong>' in page
    save(admin, 'announcement.ends', '2000-01-01T00:00')
    assert 'site-announcement' not in admin.get('/').get_data(as_text=True)


def test_sections_can_be_hidden(admin):
    save(admin, 'home.show_gallery', False)
    save(admin, 'home.countdown_mode', 'never')
    page = admin.get('/').get_data(as_text=True)
    assert 'photo-carousel-section' not in page and 'countdown-section' not in page


def test_countdown_hides_itself_with_no_events(admin):
    save(admin, 'home.countdown_mode', 'scheduled')
    assert 'countdown-section' not in admin.get('/').get_data(as_text=True)


def test_meeting_schedule_feeds_the_contact_page(admin):
    save(admin, 'meeting.days', [1, 3])
    save(admin, 'meeting.start', '14:30')
    page = admin.get('/contact').get_data(as_text=True)
    assert 'Monday &amp; Wednesday · 2:30–5:00 PM' in page
    assert 'data-days="1,3"' in page and 'data-start="14:30"' in page


def test_givebutter_id_can_be_set_from_the_admin(admin):
    save(admin, 'donate.givebutter_id', 'abc123')
    assert 'givebutter.com/embed/c/abc123' in admin.get('/donate').get_data(as_text=True)


def test_club_email_reaches_both_pages_once_set(admin):
    save(admin, 'general.contact_email', 'club@example.com')
    assert 'mailto:club@example.com' in admin.get('/contact').get_data(as_text=True)
    assert 'club@example.com' in admin.get('/donate').get_data(as_text=True)


def test_hero_photo_override_uses_a_custom_property(admin):
    save(admin, 'about.hero_image', {'src': 'https://blob.example/site/hero.webp', 'width': 1600, 'height': 900})
    page = admin.get('/about').get_data(as_text=True)
    assert 'has-custom-hero' in page and "--hero-image: url('https://blob.example/site/hero.webp')" in page


def test_gallery_can_mix_built_in_and_uploaded_photos(admin):
    save(admin, 'gallery.photos', [
        {'image': {'src': 'https://blob.example/site/new.webp', 'width': 1200, 'height': 800}, 'alt': 'Robot on field'},
        {'image': {'key': 'photos/carousel2'}, 'alt': 'Build night'},
    ])
    page = admin.get('/').get_data(as_text=True)
    assert 'src="https://blob.example/site/new.webp" width="1200" height="800" alt="Robot on field"' in page
    assert 'Build night' in page and 'Team photo 1' not in page


def test_image_upload_stores_the_file_and_its_size(admin, monkeypatch):
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob', lambda file, key: f'https://blob.example/{key}')
    resp = admin.post('/admin/api/site/image', data={'file': (io.BytesIO(b'img'), 'photo.webp'),
                                                     'width': '1600', 'height': '900'},
                      content_type='multipart/form-data')
    body = resp.get_json()
    assert resp.status_code == 200 and body['image']['width'] == 1600
    assert body['image']['src'].startswith('https://blob.example/site/image_')
    bad = admin.post('/admin/api/site/image', data={'file': (io.BytesIO(b'<svg>'), 'x.svg'), 'width': '1', 'height': '1'},
                     content_type='multipart/form-data')
    assert bad.status_code == 400


def test_replacing_an_image_deletes_the_old_upload(admin, monkeypatch):
    deleted = []
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    save(admin, 'home.hero_image', {'src': 'https://blob.example/site/a.webp', 'width': 10, 'height': 10})
    save(admin, 'home.hero_image', {'src': 'https://blob.example/site/b.webp', 'width': 10, 'height': 10})
    assert deleted == ['https://blob.example/site/a.webp']


def test_assistant_can_be_hidden(admin):
    save(admin, 'assistant.enabled', False)
    assert 'custom-chatbot-container' not in admin.get('/').get_data(as_text=True)


def test_assistant_prompt_includes_admin_facts(admin, monkeypatch):
    save(admin, 'assistant.knowledge', 'Tryouts are on Sept 30.')
    with app_module.app.test_request_context('/'):
        prompt = app_module.chat_system_prompt()
    assert 'Tryouts are on Sept 30.' in prompt and 'Tuesday & Friday' in prompt


def test_database_errors_fall_back_to_defaults(client, monkeypatch):
    def boom():
        raise RuntimeError('db down')
    monkeypatch.setattr(app_module, '_site_overrides', boom)
    page = client.get('/').get_data(as_text=True)
    assert 'Mepham Robotics' in page


def test_search_index_comes_from_the_server(client, db):
    db['teams'].insert_one({'team_number': '1A', 'nickname': 'Hydra'})
    page = client.get('/').get_data(as_text=True)
    index = page.split('id="search-pages">')[1].split('</script>')[0]
    assert '/team/1A' in index and 'Hydra' in index
    assert '77628D' not in index
    assert 'Glossary' not in index          # member pages only for signed-in visitors
