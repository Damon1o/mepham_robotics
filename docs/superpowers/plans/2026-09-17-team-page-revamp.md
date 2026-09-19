# Team Page Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Design spec:** `docs/superpowers/specs/2026-09-17-team-page-revamp-design.md` — read it before Task 1.

**Goal:** Rebuild `/team/<team_number>` into a live season hub with the feature set overclock.co gives its
teams — live world skills standing, season scoreboard, per-event results with photo galleries, a real
roster with roles and tenure, a season archive, a team journey — rendered entirely in Mepham's existing
visual style. **The Competition Awards grid is preserved exactly and guarded by a test in every task.**

**Architecture:** Flask + Jinja2. The page renders instantly from MongoDB; everything from RobotEvents
arrives asynchronously through a new `GET /api/team/<team_number>/live` JSON route backed by a TTL cache
collection, so a slow or missing upstream never slows or breaks the page. New admin fields are all
optional and back-compatible — no migration, and existing team documents keep rendering. `base.html`
loads `{% block page_styles %}` after `styles.css`, so `team.css` wins at equal specificity;
`{% block page_scripts %}` carries `team.js`.

**Tech Stack:** Flask 3.1, pymongo 4.12, `requests` 2.32 (already a dependency), Jinja2, plain CSS custom
properties, vanilla JS, three.js (CDN-pinned, lazy, viewer only), pytest + mongomock
(`tests/conftest.py` gives `db` / `client` / `make_user`; `api.index.db` is a `_DbProxy` resolving through
the patched `get_db`, so the fixtures cover these routes).

## Global Constraints

- **The awards display stays.** `templates/partials/awards_grid.html` is not edited. Its include keeps its
  position. No `.award-*` rule is touched. Every task runs **AWARDSGUARD** before its commit.
- **No visual language from overclock.co.** Features only. Colors, borders, shadows, fonts and motion come
  from the existing Mepham tokens: `--maroon-dark #800000`, `--maroon-light #944547`,
  `--accent-gold #ffd700`, `--accent-light #f1f1f1`, `--text-dark #1a1a1a`, `--text-light #666`,
  `--bg-light #fafafa`, `--spacing-*`, `--transition-base`. Cards: `border: 3px solid var(--text-dark)`,
  `border-radius: 16px`, `box-shadow: 8px 8px 0 rgba(148,69,71,0.2)`, hover `translate(-4px,-4px)`.
  Headings `'Space Mono', monospace`, section `<h2>` gets `.ripple`, sections get `fade-in-section`.
- CSS never lives in HTML: `grep -c 'style="' templates/team.html` ends at exactly **1** (the hero's
  `--team-hero-image`).
- Do not restyle `.team-grid` / `.team-card` — `about.html` and `notebook.html` use them. Roster gets new
  `roster-*` classes.
- Grep every new class name against `static/css/styles.css` and `templates/` before using it.
- Every new class that sets a color gets a `[data-theme="dark"]` variant: card `#1e1e1e`, border `#444`,
  heading `#d4a0a1`, body `#bbb`.
- Full-bleed only for background-painting sections (Live Skills, Season Scoreboard, Technical Specs):
  `max-width: none; margin-left: 0; margin-right: 0;` with an inner `max-width: 1200px; margin: 0 auto;`.
- Every new field is optional. A team document holding only `team_number` renders 200 after every task.
- Never print `TBA`, a `#` link, or a zero-value stat chip. No data → the block hides.
- **No network in tests.** RobotEvents calls are mocked with `monkeypatch`.
- Secrets: `ROBOTEVENTS_TOKEN` is read from the environment only. Never logged, never rendered, never
  committed. Absent token is a supported, tested state.
- `loading="lazy"` on every `<img>`.
- Commit style: short imperative sentence, no `feat:` prefix, ending
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Shared Verification Commands

Run from the repo root.

**SEED** — the fixture used by the render checks below; save it once as
`$CLAUDE_JOB_DIR/tmp/seed_team.py` and import it, or paste it inline:

