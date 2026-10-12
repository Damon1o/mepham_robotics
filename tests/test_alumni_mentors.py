"""Alumni page: class and school filters, mentors' "Ask me about" topics and the Ask an alum form."""
import re

import pytest

from api import site_content


@pytest.fixture
def admin(client, make_user):
    make_user(username='root', password='root-password', email='root@example.com', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'root-password'})
    return client


def alum(**overrides):
    row = {'name': 'Ada Lovelace', 'class_year': 2024, 'path': 'computing', 'school': 'Stony Brook University',
           'study': 'Computer Science', 'now': '', 'team': 'Programmer', 'quote': '', 'photo': None, 'link': '',
           'mentor': False, 'topics': '', 'hidden': False}
    row.update(overrides)
    return row


def save(client, key, value):
    return client.post('/admin/api/site', json={'key': key, 'value': value})


def test_topics_split_on_commas_and_mentors_are_listed():
    view = site_content.alumni_view([
        alum(mentor=True, topics='CAD, picking a college, ,  internships'),
        alum(name='Grace Hopper', topics='ignored unless asked'),
    ])
    assert [p['name'] for p in view['mentors']] == ['Ada Lovelace']
    ada = next(p for p in view['people'] if p['name'] == 'Ada Lovelace')
    assert ada['topic_list'] == ['CAD', 'picking a college', 'internships']


def test_topics_are_capped():
    view = site_content.alumni_view([alum(mentor=True, topics=','.join(f't{n}' for n in range(10)))])
    assert len(view['people'][0]['topic_list']) == site_content.ALUMNI_TOPICS_SHOWN


def test_mentor_card_shows_topics_and_an_ask_button(admin):
    assert save(admin, 'alumni.people', [alum(mentor=True, topics='CAD, college essays'),
                                         alum(name='Grace Hopper', class_year=2025, school='MIT')]).status_code == 200
    html = admin.get('/alumni').get_data(as_text=True)
    assert 'Ask me about' in html and '<li>CAD</li><li>college essays</li>' in html
    assert 'data-ask="Ada Lovelace"' in html and 'Ask Ada' in html
    assert 'data-ask="Grace Hopper"' not in html
    # The ask form offers only mentors.
    form = html.split('data-alumni-ask', 1)[1].split('</form>', 1)[0]
    assert 'value="Ada Lovelace"' in form and 'Grace Hopper' not in form
    assert 'Open to questions <span>1</span>' in html


def test_cards_carry_what_the_filters_match_on(admin):
    save(admin, 'alumni.people', [alum(), alum(name='Grace Hopper', class_year=2025, school=' MIT ')])
    html = admin.get('/alumni').get_data(as_text=True)
    assert re.search(r'data-class-year="2025"\s+data-school="mit"', html)
    assert '<option value="2024" data-tag="1">Class of 2024</option>' in html
    assert '<option value="mit" data-tag="1">MIT</option>' in html


def test_no_mentors_means_no_ask_form_or_chip(admin):
    save(admin, 'alumni.people', [alum()])
    html = admin.get('/alumni').get_data(as_text=True)
    assert 'data-alumni-ask' not in html and 'data-alumni-mentors' not in html


def test_ask_form_can_be_switched_off(admin):
    save(admin, 'alumni.people', [alum(mentor=True)])
    save(admin, 'alumni.ask_show', False)
    html = admin.get('/alumni').get_data(as_text=True)
    assert 'data-alumni-ask' not in html and 'data-ask=' not in html
    assert 'data-mentor' in html  # the chip still finds mentors


def test_single_class_and_school_get_no_menus(admin):
    save(admin, 'alumni.people', [alum()])
    html = admin.get('/alumni').get_data(as_text=True)
    assert 'data-alumni-class' not in html and 'data-alumni-school' not in html
