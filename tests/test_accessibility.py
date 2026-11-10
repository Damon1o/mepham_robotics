"""Accessibility guards from the November 2026 audit.

axe in CI only sees the sample pages, so the failures it could not reach (fundraiser
badges, group layouts, signed-in pages) are pinned here against the stylesheets and markup.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = ROOT / 'static' / 'css'
JS = ROOT / 'static' / 'js'


def _luminance(colour):
    channels = [int(colour.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _mix(colour, base, share):
    """`color-mix(in srgb, colour share, base)` as a hex colour."""
    pairs = zip(*[[int(c.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)] for c in (colour, base)])
    return '#' + ''.join(f'{round(top * share + bottom * (1 - share)):02x}' for top, bottom in pairs)


# --- Colour contrast --------------------------------------------------------------------

def test_avatar_initials_are_readable_on_every_tone():
    css = (CSS / 'styles.css').read_text(encoding='utf-8')
    tones = re.findall(r'\.avatar-tone--(\w+) \{ --avatar-bg: (#\w{6}); --avatar-ink: (#\w{6}); \}', css)
    assert len(tones) >= 8
    for name, background, ink in tones:
        assert contrast(background, ink) >= 4.5, name


def test_event_kind_badges_are_readable_in_the_light_theme():
    """A badge is its kind colour as text on a 12% tint of the same colour."""
    css = (CSS / 'pages' / 'events.css').read_text(encoding='utf-8')
    light = css.split('[data-theme="dark"] .ev-k-')[0]
    kinds = re.findall(r'\.ev-k-(\w+) \{ --k: (#\w{6}); \}', light)
    assert len(kinds) >= 7
    for name, colour in kinds:
        assert contrast(colour, _mix(colour, '#ffffff', 0.12)) >= 4.5, name


@pytest.mark.parametrize('sheet, selector', [
    ('pages/group-layouts/chapters.css', '[data-theme="dark"] .gc-status'),
    ('pages/group-layouts/tracker.css', '[data-theme="dark"] .gt-mini span'),
    ('pages/resources.css', '[data-theme="dark"] .hub-event-kind'),
    ('pages/contact.css', '[data-theme="dark"] .station-status.is-open'),
    ('pages/team_editor.css', '.team-picker-extra .cta-secondary'),
])
def test_dim_text_has_a_readable_override(sheet, selector):
    """Each of these inherited a colour made for the other theme (or for a photo hero)."""
    assert selector in (CSS / sheet).read_text(encoding='utf-8')


# --- Landmarks, names and headings -------------------------------------------------------

def test_contact_page_has_one_main_landmark(client):
    page = client.get('/contact').get_data(as_text=True)
    assert page.count('<main') == 1 and page.count('</main>') == 1


def test_chat_controls_have_names(client):
    page = client.get('/').get_data(as_text=True)
    bubble = re.search(r'<button[^>]*id="chatbot-bubble"[^>]*>', page).group(0)
    assert 'aria-label=' in bubble and 'aria-expanded="false"' in bubble
    for control in ('chatbot-close', 'chatbot-send', 'chatbot-input'):
        tag = re.search(rf'<(?:button|input)[^>]*id="{control}"[^>]*>', page).group(0)
        assert 'aria-label=' in tag, control


def test_footer_titles_do_not_skip_heading_levels(client):
    """The footer's <h3>/<h4> followed an <h1> on pages with no section headings."""
    page = client.get('/safety-quiz').get_data(as_text=True)
    footer = page[page.index('<footer'):page.index('</footer>')]
    assert not re.search(r'<h[1-6]\b', footer)
    assert footer.count('<nav class="footer-col"') == 2


def test_roster_names_follow_the_section_heading(client, db):
    db['teams'].insert_one({'team_number': '77628A', 'season': '2025-26',
                            'members': [{'member_id': 'm1', 'name': 'Ada Lovelace', 'role': 'Captain'}]})
    page = client.get('/team/77628A').get_data(as_text=True)
    assert '<h3 class="roster-name">' in page and '<h4 class="roster-name">' not in page


# --- Motion and scripts ---------------------------------------------------------------------

def test_sections_are_only_hidden_when_scripts_run():
    css = (CSS / 'styles.css').read_text(encoding='utf-8')
    assert '.js .fade-in-section {' in css
    assert not re.search(r'^\.fade-in-section\s*\{', css, re.M)
    theme = (JS / 'theme.js').read_text(encoding='utf-8')
    assert "classList.add('js')" in theme and 'MephamRevealReady' in theme
    assert 'window.MephamRevealReady = true' in (JS / 'script.js').read_text(encoding='utf-8')


def test_device_reduced_motion_setting_is_honoured():
    css = (CSS / 'styles.css').read_text(encoding='utf-8')
    block = css.split('@media (prefers-reduced-motion: reduce) {\n    *,', 1)
    assert len(block) == 2, 'no site-wide reduced-motion rule'
    assert 'scroll-behavior: auto !important' in block[1][:400]


def test_every_font_token_in_use_is_defined():
    css = (CSS / 'styles.css').read_text(encoding='utf-8')
    root = css[css.index(':root'):css.index('}', css.index(':root'))]
    for token in set(re.findall(r'var\((--font-[\w-]+)', css)):
        assert f'{token}:' in root, token
