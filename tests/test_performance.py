"""Page weight guards: image sizes, responsive markup, deferred chatbot libraries."""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / 'static'
MANIFEST = json.loads((STATIC / 'assets' / 'image-manifest.json').read_text(encoding='utf-8'))


# --- The optimised files themselves ---------------------------------------------

def test_manifest_points_at_real_files():
    for key, entry in MANIFEST.items():
        if 'src' not in entry:
            continue
        assert (STATIC / entry['src']).is_file(), key
        for variant in entry.get('webp', []):
            assert (STATIC / variant['src']).is_file(), variant['src']


@pytest.mark.parametrize('path', sorted((STATIC / 'assets' / 'photos').glob('carousel*')),
                         ids=lambda p: p.name)
def test_team_photos_stay_small(path):
    """The originals were 2.4-2.9 MB each; re-run scripts/optimize_images.py
    after adding a photo rather than committing a camera original."""
    assert path.stat().st_size < 400_000, f'{path.name} is {path.stat().st_size // 1024} KB'


def test_award_icons_are_icon_sized():
    from struct import unpack
    for name in ('design_award.png', 'world_championship.png', 'judges_award.png'):
        header = (STATIC / 'assets' / 'icons' / name).read_bytes()[16:24]
        width, height = unpack('>II', header)
        assert max(width, height) <= 128, name


# --- Markup ---------------------------------------------------------------------------

def test_carousel_serves_webp_with_real_widths(client):
    page = client.get('/').get_data(as_text=True)
    sources = re.findall(r'<source type="image/webp" sizes="[^"]+"\s+srcset="([^"]+)"', page)
    assert len(sources) >= 10
    for srcset in sources:
        for candidate in srcset.split(', '):
            url, width = candidate.rsplit(' ', 1)
            assert url.endswith('.webp') or '.webp?' in url
            assert re.fullmatch(r'\d+w', width)


@pytest.mark.parametrize('path', ['/', '/about', '/login', '/achievements', '/contact', '/donate'])
def test_every_image_has_intrinsic_size(client, db, path):
    db['awards'].insert_one({'title': 'Design Award', 'icon': 'design_award.png', 'count': 1})
    page = client.get(path).get_data(as_text=True)
    for tag in re.findall(r'<img\b[^>]*>', page):
        if 'sponsor-logo-img' in tag:
            continue  # uploaded logos: dimensions unknown, lazily loaded instead
        assert 'width="' in tag and 'height="' in tag, tag


def test_only_the_login_visual_loads_eagerly(client):
    page = client.get('/login').get_data(as_text=True)
    assert 'fetchpriority="high"' in page
    home = client.get('/').get_data(as_text=True)
    for tag in re.findall(r'<img\b[^>]*>', home):
        assert 'loading="lazy"' in tag, tag


def test_hero_backgrounds_prefer_webp_with_a_jpeg_fallback():
    for page in ('index', 'about', 'achievements', 'contact', 'resources'):
        css = (STATIC / 'css' / 'pages' / f'{page}.css').read_text(encoding='utf-8')
        assert "type('image/webp')" in css, page
        assert 'hero.png' not in css, page


def test_social_preview_uses_the_small_jpeg(client):
    page = client.get('/').get_data(as_text=True)
    og = re.search(r'<meta property="og:image" content="([^"]+)"', page).group(1)
    assert '/assets/photos/hero.jpg' in og


# --- Scripts ------------------------------------------------------------------------------

def test_markdown_libraries_are_not_loaded_on_every_page(client):
    page = client.get('/').get_data(as_text=True)
    assert 'marked.min.js' not in page
    assert 'purify.min.js' not in page
    script = (STATIC / 'js' / 'script.js').read_text(encoding='utf-8')
    assert 'function loadRenderer' in script
    # The fail-closed rule from round 2 must survive the lazy loading.
    assert 'window.marked && window.DOMPurify' in script


def test_error_pages_do_not_block_on_scripts(client):
    page = client.get('/no-such-page').get_data(as_text=True)
    for tag in re.findall(r'<script\b[^>]*\bsrc=[^>]*>', page):
        if 'theme.js' in tag:
            continue  # must run before first paint
        assert 'defer' in tag, tag
