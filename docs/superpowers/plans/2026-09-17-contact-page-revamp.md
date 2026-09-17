# Contact Page Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking. Backend tasks use superpowers:test-driven-development — write the failing test first.

**Design spec:** `docs/superpowers/specs/2026-09-17-contact-page-revamp-design.md`

**Goal:** Make the contact form actually work. Replace the Google-Forms `no-cors` submission (which reports
success even when it fails) with a real `POST /api/contact` Flask endpoint that validates, rate limits, and
stores messages in MongoDB; add a Messages tab to the admin panel; and finish the page's frontend — inline
styles out of the template, contact-only rules out of `styles.css`, dark mode added, form accessibility
fixed.

**Architecture:** Flask + Jinja2 (`api/index.py`), MongoDB via the lazy `db` proxy, plain CSS with custom
properties loaded per page through `{% block page_styles %}`, Lucide icons via `<i data-lucide="name">`, dark
mode through a `[data-theme="dark"]` ancestor selector. The new endpoint reuses the rate-limit and
lazy-index helpers landed with the login overhaul (PR #2, merged as `81dd18c`). Tests run against `mongomock`
through `tests/conftest.py`.

**Baseline:** branch from current `main` (`81dd18c`). `python -m pytest` is green at 40 tests before any
change — confirm that first.

## Global Constraints

- **CSS never lives in HTML.** When done, `templates/contact.html` has zero `style=` attributes and no
  `<style>` blocks. New rules go in `static/css/pages/contact.css`.
- Reuse existing tokens: `--maroon-dark: #800000`, `--maroon-light: #944547`, `--accent-gold: #ffd700`,
  `--text-dark: #1a1a1a`, `--text-light: #666`, `--bg-light: #fafafa`, `--spacing-*`, `--transition-base`.
  Card headings use `'Space Mono', monospace`. No new design language.
- Card look follows site convention: `border: 3px solid var(--text-dark)`, `border-radius: 16px`,
  `box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2)`, hover `translate(-4px, -4px)`.
- Dark-mode convention: card background `#1e1e1e`, border `#444`, heading `#d4a0a1`, body text `#bbb`.
  Every class that sets a color or background gets a `[data-theme="dark"]` variant.
- **Do not move shared CSS.** `.faq-*` is also used by `notebook.html`; `.form-group` is also used by
  `admin.html`, `donate.html`, `login.html`, `reset_password.html`. These stay in `styles.css` — only their
  dark-mode gaps get filled, in place. Re-run the grep in Task 7 before deleting anything.
- Backend style: follow the existing helpers in `api/index.py` — `_utcnow()` for naive UTC, `_client_ip()`
  for the IP, the `_ensure_auth_indexes()` lazy-flag pattern for index creation, `log_activity()` for
  admin mutations. No new dependencies; `requirements.txt` is unchanged.
- Never log or echo a submitter's message body into `log_activity` details — store the id only.
- Commit style for this repo: short imperative sentence, no `feat:` prefix, ending with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Shared Verification Commands

Run from the repo root. Tasks refer to these by name.

**TESTS**

```bash
python -m pytest -q
```

Expected: all green, count grows as tasks add tests.

**RENDER** — page returns 200 and every `/static/` URL resolves:

```bash
python -c "
import re
from api.index import app
c = app.test_client()
r = c.get('/contact'); h = r.data.decode()
print('status', r.status_code)
urls = sorted(set(re.findall(r'/static/[^\"\'?) ]+', h)))
bad = [u for u in urls if c.get(u).status_code != 200]
print('static urls', len(urls), 'broken', bad)
"
```

Expected: `status 200`, `broken []`.

**BRACES** — CSS braces balanced:

```bash
python -c "s=open('static/css/pages/contact.css').read(); print(s.count('{') == s.count('}'))"
```

Expected: `True`.

**NOINLINE**

```bash
grep -c 'style="' templates/contact.html
```

Expected: `0`.

---

## Phase 1 — Backend endpoint

### Task 1: Contact storage helpers and indexes

- [ ] Add constants near the auth helpers in `api/index.py`: `CONTACT_MAX_ATTEMPTS = 3`,
      `CONTACT_WINDOW = datetime.timedelta(minutes=15)`, field caps `CONTACT_NAME_MAX = 100`,
      `CONTACT_EMAIL_MAX = 254`, `CONTACT_MESSAGE_MAX = 4000`.
- [ ] Add `_contact_indexes_ready = False` and `_ensure_contact_indexes()` mirroring
      `_ensure_auth_indexes()` (`api/index.py:347`): TTL index on `contact_attempts.created_at` with
      `expireAfterSeconds=int(CONTACT_WINDOW.total_seconds())`, compound index on
      `contact_attempts [('key', 1), ('ip', 1)]`, and an index on `contact_messages [('created_at', -1)]`.
      No TTL on `contact_messages`.
- [ ] Add `_contact_lockout_minutes(ip)` and `_record_contact_attempt(ip)` following
      `_lockout_minutes` / `_record_attempt` (`api/index.py:357-371`), keyed on IP only.
- [ ] Add `_validate_contact(payload)` returning `(cleaned_dict, error_string_or_None)`: trims all fields;
      rejects empty name/email/message; rejects over-cap lengths with a field-named message; rejects an
      email with no `@` and no `.` after it; lowercases the email.
- [ ] Register `_contact_indexes_ready` reset in `tests/conftest.py`'s `db` fixture alongside the existing
      `_auth_indexes_ready` monkeypatch, so each test starts with indexes unbuilt.

**Verify:** TESTS still green (no behavior change yet).

### Task 2: `POST /api/contact` (TDD)

- [ ] Write `tests/test_contact.py` **first**, with these failing tests:
  - valid POST returns 200, body `{'ok': True}`, and inserts exactly one `contact_messages` doc with
    `status == 'new'`, trimmed name, lowercased email, and a `created_at`
  - missing `message` returns 400, inserts nothing
  - a 4001-character message returns 400, inserts nothing
  - `email` of `"notanemail"` returns 400, inserts nothing
  - filled honeypot (`website`) returns 200 with `{'ok': True}` and inserts **nothing**
  - 4th POST from the same IP inside the window returns 429, inserts nothing, and the JSON `error`
    mentions minutes
  - a POST from a different `X-Forwarded-For` is not affected by another IP's lockout
  - HTML in the message is stored verbatim (escaping is the template's job, asserted in Task 6)
- [ ] Confirm RED: run TESTS, see the new tests fail for the right reason (404 on the route).
- [ ] Implement `@app.route('/api/contact', methods=['POST'])` in `api/index.py`, placed with the other
      `/api/*` routes: accept JSON (`request.get_json(silent=True) or {}`), honeypot check first, then
      rate-limit check (429), then `_validate_contact` (400), then `_record_contact_attempt(ip)` and insert
      the document per the spec's schema (including `ip` and a 200-char-truncated `user_agent`).
- [ ] Confirm GREEN: TESTS all pass.

**Verify:** TESTS green; `python -m pytest tests/test_contact.py -q` shows every listed case.

---

## Phase 2 — Frontend form wiring

### Task 3: Remove the contact branch from the Google-Form interceptor

- [ ] In `static/js/script.js`, delete the `if (this.id === 'contact-form') { ... }` branch inside the
      interceptor (`script.js:412-415`) and the contact-only fallbacks in the legacy success/error handling
      (`script.js:449-464`). Leave `sponsorForm` and `.footer-newsletter-form` untouched — they still use
      Google Forms.
- [ ] Add `contact-form` to the interceptor's opt-out condition at `script.js:383`, alongside the existing
      `data-native-submit` / `chatbot-form` / `/admin` checks.

**Verify:** `grep -n "contact-form" static/js/script.js` shows only the opt-out line. Loading `/contact` and
submitting does nothing yet (handler lands in Task 4) — that is expected at this checkpoint, so Tasks 3 and 4
land in one commit.

### Task 4: Dedicated contact-form handler

- [ ] Add a self-contained block in `static/js/script.js` (near the other form code) that binds to
      `#contact-form` only if present, and on submit:
  - `preventDefault()`, read `name`, `email`, `message`, `website` (honeypot)
  - disable the button, set its text to `Transmitting…`, remember the original text
  - `fetch('/api/contact', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(...)})`
  - on `response.ok`: `form.reset()`, reveal the success banner, call the existing
    `showToast('Message sent!', 'success')`
  - on non-OK: parse JSON, render `data.error` (falling back to a generic string) in the error banner —
    this is how the 429 message reaches the user
  - on a thrown fetch: generic "Could not reach the server" in the error banner
  - `finally`: restore button text and re-enable
  - hide whichever banner is not in use, and auto-hide after 6 s (matching the existing behavior)
- [ ] Banners are toggled by adding/removing a class (`is-visible`), never by writing `style.display` —
      keeps CSS out of JS as well as out of HTML.

**Verify:** In a browser at `/contact`, a valid send shows the success banner and a row appears in
`contact_messages`; four rapid sends show the 429 text in the error banner. Stop the Flask process and
submit — the error banner shows the network message, not a success.

---

## Phase 3 — Template restructure

### Task 5: Form markup, accessibility, honeypot

- [ ] In `templates/contact.html`, give each input an `id` (`contact-name`, `contact-email`,
      `contact-message`) and point each `<label for="...">` at it.
- [ ] Add `autocomplete="name"` / `autocomplete="email"` to the first two inputs, `maxlength` matching the
      server caps (100 / 254 / 4000), and keep `required`.
- [ ] Add the honeypot: a `<div class="contact-honeypot">` wrapping
      `<label for="contact-website">Website</label>` and
      `<input type="text" id="contact-website" name="website" tabindex="-1" autocomplete="off">`,
      plus `aria-hidden="true"` on the wrapper.
- [ ] Replace the two inline-styled status `<div>`s with
      `<div id="form-success" class="contact-form-status contact-form-status--success" role="status">` and
      `<div id="form-error" class="contact-form-status contact-form-status--error" role="alert">`; drop
      every `style=` attribute on them and on the `<h2>` and submit button.
- [ ] Give the submit button `class="submit-btn contact-submit"` (the width rule moves to CSS).

**Verify:** NOINLINE returns `0`; RENDER passes.

### Task 6: FAQ, map facade, details, content

- [ ] FAQ: each `<button class="faq-question">` gets `aria-expanded="false"` and
      `aria-controls="faq-answer-N"`; each `.faq-answer` gets the matching `id`. Update the toggle in
      `static/js/script.js:529-545` to flip `aria-expanded` on the clicked button and reset it on the ones
      it closes.
- [ ] Add the two new FAQ entries from the spec (meeting time/place; company sponsorship, linking
      `{{ url_for('donate') }}`).
- [ ] Map: wrap the iframe in `<div class="contact-map-facade" data-map-src="...">` holding a static
      placeholder with a "Load map" button; move the Google URL to the `data-map-src` attribute and inject
      the `<iframe>` (with `title="Mepham High School location map"`, `loading="lazy"`,
      `referrerpolicy="no-referrer-when-downgrade"`) on click. Add the small init to `script.js`.
- [ ] Contact details: swap the email literal for the club address if the club has supplied one — otherwise
      leave `damlin@bmchsd.com` and note it in the PR body. Remove the `facebook.com` and `x.com` links
      unless real handles are supplied; keep Instagram.
- [ ] Add a test to `tests/test_contact.py`: `GET /contact` returns 200, contains `id="contact-website"`,
      contains `aria-expanded`, and does **not** contain `docs.google.com/forms`.

**Verify:** TESTS green; RENDER passes; NOINLINE returns `0`. In a browser, the network log shows no
`google.com/maps` request until the Load map button is clicked.

---

## Phase 4 — CSS

### Task 7: Move contact-only rules into `pages/contact.css`

- [ ] Re-run the ownership grep before deleting anything:
      `grep -lE '\.?(contact-section|contact-container|content-container|contact-details|contact-socials|detail-item|map-section|map-container|map-embed|map-placeholder|schedule-section|meeting-schedule|next-meeting|meeting-details|submit-btn)' templates/*.html`
      — expect `templates/contact.html` only. If any other template appears, leave that rule in
      `styles.css` and note it.
- [ ] Move those rule blocks from `static/css/styles.css` (they sit around lines 334-342, 1753-1790,
      1860-1880, 2681-2760+, 2855-2875 — find them by selector, not by line number) into
      `static/css/pages/contact.css`, below the existing hero override. Delete them from `styles.css`.
- [ ] Do **not** move `.faq-*`, `.form-group`, `.hero-image`, `.hero-cta`, `.fade-in-section`,
      `.breadcrumb` — all shared.
- [ ] Add rules for the new classes: `.contact-honeypot` (visually hidden: absolute, 1px, clipped — not
      `display:none`, which some bots skip), `.contact-form-status` plus its `--success` / `--error`
      variants and an `.is-visible` state carrying the gradients/borders that were inline,
      `.contact-submit { width: 100%; margin-top: 1rem; }`, `.contact-map-facade` (16:9 ratio, placeholder
      background, centered button).

**Verify:** BRACES `True`; RENDER passes; `/contact`, `/notebook`, `/donate`, `/login` all still render
correctly in a browser (they share `.faq-*` / `.form-group`).

### Task 8: Dark mode and responsive

- [ ] In `static/css/pages/contact.css`, add `[data-theme="dark"]` variants for `.contact-section`,
      `.content-container`, `.detail-item`, `.contact-socials a`, `.map-section`, `.map-container`,
      `.contact-map-facade`, `.schedule-section`, `.meeting-schedule`, `.next-meeting`, `.meeting-details`,
      and both `.contact-form-status` variants.
- [ ] In `static/css/styles.css`, add the missing `[data-theme="dark"]` variants for `.faq-item`,
      `.faq-question`, `.faq-answer`, `.faq-icon` and for `.form-group input` / `textarea` — these are
      shared, so they belong in the shared file and fix the other pages at the same time.
- [ ] Responsive: `.contact-container` to one column at 768px with the image last; `.contact-details` keeps
      `auto-fit, minmax(200px, 1fr)`; map facade holds 16:9 to 375px.

**Verify:** BRACES `True`. In a browser, toggle the theme on `/contact` — the form card, detail items, FAQ,
map facade, and schedule are all legible in both themes. Check `/login` and `/donate` in dark mode for the
shared `.form-group` change. Resize to 1440 / 768 / 375 with no horizontal scroll.

---

## Phase 5 — Admin Messages tab (self-contained; cuttable)

Messages are already stored and readable without this phase. Drop it if scope needs trimming.

### Task 9: Admin routes (TDD)

- [ ] Write the tests first in `tests/test_contact.py` (or a new `tests/test_admin_messages.py`):
      an anonymous request to each of `/admin/messages/<id>/read`, `/archive`, `/delete` redirects to login
      and does not mutate; an authenticated admin gets the expected status transition; `delete` removes the
      document; each mutation writes an `activity` entry.
- [ ] Confirm RED, then implement the three POST routes in `api/index.py` beside the other `/admin/*`
      routes, with the same auth decorator those use. Guard against an invalid `ObjectId`.
- [ ] Add `'message_read': 'Message read'`, `'message_archive': 'Message archived'`,
      `'message_delete': 'Message deleted'` to the activity `titles` map (`api/index.py:208`) and a `mail`
      icon in the icon map just above it (`api/index.py:186`).
- [ ] In the `/admin` view, load messages (newest first, capped at e.g. 200) and the unread count into the
      template context.

**Verify:** TESTS green.

### Task 10: Admin tab UI

- [ ] Add a ninth nav item in `templates/admin.html` after Activity:
      `data-tab="messages"`, icon `mail`, `aria-selected="false"`, `tabindex="-1"`, with an unread count
      badge rendered only when the count is non-zero.
- [ ] Add the matching panel: filter chips (All / New / Read / Archived) following the Users tab's filter
      pattern, then a table of date / name / email / excerpt / status, each row expandable to the full
      message, with Mark read / Archive / Delete actions. Escape every field with Jinja's default
      autoescaping — no `|safe`.
- [ ] Wire the filtering and row expansion in `static/js/admin.js`, reusing the existing filter helpers.
- [ ] Style in `static/css/admin.css`, including a `[data-theme="dark"]` variant and the sub-768px stacked
      card treatment the Users tab already uses.

**Verify:** TESTS green. In a browser: submit a message at `/contact`, see it appear as New in the admin
Messages tab, mark it read, archive it, delete it — each step reflected in the Activity tab.

---

## Phase 6 — Close out

### Task 11: Full verification and commit

- [ ] Run TESTS, RENDER, BRACES, NOINLINE — all pass.
- [ ] `grep -rn "docs.google.com/forms" templates/ static/js/` — the only hits left are the sponsor form and
      footer newsletter, which are deliberately out of scope.
- [ ] Manual pass: light/dark, 1440/768/375, keyboard-only through the form and FAQ, screen-reader
      announcement of the success banner.
- [ ] Commit per phase (or per task), then open a PR to `main` summarizing: the endpoint, the rate limit,
      the honeypot, the admin tab, and the two open content decisions (club email address, Facebook/X
      handles).

## Risks and Open Questions

| Item | Impact | Handling |
|------|--------|----------|
| No club-owned email address supplied | Page keeps a personal district address | Leave as-is, flag in the PR — one-line change later |
| Facebook / X handles unknown | Dead placeholder links | Remove the two icons; re-add when handles arrive |
| No notification when a message arrives | Admin must check the panel | Accepted for now; Resend was deliberately removed. A future option is a digest on admin login |
| Existing Google Form responses | Historical messages stay in the Sheet | Not migrated; the Sheet remains readable |
| `contact_messages` growth | Unbounded collection | Low volume for a club site; archive/delete exists in the admin tab |
| No CSRF tokens app-wide | Pre-existing gap, unchanged by this work | Out of scope; tracked separately |
| Room 123 / meeting times may be stale | Wrong info on a public page | Confirm with the club during Task 6 |
