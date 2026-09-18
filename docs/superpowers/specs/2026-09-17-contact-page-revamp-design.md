# Contact Page Revamp — Design Spec

Date: 2026-09-17
Scope: `templates/contact.html`, `static/css/pages/contact.css`, `static/js/script.js`, `api/index.py`,
`templates/admin.html`, `static/js/admin.js`, `static/css/admin.css`, cleanup in `static/css/styles.css`,
new tests in `tests/`.

## Goal

The contact page looks finished but does not work. Its form posts to a Google Form in `no-cors` mode, so the
browser cannot read the response and the page reports success unconditionally — a failed submission still
shows "Message transmitted successfully!". Nothing is validated server-side, nothing is rate limited, and the
only way to read a message is to open a Google Sheet that is not part of the site.

This revamp moves the form onto the Flask app: a real `POST /api/contact` endpoint that validates, rate
limits, stores the message in MongoDB, and returns a status the page can honestly act on — plus a Messages
tab in the admin panel to read what comes in. The visual pass cleans up the page at the same time: inline
styles move out of the template (project rule), contact-only rules move out of `styles.css` into
`static/css/pages/contact.css`, dark mode gets the coverage it is entirely missing, and the form gets the
label/ARIA wiring it never had.

Out of scope: a new visual language for the page, email/SMS notification of new messages (no mail provider
remains in the repo after Resend was removed), a public message archive, and a CMS-driven meeting schedule.

## Current State — Findings

| # | Finding | Where |
|---|---------|-------|
| 1 | Form submits to Google Forms with `mode: 'no-cors'`; the `.then()` always fires, so failure is reported as success | `static/js/script.js:371-468` |
| 2 | No server-side validation, no spam protection, no rate limit on contact submissions | no endpoint exists |
| 3 | Messages land in a Google Sheet, outside the admin panel the club already uses | — |
| 4 | Six inline `style=` attributes / blocks in the template, against the project rule that CSS lives in `static/css/pages/<page>.css` | `templates/contact.html` (h2, submit button, `#form-success`, `#form-error`) |
| 5 | `static/css/pages/contact.css` holds only the hero override; every other contact rule sits in the 86 KB shared `styles.css` | `static/css/styles.css:2681-2760+` |
| 6 | Dark mode is only half covered: grouped rules exist for `.content-container`, `.meeting-schedule`, `.detail-item`, `.detail-item h4` and `.map-section`, but nothing for `.contact-section`, `.contact-socials`, `.map-container`, `.schedule-section`, `.next-meeting`, `.meeting-details` or `.detail-item p` | `static/css/styles.css` |
| 7 | `<label>` elements have no `for`, inputs have no `id`; FAQ buttons have no `aria-expanded`; the map `<iframe>` has no `title` | `templates/contact.html` |
| 8 | Contact email is a personal district address (`damlin@bmchsd.com`); Facebook and X links point at bare `facebook.com` / `x.com` | `templates/contact.html` |
| 9 | Google Maps iframe loads on every page view (third-party cookies, ~1 MB) even if nobody looks at the map | `templates/contact.html` |
| 10 | Success/error `<div>`s use `display:none` toggling with no `role="status"`, so screen readers never announce the result | `templates/contact.html` |

## Target Architecture

```
contact.html form (id="contact-form", data-native-submit off)
      |  fetch POST application/json
      v
/api/contact  (api/index.py)
      |- honeypot check (silent 200)
      |- field validation (name/email/message lengths, email shape)
      |- rate limit: 3 per IP per 15 min via contact_attempts (TTL index)
      |- insert into contact_messages
      v
admin.html  ->  Messages tab  ->  /admin/messages/<id>/read | /archive | /delete
```

`contact_messages` document:

```python
{
  '_id': ObjectId,
  'name': str,            # trimmed, <= 100 chars
  'email': str,           # trimmed, lowercased, <= 254 chars
  'message': str,         # trimmed, <= 4000 chars
  'status': 'new',        # 'new' | 'read' | 'archived'
  'created_at': datetime, # naive UTC, matching _utcnow()
  'ip': str,              # from _client_ip()
  'user_agent': str,      # truncated to 200 chars
}
```

No TTL index on `contact_messages` — messages persist until an admin deletes them.

