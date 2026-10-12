"""Donate page: fundraisers running now (with goal progress) and where the money goes."""
import re

import pytest

from api import site_content

FUTURE = '2099-10-12T10:00'
PAST = '2001-01-01T10:00'


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def save(client, key, value):
    return client.post('/admin/api/site', json={'key': key, 'value': value})


# --- Spending: the pure helper -------------------------------------------------------

def test_spending_groups_by_season_newest_first_in_category_order():
    rows = [{'season': '2024-25', 'category': 'travel', 'amount': 300},
            {'season': '2025-26', 'category': 'fees', 'amount': 250},
            {'season': '2025-26', 'category': 'parts', 'amount': 500},
            {'season': '2025-26', 'category': 'parts', 'amount': 250},  # adds up
            {'season': '2025-26', 'category': 'nonsense', 'amount': 99},  # unknown: skipped
            {'season': '2023-24', 'category': 'other', 'amount': 0}]  # nothing spent: season dropped
    seasons = site_content.spending_seasons(rows)
    assert [s['season'] for s in seasons] == ['2025-26', '2024-25']
    latest = seasons[0]
    assert latest['total'] == 1000
    assert [(p['key'], p['amount'], p['percent'], p['slot']) for p in latest['parts']] == [
        ('parts', 750, 75, 1), ('fees', 250, 25, 2)]
    # A category keeps its colour slot whichever others are present.
    assert seasons[1]['parts'][0]['slot'] == 3


def test_spending_ignores_junk_rows():
    assert site_content.spending_seasons(None) == []
    assert site_content.spending_seasons([{'season': '', 'category': 'parts', 'amount': 5},
                                          {'season': '2025-26', 'category': 'parts', 'amount': 'lots'}]) == []


# --- Spending: settings and page -----------------------------------------------------

def test_admin_saves_spending_and_the_page_draws_it(admin):
    rows = [{'season': '2025-26', 'category': 'parts', 'amount': 1200},
            {'season': '2025-26', 'category': 'travel', 'amount': 400}]
    assert save(admin, 'donate.spending', rows).status_code == 200
    html = admin.get('/donate').get_data(as_text=True)
    assert 'Where the Money Goes' in html
    assert '2025-26 season' in html and '$1,600' in html
    assert re.search(r'Robot parts</span>\s*<span class="dn-spend-amount">\$1,200 · 75%', html)
    assert 'style="--share: 1200"' in html


def test_season_must_look_like_a_season(admin):
    resp = save(admin, 'donate.spending', [{'season': 'last year', 'category': 'parts', 'amount': 5}])
    assert resp.status_code == 400


def test_spending_can_be_switched_off(admin):
    save(admin, 'donate.spending', [{'season': '2025-26', 'category': 'parts', 'amount': 10}])
    save(admin, 'donate.show_spending', False)
    assert 'dn-spend' not in admin.get('/donate').get_data(as_text=True)


def test_no_spending_rows_means_no_section(client):
    assert 'id="spending"' not in client.get('/donate').get_data(as_text=True)


# --- Fundraisers running now ---------------------------------------------------------

def entry(**overrides):
    row = {'name': 'Bake Sale', 'starts': FUTURE, 'ends': '', 'location': 'Main lobby', 'description': '',
           'image': None, 'link_label': '', 'link_url': '', 'goal': None, 'raised': None,
           'featured': False, 'hidden': False}
    row.update(overrides)
    return row


def test_running_fundraisers_show_goal_progress(admin):
    save(admin, 'fundraisers.entries', [
        entry(name='Car Wash', goal=2000, raised=500),
        entry(name='Secret Plan', hidden=True),
        entry(name='Last Spring', starts=PAST),
    ])
    html = admin.get('/donate').get_data(as_text=True)
    section = html.split('id="fundraisers"', 1)[1].split('</section>', 1)[0]
    assert 'Car Wash' in section
    assert '<progress max="100" value="25"' in section
    assert '$500</strong> of $2,000' in section
    assert 'Secret Plan' not in section and 'Last Spring' not in section


def test_no_running_fundraisers_means_no_section(client):
    assert 'id="fundraisers"' not in client.get('/donate').get_data(as_text=True)
