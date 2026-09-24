"""Resize and re-encode the site's images, and write the manifest templates use.

Run from the repository root after adding or replacing a photo:

    python scripts/optimize_images.py

What it does (safe to re-run; it never re-encodes an already-small JPEG):

- Team photos (static/assets/photos/carousel*.jpg): the JPEG is scaled down to
  JPEG_WIDTH wide and re-encoded, replacing the original. That JPEG is the
  fallback for old browsers and the CSS hero backgrounds. WebP variants are
  written at each of WEBP_WIDTHS (capped at the photo's own width) for srcset.
- hero.png: a JPEG and a WebP copy at native size. The PNG itself is kept.
- Chatbot avatar and favicons: small square copies.
- Award icons: resized in place to ICON_SIZE px, keeping the filename because
  the database stores icons by name.

The manifest (static/assets/image-manifest.json) records every variant's real
pixel size so templates can emit width/height and accurate srcset descriptors.
Requires Pillow (a dev-only dependency; production never imports it).
"""
import json
import pathlib

from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'static' / 'assets'
MANIFEST = ASSETS / 'image-manifest.json'

JPEG_WIDTH = 1200
JPEG_QUALITY = 82
WEBP_WIDTHS = (480, 960, 1440)
WEBP_QUALITY = 80
ICON_SIZE = 128


def rel(path):
    return path.relative_to(ROOT / 'static').as_posix()


def open_rgb(path):
    image = ImageOps.exif_transpose(Image.open(path))
    return image.convert('RGB')


def resized(image, width):
    if image.width <= width:
        return image.copy()
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.LANCZOS)


def save_jpeg(image, path):
    image.save(path, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True, subsampling='4:2:0')


def save_webp(image, path):
    image.save(path, 'WEBP', quality=WEBP_QUALITY, method=6)


def photo(path):
    """Shrink the JPEG in place if it is oversized, then write WebP variants."""
    image = open_rgb(path)
    if image.width > JPEG_WIDTH:
        image = resized(image, JPEG_WIDTH)
        save_jpeg(image, path)
    source = open_rgb(path)
    webp = []
    widths = sorted({min(w, source.width) for w in WEBP_WIDTHS})
    for width in widths:
        variant = resized(source, width)
        out = path.with_name(f'{path.stem}-{variant.width}.webp')
        save_webp(variant, out)
        webp.append({'src': rel(out), 'width': variant.width, 'height': variant.height})
    return {'src': rel(path), 'width': source.width, 'height': source.height, 'webp': webp}


def hero(path):
    image = open_rgb(path)
    jpg = path.with_suffix('.jpg')
    webp = path.with_suffix('.webp')
    save_jpeg(image, jpg)
    save_webp(image, webp)
    return {'src': rel(jpg), 'width': image.width, 'height': image.height,
            'webp': [{'src': rel(webp), 'width': image.width, 'height': image.height}]}


def square(path, size, out_stem, fmt_list, focus_y=0.35):
    """Centre-crop to a square (biased towards the top for portraits) and resize."""
    image = ImageOps.exif_transpose(Image.open(path))
    side = min(image.size)
    left = (image.width - side) // 2
    top = round((image.height - side) * focus_y)
    image = image.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    outputs = {}
    for fmt in fmt_list:
        out = path.with_name(f'{out_stem}.{fmt}')
        if fmt == 'webp':
            save_webp(image.convert('RGB'), out)
        elif fmt == 'jpg':
            save_jpeg(image.convert('RGB'), out)
        else:
            image.save(out, 'PNG', optimize=True)
        outputs[fmt] = rel(out)
    return {'width': size, 'height': size, **outputs}


def padded_icon(path, size, out_name):
    """Fit a non-square logo into a transparent square (favicons)."""
    logo = Image.open(path).convert('RGBA')
    logo.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    canvas.paste(logo, ((size - logo.width) // 2, (size - logo.height) // 2), logo)
    out = path.with_name(out_name)
    canvas.save(out, 'PNG', optimize=True)
    return rel(out)


def award_icon(path):
    image = Image.open(path)
    if max(image.size) <= ICON_SIZE:
        return
    image = image.convert('RGBA')
    image.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    image.save(path, 'PNG', optimize=True)


def main():
    manifest = {}
    for path in sorted((ASSETS / 'photos').glob('carousel*.jpg')):
        manifest[f'photos/{path.stem}'] = photo(path)
    manifest['photos/hero'] = hero(ASSETS / 'photos' / 'hero.png')

    icons = ASSETS / 'icons'
    manifest['icons/steven'] = square(icons / 'steven.jpg', 96, 'steven-96', ('webp', 'jpg'))
    manifest['icons/favicon'] = {
        'favicon': padded_icon(icons / 'mephamrobotics.png', 32, 'favicon-32.png'),
        'apple_touch': padded_icon(icons / 'mephamrobotics.png', 180, 'apple-touch-icon.png'),
    }
    for path in sorted(icons.glob('*_award.png')) + [icons / name for name in (
            'robot_skills_champion.png', 'sportsmanship.png', 'tournament_champions.png',
            'tournament_finalists.png', 'triple_crown.png', 'world_championship.png')]:
        award_icon(path)

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    total = sum(p.stat().st_size for p in ASSETS.rglob('*') if p.is_file())
    print(f'wrote {MANIFEST.relative_to(ROOT)}; static/assets is now {total / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
