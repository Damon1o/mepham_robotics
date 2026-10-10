"""Your account page: password change, sign out everywhere, and two-step sign-in."""

import bcrypt
import pytest

import api.index as app_module
from api import devices, totp


def _sign_in(client, username='alice', password='correct-horse'):
    return client.post('/login', data={'username': username, 'password': password})


def _signed_in(c):
    """GET /login bounces a signed-in visitor and shows the form to everyone else."""
    return c.get('/login').status_code == 302


@pytest.fixture
def member(client, make_user):
    user = make_user()
    _sign_in(client)
    return user


def _turn_on_two_step(client, db, user):
    client.post('/account/two-step/start')
    secret = db['users'].find_one({'_id': user['_id']})['totp_pending']
    code = totp.code_at(secret, totp.current_step())
    resp = client.post('/account/two-step/confirm', data={'code': code})
    assert resp.status_code == 200
    return secret, resp.get_data(as_text=True)


# --- TOTP maths -------------------------------------------------------------------------

def test_totp_matches_the_rfc_6238_test_vector():
    # RFC 6238 appendix B, SHA-1, T = 59s: 94287082 -> last six digits.
    secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'  # base32 of "12345678901234567890"
    assert totp.code_at(secret, 59 // 30) == '287082'


def test_codes_from_the_next_and_previous_step_are_accepted():
    secret, now = totp.new_secret(), 1_000_000
    step = totp.current_step(now)
    for offset in (-1, 0, 1):
        assert totp.matching_step(secret, totp.code_at(secret, step + offset), now=now) == step + offset
    assert totp.matching_step(secret, totp.code_at(secret, step + 3), now=now) is None


def test_a_used_step_is_refused():
    secret, now = totp.new_secret(), 1_000_000
    step = totp.current_step(now)
    assert totp.matching_step(secret, totp.code_at(secret, step), now=now, after=step) is None


def test_codes_tolerate_spaces_but_not_junk():
    secret = totp.new_secret()
    code = totp.code_at(secret, totp.current_step())
    assert totp.matching_step(secret, f'{code[:3]} {code[3:]}') is not None
    assert totp.matching_step(secret, 'abcdef') is None
    assert totp.matching_step(secret, '') is None


def test_provisioning_uri_names_the_club():
    uri = totp.provisioning_uri('ABC', 'alice', 'Mepham Robotics')
    assert uri.startswith('otpauth://totp/Mepham%20Robotics%3Aalice?')
    assert 'secret=ABC' in uri and 'issuer=Mepham+Robotics' in uri


def test_backup_code_hash_ignores_case_and_dashes():
    assert totp.hash_backup_code('ABCD-EFGH') == totp.hash_backup_code('abcdefgh')


# --- Account page ------------------------------------------------------------------------

def test_account_page_needs_sign_in(client):
    assert client.get('/account').status_code == 302


def test_account_page_shows_the_account(client, member):
    page = client.get('/account').get_data(as_text=True)
    assert '@alice' in page
    assert 'Set up two-step sign-in' in page


def test_nav_links_to_the_account(client, member):
    assert 'My Account' in client.get('/about').get_data(as_text=True)


# --- Password -------------------------------------------------------------------------------

def test_change_password_keeps_this_device_and_signs_out_others(client, db, member):
    other = app_module.app.test_client()
    _sign_in(other)
    resp = client.post('/account/password', data={'current_password': 'correct-horse',
                                                   'new_password': 'brand-new-pw', 'confirm_password': 'brand-new-pw'})
    assert resp.status_code == 302
    stored = db['users'].find_one({'_id': member['_id']})
    assert bcrypt.checkpw(b'brand-new-pw', stored['password'])
    assert _signed_in(client)
    assert not _signed_in(other)


@pytest.mark.parametrize('form,message', [
    ({'current_password': 'wrong', 'new_password': 'brand-new-pw', 'confirm_password': 'brand-new-pw'},
     'current password is not right'),
    ({'current_password': 'correct-horse', 'new_password': 'short', 'confirm_password': 'short'},
     'at least 8'),
    ({'current_password': 'correct-horse', 'new_password': 'brand-new-pw', 'confirm_password': 'different'},
     "don&#39;t match"),
])
def test_change_password_errors(client, db, member, form, message):
    resp = client.post('/account/password', data=form)
    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True)
    assert bcrypt.checkpw(b'correct-horse', db['users'].find_one({'_id': member['_id']})['password'])


