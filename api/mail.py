"""Transactional email through Resend's HTTP API.

Plain-text only. Without RESEND_API_KEY and MAIL_FROM every send is a logged
no-op, so local development and the test suite never send anything, and the
pages that depend on email fall back to their old wording.
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

RESEND_URL = 'https://api.resend.com/emails'
TIMEOUT_SECONDS = (5, 10)


def configured():
    return bool(os.getenv('RESEND_API_KEY') and os.getenv('MAIL_FROM'))


def send(to, subject, text, reply_to=None):
    """Send one message. Returns True when the provider accepted it; never raises."""
    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    if not recipients:
        return False
    if not configured():
        logger.info('Email not configured; skipped "%s" to %d recipient(s)', subject, len(recipients))
        return False
    payload = {'from': os.environ['MAIL_FROM'], 'to': recipients, 'subject': subject, 'text': text}
    if reply_to:
        payload['reply_to'] = reply_to
    try:
        response = requests.post(RESEND_URL, json=payload, timeout=TIMEOUT_SECONDS,
                                 headers={'Authorization': f"Bearer {os.environ['RESEND_API_KEY']}"})
    except requests.RequestException:
        logger.exception('Email "%s" could not reach the provider', subject)
        return False
    if response.status_code >= 300:
        # The body can echo the payload, so only its start is logged.
        logger.error('Email "%s" refused: %s %s', subject, response.status_code, response.text[:300])
        return False
    return True
