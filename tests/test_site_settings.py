"""Site settings: placeholders, warnings, image provenance, history and draft mode."""
import datetime
import io

import pytest

import api.index as app_module
from api import site_content


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


@pytest.fixture
def visitor(db):
    return app_module.app.test_client()


def save(client, key, value):
    return client.post('/admin/api/site', json={'key': key, 'value': value})


def draft(client, action):
    return client.post('/admin/api/site/draft', json={'action': action})


def page(client, path):
    return client.get(path).get_data(as_text=True)


# --- Placeholders ------------------------------------------------------------------------

def test_meeting_details_reach_the_copy_that_names_them(admin):
    save(admin, 'meeting.room', 'Room 214')
    save(admin, 'meeting.days', [1, 3])
    contact = page(admin, '/contact')
    assert 'Room 214, after the last bell.' in contact
    assert 'during any Monday or Wednesday meeting' in contact
    assert 'We meet every Monday &amp; Wednesday from 3:00–5:00 PM in Room 214' in contact
    assert 'LL01' not in contact.split('<main')[1].split('</main>')[0]


def test_the_club_tagline_fills_the_others(admin, db):
    save(admin, 'general.tagline', 'Gears and grit.')
    assert '<p>Gears and grit.</p>' in page(admin, '/')
    db['teams'].insert_one({'team_number': '1A'})
    assert 'Gears and grit.' in page(admin, '/team/1A')


def test_the_editor_shows_placeholders_as_typed(admin):
    editor = page(admin, '/admin/site')
    assert 'value="{room}, after the last bell."' in editor and '{days_or}' in editor


def test_unknown_braces_are_left_alone():
    values = site_content.merged({'contact': {'form_title': 'Say {hello}'}})
    assert site_content.filled(values)['contact']['form_title'] == 'Say {hello}'


def test_sponsor_levels_default_in_order():
    tiers = site_content.SECTION_MAP['donate'].by_key['tiers'].default
    assert [t['colour'] for t in tiers] == ['bronze', 'silver', 'gold']


# --- Checks across fields ------------------------------------------------------------------

def test_a_fundraiser_cannot_end_before_it_starts(admin):
    row = {'name': 'Bake sale', 'starts': '2026-11-02T10:00', 'ends': '2026-11-01T10:00'}
    resp = save(admin, 'fundraisers.entries', [row])
    assert resp.status_code == 400 and 'end must come after the start' in resp.get_json()['error']


def test_announcement_window_backwards_warns_but_saves(admin):
    save(admin, 'announcement.starts', '2026-11-02T10:00')
    resp = save(admin, 'announcement.ends', '2026-11-01T10:00')
    assert resp.status_code == 200 and 'never show' in resp.get_json()['warning']


def test_meeting_ending_before_it_starts_warns(admin):
    body = save(admin, 'meeting.end', '14:00').get_json()
    assert body['ok'] and 'end before they start' in body['warning']
    assert 'warning' not in save(admin, 'meeting.end', '18:00').get_json()


# --- Images ----------------------------------------------------------------------------------

def test_only_images_uploaded_here_can_be_used(admin, db):
    image = {'src': 'https://tracker.example/pixel.png', 'width': 1, 'height': 1}
    resp = save(admin, 'home.hero_image', image)
    assert resp.status_code == 400 and 'not uploaded here' in resp.get_json()['error']


def upload(client):
    return client.post('/admin/api/site/image', data={'file': (io.BytesIO(b'img'), 'photo.webp'),
                                                      'width': '10', 'height': '10'},
                       content_type='multipart/form-data').get_json()['image']


def test_uploads_nobody_used_are_swept(admin, db, monkeypatch):
    keys = iter(range(100))
    monkeypatch.setattr(app_module, 'upload_to_vercel_blob', lambda file, key: f'https://blob.example/{next(keys)}')
    deleted = []
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    used, unused = upload(admin), upload(admin)
    assert save(admin, 'home.hero_image', used).status_code == 200
    old = app_module._utcnow() - datetime.timedelta(days=2)
    db['site_uploads'].update_many({}, {'$set': {'at': old}})
    upload(admin)
    assert deleted == [unused['src']]
    assert db['site_uploads'].find_one({'_id': used['src']})


# --- History -------------------------------------------------------------------------------------

def test_earlier_values_can_be_put_back(admin):
    save(admin, 'home.hero_title', 'First')
    save(admin, 'home.hero_title', 'Second')
    items = admin.get('/admin/api/site/history?key=home.hero_title').get_json()['items']
    assert [i['value'] for i in items] == ['First', 'Mepham Robotics']
    assert items[1]['original'] and items[0]['by'] == 'root'
    assert save(admin, 'home.hero_title', items[0]['value']).get_json()['value'] == 'First'


def test_history_keeps_the_last_few(admin, db):
    for n in range(app_module.SITE_HISTORY_KEEP + 5):
        save(admin, 'home.hero_title', f'Title {n}')
    assert db['site_history'].count_documents({'key': 'home.hero_title'}) == app_module.SITE_HISTORY_KEEP


def test_history_needs_access(client, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    assert client.get('/admin/api/site/history?key=home.hero_title').status_code == 403


# --- Draft mode -----------------------------------------------------------------------------------

def test_drafts_stay_private_until_published(admin, visitor, db):
    draft(admin, 'on')
    body = save(admin, 'home.hero_title', 'Draft title').get_json()
    assert body['draft'] and body['custom']
    assert '<h1>Draft title</h1>' not in page(visitor, '/')
    preview = admin.get('/')
    assert '<h1>Draft title</h1>' in preview.get_data(as_text=True)
    assert preview.headers['Cache-Control'] == 'private, no-store'
    assert 'data-key="home.hero_title"' in page(admin, '/admin/site')
    assert not db['activities'].find_one({'type': 'site_edit'})

    assert draft(admin, 'publish').get_json()['published'] == 1
    assert '<h1>Draft title</h1>' in page(visitor, '/')
    assert db['activities'].find_one({'type': 'site_edit'})
    assert 'draft' not in db['site_metadata'].find_one({'_id': 'site_content'})


def test_a_draft_can_be_thrown_away(admin, visitor, db):
    draft(admin, 'on')
    save(admin, 'home.hero_title', 'Never mind')
    draft(admin, 'discard')
    assert '<h1>Never mind</h1>' not in page(admin, '/')
    assert app_module._site_overrides() == {}


def test_reset_in_a_draft_waits_for_publish(admin, visitor):
    save(admin, 'home.hero_title', 'Live title')
    draft(admin, 'on')
    admin.post('/admin/api/site/reset', json={'key': 'home.hero_title'})
    assert '<h1>Live title</h1>' in page(visitor, '/')
    draft(admin, 'publish')
    assert '<h1>Mepham Robotics</h1>' in page(visitor, '/')


def test_draft_mode_is_for_admins(client, make_user):
    make_user(username='ed', password='editor-password', email='ed@example.com', role='editor')
    client.post('/login', data={'username': 'ed', 'password': 'editor-password'})
    assert draft(client, 'on').status_code == 403


def test_hint_links_point_at_the_dashboard(admin):
    assert 'href="/admin#awards"' in page(admin, '/admin/site')