```python
import mongomock, api.index as m
mock = mongomock.MongoClient()['mepham']
m.get_db = lambda: mock
mock['teams'].insert_many([
  {'team_number':'77628A','season':'2025-26','nickname':'Hydra','tagline':'Precision.',
   'division':'High School','since':2019,'worlds_appearances':2,
   'hero_image':'static/assets/photos/hero.png',
   'specs':{'drive_train':'X-drive','lift_system':'','intake':'Flex wheel','auton_consistency':''},
   'notebook_link':'https://example.com/nb',
   'members':[{'name':'Ada Lovelace','role':'Captain','roles':['Captain','Programmer'],'since':2022,'subteam':'Programming','photo':''},
              {'name':'Bo Diaz','role':'Builder','subteam':'Mechanical','photo':'static/assets/profile/base.png'}],
   'goals':[{'name':'Win states','progress':100},{'name':'Skills 200','progress':40}]},
  {'team_number':'77628A','season':'2024-25','nickname':'Hydra'},
  {'team_number':'77628Z'},
])
mock['awards'].insert_one({'team_number':'77628A','title':'Excellence','count':2,
                           'icon':'trophy.png','layout':'','border':'','shimmer':False})
m.app.config['TESTING']=True
client = m.app.test_client()
```

**RENDER** — 200, awards present, no `TBA`, all static URLs resolve, for the populated team, the bare
team, and with `ROBOTEVENTS_TOKEN` unset:

```bash
MONGO_URI=mongodb://tests-use-mongomock ROBOTEVENTS_TOKEN= python -c "
import re, runpy
g = runpy.run_path('$CLAUDE_JOB_DIR/tmp/seed_team.py'); c = g['client']
for t in ('77628A','77628Z'):
    r = c.get('/team/'+t); h = r.data.decode()
    urls = sorted(set(re.findall(r'/static/[^\"\'?) ]+', h)))
    bad = [u for u in urls if c.get(u).status_code != 200]
    print(t, 'status', r.status_code, '| awards', 'Competition Awards' in h,
          '| TBA', 'TBA' in h, '| broken', bad)
"
```

Expected for both teams: `status 200`, `awards True`, `TBA False`, `broken []`.

**AWARDSGUARD** — the non-negotiable one, run before every commit:

```bash
pytest -q tests/test_team_page.py -k awards
git diff --stat HEAD -- templates/partials/awards_grid.html   # must print nothing
grep -c "awards_grid.html" templates/team.html                # must print 1
```

**CSSCHECK**

```bash
python -c "
s=open('static/css/pages/team.css',encoding='utf-8').read()
print('braces', s.count('{'), s.count('}'), 'balanced' if s.count('{')==s.count('}') else 'UNBALANCED')
h=open('templates/team.html',encoding='utf-8').read()
print('inline style=', h.count('style=\"'), '(must be 1)'); print('<style>', h.count('<style'), '(must be 0)')
"
```

**ORPHANCHECK** — before moving any rule out of `styles.css`:

```bash
for c in robot-specs specs-container spec-card spec-label spec-value goals-section goals-container \
         goal-item goal-header goal-name goal-percent progress-bar progress-fill download-btn \
         download-icon robot-showcase robot-tagline team-img viewer-3d-container viewer-label \
         viewer-controls viewer-btn; do
  echo "$c -> $(grep -rl "$c" templates/ | tr '\n' ' ')"
done
```

Every class must map to `templates/team.html` only. Anything else stays in `styles.css`.

**TESTS**: `pytest -q`

---

## Phase 1 — Foundation

### Task 1 — Tests first (RED)

- [ ] Create `tests/test_team_page.py` with a `team_factory` helper covering: a populated team (two
      members with `roles`/`since`/`subteam`, one 100% goal, two of four specs filled, a real
      `notebook_link`, an `stl_path`, a second season document) and a bare `{team_number}`-only team.
