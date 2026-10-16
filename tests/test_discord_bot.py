"""The Discord bot (api/discord_bot.py): signed interactions, linked accounts and /asksteven limits."""
import datetime
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import api.index as app_module
from api import discord_bot

TUESDAY = datetime.datetime(2026, 10, 13, 15, 30)  # inside the default Tuesday meeting
DISCORD_ID = '123456789012345678'
KEY = Ed25519PrivateKey.generate()


@pytest.fixture
def bot(monkeypatch, raw_client):
    """Configure the bot and return send(payload) -> response, signed like Discord signs it."""
    monkeypatch.setenv('DISCORD_APP_ID', '42')
    monkeypatch.setenv('DISCORD_PUBLIC_KEY', KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex())
    monkeypatch.setattr(app_module, 'club_now', lambda: TUESDAY)

    def send(payload, sign=True):
        body = json.dumps(payload).encode()
        stamp = '1700000000'
        signature = KEY.sign(stamp.encode() + body).hex() if sign else '00' * 64
        return raw_client.post('/api/discord/interactions', data=body, content_type='application/json',
                               headers={'X-Signature-Ed25519': signature, 'X-Signature-Timestamp': stamp})
    return send


def command(name, user=DISCORD_ID, **opts):
    return {'id': '9', 'token': 'tok', 'type': discord_bot.COMMAND, 'member': {'user': {'id': user}},
            'data': {'name': name, 'options': [{'name': k, 'value': v} for k, v in opts.items()]}}


def linked(make_user, db, role='member'):
    user = make_user(role=role)
    db['users'].update_one({'_id': user['_id']}, {'$set': {'discord': {'id': DISCORD_ID, 'username': 'al'}}})
    return user


def test_unsigned_requests_are_refused_and_pings_answered(bot):
    assert bot({'type': discord_bot.PING}, sign=False).status_code == 401
    assert bot({'type': discord_bot.PING}).get_json() == {'type': discord_bot.PONG}


def test_without_keys_the_endpoint_is_off(raw_client, monkeypatch):
    monkeypatch.delenv('DISCORD_PUBLIC_KEY', raising=False)
    assert raw_client.post('/api/discord/interactions', data=b'{}').status_code == 503


def test_events_lists_whats_coming(bot, db):
    db['competitions'].insert_one({'name': 'Fall Scrimmage', 'date': TUESDAY + datetime.timedelta(days=3)})
    reply = bot(command('events')).get_json()
    assert reply['type'] == discord_bot.MESSAGE
    assert reply['data']['embeds'][0]['fields'][0]['name'] == 'Fall Scrimmage'


def test_team_counts_awards_won_not_award_rows(bot, db):
    db['teams'].insert_one({'team_number': '6418', 'season': '2026', 'members': []})
    # Every team carries one row per award category; only the counts are wins.
    db['awards'].insert_many([{'team_number': '6418', 'title': f'Award {n}', 'count': c}
                              for n, c in enumerate([0] * 10 + [2, 1])])
    fields = bot(command('team', team='6418')).get_json()['data']['embeds'][0]['fields']
    assert dict((f['name'], f['value']) for f in fields)['Awards'] == '3'


def test_personal_commands_ask_unlinked_people_to_link(bot, db):
    reply = bot(command('signin')).get_json()
    assert 'Connect your Discord' in reply['data']['content']
    assert reply['data']['flags'] == discord_bot.EPHEMERAL
    assert db['attendance'].count_documents({}) == 0


def test_linked_member_signs_in_and_rsvps(bot, db, make_user):
    user = linked(make_user, db)
    reply = bot(command('signin')).get_json()
    assert "signed in" in reply['data']['content']
    assert db['attendance'].find_one({'user_id': str(user['_id'])})

    event_id = str(db['competitions'].insert_one(
        {'name': 'Regionals', 'date': TUESDAY + datetime.timedelta(days=5)}).inserted_id)
    press = {'type': discord_bot.COMPONENT, 'member': {'user': {'id': DISCORD_ID}},
             'data': {'custom_id': f'rsvp:{event_id}:going'}}
    assert 'Going' in bot(press).get_json()['data']['content']
    assert db['competitions'].find_one()['rsvps'][str(user['_id'])]['status'] == 'going'


