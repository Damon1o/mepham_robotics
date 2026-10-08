"""Alumni page (/alumni): the wall, its numbers, the update form and where the page is linked."""
import pytest

from api import site_content


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def alum(**overrides):
    row = {'name': 'Ada Lovelace', 'class_year': 2024, 'path': 'computing', 'school': 'Stony Brook University',
           'study': 'Computer Science', 'now': '', 'team': 'Programmer', 'quote': '', 'photo': None, 'link': '',
           'hidden': False}
    row.update(overrides)
    return row


def save(client, value):
    return client.post('/admin/api/site', json={'key': 'alumni.people', 'value': value})


# --- The numbers ----------------------------------------------------------------------------

def test_view_groups_newest_class_first_and_counts():
    view = site_content.alumni_view([
        alum(),
        alum(name='Grace Hopper', class_year=2025, path='engineering', school='Stony Brook University'),
        alum(name='Bo Diddley', class_year=2025, path='arts', school='Juilliard'),
        alum(name='Hidden Person', hidden=True),
        alum(name='', class_year=2023),
    ])
    assert [year for year, _ in view['classes']] == [2025, 2024]
    assert [p['name'] for p in view['classes'][0][1]] == ['Bo Diddley', 'Grace Hopper']
    assert view['count'] == 3 and view['class_count'] == 2
    assert view['schools'][0] == ('Stony Brook University', 2)
    assert view['stem_percent'] == 67
    assert [k for k, *_ in view['paths']] == ['engineering', 'computing', 'arts']
    assert view['people'][0]['initials'] == 'BD'


def test_empty_view_has_no_division_by_zero():
    view = site_content.alumni_view([])
    assert view['count'] == 0 and view['stem_percent'] == 0 and view['paths'] == []


# --- Editing ---------------------------------------------------------------------------------

def test_admin_saves_alumni_and_page_shows_them(admin, db):
    resp = save(admin, [alum(quote='Built my first lift here.'), alum(name='Draft Dan', hidden=True)])
    assert resp.status_code == 200, resp.get_json()
    page = admin.get('/alumni').get_data(as_text=True)
    assert 'Ada Lovelace' in page and 'Stony Brook University' in page and 'Built my first lift here.' in page
    assert 'Draft Dan' not in page
    assert 'Class of</span> 2024' in page


@pytest.mark.parametrize('row, message', [
    (alum(class_year=None), 'Class of'),
    (alum(name=''), 'Name'),
    (alum(path='astronaut'), 'pathway'),
    (alum(link='http://linkedin.com/in/ada'), 'https://'),
])
def test_bad_rows_are_refused(admin, row, message):
    resp = save(admin, [row])
    assert resp.status_code == 400
    assert message in resp.get_json()['error']


def test_members_cannot_edit_alumni(client, make_user):
    make_user(username='mo', password='pw-mo', email='mo@example.com')
    client.post('/login', data={'username': 'mo', 'password': 'pw-mo'})
    assert save(client, [alum()]).status_code in (302, 403)


# --- The page --------------------------------------------------------------------------------

def test_empty_page_invites_updates(client):
    resp = client.get('/alumni')
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert 'just getting started' in page
    assert 'data-alumni-form' in page
    assert 'href="/donate"' in page


def test_alumni_update_lands_in_messages(client, db):
    resp = client.post('/api/contact', json={'name': 'Ada', 'email': 'ada@example.com', 'topic': 'alumni',
                                             'message': 'Class of 2024\n\nStudying CS at Stony Brook.'})
    assert resp.status_code == 200
    assert db['contact_messages'].find_one()['topic'] == 'alumni'


def test_page_is_linked_and_discoverable(client):
    assert 'href="/alumni"' in client.get('/').get_data(as_text=True)
    assert '/alumni' in client.get('/sitemap.xml').get_data(as_text=True)
    assert '/alumni' in client.get('/llms.txt').get_data(as_text=True)
    assert 'Disallow: /alumni' not in client.get('/robots.txt').get_data(as_text=True)