- [ ] Write these tests. Most fail now — that is the point:
  - `test_team_page_renders` — 200, populated team.
  - `test_bare_team_renders` — 200 for `team_number`-only. *(Currently 500:
    `UndefinedError: 'dict object' has no attribute 'specs'`.)*
  - `test_awards_section_always_present` — `Competition Awards` in the HTML for populated **and** bare
    teams. **Never weaken or delete this test.**
  - `test_awards_grid_partial_still_included` — `awards_grid.html` referenced once in `team.html`.
  - `test_no_tba_placeholder`, `test_empty_specs_section_hidden`,
    `test_notebook_button_hidden_when_placeholder`.
  - `test_goal_progress_has_aria`, `test_goal_progress_clamped` (a stored `150` renders
    `aria-valuenow="100"`).
  - `test_member_photo_fallback`, `test_member_initials_avatar_when_no_photo`,
    `test_member_roles_chips`, `test_roster_grouped_by_subteam`, `test_leadership_sorted_first`.
  - `test_identity_bar_stats`, `test_identity_bar_omits_missing_stats`.
  - `test_live_sections_hidden_without_token` — with `ROBOTEVENTS_TOKEN` unset, no skills panel markup
    and still 200.
  - `test_season_switcher_hidden_for_single_season`, `test_season_query_param_selects_document`.
  - `test_no_inline_styles` — exactly one `style="` in the rendered HTML.
- [ ] Run **TESTS**; record the failures. Write no page code in this task.
- [ ] Commit: `Add failing team page tests ahead of revamp`

### Task 2 — Season-aware route and safe defaults

- [ ] In `api/index.py:team_page()`: select the team document by `?season=` when present, else the newest
      `season` value, else the only document. Keep working for documents with no `season` field.
- [ ] Pass `seasons` (a sorted distinct list for this team number) to the template; the switcher renders
      only when `len(seasons) > 1`.
- [ ] Guard every optional field at render: `team.specs`, `team.members`, `team.goals`, `team.journey`,
      `team.events` all default to empty via `|default({}, true)` / `|default([], true)`. This is what
      fixes the current 500.
- [ ] Keep the existing `team_awards` query and the `awards_grid.html` include exactly as they are.
- [ ] Verify: **RENDER** (both teams 200), **AWARDSGUARD**, **TESTS** — bare-team and season tests green.
- [ ] Commit: `Make team route season-aware and safe for sparse team documents`

### Task 3 — Admin fields for the new data

- [ ] `templates/admin.html` team form: add `season` (text, `2025-26`), `division` (select: High School /
      Middle School), `since` (number), `worlds_appearances` (number), `robotevents_number` (text,
      placeholder "defaults to team number").
- [ ] `static/js/admin.js` member rows: add `member_roles_{i}` (comma-separated), `member_since_{i}`
      (number), `member_subteam_{i}` (select: Mechanical / Electrical / Programming / Notebook & Outreach /
      blank). Keep `member_role_{i}` — it stays the fallback.
- [ ] `api/index.py` team save route: persist all of the above. Split `roles` on commas, strip blanks, and
      drop the key entirely when empty. Cast the numeric fields with a guard so a blank field stores
      nothing rather than `0`.
- [ ] Do not touch the awards admin section or the `awards` collection.
- [ ] Add `tests/test_admin_team_fields.py`: saving with the new fields persists them; saving without them
      leaves an existing document's other keys intact (no clobbering).
- [ ] Verify: **TESTS**, **AWARDSGUARD**, and a manual admin round-trip — create a team, edit it, confirm
      values survive.
- [ ] Commit: `Add season, division, tenure and sub-team fields to the team admin form`

## Phase 2 — Live Data

### Task 4 — RobotEvents service layer (no UI)

- [ ] Create `api/robotevents.py`:
  - `get_token()` reads `ROBOTEVENTS_TOKEN`; returns `None` when unset. **Never log it.**
  - `fetch(path, params)` — `requests.get` against the v2 base URL, bearer auth, `timeout=2.5`, all
    exceptions caught and converted to `None`.
  - Cache helpers over a `re_cache` collection: key on path + params, store `fetched_at`, TTL index at
    7 days as a floor. Freshness windows: skills 30 min, events/awards 6 h. **On upstream failure, return
    the stale document** with its real `fetched_at` — never nothing when something exists.
  - `team_summary(team_number)` → `{skills: {...}, events: [...], awards: [...], fetched_at, stale}` or
    `None` when there is no token.
  - `record_skills_history(team_number, rank, score)` appending to a capped `re_history` document, and
    `rank_trend(team_number, current_rank)` returning `{'direction': 'up'|'down'|'flat'|'new', 'delta': n}`
    by comparing against the newest entry older than 24 h.