`contact_attempts` mirrors the existing `login_attempts` shape (`{'key', 'ip', 'created_at'}`) and carries a
TTL index of 15 minutes, so it self-cleans on Vercel exactly as the login limiter does.

### Reused helpers (already on `main` after PR #2)

- `_utcnow()`, `_client_ip()` — `api/index.py:338-346`
- `_lockout_minutes(key, ip)` / `_record_attempt(key, ip)` pattern — `api/index.py:357-375`
- `log_activity(activity_type, description, user, details)` — `api/index.py:134`
- `@login_required` / role decorators used by the other `/admin/*` routes

A new `_ensure_contact_indexes()` follows the `_ensure_auth_indexes()` lazy-index pattern (module-level flag,
created on first use) so tests with `mongomock` and cold Vercel invocations both behave.

### Rate limiting

3 submissions per IP per 15 minutes. Keyed on IP alone (not email) — email is attacker-controlled and
keying on it lets one sender rotate addresses freely. Over the limit returns HTTP 429 with
`{'error': 'Too many messages. Try again in N minutes.'}`; the page renders that text in the error banner.

### Spam protection

A honeypot field (`<input name="website">`, visually hidden via CSS, `tabindex="-1"`, `autocomplete="off"`).
Filled means bot: return 200 with the normal success body and store nothing. No CAPTCHA — it would need a
third-party key and the club has no traffic problem yet.

### CSRF

The app has no CSRF token infrastructure today, and `/api/contact` is unauthenticated and non-destructive, so
a forged cross-site POST buys an attacker nothing beyond what they can already do by loading the page. No
token is added here. The admin mutation routes (`/admin/messages/*`) inherit whatever protection the other
`/admin/*` POST routes have — this spec does not change that posture, and it stays a known gap tracked
separately.

## Section Map

| # | Section | Change |
|---|---------|--------|
| 1 | Hero | Unchanged copy and background. `#contact` and About CTAs stay |
| 2 | Breadcrumb | Unchanged |
| 3 | Contact form | Rewired to `/api/contact`. Labels bound with `for`/`id`, honeypot added, success/error banners become `role="status"` / `role="alert"` classed elements with no inline CSS, submit button loses its inline width |
| 4 | Contact details | Email becomes the club address (see Content), location unchanged, socials pruned to links that exist |
| 5 | Map | `<iframe>` gains a `title`; wrapped in a click-to-load facade so Google is only contacted if a visitor asks for the map |
| 6 | Meeting schedule | Unchanged copy, restyled for dark mode. Room number confirmed with the club before launch |
| 7 | FAQ | Existing four items kept, two added (see Content). Buttons get `aria-expanded` / `aria-controls`, answers get `id` and `hidden` handling |

Section order is unchanged — the page's structure is sound; it is the behavior that is broken.

## Content

### Contact details

- **Email** — replace `damlin@bmchsd.com` with a club-owned address. This is a decision for the club; the
  implementation uses a single Jinja-free literal in one place so it is a one-line edit. If no club address
  exists at implementation time, keep the current address and flag it in the PR.
- **Socials** — Instagram (`instagram.com/mephamrobotics`) is real and stays. Facebook and X point at bare
  domains; remove them unless the club supplies real handles. The same placeholders exist in `base.html`'s
  footer — out of scope here, but note it in the PR.

### FAQ additions

- **When and where do you meet?** — Tuesdays and Fridays, 3:00–5:00 PM, Room 123. Mirrors the schedule block
  so the answer is findable from the FAQ too.
- **How can my company sponsor the team?** — points at the donate page and the contact form.

### Form copy

"Initialize Transmission" stays — it matches the site's voice. Button text while in flight is
"Transmitting…", matching the existing JS.

## CSS Architecture

- All contact-page rules move to `static/css/pages/contact.css`, which `base.html` loads after `styles.css`
  via `{% block page_styles %}` — equal-specificity rules in the page file therefore win.
- `templates/contact.html` ends with zero `style=` attributes and no `<style>` blocks.
- Moved out of `styles.css` (used by `contact.html` only — re-grep `templates/` before deleting):
  `.contact-section`, `.contact-container`, `.content-container`, `.contact-details`, `.contact-socials`,
  `.detail-item`, `.map-section`, `.map-container`, `.map-embed`, `.map-placeholder`, `.schedule-section`,
  `.meeting-schedule`, `.next-meeting`, `.meeting-details`, `.submit-btn`. Grep over `templates/` confirms
  each of these appears in `contact.html` and nowhere else.