def test_wrong_current_password_locks_out(client, member):
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS):
        client.post('/account/password', data={'current_password': 'wrong', 'new_password': 'x' * 9,
                                               'confirm_password': 'x' * 9})
    resp = client.post('/account/password', data={'current_password': 'correct-horse', 'new_password': 'x' * 9,
                                                   'confirm_password': 'x' * 9})
    assert 'Too many wrong passwords' in resp.get_data(as_text=True)


# --- Sign out everywhere -----------------------------------------------------------------------

def test_sign_out_everywhere(client, member):
    other = app_module.app.test_client()
    _sign_in(other)
    resp = client.post('/account/sign-out-everywhere')
    assert resp.status_code == 302 and resp.location.endswith('/login')
    assert not _signed_in(client)
    assert not _signed_in(other)


# --- Two-step setup -------------------------------------------------------------------------------

def test_setup_keeps_the_secret_off_the_cookie_until_confirmed(client, db, member):
    client.post('/account/two-step/start')
    stored = db['users'].find_one({'_id': member['_id']})
    assert stored['totp_pending'] and 'totp_secret' not in stored
    with client.session_transaction() as sess:
        assert stored['totp_pending'] not in str(dict(sess))
    page = client.get('/account').get_data(as_text=True)
    assert 'data-qr="otpauth://totp/' in page
    assert 'vendor/qrcode.min.js' in page


def test_setup_refuses_a_wrong_code(client, db, member):
    client.post('/account/two-step/start')
    resp = client.post('/account/two-step/confirm', data={'code': '000000'})
    assert resp.status_code == 400
    assert 'totp_secret' not in db['users'].find_one({'_id': member['_id']})


def test_setup_turns_on_and_shows_backup_codes_once(client, db, member):
    secret, page = _turn_on_two_step(client, db, member)
    stored = db['users'].find_one({'_id': member['_id']})
    assert stored['totp_secret'] == secret and 'totp_pending' not in stored
    assert len(stored['totp_backup']) == totp.BACKUP_CODE_COUNT
    assert page.count('<li><code>') == totp.BACKUP_CODE_COUNT
    assert '<li><code>' not in client.get('/account').get_data(as_text=True)


def test_turning_it_on_signs_out_other_devices(client, db, member):
    other = app_module.app.test_client()
    _sign_in(other)
    _turn_on_two_step(client, db, member)
    assert _signed_in(client)
    assert not _signed_in(other)


def test_cancel_setup(client, db, member):
    client.post('/account/two-step/start')
    client.post('/account/two-step/cancel')
    assert 'totp_pending' not in db['users'].find_one({'_id': member['_id']})


def test_turn_off_needs_the_password(client, db, member):
    _turn_on_two_step(client, db, member)
    assert client.post('/account/two-step/off', data={'current_password': 'wrong'}).status_code == 400
    assert db['users'].find_one({'_id': member['_id']}).get('totp_secret')
    client.post('/account/two-step/off', data={'current_password': 'correct-horse'})
    assert 'totp_secret' not in db['users'].find_one({'_id': member['_id']})


def test_new_backup_codes_replace_the_old(client, db, member):
    _turn_on_two_step(client, db, member)
    old = db['users'].find_one({'_id': member['_id']})['totp_backup']
    resp = client.post('/account/two-step/backup-codes', data={'current_password': 'correct-horse'})
    assert resp.status_code == 200
    assert db['users'].find_one({'_id': member['_id']})['totp_backup'] != old