- [ ] **Verify endpoint shapes against the live RobotEvents v2 docs before coding the parsers.** The spec's
      endpoint table is a starting point, not gospel. Record what you confirmed in the commit body.
- [ ] Add `tests/test_robotevents.py`, all upstream calls monkeypatched: no token → `None`; cache hit does
      not call upstream; expired cache refetches; upstream error with a stale doc returns the stale doc
      marked `stale=True`; upstream error with no cache returns `None`; trend computes up/down/flat/new.
- [ ] Add `ROBOTEVENTS_TOKEN=` to `.env.local` (empty) and document it in `README.md`.
- [ ] Verify: **TESTS**, plus `grep -rn "ROBOTEVENTS_TOKEN" --include=*.py .` shows it read from
      `os.environ` only, never interpolated into output.
- [ ] Commit: `Add cached RobotEvents client with graceful offline degradation`

### Task 5 — Live JSON route

- [ ] Add `GET /api/team/<team_number>/live` to `api/index.py`, returning
      `{skills, trend, scoreboard, events, fetched_at, stale}`, or HTTP 204 when there is no token or no
      data. Use the team's `robotevents_number` when set.
- [ ] Scoreboard aggregation lives server-side: competitions counted by level (local / signature /
      championship), awards this season, and a Triple Crown count (an event with Tournament Champion +
      Excellence + Skills Champion).
- [ ] Response is served from `re_cache`, so N visitors produce one upstream call per TTL window.
- [ ] Route-level tests with the client fixture: 204 without a token, well-shaped JSON with mocked data,
      never a 500 on upstream failure.
- [ ] Verify: **TESTS**, **AWARDSGUARD**.
- [ ] Commit: `Add live team data JSON endpoint backed by the RobotEvents cache`

### Task 6 — Live Skills panel UI

- [ ] Markup in `team.html`: `skills-panel` section with a skeleton (`aria-busy="true"`,
      `aria-live="polite"`), tiles for combined / driver / programming score, world rank, region rank,
      percentile, a trend marker, `Updated <relative>`, and a RobotEvents profile link.
- [ ] The section is present but hidden by default; `team.js` reveals it only on a 200 from the live route.
      On 204 or error it removes the section entirely — no empty frame, no spinner that never resolves.
- [ ] Trend marker carries text (`▲ Up 4`), never colour alone. Stale data is labelled with its real age.
- [ ] `skills-*` CSS in `team.css`: Mepham card treatment, maroon full-bleed band, gold numerals, dark
      variant, 3→2→1 column breakpoints. No count-up animation under `prefers-reduced-motion`.
- [ ] Verify: **RENDER** with `ROBOTEVENTS_TOKEN` unset (no skills markup visible, page 200),
      **CSSCHECK**, **AWARDSGUARD**, **TESTS**.
- [ ] Commit: `Add live world skills panel to the team page`

### Task 7 — Season Scoreboard and season award list

- [ ] Scoreboard band **above** the untouched awards grid: competition counts by level, awards this
      season, Triple Crown badge when the count is non-zero. Filled by the same `team.js` fetch — one
      request feeds both panels.
- [ ] Under the awards grid, a chronological season award list (award, event, date) from the live data.
      This is additive: the grid itself and its own empty state are unchanged.
- [ ] Hide the whole scoreboard when there is no live data.
- [ ] Verify: **AWARDSGUARD** (`git diff` on the partial must be empty), **RENDER**, **TESTS**.
- [ ] Commit: `Add season scoreboard above the awards grid`

### Task 8 — Event Results timeline

- [ ] Rows per event: date, name, level badge, qualification record, elimination result, awards, skills
      rank at that event. Live data merged with any `team.events[]` document for photos.
- [ ] A row with photos expands (`<details>`/`<summary>`, or a button with `aria-expanded`) to a
      horizontal photo strip. Clicking a photo opens a lightbox: focus trapped, Escape closes, focus
      returns to the thumbnail. No `alert()` / `confirm()` anywhere.
