"""The 404 page doubles as Hat Toss, a ring toss game (static/js/hat-toss.js)."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME_JS = (ROOT / 'static' / 'js' / 'hat-toss.js').read_text(encoding='utf-8')


def test_missing_page_serves_the_game_with_a_404(client):
    resp = client.get('/this-page-does-not-exist')
    assert resp.status_code == 404
    page = resp.get_data(as_text=True)
    assert 'data-hat-toss' in page
    assert 'class="ht-canvas"' in page
    assert 'js/hat-toss.js' in page
    assert 'css/pages/hat-toss.css' in page
    # The way out stays above the game.
    assert page.index('Go Home') < page.index('data-hat-toss')


def test_missing_page_keeps_inline_script_out(client):
    page = client.get('/nope').get_data(as_text=True)
    for attributes, body in re.findall(r'<script\b([^>]*)>(.*?)</script>', page, re.S):
        assert 'src=' in attributes or not body.strip()


def test_json_callers_still_get_json(client):
    resp = client.get('/api/nope')
    assert resp.status_code == 404
    assert resp.get_json() == {'error': 'Not found.'}


def test_pickelhaube_is_the_starter_hat():
    hats = re.findall(r"id: '([a-z]+)', name: '[^']+'.*?unlock: (\d+)", GAME_JS, re.S)
    assert hats[0] == ('pickelhaube', '0')
    unlocks = [int(u) for _, u in hats]
    assert unlocks == sorted(unlocks) and len(set(unlocks)) == len(unlocks)
    assert len(hats) >= 10


def test_every_hat_has_a_history_note_and_a_profile_that_ends_at_a_tip():
    hats = GAME_JS.split('var HATS = [')[1].split('var HAT_BY_ID')[0]
    blocks = hats.split("id: '")[1:]
    assert len(blocks) >= 10
    for block in blocks:
        assert "fact: '" in block
        profile = re.search(r'profile: \[(.*?)\]\],', block, re.S).group(1)
        assert profile.startswith('[0,') and re.search(r'\[1, [\d.]+$', profile)


def test_progress_storage_is_guarded():
    # Private windows throw on localStorage; the game must still load.
    for line in GAME_JS.splitlines():
        if 'localStorage.' in line:
            assert line.strip().startswith('try {') or 'JSON.parse(localStorage' in line, line
    assert 'try {\n            var saved = JSON.parse(localStorage' in GAME_JS
