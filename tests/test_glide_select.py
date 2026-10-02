"""Dropdown menus glide: one highlight pill travels between rows, the menu grows
out of its anchor's corner, and options can carry a muted data-tag.

The motion happens in the browser; these guard the wiring.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTROLS_JS = (ROOT / 'static' / 'js' / 'controls.js').read_text(encoding='utf-8')
CONTROLS_CSS = (ROOT / 'static' / 'css' / 'controls.css').read_text(encoding='utf-8')


def test_dropdown_draws_a_gliding_pill_and_tags():
    assert "className: 'cs-pill'" in CONTROLS_JS
    assert 'option.dataset.tag' in CONTROLS_JS
    for rule in ('.cs-pill {', '.cs-pill.is-instant', '.cs-tag {', '.ctl-pop.is-leaving', '@keyframes cs-swap'):
        assert rule in CONTROLS_CSS, rule


def test_motion_respects_reduced_motion():
    block = CONTROLS_CSS[CONTROLS_CSS.index('@media (prefers-reduced-motion: reduce)'):]
    assert '.cs-pill' in block and 'select.cs-select.cs-swap' in block


def test_sponsor_levels_show_their_amount_as_a_tag(client):
    page = client.get('/donate').get_data(as_text=True)
    select = page[page.index('id="sponsor-level"'):page.index('</select>', page.index('id="sponsor-level"'))]
    tags = re.findall(r'data-tag="([^"]+)"', select)
    assert tags and any('$' in tag for tag in tags)
