# Team Page Revamp — Design Spec

Date: 2026-09-17
Scope: `templates/team.html`, `static/css/pages/team.css`, new `static/js/team.js`, cleanup in `static/css/styles.css`, new `tests/test_team_page.py`

Route: `/team/<team_number>` → `api/index.py:team_page()` → `render_template('team.html', team=team, team_awards=team_awards)`

## Goal

`/team/<number>` is the deepest page on the site and the weakest. Today it is six stacked bands with no
identity layer, a dead 3D viewer that has never rendered anything, a spec grid that prints "TBA" four
times for most teams, and ~30 team-only rules squatting in the 86 KB shared `styles.css` — against the
project rule that page styles live in `static/css/pages/<page>.css`.

The revamp keeps every section the page already has, makes each one degrade honestly when data is
missing, replaces the fake 3D viewer with a working one, and moves team-only CSS into `team.css`.

**Hard requirement: the Competition Awards display stays.** `templates/partials/awards_grid.html` is
included as-is, in the same position, and is not edited by this work.

Out of scope: admin-panel schema changes (no new team fields), a new visual language, changes to
`nav_teams`, and anything touching the `awards` collection.

## Current State

| Thing | Problem |
|-------|---------|
| Hero | Title + nickname only. No sense of how big the team is or how it is doing |
| Meet the Team | Flat grid, no ordering, breaks on a missing `member.photo` |
| Competition Awards | **Works. Keep exactly as-is.** |
| Interactive 3D View | Placeholder text and a "Rotate" button wired to nothing. `team.stl_path` is uploaded to Vercel Blob by the admin panel and then never used |
| Technical Specs | Four hardcoded fields, each printing "TBA" when unset |
| Season Goals | Fine. Needs accessibility attributes; `.progress-fill` animation already lives in `static/js/script.js:578` |
| CSS | `.team-img`, `.robot-*`, `.viewer-*`, `.spec*`, `.goal*`, `.progress-*`, `.download-*` are used only by `team.html` but live in `styles.css` |
| Heading `<h2>` on specs | Missing `.ripple`, unlike every other section |
| Bare team | **Crashes.** A team document with only `team_number` returns HTTP 500: `jinja2.exceptions.UndefinedError: 'dict object' has no attribute 'specs'`. Verified against the current template on 2026-09-17. The revamp's data-guarded rendering fixes this |

## Section Map

| # | Section | Change |
|---|---------|--------|
| 1 | Hero | Keep image + nickname. Add a stat strip: members, awards won, season goals tracked |
| 2 | Breadcrumb | Unchanged |
| 3 | Roster ("Meet the Team") | New classes `roster-*`. Leadership-first ordering, photo fallback, optional profile link |
| 4 | **Competition Awards** | **Untouched.** `{% include "partials/awards_grid.html" %}` stays in place |
| 5 | Robot Showcase | Real STL viewer when `team.stl_path` is set; honest empty state when it is not |
| 6 | Technical Specs | Render only the specs that have values; hide the whole section when none do |
| 7 | Season Goals | Add ARIA, an empty state, and a done state at 100% |
| 8 | Join CTA | New closing band linking to `/contact` and `/achievements` |

Rhythm follows the about-page convention: only sections that paint a background go full-bleed (Robot
Showcase and Technical Specs, both dark). The rest sit inside the standard 1200px container.

## Section Detail

### 1. Hero stat strip

Three chips below the tagline, inside `.hero-content`:

| Chip | Source | Hidden when |
|------|--------|-------------|
| `{{ team.members|length }} Members` | `team.members` | list empty |
| `{{ team_awards|sum(attribute='count') }} Awards` | `team_awards` | sum is 0 |
| `{{ team.goals|length }} Season Goals` | `team.goals` | list empty |

If all three are empty the strip does not render — no zero chips. The awards count is derived from the
same `team_awards` the awards grid already receives; no new query, no route change.

### 2. Roster

Markup moves off the shared `.team-card` (also used by `about.html` and `notebook.html` — do **not**
restyle it) onto new `roster-card` / `roster-grid` / `roster-photo` classes.

- **Ordering**: leadership first. Sort in the template with a Jinja filter over a role-keyword list
  (`captain`, `lead`, `president`, `mentor`), everyone else after, each group in its existing order.
  No data change — this reads the existing free-text `member.role`.
- **Photo fallback**: `member.photo or 'static/assets/profile/base.png'`, matching the default the save
  route in `api/index.py` already writes. `loading="lazy"` stays.
- **Role line**: rendered only when `member.role` is set.
- **Profile link**: `member.user_id` is already stored. Only link if a public profile route exists at
  implementation time — verify with grep; if there is none, render plain text and do not invent a route.
- **Empty state**: "Roster coming soon for this team." instead of an empty grid.

### 3. Robot Showcase — the 3D viewer

The current placeholder is removed. Replacement, in order of preference:

**Chosen: a real STL viewer, lazily loaded.**

- `three` + `STLLoader` + `OrbitControls` from a pinned CDN build, loaded from a new
  `static/js/team.js` and only when `#robot-viewer[data-stl]` is present on the page. Pages without an
  STL pay nothing.
- The canvas gets `role="img"` and an `aria-label` naming the robot, plus visible caption text — a WebGL
  canvas is invisible to screen readers otherwise.
- Controls: drag to rotate, scroll to zoom, plus a real Reset View button (the existing dead "Rotate"
  button is deleted, not rewired).
- Failure path: if WebGL is unavailable or the STL fails to fetch, the container swaps to the same empty
  state used when there is no STL. No console-only failures, no spinner that never resolves.
