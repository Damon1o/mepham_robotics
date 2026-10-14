"""Send the Discord bot's slash commands to Discord.

Run once after setting the bot up, and again whenever COMMANDS in api/discord_bot.py
changes. Reads DISCORD_APP_ID and DISCORD_BOT_TOKEN from the environment or .env:
    python scripts/register_discord_commands.py
"""
import pathlib
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')

from api import discord_bot  # noqa: E402

ok, detail = discord_bot.register_commands()
print(detail)
sys.exit(0 if ok else 1)