# --- Signing in with two-step ------------------------------------------------------------------------

@pytest.fixture
def two_step_user(db, make_user):
    user = make_user()
    secret = totp.new_secret()
    codes = totp.new_backup_codes()
    db['users'].update_one({'_id': user['_id']}, {'$set': {
        'totp_secret': secret, 'totp_backup': [totp.hash_backup_code(c) for c in codes]}})
    return {'user': user, 'secret': secret, 'codes': codes}


def test_password_alone_does_not_sign_in(client, two_step_user):
    resp = _sign_in(client)
    assert resp.status_code == 302 and resp.location.endswith('/login/verify')
    with client.session_transaction() as sess:
        assert 'user' not in sess
    assert client.get('/my-team').status_code == 302


def test_code_finishes_sign_in_and_keeps_next(client, two_step_user):
    client.post('/login?next=/resources', data={'username': 'alice', 'password': 'correct-horse'})
    code = totp.code_at(two_step_user['secret'], totp.current_step())
    resp = client.post('/login/verify', data={'code': code})
    assert resp.status_code == 302 and resp.location == '/resources'
    assert _signed_in(client)


def test_two_step_sign_in_can_still_be_signed_out_server_side(client, two_step_user):
    _sign_in(client)
    client.post('/login/verify', data={'code': totp.code_at(two_step_user['secret'], totp.current_step())})
    with client.session_transaction() as sess:
        stolen = dict(sess)
    assert stolen.get('sid')
    client.post('/logout')
    with client.session_transaction() as sess:
        sess.update(stolen)
    assert not _signed_in(client)


def test_a_code_cannot_be_used_twice(client, two_step_user):
    code = totp.code_at(two_step_user['secret'], totp.current_step())
    _sign_in(client)
    client.post('/login/verify', data={'code': code})
    other = app_module.app.test_client()
    _sign_in(other)
    assert other.post('/login/verify', data={'code': code}).status_code == 401


def test_backup_code_works_once(client, db, two_step_user):
    code = two_step_user['codes'][0]
    _sign_in(client)
    assert client.post('/login/verify', data={'code': code.upper()}).status_code == 302
    left = db['users'].find_one({'_id': two_step_user['user']['_id']})['totp_backup']
    assert len(left) == totp.BACKUP_CODE_COUNT - 1
    other = app_module.app.test_client()
    _sign_in(other)
    assert other.post('/login/verify', data={'code': code}).status_code == 401


def test_wrong_codes_lock_out(client, two_step_user):
    _sign_in(client)
    for _ in range(app_module.LOGIN_MAX_ATTEMPTS):
        client.post('/login/verify', data={'code': '000000'})
    good = totp.code_at(two_step_user['secret'], totp.current_step())
    assert client.post('/login/verify', data={'code': good}).status_code == 429


def test_verify_without_a_password_step_goes_back_to_login(client, two_step_user):
    resp = client.get('/login/verify')
    assert resp.status_code == 302 and resp.location.endswith('/login')


def test_a_stale_password_step_expires(client, two_step_user, monkeypatch):
    _sign_in(client)
    later = app_module._utcnow() + app_module.TWO_STEP_WINDOW * 2
    monkeypatch.setattr(app_module, '_utcnow', lambda: later)
    code = totp.code_at(two_step_user['secret'], totp.current_step())
    resp = client.post('/login/verify', data={'code': code})
    assert resp.status_code == 302 and resp.location.endswith('/login')


# --- Admin --------------------------------------------------------------------------------------------

@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    _sign_in(client, 'root', 'root-password')
    return client


def test_dashboard_nudges_an_admin_without_two_step(admin):
    page = admin.get('/admin').get_data(as_text=True)
    assert 'Your admin account has no two-step sign-in' in page
    assert '/account#two-step' in page


