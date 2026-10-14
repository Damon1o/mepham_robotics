"""The club's Discord bot: slash commands answered over HTTP, so it runs inside the site's
own Vercel deployment with nothing left running between requests.

Discord POSTs every slash command, button press and autocomplete to one URL
(/api/discord/interactions). This module holds the parts that do not touch the
database: checking Discord's signature, the command list sent to Discord, and
the shapes of the replies. api/index.py answers each command with the same
helpers the Member Hub uses, so the site and the bot never disagree.

Setup lives in docs/discord-bot.md.
"""
import datetime
import os

import requests

API = 'https://discord.com/api/v10'
AUTHORIZE_URL = 'https://discord.com/oauth2/authorize'

# Interaction types Discord sends.
PING, COMMAND, COMPONENT, AUTOCOMPLETE = 1, 2, 3, 4
# Reply types.
PONG, MESSAGE, UPDATE, CHOICES = 1, 4, 7, 8
EPHEMERAL = 64

# Option types.
STRING, INTEGER, BOOLEAN = 3, 4, 5
BUTTON = 2
ROW = 1
BUTTON_STYLES = {'primary': 1, 'secondary': 2, 'success': 3, 'danger': 4, 'link': 5}

# Club maroon, for the bar down the side of each embed.
COLOR = 0x7B1E28
# Discord's limits.
CHOICES_MAX = 25
FIELD_MAX = 1024
EMBED_FIELDS_MAX = 25
DESCRIPTION_MAX = 4096

ENV = {'app_id': 'DISCORD_APP_ID', 'public_key': 'DISCORD_PUBLIC_KEY',
       'client_secret': 'DISCORD_CLIENT_SECRET', 'bot_token': 'DISCORD_BOT_TOKEN'}


def setting(name):
    return (os.getenv(ENV[name]) or '').strip()


def interactions_ready():
    return bool(setting('app_id') and setting('public_key'))


def linking_ready():
    return bool(setting('app_id') and setting('client_secret'))


def verify(signature, timestamp, body, public_key=None):
    """True when Discord signed this request. Discord sends unsigned probes to check that we refuse them."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    key = public_key or setting('public_key')
    if not (key and signature and timestamp):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(
            bytes.fromhex(signature), timestamp.encode() + body)
        return True
    except (ValueError, InvalidSignature):
        return False


def _option(kind, name, description, required=False, autocomplete=False, choices=None, **extra):
    opt = {'type': kind, 'name': name, 'description': description, 'required': required}
    if autocomplete:
        opt['autocomplete'] = True
    if choices:
        opt['choices'] = [{'name': label, 'value': value} for value, label in choices]
    opt.update(extra)
    return opt


RSVP_OPTIONS = (('going', 'Going'), ('maybe', 'Maybe'), ('no', "Can't go"), ('clear', 'Clear my answer'))

# Sent to Discord by register_commands(). Descriptions show in Discord's command picker.
COMMANDS = [
    {'name': 'events', 'description': "What's coming up on the club calendar"},
    {'name': 'event', 'description': 'One event, with buttons to say if you are going',
     'options': [_option(STRING, 'event', 'Which event', required=True, autocomplete=True)]},
    {'name': 'rsvp', 'description': 'Say if you are going to an event',
     'options': [_option(STRING, 'event', 'Which event', required=True, autocomplete=True),
                 _option(STRING, 'answer', 'Your answer', required=True, choices=RSVP_OPTIONS)]},
    {'name': 'next', 'description': 'Countdown to the next competition'},
    {'name': 'signin', 'description': "Sign in to today's meeting"},
    {'name': 'signout', 'description': "Sign out of today's meeting"},
    {'name': 'attendance', 'description': 'Your meetings and hours this school year'},
    {'name': 'signups', 'description': 'Open sign-up sheets, like bake sales'},
    {'name': 'signup', 'description': 'Take a spot on a sign-up sheet (or give it back)',
     'options': [_option(STRING, 'sheet', 'Which sheet', required=True, autocomplete=True),
                 _option(STRING, 'role', 'Which role', required=True, autocomplete=True),
                 _option(STRING, 'note', 'A note, like what you are baking', max_length=80),
                 _option(BOOLEAN, 'leave', 'Give your spot back instead')]},
    {'name': 'team', 'description': 'A team: roster, season and awards',
     'options': [_option(STRING, 'team', 'Team number or group', required=True, autocomplete=True)]},
    {'name': 'member', 'description': "A member's page",
     'options': [_option(STRING, 'name', 'Who', required=True, autocomplete=True)]},
    {'name': 'alumni', 'description': 'Where club alumni went, and who is happy to mentor'},
    {'name': 'hub', 'description': 'Links to the Member Hub, guide, calendar and more'},
    {'name': 'link', 'description': 'Connect your Discord to your club account'},
]


COMMANDS.append(
    {'name': 'asksteven', 'description': 'Ask Steven, the club assistant, a question',
     'options': [_option(STRING, 'question', 'What do you want to know?', required=True, max_length=1000)]})


def defer(interaction, private=False):
    """Tell Discord an answer is coming (it shows "thinking…"), for replies that take over 3 seconds."""
    data = {'flags': EPHEMERAL} if private else {}
    response = requests.post(f"{API}/interactions/{interaction['id']}/{interaction['token']}/callback",
                             json={'type': 5, 'data': data}, timeout=5)
    return response.ok


def edit_reply(interaction, content):
    """Replace the "thinking…" placeholder from defer() with the answer."""
    requests.patch(f"{API}/webhooks/{setting('app_id')}/{interaction['token']}/messages/@original",
                   json={'content': clip(content, 2000), 'allowed_mentions': {'parse': []}}, timeout=10)


def register_commands():
    """Replace the app's global slash commands with COMMANDS. Returns (ok, detail)."""
    app_id, token = setting('app_id'), setting('bot_token')
    if not (app_id and token):
        return False, 'Set DISCORD_APP_ID and DISCORD_BOT_TOKEN first.'
    response = requests.put(f'{API}/applications/{app_id}/commands', json=COMMANDS,
                            headers={'Authorization': f'Bot {token}'}, timeout=15)
    if response.ok:
        return True, f'{len(response.json())} commands registered.'
    return False, f'Discord said {response.status_code}: {response.text[:300]}'


