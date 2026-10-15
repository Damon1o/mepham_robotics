"""Hidden /science/ lab: only reachable by typing the address, never linked or indexed."""
import pathlib

import pytest

TYPED = {'Sec-Fetch-Site': 'none', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-User': '?1'}
ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path', ['/science/', '/science'])
def test_typed_address_opens_the_lab(client, path):
    resp = client.get(path, headers=TYPED)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Interactions between' in html
    assert 'How do <strong>charge</strong> and <strong>distance</strong>' in html
    assert 'How to get there' in html
    assert 'href="/donate"' in html
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'
    assert resp.headers['Cache-Control'] == 'no-store'
    assert resp.headers['Referrer-Policy'] == 'no-referrer'


@pytest.mark.parametrize('site', [None, 'same-origin', 'same-site', 'cross-site'])
@pytest.mark.parametrize('path', ['/science/', '/science'])
def test_followed_links_and_scripts_get_a_plain_404(client, site, path):
    headers = {'Sec-Fetch-Site': site} if site else {}
    resp = client.get(path, headers=headers)
    assert resp.status_code == 404
    assert 'Interactions between' not in resp.get_data(as_text=True)


def test_nothing_points_at_it(client):
    assert '/science' not in client.get('/sitemap.xml').get_data(as_text=True)
    assert '/science' not in client.get('/robots.txt').get_data(as_text=True)
    for page in ('/', '/about', '/donate'):
        assert '/science' not in client.get(page).get_data(as_text=True)
    others = [p for p in (ROOT / 'templates').rglob('*.html') if p.name != 'science.html']
    assert not [p.name for p in others if '/science' in p.read_text(encoding='utf-8')]
