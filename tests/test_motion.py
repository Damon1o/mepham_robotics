"""The sea and the rigging: the homepage voyage, hero waves and the footer ship.

Browser behaviour (the pinned scroll) is checked by hand; these guard the markup the
script and stylesheets rely on, and the reduced-motion and no-script fallbacks.
"""
import pathlib
import re

import pytest

from api.index import SITE_CONTENT_ID

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / 'static'
def stylesheet(path):
    """A stylesheet without its comments, so a rule's selector is only its selector."""
    return re.sub(r'/\*.*?\*/', '', (STATIC / 'css' / path).read_text(encoding='utf-8'), flags=re.S)


MOTION = stylesheet('motion.css')
INDEX = stylesheet('pages/index.css')
VOYAGE = (STATIC / 'js' / 'voyage.js').read_text(encoding='utf-8')


# --- The voyage (homepage club numbers) ---------------------------------------------

def test_voyage_wraps_the_club_numbers(client, db):
    page = client.get('/').get_data(as_text=True)
    section = page[page.index('data-voyage'):page.index('</section>', page.index('data-voyage'))]
    assert section.count('data-voyage-stop') == 4
    assert section.count('class="stat-number"') == 4
    assert 'The Voyage So Far</h2>' in section
    assert 'mascot-ship.webp' in section
    assert re.search(r'<script src="/static/js/voyage\.js[^"]*" defer>', page)


def test_voyage_scenery_is_hidden_from_screen_readers(client, db):
    page = client.get('/').get_data(as_text=True)
    assert '<div class="voyage-sea" aria-hidden="true">' in page
    assert '<span class="voyage-sun rig-cog" aria-hidden="true">' in page


def test_voyage_heading_and_script_follow_site_settings(client, db):
    db['site_metadata'].insert_one({'_id': SITE_CONTENT_ID, 'values': {'home': {'stats_heading': 'Ship log'}}})
    page = client.get('/').get_data(as_text=True)
    assert 'Ship log</h2>' in page and 'The Voyage So Far' not in page

    db['site_metadata'].update_one({'_id': SITE_CONTENT_ID}, {'$set': {'values': {'home': {'show_stats': False}}}})
    page = client.get('/').get_data(as_text=True)
    assert 'data-voyage' not in page and 'voyage.js' not in page


def test_voyage_script_stands_down_for_reduced_motion():
    assert "(prefers-reduced-motion: reduce)" in VOYAGE
    assert "getAttribute('data-motion') === 'reduce'" in VOYAGE
    # The pinned layout hangs off .is-live, which only the script adds.
    assert VOYAGE.index('if (reduced || !sticky) return;') < VOYAGE.index("classList.add('is-live')")
    assert '.voyage.is-live .voyage-stage' in INDEX
    assert not re.search(r'^\.voyage\s*\{[^}]*height:', INDEX, re.M)


def test_the_old_stat_counter_does_not_fight_the_voyage(client, db):
    """script.js counts .stat-number up when it finds .stats-section; the voyage counts
    its own numbers, one at a time."""
    page = client.get('/').get_data(as_text=True)
    assert 'stats-section' not in page


# --- Heroes and the footer ----------------------------------------------------------------

@pytest.mark.parametrize('path', ['/', '/about', '/achievements', '/events', '/alumni', '/contact', '/donate'])
def test_every_hero_sits_on_the_sea(client, db, path):
    page = client.get(path).get_data(as_text=True)
    assert page.count('<div class="hero-sea" aria-hidden="true">') == 1, path
    hero = page[page.index('class="hero-image'):]
    assert hero.index('hero-sea') < hero.index('hero-content'), path


def test_team_hero_sits_on_the_sea(client, db):
    db['teams'].insert_one({'team_number': '77628A'})
    assert 'class="hero-sea"' in client.get('/team/77628A').get_data(as_text=True)


@pytest.mark.parametrize('path', ['/', '/about', '/privacy', '/credits'])
def test_footer_sea_is_on_every_page(client, db, path):
    page = client.get(path).get_data(as_text=True)
    sea = re.search(r'<div class="footer-sea" aria-hidden="true">(.*?)</div>\s*<footer>', page, re.S)
    assert sea, path
    img = re.search(r'<img\b[^>]*>', sea.group(1)).group(0)
    assert 'mascot-ship.webp' in img and 'alt=""' in img
    assert 'width="' in img and 'height="' in img and 'loading="lazy"' in img


def test_motion_stylesheet_is_linked_after_the_base_styles(client, db):
    page = client.get('/').get_data(as_text=True)
    assert page.index('css/styles.css') < page.index('css/motion.css') < page.index('css/pages/index.css')


# --- Reduced motion -----------------------------------------------------------------------

def animated_selectors(css):
    """Selectors that start an animation, outside the reduced-motion rules."""
    found = set()
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if not re.search(r'(?<![-\w])animation(?:-name)?:\s*(?!\s|none)', body):
            continue
        for selector in selectors.split(','):
            selector = ' '.join(selector.split())
            if selector and 'data-motion' not in selector:
                found.add(selector)
    return found


def stilled_selectors(css):
    found = set()
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if 'animation: none' in body:
            found.update(' '.join(s.split()) for s in selectors.split(','))
    return found


@pytest.mark.parametrize('css, only', [(MOTION, None), (INDEX, ('.voyage', '.countdown-section::'))],
                         ids=['motion.css', 'index.css'])
def test_looping_decoration_is_stilled_when_motion_is_reduced(css, only):
    """styles.css cuts animations to an instant, which leaves a loop on its last frame
    (waves pushed aside, the ship off the page); each one needs an explicit `none`, for
    the device setting and for the switch on My Account."""
    stilled = stilled_selectors(css)
    for selector in animated_selectors(css):
        if only and not selector.startswith(only):
            continue
        if 'is-landed' in selector:
            continue  # a one-off, and only the script (off when motion is reduced) sets it
        assert selector in stilled, selector
        assert f'[data-motion="reduce"] {selector}' in stilled, selector


def test_mascot_ship_is_in_the_image_manifest():
    import json
    entry = json.loads((STATIC / 'assets' / 'image-manifest.json').read_text(encoding='utf-8'))['icons/mascot_ship']
    assert (STATIC / entry['src']).is_file()
    assert entry['width'] and entry['height']
