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
api/index.py            # The entire Flask application: routes, auth, admin, JSON APIs
templates/              # Jinja2 templates (base.html holds the site chrome)
  partials/             # Shared fragments
static/css/styles.css   # Global design system + dark theme
static/css/pages/       # One stylesheet per page — no styles live in templates
static/js/script.js     # Site-wide behaviour (nav, search, forms, chatbot, animations)
static/js/theme.js      # Theme bootstrap, loaded before first paint
static/js/admin.js      # Admin dashboard behaviour
tests/                  # pytest suite, backed by mongomock
docs/superpowers/       # Design specs and implementation plans
```

## Running Locally

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements-dev.txt
python api/index.py
```

The app reads configuration from `.env` (see below) and serves on <http://127.0.0.1:5000>.

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `MONGO_URI` | yes | MongoDB connection string |
| `SECRET_KEY` | yes in production | Signs the session cookie. Startup fails on Vercel without it. |
| `BLOB_READ_WRITE_TOKEN` | for uploads | Vercel Blob token |
| `PUBLIC_BASE_URL` | optional | Base URL used when building password-reset links |
| `ROBOTEVENTS_API_KEY` | optional | Enables `/api/matches`; results are cached for 5 minutes |
| `CHATBOT_API_KEY` | optional | Enables the on-site assistant; without it the widget reports it is offline |
| `CHATBOT_API_URL`, `CHATBOT_MODEL` | optional | Override the assistant's upstream and model |
| `GIVEBUTTER_CAMPAIGN_ID` | optional | Renders the donation embed; without it the page shows an email fallback |
| `CONTACT_EMAIL` | optional | Address shown in fallbacks |

## Tests

```bash
python -m pytest
```

The suite runs against `mongomock`, so no database is needed. It covers authentication, password reset, the contact
and newsletter endpoints, CSRF enforcement, security headers, upload validation, rate limiting, and that every page
renders.

## Security Notes

- Every non-`GET` request must carry a CSRF token (`_csrf_token` field or `X-CSRF-Token` header). The check is a
  `before_request` hook, so new routes are protected by default.
- Public pages are served under a Content-Security-Policy with no inline script. Adding an `onclick=` attribute or an
  inline `<script>` to a public template will silently break it — `tests/test_pages.py` guards against this.
- Uploads are restricted by extension, capped at 8 MB, and stored under keys built with `secure_filename`.
- Sign-in attempts are rate limited per (account, IP) and per account, so rotating addresses does not reset the count.
- `/api/contact`, `/api/newsletter`, and `/api/chat` are rate limited per IP and validate their input.

## Support Us

We're always looking for sponsors. See the [support page](/donate) for sponsorship levels, or use the contact form.
