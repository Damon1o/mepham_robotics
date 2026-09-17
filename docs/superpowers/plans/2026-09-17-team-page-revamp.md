# Team Page Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Design spec:** `docs/superpowers/specs/2026-09-17-team-page-revamp-design.md` — read it before Task 1.

**Goal:** Rebuild `templates/team.html` into eight sections (Hero + stat strip, Breadcrumb, Roster,
**Competition Awards — unchanged**, Robot Showcase with a working STL viewer, Technical Specs that hide
what has no data, Season Goals with ARIA, Join CTA); move every team-only rule out of
`static/css/styles.css` into `static/css/pages/team.css`; add `static/js/team.js`; add
`tests/test_team_page.py`.

**Architecture:** Flask + Jinja2. Route `/team/<team_number>` in `api/index.py:team_page()` already passes
`team` and `team_awards`. **No route, no schema, and no admin-panel changes** — every new thing on the page
is derived from data the admin panel already writes. `base.html` loads `{% block page_styles %}` after
`styles.css`, so equal-specificity rules in `team.css` win. `{% block page_scripts %}` is the hook for
`team.js`. Dark mode is a `[data-theme="dark"]` ancestor selector. Icons are Lucide via
`<i data-lucide="name">`, initialized by `base.html`.

**Tech Stack:** Flask, Jinja2, plain CSS custom properties, vanilla JS, three.js (CDN, lazy, viewer only),
pytest + mongomock (`tests/conftest.py` supplies `db` / `client` fixtures; `api.index.db` is a `_DbProxy`
that resolves through the patched `get_db`, so the fixtures cover this route).

## Global Constraints

- **The awards display stays.** `{% include "partials/awards_grid.html" %}` keeps its position between the
  Roster and the Robot Showcase. Do not edit `templates/partials/awards_grid.html`. Do not touch any
  `.award-*` rule. Every task's verification asserts the awards grid is still rendered.
- CSS never lives in HTML. When done, `grep -c 'style="' templates/team.html` returns exactly **1** — the
  hero's `--team-hero-image` custom property, which carries data, not style.
- Do not restyle `.team-grid` or `.team-card`: `about.html` and `notebook.html` use them. The roster gets
  new `roster-*` classes.
- Before adding any new class name, grep `static/css/styles.css` and `templates/` for it.
- Reuse existing tokens only: `--maroon-dark: #800000`, `--maroon-light: #944547`, `--accent-gold: #ffd700`,
  `--accent-light: #f1f1f1`, `--text-dark: #1a1a1a`, `--text-light: #666`, `--bg-light: #fafafa`,
  `--spacing-*`, `--transition-base`. Card look: `border: 3px solid var(--text-dark)`,
  `border-radius: 16px`, `box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2)`, hover `translate(-4px, -4px)`.
  Headings in cards use `'Space Mono', monospace`.
- Every new class that sets a color or background gets a `[data-theme="dark"]` variant: card background
  `#1e1e1e`, border `#444`, heading `#d4a0a1`, body `#bbb`.
- Full-bleed only for sections that paint a background (Robot Showcase, Technical Specs):
  `max-width: none; margin-left: 0; margin-right: 0;` with an inner `max-width: 1200px; margin: 0 auto;`.
- Never print `TBA`, `#`, or a zero-count chip. A section with no data does not render.
- `loading="lazy"` on every `<img>`.
- Commit style: short imperative sentence, no `feat:` prefix, ending with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Shared Verification Commands

Run from the repo root.

**RENDER** — page returns 200 for a populated and a bare team, awards grid survives, no `TBA`, every
static URL resolves:

```bash
python -c "
import re, mongomock, api.index as m
mock = mongomock.MongoClient()['mepham']
m.get_db = lambda: mock
mock['teams'].insert_many([
  {'team_number':'77628A','nickname':'Hydra','tagline':'Precision.','hero_image':'static/assets/photos/hero.png',
   'specs':{'drive_train':'X-drive','lift_system':'','intake':'Flex wheel','auton_consistency':''},
   'notebook_link':'https://example.com/nb',
   'members':[{'name':'Ada','role':'Captain','photo':''},{'name':'Bo','role':'Builder','photo':'static/assets/profile/base.png'}],
   'goals':[{'name':'Win states','progress':100},{'name':'Skills 200','progress':40}]},
  {'team_number':'77628Z'},
])
mock['awards'].insert_one({'team_number':'77628A','title':'Excellence','count':2,'icon':'trophy.png','layout':'','border':'','shimmer':False})
m.app.config['TESTING']=True; c = m.app.test_client()
for t in ('77628A','77628Z'):
    r = c.get('/team/'+t); h = r.data.decode()
    urls = sorted(set(re.findall(r'/static/[^\"\'?) ]+', h)))
    bad = [u for u in urls if c.get(u).status_code != 200]
    print(t, 'status', r.status_code, '| awards', 'Competition Awards' in h, '| TBA', 'TBA' in h, '| broken', bad)
"
```

Expected: `status 200`, `awards True`, `TBA False`, `broken []` for **both** teams.

**CSSCHECK** — brace balance and no leaked inline styles:

```bash
python -c "
s=open('static/css/pages/team.css',encoding='utf-8').read()
print('braces', s.count('{'), s.count('}'), 'balanced' if s.count('{')==s.count('}') else 'UNBALANCED')
h=open('templates/team.html',encoding='utf-8').read()
print('inline style= count', h.count('style=\"'), '(must be 1)')
print('<style> blocks', h.count('<style'), '(must be 0)')
"
```

**ORPHANCHECK** — a class moved out of `styles.css` is not still referenced by another template:

```bash
for c in robot-specs specs-container spec-card spec-label spec-value goals-section goals-container goal-item goal-header goal-name goal-percent progress-bar progress-fill download-btn download-icon robot-showcase robot-tagline team-img viewer-3d-container viewer-label viewer-controls viewer-btn; do
  echo "$c -> $(grep -rl "$c" templates/ | tr '\n' ' ')"
done
```

Expected before Task 6: every class maps to `templates/team.html` only. If any maps elsewhere, stop and
leave that rule in `styles.css`.

**TESTS**: `pytest -q`

## Tasks

### Task 1 — Test harness first (RED)

- [ ] Create `tests/test_team_page.py` using the `db` and `client` fixtures from `tests/conftest.py`.
- [ ] Add a `team_factory`-style helper inserting a populated team (two members, one at 100% goal, two of
      four specs filled, a real `notebook_link`, an `stl_path`) and a bare team with only `team_number`.
- [ ] Write these tests. They describe the finished page, so most fail now:
  - `test_team_page_renders` — 200 for the populated team.
  - `test_awards_section_always_present` — `Competition Awards` in the HTML for **both** the populated and
    the bare team. **This test must never be weakened or deleted.**
  - `test_no_tba_placeholder` — `TBA` not in the HTML for either team.
  - `test_empty_specs_section_hidden` — bare team's HTML has no `robot-specs`.
  - `test_notebook_button_hidden_when_placeholder` — a team with `notebook_link` `'#'` renders no
    Engineering Notebook button.
  - `test_goal_progress_has_aria` — `aria-valuenow="40"` and `role="progressbar"` present.
  - `test_goal_progress_clamped` — a goal stored at `150` renders `aria-valuenow="100"` and no width above
    `100%`.
  - `test_member_photo_fallback` — a member with an empty `photo` renders `static/assets/profile/base.png`.
  - `test_leadership_sorted_first` — index of `Captain` member's name < index of the non-lead member's.
  - `test_no_inline_styles` — the rendered HTML contains exactly one `style="` (the hero variable).
  - `test_bare_team_renders` — 200 for a team with only `team_number`, no traceback.
- [ ] Run **TESTS**. Record which fail and why. Do not write page code in this task.
- [ ] Commit: `Add failing team page tests ahead of revamp`

