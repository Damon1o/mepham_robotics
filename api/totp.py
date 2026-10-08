"""Time-based one-time passwords (RFC 6238) for two-step sign-in, standard library only.

Works with any authenticator app: Google Authenticator, Microsoft Authenticator,
1Password, Authy and the like. Six digits, SHA-1, 30-second steps.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

STEP_SECONDS = 30
DIGITS = 6
# Accept the code from one step either side, for a phone clock that drifts a little.
DRIFT_STEPS = 1
BACKUP_CODE_COUNT = 8


def new_secret():
    """A random 160-bit secret, base32 as authenticator apps expect it."""
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _hotp(secret, counter):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def current_step(now=None):
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret, step):
    return _hotp(secret, step)


def matching_step(secret, code, now=None, after=None):
    """The time step a typed code belongs to, or None.

    `after` is the last step already used: a code at or before it is refused,
    so one code can't be replayed by someone looking over a shoulder.
    """
    code = ''.join(ch for ch in str(code or '') if ch.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if after is not None and candidate <= after:
            continue
        if hmac.compare_digest(_hotp(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret, account, issuer):
    """The otpauth:// link a QR code carries."""
    label = urllib.parse.quote(f'{issuer}:{account}')
    query = urllib.parse.urlencode({'secret': secret, 'issuer': issuer, 'digits': DIGITS,
                                    'period': STEP_SECONDS})
    return f'otpauth://totp/{label}?{query}'


def new_backup_codes():
    """Plain codes to show once, e.g. 'k3f9-2m7q'. Store only their hashes."""
    alphabet = 'abcdefghjkmnpqrstuvwxyz23456789'
    return ['-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))
            for _ in range(BACKUP_CODE_COUNT)]


def hash_backup_code(code):
    normal = ''.join(ch for ch in str(code or '').lower() if ch.isalnum())
    return hashlib.sha256(normal.encode('utf-8')).hexdigest()
