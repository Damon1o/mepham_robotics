import sys
import os

# Add the project root to the path so app.py and all its imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel looks for a variable named `app` in this file
handler = app
