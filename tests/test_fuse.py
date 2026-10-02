"""Fuse buttons: destructive actions light a fuse with Undo instead of a modal.

The burning and undoing happen in the browser; these guard the wiring: every
page loads fuse.js, and no delete path falls back to a confirm box.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = ROOT / 'static' / 'js'


def test_every_page_loads_the_fuse(client):
    html = client.get('/').get_data(as_text=True)
    assert 'css/fuse.css' in html
    assert 'js/fuse.js' in html


def test_no_delete_waits_on_a_confirm_box():
    source = (JS / 'admin.js').read_text(encoding='utf-8')
    for call in re.finditer(r'Dialog\.confirm\(\{(.*?)\}\)', source, re.S):
        assert not re.search(r'[Dd]elete|[Rr]emove|[Rr]eject', call.group(1)), call.group(0)[:120]


@pytest.mark.parametrize('name, count', [
    ('admin.js', 7),          # forms, award, prune, reject, message, bulk, subscriber
    ('team-editor.js', 2),    # image/photo/CAD, roster member
    ('site-editor.js', 4),    # list row, reset, clear value, clear image
])
def test_destructive_actions_light_a_fuse(name, count):
    source = (JS / name).read_text(encoding='utf-8')
    assert source.count('Fuse.arm(') == count


@pytest.mark.parametrize('name', ['admin.js', 'team-editor.js', 'site-editor.js'])
def test_fetches_survive_the_page_closing(name):
    """A fuse still burning when the page closes commits with keepalive."""
    assert 'Fuse?.leaving' in (JS / name).read_text(encoding='utf-8')