- **Kept in `styles.css`** (shared with other pages — verified by grep over `templates/`): `.faq-*` (also
  used by `notebook.html`), `.form-group` (also used by `admin.html`, `donate.html`, `login.html`,
  `reset_password.html`), `.hero-image`, `.hero-cta`, `.fade-in-section`, `.breadcrumb`. Only their
  dark-mode gaps are filled, in place.
- New classes are prefixed `contact-` where they are new (`contact-form-status`, `contact-honeypot`,
  `contact-map-facade`) so nothing collides.
- Every class that sets a color or background gets a `[data-theme="dark"]` variant, following the site
  convention: card background `#1e1e1e`, border `#444`, heading `#d4a0a1`, body text `#bbb`. The existing
  dark-mode rules are grouped across many pages' selectors (`[data-theme="dark"] .tier-card, ... .content-container, ...`);
  those grouped rules stay in `styles.css` untouched, and the contact page's missing variants are added in
  `contact.css`, which loads after.
- Reuse existing tokens only: `--maroon-dark`, `--maroon-light`, `--accent-gold`, `--text-dark`,
  `--text-light`, `--bg-light`, `--spacing-*`, `--transition-base`. No new design language.

## JavaScript

`static/js/script.js` currently branches on `this.id === 'contact-form'` inside the Google Form interceptor.
That branch is deleted. The contact form is excluded from the interceptor the same way the auth pages are —
by `data-native-submit`-style opt-out (`script.js:383`) — and handled by a small dedicated block that:

1. Reads the fields, posts JSON to `/api/contact`.
2. On `response.ok`: resets the form, shows the success banner, fires the existing `showToast(...)`.
3. On non-OK: reads `error` from the JSON body and shows it in the error banner (this is where the 429
   message surfaces).
4. On network failure: shows a generic failure message.
5. Restores button text and the disabled state in `finally`.

The sponsor form and the footer newsletter keep using Google Forms — migrating them is a separate job, and
this spec deliberately does not touch them.

## Admin Messages Tab

A ninth tab in `templates/admin.html`, after Activity, icon `mail`:

- Table of messages, newest first: date, name, email, first ~80 chars of the message, status badge.
- Row click expands the full message.
- Per-row actions: Mark read (`new` → `read`), Archive, Delete (with the panel's existing confirm pattern).
- Filter chips: All / New / Read / Archived, matching the dual-axis filter pattern already in the Users tab.
- A count badge on the tab label when unread messages exist.
- Every mutation calls `log_activity` with new types `message_read`, `message_archive`, `message_delete`,
  and matching titles added to the `titles` map at `api/index.py:~200`.

This tab is the one part of the revamp that can be cut without breaking the rest — if it is dropped, messages
still arrive in `contact_messages` and are readable from a Mongo client. Phase 5 of the plan is therefore
self-contained.

## Responsive Behavior

- `.contact-container` collapses from two columns to one at 768px, image last.
- `.contact-details` stays `auto-fit, minmax(200px, 1fr)`.
- Map facade keeps a 16:9 ratio down to 375px.
- The admin messages table becomes a stacked card list below 768px, matching the Users tab's existing
  mobile treatment.

## Verification

- `POST /api/contact` with a valid body returns 200 and inserts exactly one `contact_messages` document.
- A fourth submission from the same IP inside 15 minutes returns 429 and inserts nothing.
- A filled honeypot returns 200 and inserts nothing.
- Missing/oversized/malformed fields return 400 with a field-specific message; nothing is inserted.
- `grep -c 'style="' templates/contact.html` returns 0.
- `grep -c 'contact-form' static/js/script.js` shows no remaining Google-Form branch for it.
- `/contact` renders 200 with every `/static/` URL resolving.
- Light and dark themes both render the form card, detail items, FAQ, map, and schedule legibly.
- Layout holds at 1440px, 768px, 375px with no horizontal scroll.
- Keyboard: tab order reaches every control, FAQ toggles with Enter/Space and reports `aria-expanded`.
- `python -m pytest` stays green (40 existing tests plus the new contact tests).
