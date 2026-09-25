"""Data layer: query cost, indexes, error handling, and admin routes that had no tests."""
import datetime

import pytest
from bson import ObjectId

import api.index as app_module


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


class CountingDb:
    """Wraps the mongomock database and counts reads per collection."""

    READS = ('find', 'find_one', 'aggregate', 'count_documents')

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def __getitem__(self, name):
        collection = self.inner[name]
        calls = self.calls

        class Wrapped:
            def __getattr__(self, attr):
                value = getattr(collection, attr)
                if attr in CountingDb.READS:
                    def counted(*a, **k):
                        calls.append((name, attr))
                        return value(*a, **k)
                    return counted
                return value
        return Wrapped()

    def __getattr__(self, attr):
        return getattr(self.inner, attr)


@pytest.fixture
def counting(db, monkeypatch):
    wrapper = CountingDb(db)
    monkeypatch.setattr(app_module, 'get_db', lambda: wrapper)
    return wrapper


# --- Query cost -------------------------------------------------------------

def test_homepage_skips_awards_and_sponsors(client, counting):
    client.get('/')
    touched = {name for name, _ in counting.calls}
    assert touched == {'site_metadata', 'competitions', 'teams'}


def test_404_page_makes_no_queries(client, counting):
    assert client.get('/no-such-page').status_code == 404
    assert counting.calls == []


def test_nav_still_lists_teams(client, db):
    db['teams'].insert_many([{'team_number': '77628P'}, {'team_number': '77628D'}])
    page = client.get('/about').get_data(as_text=True)
    assert page.index('/team/77628D') < page.index('/team/77628P')


def test_achievements_and_donate_load_their_own_data(client, db):
    db['awards'].insert_one({'title': 'Judges Award', 'icon': 'judges_award.png', 'count': 1})
    db['sponsors'].insert_one({'name': 'Acme Machining', 'level': 'Gold', 'logo': 'https://blob.example/l.png'})
    assert 'Judges Award' in client.get('/achievements').get_data(as_text=True)
    donate = client.get('/donate').get_data(as_text=True)
    assert 'Acme Machining' in donate
    assert 'https://blob.example/l.png' in donate


def test_database_outage_degrades_the_nav_instead_of_failing(client, monkeypatch):
    def down():
        raise RuntimeError('db down')
    monkeypatch.setattr(app_module, 'get_db', down)
    # /about needs nothing but the nav, which now fails soft.
    assert client.get('/about').status_code == 200


# --- Indexes and client ------------------------------------------------------

def test_core_indexes(db):
    app_module._ensure_core_indexes(db)
    users = db['users'].index_information()
    assert any(v['key'] == [('username', 1)] and v.get('unique') for v in users.values())
    teams = db['teams'].index_information()
    assert any(v['key'] == [('team_number', 1), ('season', 1)] and v.get('unique')
               for v in teams.values())
    # The single-field version would reject a second season's document.
    assert not any(v['key'] == [('team_number', 1)] and v.get('unique') for v in teams.values())
    tokens = db['newsletter_subscribers'].index_information()
    assert any(v['key'] == [('unsubscribe_token', 1)] for v in tokens.values())


def test_one_bad_index_does_not_stop_the_rest(db, monkeypatch):
    db['users'].insert_many([{'username': 'dup'}, {'username': 'dup'}])
    app_module._ensure_core_indexes(db)  # the unique users index fails
    assert any(v['key'] == [('team_number', 1), ('season', 1)]
               for v in db['teams'].index_information().values())


def test_mongo_client_has_timeouts(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, uri, **kwargs):
            captured.update(kwargs)

        def __getitem__(self, name):
            import mongomock
            return mongomock.MongoClient()[name]

    monkeypatch.setattr(app_module, 'MongoClient', FakeClient)
    monkeypatch.setattr(app_module, '_db', None)
    monkeypatch.setenv('MONGO_URI', 'mongodb://example')
    app_module.get_db()
    assert captured['socketTimeoutMS'] and captured['connectTimeoutMS']
    assert captured['maxPoolSize'] <= 20


# --- Homepage events -----------------------------------------------------------

