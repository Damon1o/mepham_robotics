import pytest


@pytest.fixture
def admin_client(client, make_user):
    make_user(username='root', role='admin')
    client.post('/login', data={'username': 'root', 'password': 'correct-horse'})
    return client


BASE_FORM = {
    'team_id': '',
    'team_number': '77628A',
    'nickname': 'Hydra',
    'tagline': 'Precision.',
    'drive_train': 'X-Drive',
    'lift_system': '',
    'intake': '',
    'auton_consistency': '',
    'notebook_link': 'https://example.com/nb',
}


def save(admin_client, **extra):
    data = dict(BASE_FORM)
    data.update(extra)
    return admin_client.post('/admin/save-team', data=data, follow_redirects=False)


def test_new_profile_fields_persist(admin_client, db):
    save(admin_client, season='2025-26', division='High School', since='2019',
         worlds_appearances='2', robotevents_number='77628A')
    team = db['teams'].find_one({'team_number': '77628A'})
    assert team['season'] == '2025-26'
    assert team['division'] == 'High School'
    assert team['since'] == 2019
    assert team['worlds_appearances'] == 2
    assert team['robotevents_number'] == '77628A'


def test_blank_optional_fields_are_not_stored(admin_client, db):
    save(admin_client, season='', division='', since='', worlds_appearances='',
         robotevents_number='')
    team = db['teams'].find_one({'team_number': '77628A'})
    for field in ('season', 'division', 'since', 'worlds_appearances', 'robotevents_number'):
        assert field not in team, f'{field} should be absent, not empty or zero'


def test_non_numeric_year_is_ignored(admin_client, db):
    save(admin_client, since='not-a-year')
    team = db['teams'].find_one({'team_number': '77628A'})
    assert 'since' not in team


def test_member_roles_subteam_and_tenure_persist(admin_client, db):
    save(admin_client,
         member_name_0='Ada Lovelace', member_role_0='Captain',
         member_roles_0='Captain, Programmer', member_subteam_0='Programming',
         member_since_0='2022', member_user_0='', member_photo_path_0='static/x.png')
    member = db['teams'].find_one({'team_number': '77628A'})['members'][0]
    assert member['roles'] == ['Captain', 'Programmer']
    assert member['subteam'] == 'Programming'
    assert member['since'] == 2022
    assert member['role'] == 'Captain'


def test_member_optional_keys_absent_when_blank(admin_client, db):
    save(admin_client, member_name_0='Bo Diaz', member_role_0='Builder',
         member_roles_0='  ,  ', member_subteam_0='', member_since_0='',
         member_user_0='', member_photo_path_0='static/x.png')
    member = db['teams'].find_one({'team_number': '77628A'})['members'][0]
    for field in ('roles', 'subteam', 'since'):
        assert field not in member


def test_journey_milestones_persist(admin_client, db):
    save(admin_client, journey_date_0='2019', journey_title_0='Team founded',
         journey_description_0='First season.')
    journey = db['teams'].find_one({'team_number': '77628A'})['journey']
    assert journey == [{'date': '2019', 'title': 'Team founded', 'description': 'First season.'}]


def test_existing_team_keeps_uploaded_files_on_edit(admin_client, db):
    save(admin_client, season='2025-26')
    team = db['teams'].find_one({'team_number': '77628A'})
    db['teams'].update_one({'_id': team['_id']},
                           {'$set': {'hero_image': 'https://blob/hero.png',
                                     'stl_path': 'https://blob/robot.stl'}})

    save(admin_client, team_id=str(team['_id']), season='2025-26', nickname='Hydra II')

    updated = db['teams'].find_one({'_id': team['_id']})
    assert updated['nickname'] == 'Hydra II'
    assert updated['hero_image'] == 'https://blob/hero.png'
    assert updated['stl_path'] == 'https://blob/robot.stl'