- [ ] Under 768px rows become stacked cards.
- [ ] Section hidden when there are no events.
- [ ] Verify: **RENDER**, **CSSCHECK**, **AWARDSGUARD**, **TESTS**, plus a keyboard pass on expand and
      lightbox.
- [ ] Commit: `Add per-event results timeline with photo galleries`

## Phase 3 — Static Sections

### Task 9 — Roster rebuild and hero identity bar

- [ ] Identity bar under the hero copy: members, awards (`team_awards|sum(attribute='count')` — no new
      query), `SINCE <year>`, `<n>× WORLDS`, division badge. Each chip omitted when empty; the bar omitted
      when all are.
- [ ] Season switcher pill row, rendered only when `seasons|length > 1`, linking `?season=`.
- [ ] Roster on new `roster-*` classes (leave `.team-card` alone): grouped by `subteam` with an ungrouped
      fallback, leadership first inside each group (role keywords `captain`, `lead`, `president`,
      `mentor`, case-insensitive), role chips from `roles` falling back to `role`, `Since <year>` when set.
- [ ] Avatar: photo when set, otherwise an initials circle (`aria-hidden`, since the name is adjacent).
- [ ] Roster empty state: "Roster coming soon for this team."
- [ ] `member.user_id` profile link only if a public profile route exists — `grep -n "profile\|/user/"
      api/index.py` first. If none, plain text; do not invent a route.
- [ ] Verify: **RENDER**, **CSSCHECK**, **AWARDSGUARD**, **TESTS** — roster, avatar, chips, grouping,
      identity-bar and season-switcher tests green.
- [ ] Commit: `Rebuild roster with sub-teams, role chips and a hero identity bar`

### Task 10 — Robot showcase: working viewer and photo gallery

- [ ] Delete the placeholder: `.viewer-3d-container` markup, `.viewer-label`, the dead Rotate button.
- [ ] New markup: `<div id="robot-viewer" data-stl="..." role="img" aria-label="3D model of ...">` plus a
      visible caption and a Reset View button. `data-stl` rendered only when `team.stl_path` is set.
- [ ] `static/js/team.js`: do nothing when `#robot-viewer[data-stl]` is absent — **no three.js fetch at
      all**. Otherwise dynamically import a pinned three.js + `STLLoader` + `OrbitControls` from
      `cdn.jsdelivr.net`, initialize only when the section scrolls into view, center and auto-scale the
      model, wire drag-rotate / scroll-zoom / Reset View, and skip auto-spin under
      `prefers-reduced-motion`.
- [ ] Failure path — no WebGL, import failure, or fetch failure — swaps in the same fallback used when
      there is no STL. No console-only failure.
- [ ] Fallback order: STL viewer → robot photo gallery (`team.events[].photos` or hero image) → tagline
      card alone with "CAD model not published for this robot yet."
- [ ] Viewer CSS in `team.css`: `16/9`, `4/3` under 768px, dark variant, focus-visible ring on Reset.
- [ ] Verify: **RENDER**; in a browser, a team with an STL renders and orbits, and a team without shows
      the fallback with **zero** three.js requests in the network log.
- [ ] Commit: `Replace the 3D viewer placeholder with a working STL viewer`

### Task 11 — Specs, goals, journey, CTA

- [ ] Specs: build the list from the four existing fields, dropping falsies; one `.spec-card` each; never
      `TBA`; section hidden when empty; `.ripple` added to its `<h2>`; Engineering Notebook button only
      when `notebook_link` is truthy and not `'#'`.
- [ ] Goals: `role="progressbar"`, `aria-valuenow` clamped 0–100 in the template, `aria-valuemin/max`,
      goal name as `aria-label`; `.goal-complete` gold state with a Lucide `check` at 100%; section hidden
      when empty. Keep the `data-progress` contract read by the existing `IntersectionObserver` at
      `static/js/script.js:578` — do not duplicate that logic in `team.js`.
- [ ] Team Journey timeline from `team.journey[]`, reusing the about page's existing timeline classes;
      hidden when empty. Add the matching admin repeater (`journey_date_{i}` / `journey_title_{i}` /
      `journey_description_{i}`) mirroring the goals repeater in `static/js/admin.js`.
