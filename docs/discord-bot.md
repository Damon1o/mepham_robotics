# Discord bot

The bot runs inside the site's Vercel deployment. Discord POSTs each slash command,
button press and autocomplete to `/api/discord/interactions`; nothing runs between requests.

## Setup

1. In the [Discord Developer Portal](https://discord.com/developers/applications), open the app.
2. Add these to the Vercel project's environment variables (and `.env` for local runs):

   | Variable | Where it is in the portal |
   | --- | --- |
   | `DISCORD_APP_ID` | General Information → Application ID |
   | `DISCORD_PUBLIC_KEY` | General Information → Public Key |
   | `DISCORD_CLIENT_SECRET` | OAuth2 → Client Secret (for linking accounts) |
   | `DISCORD_BOT_TOKEN` | Bot → Token (only for registering commands) |

3. Redeploy, then set **General Information → Interactions Endpoint URL** to
   `https://<site>/api/discord/interactions`. Discord sends a test ping; saving fails if the keys are wrong.
4. Under **OAuth2 → Redirects**, add `https://<site>/account/discord/callback`.
5. Register the commands: `python scripts/register_discord_commands.py`
   (global commands can take a few minutes to show up).
6. Invite the bot: OAuth2 → URL Generator, scopes `bot` and `applications.commands`, no permissions needed.

Members link their Discord from **Account → Discord**.

## Commands

| Command | Who | What |
| --- | --- | --- |
| `/events`, `/event`, `/next` | anyone | Calendar, one event with RSVP buttons, competition countdown |
| `/rsvp` | linked | Going / maybe / can't go / clear |
| `/signin`, `/signout`, `/attendance` | linked | Meeting sign-in sheet (same window as the Member Hub) |
| `/signups`, `/signup` | anyone sees open spots; linked can sign up | Sign-up sheets like bake sales |
| `/team`, `/member`, `/alumni` | anyone (member pages follow their visibility) | Lookups |
| `/hub`, `/link` | anyone | Links |
| `/asksteven` | anyone | Asks Steven (the site chatbot, `CHATBOT_API_KEY`) |

`/asksteven` limits: a 30-second cooldown per person, 10 questions per person per hour,
and 40 per 10 minutes across the whole server (`STEVEN_*` in `api/index.py`).
