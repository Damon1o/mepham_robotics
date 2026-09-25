"""Stylesheet guards for the contrast fixes.

A full WCAG check needs a browser; these catch the specific regressions that
produced the failures: faint greys, flipping ink on gold, and missing dark
rules. See the PR description for the measured before/after numbers.
"""
import pathlib
import re

import pytest

CSS = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'css'
FILES = sorted([CSS / 'styles.css', CSS / 'admin.css', *(CSS / 'pages').glob('*.css')], key=str)
RULE = re.compile(r'([^{}]+)\{([^{}]*)\}')


def rules(path):
    return [(' '.join(m.group(1).split()), m.group(2)) for m in RULE.finditer(path.read_text(encoding='utf-8'))]


@pytest.mark.parametrize('path', FILES, ids=lambda p: p.name)
def test_no_faint_grey_text_in_the_light_theme(path):
    """#999 measured 2.7-2.9:1 and #888 3.3-3.5:1 on the site's white surfaces."""
    for selector, body in rules(path):
        if 'data-theme="dark"' in selector:
            continue
        match = re.search(r'(?<![-\w])color:\s*(#999999|#999|#888888|#888|#777)\b', body, re.I)
        assert not match, f'{path.name}: {selector} uses {match.group(1)}'


@pytest.mark.parametrize('path', FILES, ids=lambda p: p.name)
def test_text_on_gold_uses_the_fixed_ink(path):
    """var(--text-dark) flips to #e0e0e0 in dark mode: 1.06:1 on gold."""
    gold = re.compile(r'var\(--accent-gold\)\s*0%,\s*#ffed4e|background(?:-color)?:\s*var\(--accent-gold\)')
    for selector, body in rules(path):
        if 'data-theme' in selector or not gold.search(body):
            continue
        assert not re.search(r'(?<![-\w])color:\s*var\(--text-dark\)', body), f'{path.name}: {selector}'


def test_ink_on_gold_token_is_defined_once():
    styles = (CSS / 'styles.css').read_text(encoding='utf-8')
    assert styles.count('--ink-on-gold: #1a1a1a') == 1


def test_admin_has_a_dark_theme():
    admin = (CSS / 'admin.css').read_text(encoding='utf-8')
    assert '[data-theme="dark"] .admin-card' in admin
    assert '--admin-card-bg: #1e1e1e' in admin


def test_contact_stylesheet_has_no_duplicated_block():
    contact = (CSS / 'pages' / 'contact.css').read_text(encoding='utf-8')
    assert contact.count('6. CLOSING BAND') == 1
    assert '[data-theme="dark"] /*' not in contact


@pytest.mark.parametrize('path', FILES, ids=lambda p: p.name)
def test_braces_are_balanced(path):
    """A dropped '}' silently scopes every later rule to the @media block above it."""
    text = re.sub(r'/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)
    depth = 0
    for number, line in enumerate(text.split('\n'), 1):
        depth += line.count('{') - line.count('}')
        assert depth >= 0, f'{path.name}:{number} closes a block that was never opened'
    assert depth == 0, f'{path.name} leaves {depth} block(s) open'


@pytest.mark.parametrize('name', ['admin.css', 'pages/team_editor.css'])
def test_no_gold_text_on_admin_surfaces(name):
    """Admin cards are white in the light theme; gold text on them measured 1.4:1."""
    for selector, body in rules(CSS / name):
        if 'data-theme="dark"' in selector:
            continue
        assert not re.search(r'(?<![-\w])color:\s*(var\(--accent-gold\)|#ffd700)', body, re.I), f'{name}: {selector}'
