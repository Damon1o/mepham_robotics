import sys
import os

# Make sure the root of the project is in the path so app.py can be found
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app

# Vercel looks for a variable named `app` in this file
