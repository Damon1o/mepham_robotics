# Donate Page Neo-Brutalist Restyle

Date: 2026-09-15

## Goal

Restyle `templates/donate.html` to match the neo-brutalist visual system already applied to the index page (thick solid borders, hard offset shadows, flat solid colors, no gradients/blur/soft rounded corners). No section reorder, no content changes, no backend/JS changes.

## Visual system

Reuse existing palette/tokens only:
- Colors: `--maroon-dark`, `--maroon-light`, `--accent-gold`, `--accent-light`, `--bg-light`, `--text-dark`, `--text-light`
- Borders: solid `--text-dark`, 2-3px on cards/inputs, 3-4px on section-level panels
- Shadows: `--shadow-brutal` (6px 6px) for cards, hover = translate + shadow grow (not soft lift)
- Fonts: `--font-display` for headings, existing body font elsewhere — no new fonts

## Per-section changes

**Hero**: replace gradient-over-photo (`linear-gradient(...) url(about.png)`) with a flat solid neo-brutalist banner block — solid maroon background, thick border, no photo overlay. CTA buttons (`.cta-primary`/`.cta-secondary`) unchanged, already neo-brutalist-compatible.

**Givebutter embed panel** (`.givebutter-container`): wrap in thick-border box with hard shadow, sharp corners. Campaign ID placeholder (`YOUR_CAMPAIGN_ID`) left as-is — out of scope, content issue not visual.

**Donation tiers** (`.tier-card` bronze/silver/gold): convert to solid color-block cards — thick border, hard offset shadow, sharp corners, icon badge with border instead of soft circle. Hover = translate + shadow grow, remove any soft lift/glow transition.

**Impact stats** (`.impact-section`, `.impact-card`): solid card blocks, thick border, bold numbers, remove gradient/glass background if present.

**Corporate sponsor form** (`#sponsorForm`): move all inline styles in `templates/donate.html` (currently `border:2px solid #ccc;border-radius:8px` per input) into CSS classes — thick black border, sharp corners (no border-radius), bold focus state (border color shift + shadow, no glow/blur). Submit button reuses existing `.cta-button.cta-primary`.

**Sponsors grid** (`.sponsor-card`, `.sponsor-logo`): move inline styles (rounded corners, grey background, soft appearance) into CSS classes — thick border logo box, sharp corners, hard shadow on hover.

## Non-goals

- No section reorder or copy changes.
- No fix to Givebutter placeholder campaign ID.
- No sponsor form backend/action wiring.
- No changes to sponsor data logic/Jinja loop structure.
- No new image assets or JS.

## Testing

- Manual render check: `/donate` route loads 200, all sections present, sponsors loop still renders (with and without sponsors).
- Visual check in browser at desktop + mobile widths — no layout overflow, borders/shadows consistent with index page.
- No JS console errors (sponsor form submit handler, if any, still fires).
