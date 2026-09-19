# Team Page Revamp — Design Spec

Date: 2026-09-17
Reference site for **features**: [overclock.co](https://overclock.co) (VEX team 16099, Flushing NY)
Visual style: **unchanged Mepham** — maroon/gold, thick-border cards, offset shadows, Space Mono headings

Scope: `templates/team.html`, `templates/partials/*`, `static/css/pages/team.css`, `static/js/team.js`,
new `api/robotevents.py`, route additions in `api/index.py`, admin team form in `templates/admin.html` +
`static/js/admin.js`, new tests.

Route today: `/team/<team_number>` → `api/index.py:team_page()` → `team`, `team_awards`.

## Goal

Turn `/team/<number>` from a static brochure into the team's live season hub, matching the *capabilities*
overclock.co gives its teams — live world skills standing, a season scoreboard, a real roster with roles
and tenure, per-event results, event photo galleries, a season archive — while keeping Mepham's existing
visual language exactly as it is.

Nothing on this page adopts overclock's look. Every new block is built from the Mepham tokens already in
`styles.css`: `--maroon-dark #800000`, `--maroon-light #944547`, `--accent-gold #ffd700`,
`--text-dark #1a1a1a`, `border: 3px solid var(--text-dark)`, `border-radius: 16px`,
`box-shadow: 8px 8px 0 rgba(148,69,71,0.2)`, hover `translate(-4px,-4px)`, `'Space Mono'` headings,
`.ripple` section headings, `fade-in-section` reveal, dark mode via `[data-theme="dark"]`.

**Hard requirement: the Competition Awards display stays.** `templates/partials/awards_grid.html` keeps
its markup, its `.award-*` classes, its shimmer/border/layout modifiers and its position on the page. New
award-related UI is added *around* it, never in place of it.

## Feature Map — overclock.co → Mepham team page

| overclock.co feature | What we build | Data source |
|---|---|---|
| Roster grouped by division, each team headed `7 MEMBERS · 7× WORLDS` | Team identity bar in the hero | new admin fields + existing `members` |
| Member card: initials avatar, name, multiple role chips, `Since 2022` | Roster card rebuild | `members[].roles`, `.since` (new), photo still optional |
| `/skills` live world standings with driver/programming split, rank trend, percentile | **Live Skills panel** scoped to this one team | RobotEvents API v2 |
| Season achievements strip: `15 competitions (5 local, 8 signature, 2 worlds) · 27 awards · 2 Triple Crowns` | **Season Scoreboard** above the awards grid | RobotEvents events + awards, with manual override |
| `/awards` detailed award history | **Existing awards grid — kept** — plus a season award list under it | `awards` collection (unchanged) + RobotEvents |
| Event recap pages with 230-photo galleries | **Event Results timeline**, each event expandable to its photo strip | RobotEvents events + `team.events[].photos` |
| Season selector 2025–26 … 2017–18 | **Season switcher** on the team page | new `season` field + `?season=` query param |
| `/journey` team history | **Team Journey** timeline | new `team.journey[]` |
| `/interested`, `/faq` | **Join CTA** band | static |
| `/pit/login` members area | Link to the existing `/login` when signed out; nothing new | existing auth |
| Sponsors, press coverage, Chinese version | **Out of scope** — site-global concerns, not a team page |

## Page Structure (top to bottom)

1. **Hero** — existing hero image, team number, nickname, tagline.
   Identity bar under it: `12 MEMBERS · 8 AWARDS · SINCE 2019 · 2× WORLDS`. Each stat omitted when its
   value is missing or zero. Season switcher pill row sits at the right of the bar.
2. **Breadcrumb** — unchanged.
3. **Live Skills panel** — the marquee feature. Combined score, driver score, programming score, world
   rank, region rank, percentile, and a rank-trend marker (`▲ / ▼ / NEW`), plus `Updated <relative time>`
   and a link to the team's RobotEvents page. Loads async; renders a skeleton first.
4. **Season Scoreboard** — competitions counted by kind (local / signature / championship), awards won
   this season, and a "Triple Crown" badge when an event yielded Tournament Champion + Excellence +
   Skills Champion.
5. **Competition Awards** — **the existing `awards_grid.html` include, untouched.** Under it, a
   chronological list of this season's awards with event name and date.
6. **Event Results** — per-event rows: date, event name, level badge, qualification record, elimination
   result, awards, skills rank at that event. A row with photos expands to a horizontal photo strip;
   clicking a photo opens a lightbox.
7. **Roster** — sub-team grouped (Mechanical / Electrical / Programming / Notebook, or ungrouped when no
   sub-team is set), leadership first inside each group. Card: photo or initials avatar, name, role chips,
   `Since <year>`.
8. **Robot Showcase** — working STL viewer when `team.stl_path` is set (three.js, lazy, CDN-pinned);
   otherwise a robot photo gallery; otherwise the tagline alone. The dead "Rotate" button is deleted.
9. **Technical Specifications** — only the fields that have values. Never "TBA". Section hidden when empty.
   Engineering Notebook button only when `notebook_link` is real (the save route defaults it to `'#'`).
10. **Season Goals** — existing bars plus `role="progressbar"`, ARIA values, 0–100 clamp, and a gold
    complete state at 100%.
11. **Team Journey** — timeline of this team's milestones, reusing the about page's timeline classes.
12. **Join CTA** — "Interested?" band → `/contact` and `/achievements`.

Full-bleed only for sections that paint a background: Live Skills, Season Scoreboard, Technical Specs.

## RobotEvents Integration

The single biggest thing overclock has that we do not: real competition data. Everything live comes from
the RobotEvents v2 API.

- **New module** `api/robotevents.py`, using `requests` (already in `requirements.txt`).
- **Auth**: bearer token in `ROBOTEVENTS_TOKEN`. **Absent token is a supported state** — every live
  section hides itself and the page renders exactly as it would offline. No crash, no error banner.
- **Endpoints** (verify shapes against the live docs during implementation, do not trust this table
  blindly): `GET /api/v2/teams?number[]=&program[]=` for the team id, then `/teams/{id}/events`,
  `/teams/{id}/awards`, `/teams/{id}/rankings`, and the season skills endpoint for driver/programming.
- **Team number mapping**: a new optional `robotevents_number` field on the team; falls back to
  `team_number`. Mepham numbers such as `77628A` are already RobotEvents-shaped.
- **Caching**: a `re_cache` MongoDB collection, one document per request key, with a fetched-at timestamp
  and a TTL index. Skills 30 min, events/awards 6 h. On an API error or timeout, **serve the stale
  document** rather than showing nothing; label the panel with its real age.
- **Delivery**: the page never blocks on the API. `team_page()` renders immediately; `static/js/team.js`
  calls a new `GET /api/team/<team_number>/live` JSON route and fills the skeleton. A 2.5 s upstream
  timeout keeps the Vercel function well inside its budget.
- **Rate limiting**: the JSON route is cached server-side by the same `re_cache`, so a traffic spike
  produces one upstream call per TTL window, not one per visitor.
- **Rank trend**: computed locally. Each skills fetch appends `{date, rank, score}` to a capped
  `re_history` document for the team; the trend marker compares today's rank with the newest entry older
  than 24 h. `NEW` when there is no prior entry.

## Data Model Additions

All optional, all back-compatible — a team document that lacks every one of them still renders.

**Team**

| Field | Type | Use |
|---|---|---|
| `season` | string, `"2025-26"` | Which season this document describes; drives the season switcher |
| `division` | string | "High School" / "Middle School" badge |
| `since` | int year | `SINCE 2019` in the identity bar |
| `worlds_appearances` | int | `2× WORLDS` in the identity bar |
| `robotevents_number` | string | Override when the RobotEvents number differs |
| `journey` | list of `{date, title, description}` | Team Journey timeline |
| `events` | list of `{name, date, photos[]}` | Photo strips attached to Event Results rows |

**Member** (inside `team.members`)

| Field | Type | Use |
|---|---|---|
| `roles` | list of strings | Role chips. Falls back to the existing single `role` string |
| `since` | int year | `Since 2022` line |
| `subteam` | string | Roster grouping |

The existing `role`, `name`, `photo`, `user_id` keys are untouched, so no migration is required and no
existing team document breaks.

## Season Switcher

Teams are stored one document per team number today. Seasons are added by storing one document per
`(team_number, season)` pair; the route picks `?season=` when given, otherwise the newest `season` value,
otherwise the sole document. The switcher renders only when more than one season exists — a club with one
season sees no dead control. The route must keep working for documents with no `season` field at all.

## Degradation Rules

Every one of these is a test, not a hope:

- No `ROBOTEVENTS_TOKEN` → Live Skills, Season Scoreboard and Event Results hide. Page is 200.
- Token present, API down, no cache → same as above. Page is 200.
- Token present, API down, stale cache → data shown, labelled with its real age.
- Team document with only `team_number` → page is 200. *(It currently returns HTTP 500:
  `jinja2.exceptions.UndefinedError: 'dict object' has no attribute 'specs'` — verified 2026-09-17.)*
- No members / no goals / no specs / no awards → each section hides itself. The awards grid keeps its own
  existing "No awards recorded for this team yet" state, which stays as written.
- No STL and no robot photos → showcase shows the tagline alone.

## CSS Architecture

- Every rule for this page lives in `static/css/pages/team.css`. `templates/team.html` ends with exactly
  one `style=` — the hero's `--team-hero-image` custom property, which carries data.
- **Move** from `styles.css` to `team.css` (team-only, verified by grep): `.robot-specs`,
  `.specs-container`, `.spec-card`, `.spec-label`, `.spec-value`, `.goals-section`, `.goals-container`,
  `.goal-item`, `.goal-header`, `.goal-name`, `.goal-percent`, `.progress-bar`, `.progress-fill`,
  `.download-btn`, `.download-icon`, `.robot-showcase`, `.robot-tagline`, `.team-img`, and the
  `.specs-container` media query. Re-grep for line numbers before cutting.
- **Delete**: `.viewer-3d-container`, `.viewer-label`, `.viewer-controls`, `.viewer-btn`.
- **Never touch**: `.team-grid`, `.team-card` (shared with `about.html` and `notebook.html`),
  `.award-*`, `.hero-image`, `.scroll-indicator`, `.cta-*`, `.breadcrumb`, the timeline classes.
- New classes by section: `identity-`, `skills-`, `scoreboard-`, `results-`, `roster-`, `viewer-`,
  `journey-`, `teamcta-`. Grep every new name against `styles.css` and `templates/` before using it.
- Each new class that sets a color gets a `[data-theme="dark"]` variant: card `#1e1e1e`, border `#444`,
  heading `#d4a0a1`, body `#bbb`.

## Accessibility

- Live panels are `aria-live="polite"`; the skeleton is `aria-busy="true"` until filled.
- Rank trend markers carry text, not colour alone: `▲ Up 4`, not a green arrow by itself.
- Progress bars get `role="progressbar"` with `aria-valuenow/min/max` and the goal name as label.
- The WebGL canvas gets `role="img"` and an `aria-label`; the gallery lightbox traps focus, closes on
  Escape, and returns focus to the thumbnail.
- Initials avatars are decorative (`aria-hidden`) because the name is already text beside them.
- `prefers-reduced-motion`: no model auto-spin, no counter count-up animations.

## Responsive

- Identity bar: one row, wrapping to two lines under 700px.
- Live Skills: 3 columns → 2 at 900px → 1 at 560px.
- Event Results: table-like rows become stacked cards under 768px.
- Roster: `auto-fit, minmax(220px, 1fr)`, single column under 480px.
- Viewer: `16/9`, then `4/3` under 768px.
- No horizontal scroll at 1440 / 768 / 375px.

## Verification

- `pytest` green, including new tests for the RobotEvents layer (upstream mocked — **no network in tests**).
- `/team/<n>` is 200 for: a fully populated team, a bare `team_number`-only team, and with
  `ROBOTEVENTS_TOKEN` unset.
- **`Competition Awards` present in every one of those renders** — a regression guard, run in every task.
- No `TBA` anywhere in the output.
- `grep -c 'style="' templates/team.html` returns 1.
- Every `/static/` URL in the render resolves 200.
- Light and dark both legible at 1440 / 768 / 375px.
- With no STL, the network log shows three.js was never fetched.

## Open Questions

1. **RobotEvents token** — someone with a RobotEvents account must generate one and set
   `ROBOTEVENTS_TOKEN` in Vercel (all environments) and `.env.local`. Until then the live sections ship
   hidden. This does not block any other task.
2. **Season backfill** — the archive is only as deep as the team documents that exist. Past seasons need
   someone to enter them in the admin panel; the switcher appears on its own once a second season exists.
3. **Event photos** — the Event Results photo strips need uploads. Overclock's 230-photo galleries are
   their strongest content; ours will be empty until photos are added, and rows without photos simply do
   not expand.