def test_signup_takes_a_spot_and_respects_full_roles(bot, db, make_user):
    linked(make_user, db)
    sheet_id = db['signup_sheets'].insert_one({
        'title': 'Bake sale', 'date': TUESDAY + datetime.timedelta(days=2),
        'roles': [{'key': 'baker', 'name': 'Baker', 'slots': 1, 'prompt': ''}],
        'signups': {}}).inserted_id
    reply = bot(command('signup', sheet=str(sheet_id), role='baker', note='brownies')).get_json()
    assert "on **Baker**" in reply['data']['content']
    assert db['signup_sheets'].find_one()['signups']['baker'][0]['note'] == 'brownies'
    other = command('signup', user='555', sheet=str(sheet_id), role='baker')
    db['users'].insert_one({'username': 'bob', 'discord': {'id': '555'}})
    assert 'full' in bot(other).get_json()['data']['content']
    autocomplete = {'type': discord_bot.AUTOCOMPLETE, 'member': {'user': {'id': DISCORD_ID}},
                    'data': {'name': 'signup', 'options': [{'name': 'sheet', 'value': 'bake', 'focused': True}]}}
    assert bot(autocomplete).get_json()['data']['choices'][0]['value'] == str(sheet_id)


def test_asksteven_defers_answers_and_cools_down(bot, db, monkeypatch):
    calls = []
    monkeypatch.setattr(discord_bot, 'defer', lambda i, private=False: calls.append('defer') or True)
    monkeypatch.setattr(discord_bot, 'edit_reply', lambda i, text: calls.append(text))
    monkeypatch.setattr(app_module, 'steven_reply', lambda q, history=(): ('Meetings are Tuesdays.', '', 200))
    assert bot(command('asksteven', question='When do we meet?')).status_code == 202
    assert calls[0] == 'defer' and 'Meetings are Tuesdays.' in calls[1]
    # A second question straight away waits out the cooldown and never reaches the model.
    reply = bot(command('asksteven', question='And where?')).get_json()
    assert 'catching his breath' in reply['data']['content'] and len(calls) == 2


def test_asksteven_hourly_cap_per_person(bot, db, monkeypatch):
    monkeypatch.setattr(discord_bot, 'defer', lambda i, private=False: True)
    monkeypatch.setattr(discord_bot, 'edit_reply', lambda i, text: None)
    monkeypatch.setattr(app_module, 'steven_reply', lambda q, history=(): ('ok', '', 200))
    for _ in range(app_module.STEVEN_USER_LIMIT):
        assert bot(command('asksteven', question='hi')).status_code == 202
        db['rate_limits'].delete_many({'bucket': 'steven_cooldown'})  # skip the 30-second wait
    assert 'this hour' in bot(command('asksteven', question='hi')).get_json()['data']['content']


def test_account_links_discord_through_oauth(client, make_user, db, monkeypatch):
    monkeypatch.setenv('DISCORD_APP_ID', '42')
    monkeypatch.setenv('DISCORD_CLIENT_SECRET', 'shh')
    make_user()
    client.post('/login', data={'username': 'alice', 'password': 'correct-horse'})
    start = client.post('/account/discord/connect')
    assert start.headers['Location'].startswith(discord_bot.AUTHORIZE_URL)
    with client.session_transaction() as sess:
        state = sess['discord_state']
    monkeypatch.setattr(discord_bot, 'fetch_identity',
                        lambda code, uri: {'id': DISCORD_ID, 'username': 'al', 'global_name': 'Al'})
    assert client.get('/account/discord/callback?code=x&state=wrong').status_code == 302
    assert 'discord' not in db['users'].find_one()
    client.post('/account/discord/connect')
    with client.session_transaction() as sess:
        state = sess['discord_state']
    client.get(f'/account/discord/callback?code=x&state={state}')
    assert db['users'].find_one()['discord']['id'] == DISCORD_ID
    assert 'Linked' in client.get('/account').get_data(as_text=True)
    client.post('/account/discord/disconnect')
    assert 'discord' not in db['users'].find_one()