- `prefers-reduced-motion`: no auto-spin; the model loads static and only moves on user input.

**Empty state** (no `stl_path`, or viewer failed): the hero image again is not interesting — instead show
the tagline card alone with a short line, "CAD model not published for this robot yet." The section still
renders so the tagline keeps its home.

*Alternative if the club does not want a CDN dependency:* delete the showcase section entirely and move
`team.tagline` under the hero. Cheaper, and honest. This spec assumes the viewer; switching costs one
task.

### 4. Technical Specs

Specs stay the same four admin fields (`drive_train`, `lift_system`, `intake`, `auton_consistency`) —
no admin form or save-route change. What changes is rendering:

- Build a list in the template from the four fields, dropping any that are falsy.
- Render one `.spec-card` per surviving entry. Never print "TBA".
- If nothing survives, the entire `robot-specs` section does not render.
- The Engineering Notebook button renders only when `team.notebook_link` is set and is not `'#'` (the
  save route defaults it to `'#'`, so this check matters).
- Section `<h2>` gains `.ripple` to match every other heading on the page.

### 5. Season Goals

- `.progress-bar` gets `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"`,
  and `aria-label` with the goal name.
- Progress clamped to 0–100 in the template (`goal.progress|default(0)|int`); a bad admin entry must not
  paint a bar past its track.
- A goal at 100% gets a `.goal-complete` modifier: gold fill and a check icon next to the name.
- Empty `team.goals` hides the section.
- The existing `IntersectionObserver` in `static/js/script.js:578` already animates `.progress-fill`;
  keep the `data-progress` attribute contract it reads. Do not duplicate that logic in `team.js`.

### 6. Join CTA

Closing band, no background paint: one line of copy plus two buttons — "Join the Club" → `/contact`,
"All Achievements" → `/achievements`, using the existing `.cta-button` / `.cta-primary` classes.

## CSS Architecture

- Every rule for this page ends in `static/css/pages/team.css`. `templates/team.html` ends with zero
  `style=` attributes, except the one existing custom-property carrier on the hero
  (`style="--team-hero-image: url(...)"`), which passes data, not style, and has no CSS-file equivalent.
- **Move** (cut from `styles.css`, paste into `team.css`, unchanged unless noted): `.robot-specs`,
  `.specs-container`, `.spec-card`, `.spec-label`, `.spec-value`, `.goals-section`, `.goals-container`,
  `.goal-item`, `.goal-header`, `.goal-name`, `.goal-percent`, `.progress-bar`, `.progress-fill`,
  `.download-btn`, `.download-icon`, `.robot-showcase`, `.robot-tagline`, `.team-img`, and the
  `.specs-container` media query near line 2568. Approximate line anchors in the current `styles.css`:
  336–341 (a shared selector list — edit, do not delete), 1622–1740, 2035–2100, 2455–2470, 2568, 3075–3090.
  Re-grep before cutting; the login work has moved lines since.
- **Delete**: `.viewer-3d-container`, `.viewer-label`, `.viewer-controls`, `.viewer-btn` — the new viewer
  brings its own classes and these are used by nothing else.
- **Do not touch**: `.team-grid`, `.team-card` (shared with `about.html` and `notebook.html`),
  `.hero-image`, `.scroll-indicator`, `.award-*`, `.cta-*`, `.breadcrumb`.
- New classes are prefixed by section, not by page: `roster-`, `viewer-`, `spec-`, `goal-`, `teamcta-`.
  Before adding any new class name, grep `static/css/styles.css` and `templates/` for it.
- Reuse existing tokens only: `--maroon-dark: #800000`, `--maroon-light: #944547`,
  `--accent-gold: #ffd700`, `--accent-light: #f1f1f1`, `--text-dark: #1a1a1a`, `--text-light: #666`,
  `--bg-light: #fafafa`, `--spacing-*`, `--transition-base`. Card look: `border: 3px solid var(--text-dark)`,
  `border-radius: 16px`, `box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2)`, hover `translate(-4px, -4px)`.
- Every new class that sets a color or background gets a `[data-theme="dark"]` variant: card background
  `#1e1e1e`, border `#444`, heading `#d4a0a1`, body `#bbb`. The specs band is already dark in both themes;
  leave its palette alone.

## Responsive Behavior

- Hero stat chips: row, wrapping to two lines under 600px. No horizontal scroll.
- Roster grid: `repeat(auto-fit, minmax(220px, 1fr))`, 1 column under 480px.
- Viewer: `aspect-ratio: 16/9` down to 768px, then `4/3` so the model does not become a letterbox slit.
- Specs: existing `auto-fit, minmax(200px, 1fr)` behavior kept.
- Goals: unchanged; full width at every size.

## Verification

- `pytest` green, including a new `tests/test_team_page.py` (uses the mongomock `client` fixture in
  `tests/conftest.py`).
- `/team/<number>` renders 200 for a fully populated team and for a bare `{team_number}`-only team.
- **Awards grid present in both cases** — assert `Competition Awards` in the HTML. This is a regression
  guard, not a nicety.
- No `TBA` string anywhere in the rendered page.
- `grep -c 'style="' templates/team.html` returns 1 (the hero custom property, and nothing else).
- Every `/static/` URL in the rendered page resolves 200.
- Light and dark themes both legible; layout holds at 1440px, 768px, 375px with no horizontal scroll.
- With an STL: model renders and orbits. Without: empty state, and the network log shows three.js was
  never fetched.
