"""Name a signed-in device from its User-Agent, for the account page's device list.

Only a rough label: "Chrome on Windows", plus whether it is a phone, tablet or
computer so the page can pick an icon. Anything unrecognised falls back to
"Unknown browser" rather than guessing.
"""

import re

# Order matters: Edge, Opera and Samsung Internet all also claim to be Chrome,
# and Chrome claims to be Safari.
BROWSERS = (
    ('Edge', re.compile(r'Edg(?:e|A|iOS)?/')),
    ('Opera', re.compile(r'OPR/|Opera')),
    ('Samsung Internet', re.compile(r'SamsungBrowser/')),
    ('Firefox', re.compile(r'Firefox/|FxiOS/')),
    ('Chrome', re.compile(r'Chrome/|CriOS/')),
    ('Safari', re.compile(r'Safari/')),
)

SYSTEMS = (
    ('iPad', re.compile(r'iPad')),
    ('iPhone', re.compile(r'iPhone|iPod')),
    ('Android', re.compile(r'Android')),
    ('ChromeOS', re.compile(r'CrOS')),
    ('Windows', re.compile(r'Windows')),
    ('macOS', re.compile(r'Macintosh|Mac OS X')),
    ('Linux', re.compile(r'Linux')),
)


def _first(table, agent):
    return next((name for name, pattern in table if pattern.search(agent)), None)


def describe(agent):
    """(label, kind) for a User-Agent string. kind is 'phone', 'tablet' or 'computer'."""
    agent = agent or ''
    browser, system = _first(BROWSERS, agent), _first(SYSTEMS, agent)
    if system == 'iPad' or (system == 'Android' and 'Mobile' not in agent):
        kind = 'tablet'
    elif system in ('iPhone', 'Android') or 'Mobile' in agent:
        kind = 'phone'
    else:
        kind = 'computer'
    if browser and system:
        label = f'{browser} on {system}'
    else:
        label = browser or system or 'Unknown browser'
    return label, kind
