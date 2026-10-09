"""How search engines and AI assistants see the club: schema.org data, canonical links, /llms.txt."""
import json
import re

import pytest



@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def save(client, key, value):
    response = client.post('/admin/api/site', json={'key': key, 'value': value})
    assert response.status_code == 200, response.get_data(as_text=True)


def jsonld(page):
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    return json.loads(block.group(1))


def test_every_page_describes_the_club(client):
    for path in ('/', '/about', '/contact'):
        data = jsonld(client.get(path).get_data(as_text=True))
        assert data['@type'] == 'SportsTeam'
        assert data['name'] == 'Mepham Robotics Club'
        assert 'Team 77628' in data['alternateName']
        assert data['location']['address']['addressLocality'] == 'Bellmore'
        assert 'world-class' in data['description']
        assert 'https://instagram.com/mephamrobotics' in data['sameAs']


def test_homepage_title_says_robotics_and_where(client):
    title = re.search(r'<title>(.*?)</title>', client.get('/').get_data(as_text=True)).group(1)
    assert title == 'Mepham Robotics Club | VEX Robotics Team 77628 in Bellmore, NY'


def test_canonical_drops_the_query(client):
    page = client.get('/about?utm_source=x').get_data(as_text=True)
    assert '<link rel="canonical" href="http://localhost/about">' in page


def test_admin_text_cannot_break_out_of_the_data_block(admin, client):
    save(admin, 'general.ai_summary', 'Best team </script><script>alert(1)</script>')
    page = client.get('/').get_data(as_text=True)
    assert '</script><script>alert(1)' not in page
    assert jsonld(page)['description'].startswith('Best team </script>')


def test_llms_txt_summarises_the_club(client, db):
    db['teams'].insert_one({'team_number': '77628A', 'nickname': 'Gearheads', 'season': '2026-27'})
    db['awards'].insert_one({'title': 'Excellence Award', 'count': 2})
    response = client.get('/llms.txt')
    assert response.status_code == 200 and response.mimetype == 'text/plain'
    body = response.get_data(as_text=True)
    assert body.startswith('# Mepham Robotics Club\n\n> Mepham Robotics is a world-class')
    assert 'Bellmore, Long Island, NY' in body
    assert '77628A (Gearheads)' in body
    assert '2× Excellence Award' in body
    assert '/team/77628A' in body
    assert '/resources' not in body


def test_llms_txt_follows_site_settings(admin, client):
    save(admin, 'general.ai_summary', 'We build robots.')
    save(admin, 'general.town', '')
    body = client.get('/llms.txt').get_data(as_text=True)
    assert '> We build robots.' in body
    assert ', ,' not in body
    title = re.search(r'<title>(.*?)</title>', client.get('/').get_data(as_text=True)).group(1)
    assert title.endswith('Team 77628')