def test_dashboard_marks_two_step_accounts_without_leaking_secrets(admin, two_step_user):
    page = admin.get('/admin').get_data(as_text=True)
    assert '2-step' in page
    assert two_step_user['secret'] not in page
    assert 'two-step-off' in page


def test_admin_can_turn_off_someone_elses_two_step(admin, db, two_step_user):
    uid = two_step_user['user']['_id']
    assert admin.post(f'/admin/users/{uid}/two-step-off').status_code == 302
    assert 'totp_secret' not in db['users'].find_one({'_id': uid})


def test_members_cannot_turn_off_two_step_for_others(client, db, make_user, two_step_user):
    make_user(username='bob', password='bob-password', email='bob@example.com')
    _sign_in(client, 'bob', 'bob-password')
    client.post(f"/admin/users/{two_step_user['user']['_id']}/two-step-off")
    assert db['users'].find_one({'_id': two_step_user['user']['_id']}).get('totp_secret')


# --- Profile ----------------------------------------------------------------------------------------

def test_profile_saves_a_name_without_the_password(client, db, member):
    resp = client.post('/account/profile', data={'full_name': '  Alice   Liddell ', 'email': 'alice@example.com'})
    assert resp.status_code == 302
    assert db['users'].find_one({'_id': member['_id']})['full_name'] == 'Alice Liddell'
    assert 'Alice Liddell' in client.get('/account').get_data(as_text=True)


def test_profile_can_clear_the_name(client, db, member):
    db['users'].update_one({'_id': member['_id']}, {'$set': {'full_name': 'Old Name'}})
    client.post('/account/profile', data={'full_name': '', 'email': 'alice@example.com'})
    assert 'full_name' not in db['users'].find_one({'_id': member['_id']})


def test_new_email_needs_the_password(client, db, member):
    resp = client.post('/account/profile', data={'email': 'new@example.com', 'current_password': 'wrong'})
    assert resp.status_code == 400
    assert 'current password is not right' in resp.get_data(as_text=True)
    assert db['users'].find_one({'_id': member['_id']})['email'] == 'alice@example.com'

    resp = client.post('/account/profile', data={'email': 'New@Example.com', 'current_password': 'correct-horse'})
    assert resp.status_code == 302
    assert db['users'].find_one({'_id': member['_id']})['email'] == 'new@example.com'


@pytest.mark.parametrize('email,message', [('not-an-email', 'valid email'), ('', 'valid email'),
                                           ('bob@example.com', 'already registered')])
def test_bad_emails_are_refused(client, db, make_user, member, email, message):
    make_user(username='bob', password='bob-password', email='bob@example.com')
    resp = client.post('/account/profile', data={'email': email, 'current_password': 'correct-horse'})
    assert resp.status_code == 400
    assert message in resp.get_data(as_text=True)
    assert db['users'].find_one({'_id': member['_id']})['email'] == 'alice@example.com'


def test_profile_name_has_a_length_limit(client, db, member):
    resp = client.post('/account/profile', data={'full_name': 'x' * (app_module.FULL_NAME_MAX + 1),
                                                 'email': 'alice@example.com'})
    assert resp.status_code == 400
    assert 'full_name' not in db['users'].find_one({'_id': member['_id']})


def test_profile_change_shows_in_activity(client, member):
    client.post('/account/profile', data={'full_name': 'Alice L', 'email': 'alice@example.com'})
    assert 'Profile updated' in client.get('/account').get_data(as_text=True)


# --- Devices ------------------------------------------------------------------------------------------

PHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
            '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
WINDOWS_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/126.0 Safari/537.36 Edg/126.0')


@pytest.mark.parametrize('agent,label,kind', [
    (PHONE_UA, 'Safari on iPhone', 'phone'),
    (WINDOWS_UA, 'Edge on Windows', 'computer'),
    ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36',
     'Chrome on Android', 'phone'),
    ('Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0', 'Firefox on Linux', 'computer'),
    ('', 'Unknown browser', 'computer'),
])
def test_devices_are_named_from_the_user_agent(agent, label, kind):
    assert devices.describe(agent) == (label, kind)


