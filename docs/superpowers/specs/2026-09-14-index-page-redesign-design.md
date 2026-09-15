# Index Page Redesign: Countdown → Carousel

Date: 2026-09-14

## Goal

Redesign `templates/index.html` sections from countdown through carousel for visual cohesion (one consistent neo-brutalist system instead of per-section bespoke gradients) and improved info flow. Hero content stays as-is; add flanking side photos.

## Section order change

Old: Hero → Countdown → Stats → Donate CTA → Timeline → Carousel
New: Hero → Countdown → Timeline (Upcoming Events) → Stats → Carousel → Donate CTA

Rationale: events belong next to countdown (both forward-looking); donate moves to the end as the closing ask after social proof (stats) and emotional hook (photos).

## Visual system

Reuse existing palette/tokens only — no new gradients invented per section:
- Colors: `--maroon-dark`, `--maroon-light`, `--accent-gold`, `--accent-light`, `--bg-light`, `--text-dark`, `--text-light`
- Borders: solid `--text-dark`, 2-3px on cards, 3-4px on section-level panels
- Shadows: `--shadow-brutal` (6px 6px) for cards, an 8px 8px variant for larger panels
- Fonts: `--font-display` (Balsamiq Sans) for headings, Space Mono for numeric displays (countdown, stats)
- Recurring motif: small rotated "sticker" tag (already exists as `.date-tag`) reused for section labels

## Per-section changes

**Hero**: unchanged center content (h1, tagline, CTA buttons). Add two flanking photo panels pinned to left/right edges, thick brutalist border, hidden below ~900px viewport width. Uses `hero.png` (center bg, unchanged) plus `carousel1.jpg` / `carousel2.jpg` as side photos (no new assets available).

**Countdown**: 4 boxes restyled as brutalist tiles — thick border, hard offset shadow, gold Space Mono numbers on maroon background, subtle rotate/lift on hover. Same JS/data (`#days #hours #minutes #seconds`, `window.COUNTDOWN_DATE`) untouched.

**Timeline** (moved up): keep existing vertical line + card structure and Jinja data (`event.month/day/name/location/time`). Restyle border/shadow weight to match new heavier brutalist scale; bigger date-tag stickers. No markup structure change beyond section reorder.

**Stats**: convert from glass/blur cards to solid brutalist cards — white/gold card, thick dark border, hard shadow, hover = lift + shadow grow. Remove `backdrop-filter: blur` and dot-pattern overlay.

**Carousel**: keep infinite-scroll track, dots, and JS entirely as-is. Swap item framing from soft rounded/glass border+glow to thick brutalist border + hard offset shadow on hover.

**Donate CTA** (moved to end): keep existing button style. Remove radial-dot pulse background animation; flat panel with maroon border matching new consistent language. Still closes the page.

## Non-goals

- No changes to countdown timer JS, carousel scroll JS, or backend/Jinja data shape.
- No new image assets sourced — side hero photos reuse existing carousel photos.
- No changes above the hero (nav/base template) or below carousel/donate.

## Testing

- Manual render check: `/` route loads 200, all sections present in new order.
- Visual check in browser at desktop + mobile (~600px, ~900px) widths — hero side photos hide correctly, brutalist borders/shadows consistent, no layout overflow.
- No JS console errors (countdown ticking, carousel scrolling/dots still functional).
