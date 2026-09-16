# About Page Redesign — Design Spec

Date: 2026-09-15
Scope: `templates/about.html`, `static/css/pages/about.css`, cleanup in `static/css/styles.css`

## Goal

Content restructure plus visual polish. The current page runs eight same-shaped bands, duplicates itself
(Mission vs. Values), carries a placeholder photo carousel, and violates the project rule that CSS never
lives in HTML. The redesign merges the overlapping sections, adds the sub-teams block the page's own meta
description already promises, and moves every style into the per-page stylesheet.

Out of scope: a new visual language, a by-the-numbers stat strip, and new timeline entries for 2025–26.
Those need real data from the club and can come later.

## Section Map

| # | Section | Change |
|---|---------|--------|
| 1 | Hero | Keep `carousel6.jpg` background and copy. Retarget the dead `#process` CTA to `#subteams`, labeled "Our Teams" |
| 2 | Breadcrumb | Unchanged |
| 3 | Who We Are | Two columns, text left. Replace `assets/other/vexrobotics.png` with a real team photo in a bordered frame |
| 4 | What We Stand For | New merged band (replaces Mission + Values). Painted maroon background, six cards in a 3x2 grid |
| 5 | Sub-Teams | New. Photo left, four cards in a 2x2 grid right. Anchor `#subteams` |
| 6 | Culture & Safety | Merged D&I + Safety Captain. Painted background, two columns, safety-quiz CTA |
| 7 | Our Journey | Same four timeline entries, restyled |
| 8 | Team Moments | Carousel switches from the `base.png` stub to `carousel1.jpg`–`carousel10.jpg` |

Layout rhythm: sections 4 and 6 paint a background and run full-bleed; 3 and 5 alternate which side holds
the image. This follows the existing full-bleed convention — only sections that paint a background go
edge-to-edge.

## Content

### What We Stand For (six principles)

Merges the three Mission cards and four Values items, which overlapped. Community is folded into
Collaboration rather than kept as a seventh card, so the grid stays a clean 3x2.

| Principle | Lucide icon | Copy source |
|-----------|-------------|-------------|
| Excellence | `target` | Existing mission copy, verbatim |
| Innovation | `lightbulb` | Existing mission copy, verbatim |
| Collaboration | `handshake` | Existing mission copy, rewritten to absorb the Community line about giving back to school and local community |
| Perseverance | `mountain` | Existing value copy, verbatim |
| Integrity | `scale` | Existing value copy, verbatim |
| Mentorship | `graduation-cap` | Existing value copy, verbatim |

### Sub-Teams (four cards)

Draft copy, written for this spec, to be edited by the club before launch:

- **Mechanical** — CAD, fabrication, drivetrain and manipulator design.
- **Electrical** — wiring, sensors, and V5 brain configuration.
- **Programming** — C++ and Python, autonomous routines, odometry.
- **Notebook & Outreach** — engineering notebook, judging interviews, community events.

### Culture & Safety

Two existing one-card sections become one two-column band: the D&I statement (`globe` icon) on the left,
the Safety Captain block (`hard-hat` icon) plus the Take Safety Quiz CTA on the right. Copy for both is
carried over unchanged.

## CSS Architecture

- Every new rule goes in `static/css/pages/about.css`. `templates/about.html` ends with zero `style=`
  attributes — this removes the inline block currently on the Safety Captain section.
- Reuse existing tokens and components from `styles.css`: `cta-button`, `fade-in-section`, the timeline
  classes, and the shared border/shadow/color custom properties. No new design language is introduced.
- Each new class gets a `[data-theme="dark"]` variant. The existing dark-mode rules cover only
  `.mission-card` and `.di-statement`, both of which are retired.
- Dead-rule cleanup: `.mission-card`, `.values-list`, `.value-item`, and `.di-statement` are used by
  `templates/about.html` and nothing else (verified by grep across `templates/`). Their rules in
  `styles.css` — around lines 345, 2716–2760, 3313–3343, and 4244–4284 — are removed once the new markup
  lands. Re-run the grep at implementation time before deleting, in case another template picked them up.

## Responsive Behavior

- Two-column bands (Who We Are, Sub-Teams, Culture & Safety) collapse to one column at 768px, image last.
- What We Stand For: 3 columns, to 2 at 900px, to 1 at 600px.
- Sub-Teams cards: 2x2, to a single column at 600px.
- Timeline keeps its existing mobile rules in `styles.css`.

## Images

- Who We Are and Sub-Teams each take one existing `carousel*.jpg` photo. Several are 2.3–2.8 MB portrait
  originals; pick from the smaller landscape files (`carousel1`, `carousel5`, `carousel7`, `carousel8`,
  `carousel10`) where the slot is landscape, and keep `loading="lazy"`.
- Team Moments lists all ten carousel photos explicitly, matching the markup pattern already used by the
  index gallery. No Jinja `range()` loops — those produced the broken paths this page still carries.

## Verification

- Page renders at `/about` with HTTP 200 and every image URL resolves (no 404s in the network log).
- `grep -c 'style="' templates/about.html` returns 0.
- Light and dark themes both render every new section legibly.
- Layout holds at 1440px, 768px, and 375px with no horizontal scroll.
- Hero "Our Teams" CTA scrolls to the Sub-Teams section.
