"""Swipe rows: admin messages and subscribers drag aside for their actions.

The dragging happens in the browser; these guard the wiring: the admin page
loads the component, every swiped row has the element it attaches to, and a
full-swipe delete still goes through the fuse instead of deleting at once.
"""
import datetime
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = ROOT / 'static' / 'js'


@pytest.fixture
def admin_client(client, make_user):
    make_user(username='root', password='hunter2hunter2', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'hunter2hunter2'})
    return client


@pytest.fixture
def inbox(db):
    db['contact_messages'].insert_one({
        'name': 'Ada Lovelace', 'email': 'ada@example.com', 'message': 'Hello team', 'status': 'new',
        'created_at': datetime.datetime(2026, 9, 17, 12, 0, 0),
    })
    db['newsletter_subscribers'].insert_one({'email': 'grace@example.com', 'created_at': datetime.datetime(2026, 9, 18)})


def test_admin_page_loads_swipe_rows(admin_client, inbox):
    html = admin_client.get('/admin').get_data(as_text=True)
    assert 'css/swipe-row.css' in html
    # Before admin.js, which attaches the rows on DOMContentLoaded.
    assert html.index('js/swipe-row.js') < html.index('js/admin.js')
    assert 'class="message-summary"' in html
    assert 'class="subscriber-row"' in html


def test_swiped_deletes_light_a_fuse():
    admin = (JS / 'admin.js').read_text(encoding='utf-8')
    attached = re.findall(r'SwipeRow\.attach\((.*?)\n\s*\}\);', admin, re.S)
    assert len(attached) == 2
    for call in attached:
        assert re.search(r"fuse: [`']", call), call[:120]
    source = (JS / 'swipe-row.js').read_text(encoding='utf-8')
    assert 'Fuse.arm(' in source
    assert 'onUndo: reset' in source