### Task 2 — Roster and hero stat strip

- [ ] In `templates/team.html`, add the hero stat strip per the spec (members / awards / goals), each chip
      rendered only when its value is non-zero; the whole strip omitted when all three are.
      Awards count = `team_awards|sum(attribute='count')` — no new query.
- [ ] Replace the `#team` section's `.team-grid` / `.team-card` / `.team-img` markup with
      `roster-grid` / `roster-card` / `roster-photo`. Keep the `.ripple` heading and `fade-in-section`.
- [ ] Leadership-first ordering via a Jinja `selectattr`/`rejectattr` pair over the role keywords
      `captain`, `lead`, `president`, `mentor` (case-insensitive). Everyone else keeps existing order.
- [ ] Photo fallback to `static/assets/profile/base.png`; role line rendered only when set; roster empty
      state "Roster coming soon for this team."
- [ ] `member.user_id` profile link: **first** `grep -n "profile\|/user/" api/index.py`. Link only if a
      public profile route exists. If none, render plain text and note it in the commit body.
- [ ] Add `roster-*` rules (plus dark variants and the 480px single-column breakpoint) to
      `static/css/pages/team.css`.
- [ ] Verify: **RENDER**, **CSSCHECK**, **TESTS** — roster, photo-fallback and inline-style tests green;
      awards assertion still green.
- [ ] Commit: `Rebuild team roster with leadership ordering and hero stats`

### Task 3 — Technical specs and season goals

- [ ] Specs: build the list in-template from the four existing fields, dropping falsy ones. One
      `.spec-card` each. No `TBA`. Whole section omitted when the list is empty.
- [ ] Engineering Notebook button renders only when `team.notebook_link` is truthy and not `'#'`.
- [ ] Add `.ripple` to the Technical Specifications `<h2>`.
- [ ] Goals: `role="progressbar"`, `aria-valuenow` (clamped 0–100 in the template), `aria-valuemin`,
      `aria-valuemax`, `aria-label` with the goal name. Keep the `data-progress` attribute — the existing
      `IntersectionObserver` at `static/js/script.js:578` reads it. Do not duplicate that logic.
- [ ] `.goal-complete` modifier at 100%: gold fill plus a Lucide `check` icon beside the name.
- [ ] Section omitted when `team.goals` is empty.
- [ ] Add the new `.spec-*` / `.goal-*` rules to `team.css` (dark variants included; the specs band is
      already dark in both themes — leave its palette).
- [ ] Verify: **RENDER**, **TESTS** — specs, notebook, clamp and ARIA tests green.
- [ ] Commit: `Render only populated specs and add goal progress accessibility`

### Task 4 — Robot showcase: the real STL viewer

- [ ] Delete the placeholder markup: `.viewer-3d-container`, `.viewer-label`, the dead Rotate button.
- [ ] New markup: `<div id="robot-viewer" data-stl="{{ team.stl_path }}" role="img" aria-label="3D model of
      {{ team.nickname or team.team_number }}">` plus a visible caption and a Reset View button. Render the
      `data-stl` attribute only when `team.stl_path` is set.
- [ ] Create `static/js/team.js`, loaded via `{% block page_scripts %}`. It must:
  - do nothing at all when `#robot-viewer[data-stl]` is absent (no three.js fetch — verified in the
    network log);
  - dynamically import a **pinned** three.js build plus `STLLoader` and `OrbitControls` from
    `cdn.jsdelivr.net`;
  - render the model centered and auto-scaled to fit, with drag-rotate, scroll-zoom and Reset View;
  - honor `prefers-reduced-motion` — no auto-spin, motion on user input only;
  - on WebGL-unavailable, import failure, or fetch failure, replace the container with the same empty
    state used when there is no STL. No silent console-only failure.
- [ ] Empty state: tagline card plus "CAD model not published for this robot yet."
- [ ] Viewer CSS in `team.css`: `aspect-ratio: 16/9`, `4/3` under 768px, dark variant, focus-visible ring
      on the Reset button.
