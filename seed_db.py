import os
import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# --- MongoDB Connection ---
client = MongoClient(os.getenv('MONGO_URI'))
db = client['mepham']

def seed_data():
    # 1. Site Metadata (Stats)
    site_metadata = db['site_metadata']
    site_metadata.update_one(
        {'_id': 'global_stats'},
        {'$set': {
            'teams_count': 2,
            'members_count': 32,
            'awards_count': 3,
            'hours_built': 100
        }},
        upsert=True
    )
    print("Site metadata seeded.")

    # 2. Upcoming Competitions
    competitions = db['competitions']
    # Clear existing and add new
    competitions.delete_many({})
    competitions.insert_one({
        'name': 'Southern New York State Championship',
        'date': datetime.datetime(2026, 3, 15, 7, 30, 0)
    })
    print("Competitions seeded.")

    # 3. All-Time Awards
    awards_col = db['awards']
    awards_col.delete_many({})
    initial_awards = [
        {'title': 'World Championship', 'count': 0, 'icon': 'world_championship.png', 'border': 'gold', 'shimmer': True},
        {'title': 'Triple Crown', 'count': 0, 'icon': 'triple_crown.png', 'border': 'purple', 'shimmer': True},
        {'title': 'Excellence', 'count': 0, 'icon': 'exellence_award.png'},
        {'title': 'Champions', 'count': 0, 'icon': 'tournament_champions.png'},
        {'title': 'Skills Champion', 'count': 0, 'icon': 'robot_skills_champion.png'},
        {'title': 'Finalists', 'count': 1, 'icon': 'tournament_finalists.png'},
        {'title': 'Design', 'count': 1, 'icon': 'design_award.png'},
        {'title': 'Judges', 'count': 1, 'icon': 'judges_award.png'},
        {'title': 'Innovate', 'count': 0, 'icon': 'innovate_award.png'},
        {'title': 'Amaze', 'count': 0, 'icon': 'amaze_award.png'},
        {'title': 'Create', 'count': 0, 'icon': 'create_award.png', 'border': 'red'},
        {'title': 'Sportsmanship', 'count': 0, 'icon': 'sportsmanship.png', 'border': 'green'},
    ]
    awards_col.insert_many(initial_awards)
    print("Awards seeded.")

if __name__ == '__main__':
    seed_data()
