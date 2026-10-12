"""Run the site on an in-memory database with sample content, for the accessibility check.

    python scripts/a11y_server.py [port]      # default 5099; then: node scripts/a11y.mjs

Nothing here touches a real database or outside service: get_db() is swapped for
mongomock and the API keys that would reach RobotEvents or the chatbot are dropped.
"""
import datetime as dt
import os
import pathlib
import sys

import mongomock
from bson import ObjectId

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault('SECRET_KEY', 'a11y-check-only')

from api import index  # noqa: E402  (needs the path and secret above)

for key in ('ROBOTEVENTS_API_KEY', 'ROBOTEVENTS_TOKEN', 'CHATBOT_API_KEY', 'GIVEBUTTER_CAMPAIGN_ID'):
    os.environ.pop(key, None)

db = mongomock.MongoClient()['mepham']
index.get_db = lambda: db

db['teams'].insert_many([
    {'team_number': '77628A', 'season': '2025-26', 'nickname': 'Hydra',
     'tagline': 'Precision. Power. Performance.', 'division': 'High School', 'since': 2019,
     'notebook_link': 'https://example.com/notebook', 'specs': {'drive_train': 'X-Drive', 'intake': 'Flex Wheel'},
     'members': [{'member_id': 'm1', 'name': 'Ada Lovelace', 'role': 'Captain'},
                 {'member_id': 'm2', 'name': 'Bo Diaz', 'role': 'Builder'}],
     'goals': [{'name': 'Win States', 'progress': 60}, {'name': 'Skills 200', 'progress': 25}],
     'journey': [{'date': '2019', 'title': 'Team founded', 'description': 'First season.'}]},
    {'kind': 'group', 'team_number': 'media', 'title': 'Media', 'season': '2025-26',
     'tagline': 'We tell the club story.',
     'members': [{'member_id': 'g1', 'name': 'Grace Hopper', 'role': 'Media Captain'}],
     'goals': [{'name': 'Weekly reels', 'progress': 40, 'note': 'One a week.', 'owners': ['g1']}]},
])
db['awards'].insert_one({'team_number': '77628A', 'title': 'Excellence Award', 'count': 2, 'icon': 'design_award.png'})
soon = (index.club_now() + dt.timedelta(days=10)).replace(hour=9, minute=0, second=0, microsecond=0)
db['competitions'].insert_many([
    # Fixed id: scripts/a11y.mjs checks this event's own page.
    {'_id': ObjectId('0000000000000000000a11e0'), 'name': 'Regional Qualifier', 'date': soon, 'location': 'Mepham Gym', 'kind': 'competition',
     'details': 'Doors at 7.', 'link': 'https://robotevents.com/x'},
    {'name': 'Library Robot Day', 'date': soon - dt.timedelta(days=7), 'location': 'Bellmore Library',
     'kind': 'outreach'},
])

# Fixed id: scripts/a11y.mjs checks this member's page. Public, so it renders signed out,
# and linked to Ada's roster card so the team page links to it.
db['users'].insert_one({
    '_id': ObjectId('0000000000000000000a11e1'), 'username': 'ada', 'password': b'x', 'role': 'member',
    'full_name': 'Ada Lovelace', 'profile': {
        'visibility': 'public', 'headline': 'Captain and lead programmer', 'grad_year': 2027,
        'bio': 'I write our autonomous code.\n\nI also run library demo days.',
        'skills': ['Programming', 'CAD'], 'links': [{'label': 'GitHub', 'url': 'https://github.com/example'}],
        'honors': [{'kind': 'award', 'title': 'Excellence Award', 'event': 'Regional', 'when': 'Feb 2026',
                    'link': 'https://robotevents.com/x', 'pinned': True},
                   {'kind': 'outreach', 'title': 'Library demos', 'hours': 12}],
        'photos': [{'path': 'static/assets/photos/hero.jpg', 'caption': 'At the pit'}]}})
db['teams'].update_one({'team_number': '77628A', 'members.member_id': 'm1'},
                       {'$set': {'members.$.user_id': '0000000000000000000a11e1'}})

if __name__ == '__main__':
    index.app.run(port=int(sys.argv[1]) if len(sys.argv) > 1 else 5099)