# --- Linking accounts (OAuth2, "identify" scope only) ----------------------------------------

def authorize_url(redirect_uri, state):
    from urllib.parse import urlencode
    return AUTHORIZE_URL + '?' + urlencode({
        'client_id': setting('app_id'), 'response_type': 'code', 'scope': 'identify',
        'redirect_uri': redirect_uri, 'state': state, 'prompt': 'consent'})


def fetch_identity(code, redirect_uri):
    """The Discord account ({id, username, global_name}) that approved the link, or None."""
    try:
        token = requests.post(f'{API}/oauth2/token', timeout=10, data={
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri,
            'client_id': setting('app_id'), 'client_secret': setting('client_secret')})
        if not token.ok:
            return None
        me = requests.get(f'{API}/users/@me', timeout=10,
                          headers={'Authorization': f"Bearer {token.json()['access_token']}"})
        if not me.ok:
            return None
        data = me.json()
        return {'id': str(data['id']), 'username': data.get('username') or '',
                'global_name': data.get('global_name') or ''}
    except (requests.RequestException, KeyError, ValueError):
        return None


# --- Reading an interaction ----------------------------------------------------------------

def user_id(interaction):
    """The Discord user behind an interaction, in a server or a DM."""
    user = (interaction.get('member') or {}).get('user') or interaction.get('user') or {}
    return str(user.get('id') or '')


def options(interaction):
    """{name: value} for a command's options."""
    return {o['name']: o.get('value') for o in (interaction.get('data') or {}).get('options') or ()
            if isinstance(o, dict) and 'name' in o}


def focused(interaction):
    """(option name, typed text) for an autocomplete request."""
    for o in (interaction.get('data') or {}).get('options') or ():
        if o.get('focused'):
            return o['name'], str(o.get('value') or '')
    return '', ''


# --- Building replies ----------------------------------------------------------------------

def clip(text, limit):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit - 1] + '…'


def message(content='', embeds=(), components=(), private=False, update=False):
    data = {'content': clip(content, 2000), 'embeds': list(embeds), 'components': list(components),
            'allowed_mentions': {'parse': []}}
    if private:
        data['flags'] = EPHEMERAL
    return {'type': UPDATE if update else MESSAGE, 'data': data}


def say(content, private=True):
    return message(content, private=private)


def embed(title, description='', url='', fields=(), footer=''):
    out = {'title': clip(title, 256), 'color': COLOR}
    if description:
        out['description'] = clip(description, DESCRIPTION_MAX)
    if url:
        out['url'] = url
    if fields:
        out['fields'] = [{'name': clip(n, 256), 'value': clip(v or '—', FIELD_MAX), 'inline': inline}
                         for n, v, inline in list(fields)[:EMBED_FIELDS_MAX]]
    if footer:
        out['footer'] = {'text': clip(footer, 2048)}
    return out


def button(label, custom_id='', style='secondary', url='', disabled=False):
    out = {'type': BUTTON, 'label': clip(label, 80), 'style': BUTTON_STYLES[style], 'disabled': disabled}
    if style == 'link':
        out['url'] = url
    else:
        out['custom_id'] = clip(custom_id, 100)
    return out


def row(*buttons):
    return {'type': ROW, 'components': list(buttons)[:5]}


def choices(pairs):
    """Autocomplete reply from (label, value) pairs."""
    return {'type': CHOICES, 'data': {'choices': [{'name': clip(label, 100), 'value': clip(value, 100)}
                                                  for label, value in list(pairs)[:CHOICES_MAX]]}}


def matches(text, *haystacks):
    text = text.lower().strip()
    return not text or any(text in (h or '').lower() for h in haystacks)


def stamp(moment, style='f'):
    """A Discord timestamp, shown in each reader's own time zone. `moment` is aware or UTC-naive."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return f'<t:{int(moment.timestamp())}:{style}>'
