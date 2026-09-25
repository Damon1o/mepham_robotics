# Mepham Robotics Club Website

![Mepham Robotics](static/assets/icons/mephamrobotics.png)

## Build. Code. Compete.

The official site for the **Mepham Robotics Club** (Team 77628), a student-led team from Wellington C. Mepham High
School competing in the VEX V5 Robotics Competition.

## Tech Stack

- **Flask 3** on Python, deployed as a Vercel function (`api/index.py`)
- **MongoDB** for teams, awards, competitions, users, contact messages, and newsletter subscribers
- **Vercel Blob** for uploaded hero images, member photos, sponsor logos, and STL models
- **Jinja2** templates with plain CSS and vanilla JavaScript — no build step
- Fonts: [Balsamiq Sans](https://fonts.google.com/specimen/Balsamiq+Sans) and
  [Space Mono](https://fonts.google.com/specimen/Space+Mono)

## Project Structure

```text
api/index.py            # The Flask application: routes, auth, admin, JSON APIs
api/robotevents.py      # Cached RobotEvents v2 client for the team pages
templates/              # Jinja2 templates (base.html holds the site chrome)
  partials/             # Shared fragments
static/css/styles.css   # Global design system + dark theme
static/css/pages/       # One stylesheet per page — no styles live in templates
static/js/script.js     # Site-wide behaviour (nav, search, forms, chatbot, animations)
static/js/theme.js      # Theme bootstrap, loaded before first paint
static/js/team.js       # Team page: live skills panel, event results, STL viewer
static/js/admin.js      # Admin dashboard behaviour
tests/                  # pytest suite, backed by mongomock
docs/superpowers/       # Design specs and implementation plans
```

## Running Locally

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements-dev.txt
cp .env.example .env    # then fill in MONGO_URI at minimum
python api/index.py
```

The app reads configuration from `.env` and serves on <http://127.0.0.1:5000>. Set `FLASK_DEBUG=1` to get the
Werkzeug debugger; it is off by default because it executes code from the browser.

Python 3.12 is the target (`.python-version`); Vercel deploys with the Flask framework preset pinned in
`vercel.json`. Do not add a catch-all rewrite there: the preset routes requests itself, and a rewrite to
`/api/index` breaks every path.

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `MONGO_URI` | yes | MongoDB connection string |
| `SECRET_KEY` | yes in production | Signs the session cookie. Startup fails on Vercel without it. |
| `BLOB_READ_WRITE_TOKEN` | for uploads | Vercel Blob token |
| `PUBLIC_BASE_URL` | optional | Base URL used when building password-reset links |
| `ROBOTEVENTS_API_KEY` | optional | Enables `/api/matches`; results are cached for 5 minutes |
| `ROBOTEVENTS_TOKEN` | optional | Enables the live panels on team pages; check it with `python -m api.robotevents probe 77628A` |
| `CHATBOT_API_KEY` | optional | Enables the on-site assistant; without it the widget reports it is offline |
| `CHATBOT_API_URL`, `CHATBOT_MODEL` | optional | Override the assistant's upstream and model |
| `GIVEBUTTER_CAMPAIGN_ID` | optional | Renders the donation embed; without it the page shows an email fallback |
| `CONTACT_EMAIL` | optional | Address shown in fallbacks |
| `CLUB_TIMEZONE` | optional | Zone event times are entered in (default `America/New_York`) |
| `FLASK_DEBUG` | optional | `1` enables the debugger for the local server only |

## Tests

```bash
python -m pytest
```

The suite runs against `mongomock`, so no database is needed. GitHub Actions runs it, plus `node --check` on every
script, on each push and pull request (`.github/workflows/tests.yml`). It covers authentication, password reset, the contact
and newsletter endpoints, CSRF enforcement, security headers, upload validation, rate limiting, and that every page
renders.

## Security Notes

- Every non-`GET` request must carry a CSRF token (`_csrf_token` field or `X-CSRF-Token` header). The check is a
  `before_request` hook, so new routes are protected by default.
- Every page, including the admin dashboard, is served under a Content-Security-Policy with no inline script. An
  `onclick=` attribute, an inline `<script>`, or a handler written into an `innerHTML` string will silently stop
  working. Wire controls with `data-*` attributes and delegated listeners; `tests/test_pages.py` scans the templates
  and the JS bundles for inline handlers.
- No CSS in templates: styles live in `static/css/styles.css` or `static/css/pages/<page>.css`. A DB-backed value
  may be passed as a CSS custom property (see `--team-hero-image`). `tests/test_content.py` enforces this.
- Uploads are restricted by extension, capped at 8 MB, and stored under keys built with `secure_filename`.
- Sign-in attempts are rate limited per (account, IP) and per account, so rotating addresses does not reset the count.
- `/api/contact`, `/api/newsletter`, and `/api/chat` are rate limited per IP and validate their input.

## Support Us

We're always looking for sponsors. See the [support page](/donate) for sponsorship levels, or use the contact form.