def _sign_in_as(client, agent):
    return client.post('/login', data={'username': 'alice', 'password': 'correct-horse'},
                       headers={'User-Agent': agent})


def _sessions(db, username='alice'):
    return db['users'].find_one({'username': username}).get('sessions', [])


def test_signed_in_devices_are_listed_without_session_ids(client, db, make_user):
    make_user()
    _sign_in_as(client, WINDOWS_UA)
    phone = app_module.app.test_client()
    _sign_in_as(phone, PHONE_UA)
    page = client.get('/account').get_data(as_text=True)
    assert 'Edge on Windows' in page and 'Safari on iPhone' in page
    assert 'This device' in page
    for entry in _sessions(db):
        assert entry['sid'] not in page


def test_signing_out_another_device(client, db, make_user):
    make_user()
    _sign_in_as(client, WINDOWS_UA)
    phone = app_module.app.test_client()
    _sign_in_as(phone, PHONE_UA)
    key = next(s['key'] for s in _sessions(db) if 'iPhone' in s['agent'])
    assert client.post(f'/account/devices/{key}/sign-out').status_code == 302
    assert _signed_in(client)
    assert not _signed_in(phone)
    page = client.get('/account').get_data(as_text=True)
    assert 'Signed out Safari on iPhone.' in page
    assert len(_sessions(db)) == 1 and 'Edg/' in _sessions(db)[0]['agent']
    assert 'Device signed out' in page


def test_signing_out_this_device_from_the_list(client, db, member):
    key = _sessions(db)[0]['key']
    resp = client.post(f'/account/devices/{key}/sign-out')
    assert resp.location.endswith('/login')
    assert not _signed_in(client)


def test_someone_elses_device_key_does_nothing(client, db, make_user, member):
    make_user(username='bob', password='bob-password', email='bob@example.com')
    bob = app_module.app.test_client()
    _sign_in(bob, 'bob', 'bob-password')
    client.post(f"/account/devices/{_sessions(db, 'bob')[0]['key']}/sign-out")
    assert _signed_in(bob)


def test_password_change_keeps_only_this_device_listed(client, db, member):
    other = app_module.app.test_client()
    _sign_in_as(other, PHONE_UA)
    client.post('/account/password', data={'current_password': 'correct-horse',
                                           'new_password': 'brand-new-pw', 'confirm_password': 'brand-new-pw'})
    page = client.get('/account').get_data(as_text=True)
    assert 'This device' in page
    assert 'Safari on iPhone' not in page
    assert db['users'].find_one({'_id': member['_id']}).get('password_changed')


def test_logout_drops_the_device(client, db, member):
    client.post('/logout')
    assert _sessions(db) == []


def test_last_active_time_is_updated_now_and_then(client, db, member, monkeypatch):
    first = _sessions(db)[0]['seen']
    later = app_module._utcnow() + app_module.SESSION_SEEN_EVERY * 2
    monkeypatch.setattr(app_module, '_utcnow', lambda: later)
    client.get('/account')
    assert _sessions(db)[0]['seen'] > first


def test_device_list_is_capped(client, db, member):
    for _ in range(app_module.SESSIONS_KEPT + 3):
        _sign_in(app_module.app.test_client())
    assert len(_sessions(db)) == app_module.SESSIONS_KEPT


# --- Checkup ----------------------------------------------------------------------------------------------

def test_checkup_counts_what_is_done(client, db, member):
    # Only the email counts at first: no two-step, and no date to call the password fresh.
    assert 'Security checkup: 1 of 4 done' in client.get('/account').get_data(as_text=True)
    _turn_on_two_step(client, db, member)
    client.post('/account/password', data={'current_password': 'correct-horse',
                                           'new_password': 'brand-new-pw', 'confirm_password': 'brand-new-pw'})
    assert 'Security checkup: 4 of 4 done' in client.get('/account').get_data(as_text=True)