- [ ] Verify: **RENDER**; then in a browser, a team with an `stl_path` renders and orbits, and a team
      without shows the empty state with zero three.js requests in the network log.
- [ ] Commit: `Replace 3D viewer placeholder with a working STL viewer`

### Task 5 — Join CTA band

- [ ] Closing section after Season Goals: one line of copy, `.cta-button .cta-primary` → `/contact`
      ("Join the Club") and a secondary → `/achievements` ("All Achievements"). Reuse existing CTA classes;
      add only layout rules under `teamcta-` in `team.css`.
- [ ] Verify: **RENDER**, **TESTS**.
- [ ] Commit: `Add join call-to-action band to team page`

### Task 6 — CSS migration and dead-rule cleanup

- [ ] Run **ORPHANCHECK**. Any class that resolves to a template other than `team.html` stays in
      `styles.css` — record which, and skip it.
- [ ] Move, byte-for-byte unless the task above already replaced them, from `styles.css` to `team.css`:
      `.robot-specs`, `.specs-container`, `.spec-card`, `.spec-label`, `.spec-value`, `.goals-section`,
      `.goals-container`, `.goal-item`, `.goal-header`, `.goal-name`, `.goal-percent`, `.progress-bar`,
      `.progress-fill`, `.download-btn`, `.download-icon`, `.robot-showcase`, `.robot-tagline`,
      `.team-img`, and the `.specs-container` media query. Approximate current anchors: 336–341 (shared
      selector list — edit it, do not delete the block), 1622–1740, 2035–2100, 2455–2470, 2568, 3075–3090.
      Re-grep for exact lines; the login branch has shifted them.
- [ ] Delete outright: `.viewer-3d-container`, `.viewer-label`, `.viewer-controls`, `.viewer-btn`.
- [ ] Leave alone: `.team-grid`, `.team-card`, `.hero-image`, `.scroll-indicator`, `.award-*`, `.cta-*`,
      `.breadcrumb`.
- [ ] Verify: **CSSCHECK**, **RENDER**, **TESTS**, and open `/about` and `/notebook` in a browser — they
      share `.team-card` and must look unchanged.
- [ ] Commit: `Move team-only styles into pages/team.css and drop dead viewer rules`

### Task 7 — Cross-cutting verification

- [ ] `pytest -q` fully green.
- [ ] **RENDER** clean for both the populated and the bare team, with `awards True` in both.
- [ ] `grep -c 'style="' templates/team.html` → `1`.
- [ ] Browser pass at 1440 / 768 / 375px, light and dark, on a populated team and a bare team: no
      horizontal scroll, no overlap, every section legible, awards grid present.
- [ ] Keyboard pass: tab reaches the Reset View button, both CTAs and the notebook link, with a visible
      focus ring on each.
- [ ] Confirm nothing in `api/index.py`, `templates/partials/awards_grid.html`, or the admin panel was
      modified: `git diff --stat main...HEAD` lists only `templates/team.html`,
      `static/css/pages/team.css`, `static/css/styles.css`, `static/js/team.js`, `tests/test_team_page.py`,
      and the two docs.
- [ ] Use superpowers:requesting-code-review on the whole branch before opening a PR.

## Risks

| Risk | Mitigation |
|------|-----------|
| Moving CSS breaks `/about` or `/notebook` via shared `.team-card` | ORPHANCHECK before every move; browser check in Task 6 |
| Awards grid dropped during the rewrite | `test_awards_section_always_present` runs in every task's TESTS gate |
| three.js CDN dependency unwanted | Spec's alternative: delete the showcase, move the tagline under the hero — one task to switch |
| `styles.css` line anchors stale after the login branch merges | Every anchor is "re-grep before cutting" |
| `stl_path` blobs are large and slow on mobile | Lazy load; viewer only initializes when the section scrolls into view |