- [ ] Join CTA band: one line of copy, `.cta-button .cta-primary` → `/contact` ("Join the Club") and a
      secondary → `/achievements` ("All Achievements"). Layout-only rules under `teamcta-`.
- [ ] Verify: **RENDER**, **CSSCHECK**, **AWARDSGUARD**, **TESTS**.
- [ ] Commit: `Harden specs and goals, add team journey and join CTA`

## Phase 4 — Cleanup and Sign-off

### Task 12 — CSS migration and dead-rule removal

- [ ] Run **ORPHANCHECK**. Anything resolving to a template other than `team.html` stays in `styles.css`;
      record which in the commit body.
- [ ] Move to `team.css`: `.robot-specs`, `.specs-container`, `.spec-card`, `.spec-label`, `.spec-value`,
      `.goals-section`, `.goals-container`, `.goal-item`, `.goal-header`, `.goal-name`, `.goal-percent`,
      `.progress-bar`, `.progress-fill`, `.download-btn`, `.download-icon`, `.robot-showcase`,
      `.robot-tagline`, `.team-img`, and the `.specs-container` media query. Approximate current anchors —
      **re-grep, the login branch shifted them**: 336–341 (a shared selector list: edit, do not delete),
      1622–1740, 2035–2100, 2455–2470, 2568, 3075–3090.
- [ ] Delete: `.viewer-3d-container`, `.viewer-label`, `.viewer-controls`, `.viewer-btn`.
- [ ] Leave alone: `.team-grid`, `.team-card`, `.award-*`, `.hero-image`, `.scroll-indicator`, `.cta-*`,
      `.breadcrumb`, the timeline classes.
- [ ] Verify: **CSSCHECK**, **RENDER**, **TESTS**, plus a browser pass on `/about` and `/notebook` — they
      share `.team-card` and must look unchanged.
- [ ] Commit: `Move team-only styles into pages/team.css and drop dead viewer rules`

### Task 13 — Cross-cutting verification

- [ ] `pytest -q` fully green.
- [ ] **RENDER** clean for populated, bare, and token-less cases, with `awards True` in every one.
- [ ] **AWARDSGUARD**: `git diff main...HEAD -- templates/partials/awards_grid.html` prints nothing.
- [ ] `grep -c 'style="' templates/team.html` → `1`.
- [ ] Browser pass at 1440 / 768 / 375px, light and dark, on a populated team, a bare team, and with the
      token unset: no horizontal scroll, no overlap, no empty skeletons left behind, awards grid present
      in all three.
- [ ] Keyboard pass: season switcher, event expanders, lightbox (Escape + focus return), Reset View, both
      CTAs, notebook link — all reachable with a visible focus ring.
- [ ] Network pass: no three.js when there is no STL; one `/api/team/<n>/live` call per page load.
- [ ] Confirm `ROBOTEVENTS_TOKEN` appears in no committed file other than `.env.local` (empty) and
      `README.md` (as documentation).
- [ ] Use superpowers:requesting-code-review on the whole branch, then open the PR.

## Risks

| Risk | Mitigation |
|---|---|
| Awards grid damaged during a large rewrite | AWARDSGUARD runs before every commit; two dedicated tests; the partial must show an empty diff at sign-off |
| RobotEvents token never provisioned | Every live section degrades to hidden and is tested that way; Tasks 9–13 do not depend on it |
| RobotEvents API shapes differ from the spec's table | Task 4 verifies against live docs before writing parsers |
| Upstream slowness hurting page load | Page never blocks: async route, 2.5 s timeout, server-side cache, stale-serve on failure |
| Scope: this is 13 tasks | Phases are independently shippable. Phase 1 alone fixes the 500 and the data model; Phase 2 is the overclock-class feature; Phase 3 is the visible rebuild |
| Moving CSS breaks `/about` or `/notebook` via shared `.team-card` | ORPHANCHECK before every move, browser check in Task 12 |
| three.js CDN dependency unwanted | Task 10's fallback chain already renders without it — drop the import and the photo gallery takes over |
| Empty archive and empty galleries at launch | Season switcher and photo strips only appear once data exists; see the spec's Open Questions |