def test_upcoming_events_use_club_time(client, db, monkeypatch):
    now = datetime.datetime(2026, 10, 10, 7, 0)
    monkeypatch.setattr(app_module, 'club_now', lambda: now)
    db['competitions'].insert_many([
        {'name': 'Earlier today', 'location': 'x', 'date': now - datetime.timedelta(hours=1)},
        {'name': 'Later today', 'location': 'x', 'date': now + datetime.timedelta(hours=2)},
    ])
    page = client.get('/').get_data(as_text=True)
    assert 'Later today' in page
    assert 'Earlier today' not in page


# --- Admin error handling --------------------------------------------------------

def test_admin_flash_hides_exception_text(admin, db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('mongodb+srv://secret-cluster.example.net')
    monkeypatch.setattr(app_module, 'seed_team_awards', boom)
    page = admin.post('/admin/save-team', data={'team_number': '1'},
                      follow_redirects=True).get_data(as_text=True)
    assert 'secret-cluster' not in page
    assert 'Error saving team' in page


def test_bad_event_date_gets_a_friendly_message(admin, db):
    page = admin.post('/admin/add-competition', data={
        'comp_name': 'Q', 'comp_location': 'L', 'comp_date': 'tomorrow-ish'},
        follow_redirects=True).get_data(as_text=True)
    assert 'Enter a valid event date and time.' in page
    assert db['competitions'].count_documents({}) == 0


# --- Competitions --------------------------------------------------------------------

def test_competition_add_update_delete(admin, db):
    admin.post('/admin/add-competition', data={
        'comp_name': 'Qualifier', 'comp_location': 'Mepham', 'comp_date': '2026-11-01T08:30'})
    comp = db['competitions'].find_one({'name': 'Qualifier'})
    assert comp['date'] == datetime.datetime(2026, 11, 1, 8, 30)

    admin.post(f"/admin/update-competition/{comp['_id']}", data={
        'comp_name': 'Qualifier II', 'comp_location': 'Calhoun', 'comp_date': '2026-11-02T09:00'})
    assert db['competitions'].find_one({'_id': comp['_id']})['location'] == 'Calhoun'

    admin.post(f"/admin/delete-competition/{comp['_id']}")
    assert db['competitions'].count_documents({}) == 0


# --- Users -----------------------------------------------------------------------------

def test_admin_cannot_delete_themselves(admin, db):
    me = db['users'].find_one({'username': 'root'})
    admin.post(f"/admin/delete-user/{me['_id']}")
    assert db['users'].find_one({'_id': me['_id']})


def test_an_admin_can_remove_another_admin(admin, db, make_user):
    # The requester is always an admin and cannot delete themselves, so a
    # second admin always remains; the last-admin guard is belt-and-braces.
    other = make_user(username='other', password='other-password', role='admin')
    admin.post(f"/admin/delete-user/{other['_id']}")
    assert db['users'].find_one({'_id': other['_id']}) is None
    assert db['users'].count_documents({'role': 'admin'}) == 1


def test_other_admin_exists(db, make_user):
    only = make_user(username='only', password='only-password', role='admin')
    with app_module.app.test_request_context('/'):
        assert app_module._other_admin_exists(only['_id']) is False
        make_user(username='second', password='second-password', role='admin')
        assert app_module._other_admin_exists(only['_id']) is True


def test_deleting_a_user_unlinks_their_team_rows(admin, db, make_user):
    member = make_user(username='kid', password='kid-password')
    db['teams'].insert_one({'team_number': '77628D', 'members': [
        {'name': 'Kid', 'user_id': str(member['_id'])},
        {'name': 'Other', 'user_id': 'someone-else'},
    ]})
    admin.post(f"/admin/delete-user/{member['_id']}")
    members = db['teams'].find_one({'team_number': '77628D'})['members']
    assert members[0]['user_id'] == ''
    assert members[1]['user_id'] == 'someone-else'


# --- Sponsors ------------------------------------------------------------------------------

def test_deleting_a_sponsor_deletes_its_logo(admin, db, monkeypatch):
    deleted = []
    monkeypatch.setattr(app_module, 'delete_from_vercel_blob', deleted.append)
    sponsor_id = db['sponsors'].insert_one({'name': 'Acme', 'logo': 'https://blob.example/logo.png'}).inserted_id
    admin.post(f'/admin/delete-sponsor/{sponsor_id}')
    assert deleted == ['https://blob.example/logo.png']
    assert db['sponsors'].count_documents({}) == 0


def test_monthly_changes_match_the_activity_log(admin, db):
    now = app_module._utcnow()
    db['activities'].insert_many([
        {'type': 'team_add', 'timestamp': now, 'details': {'members_count': 4}},
        {'type': 'team_delete', 'timestamp': now, 'details': {'members_count': 1}},
        {'type': 'team_update', 'timestamp': now, 'details': {'members_change': 2}},
        {'type': 'stats_update', 'timestamp': now, 'details': {'teams_change': 1, 'members_change': 3,
                                                                'awards_change': 2}},
        {'type': 'awards_update', 'timestamp': now, 'details': {'count_change': 5}},
        {'type': 'awards_update', 'timestamp': now, 'details': {'total_change': 1}},
        {'type': 'competition_add', 'timestamp': now, 'details': {}},
        {'type': 'competition_add', 'timestamp': now, 'details': {}},
        {'type': 'competition_delete', 'timestamp': now, 'details': {}},
        # last month: ignored
        {'type': 'team_add', 'timestamp': now - datetime.timedelta(days=40), 'details': {'members_count': 9}},
    ])
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with app_module.app.test_request_context('/'):
        changes = app_module.monthly_stat_changes(first)
    assert changes == {'teams_change': 1, 'members_change': 8, 'awards_change': 8, 'events_change': 1}


# --- Seasons -------------------------------------------------------------------

def test_a_second_season_can_be_stored(db):
    app_module._ensure_core_indexes(db)
    db['teams'].insert_one({'team_number': '77628D', 'season': '2024-25'})
    db['teams'].insert_one({'team_number': '77628D', 'season': '2025-26'})
    assert db['teams'].count_documents({'team_number': '77628D'}) == 2


def test_the_same_season_twice_is_rejected(db):
    import pymongo.errors
    app_module._ensure_core_indexes(db)
    db['teams'].insert_one({'team_number': '77628D', 'season': '2025-26'})
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        db['teams'].insert_one({'team_number': '77628D', 'season': '2025-26'})


def test_the_pre_season_unique_index_is_dropped(db):
    db['teams'].create_index('team_number', unique=True)
    app_module._ensure_core_indexes(db)
    db['teams'].insert_one({'team_number': '77628D', 'season': '2024-25'})
    db['teams'].insert_one({'team_number': '77628D', 'season': '2025-26'})
    assert db['teams'].count_documents({}) == 2


@pytest.mark.parametrize('field', ['specs', 'members', 'goals', 'journey', 'events'])
def test_team_page_survives_null_fields(client, db, field):
    db['teams'].insert_one({'team_number': '77628N', field: None})
    assert client.get('/team/77628N').status_code == 200


def test_event_photos_are_resolved_to_urls(client, db, monkeypatch):
    monkeypatch.setenv('ROBOTEVENTS_TOKEN', 'test-token')
    db['teams'].insert_one({'team_number': '77628E', 'events': [
        {'name': 'Qualifier', 'photos': ['static/assets/photos/carousel1.jpg',
                                         'https://blob.example/p.jpg']}]})
    page = client.get('/team/77628E').get_data(as_text=True)
    assert '/static/assets/photos/carousel1.jpg' in page
    assert '"static/assets/photos/carousel1.jpg"' not in page
    assert 'https://blob.example/p.jpg' in page


def test_robot_photo_fallback_resolves_once(client, db):
    db['teams'].insert_one({'team_number': '77628R', 'events': [
        {'name': 'Qualifier', 'photos': ['static/assets/photos/carousel1.jpg']}]})
    page = client.get('/team/77628R').get_data(as_text=True)
    # Resolving twice would turn the real photo into the placeholder.
    assert 'viewer-gallery-photo' in page
    assert '/static/assets/photos/carousel1.jpg' in page
