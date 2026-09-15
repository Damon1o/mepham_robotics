# Donate Page Neo-Brutalist Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `templates/donate.html` (hero, tier cards, impact stats, sponsor form, sponsors grid) from soft/glassmorphism styling to the neo-brutalist system already applied to the index page — flat colors, thick solid borders, hard offset shadows, sharp corners — with zero content, structure, or backend changes.

**Architecture:** Pure CSS edits to `static/css/styles.css` plus removal of inline styles from `templates/donate.html` (replaced with classes). No JS, no route, no data model changes. This codebase has no automated test suite (Flask app in `api/index.py`, Jinja templates, no pytest), so verification for every task is: (1) the Flask dev server renders the route with HTTP 200 and the expected markup/classes present, and (2) a manual visual check in a browser at desktop and mobile widths.

**Tech Stack:** Flask + Jinja2 templates, plain CSS (no preprocessor/framework), design tokens defined as CSS custom properties in `static/css/styles.css` (`--maroon-dark: #800000`, `--maroon-light: #944547`, `--accent-gold: #ffd700`, `--bg-light: #fafafa`, `--text-dark: #1a1a1a`, `--font-display: 'Balsamiq Sans', cursive`, `--font-body: 'Balsamiq Sans', cursive`, `--shadow-brutal: 6px 6px 0px rgba(0, 0, 0, 0.2)`, `--transition-fast: 0.2s cubic-bezier(0.4, 0, 0.2, 1)`).

## Global Constraints

- No section reorder or copy changes on `templates/donate.html`.
- No fix to the Givebutter placeholder campaign ID (`YOUR_CAMPAIGN_ID` stays as-is).
- No sponsor form backend/action wiring changes.
- No changes to the sponsors Jinja loop structure (`{% for sponsor in sponsors %}` block) or its data fields (`sponsor.website`, `sponsor.logo_path`, `sponsor.name`, `sponsor.level`).
- Reuse existing design tokens only — do not invent new colors, shadow values, or fonts.
- Do not modify shared classes used by other pages (e.g. base `.hero-image`, `.form-group input/textarea`) in ways that change their appearance elsewhere — donate-specific overrides must be scoped to donate-only selectors.

---

### Task 1: Hero banner — flat neo-brutalist, remove gradient/photo overlay

**Files:**
- Modify: `templates/donate.html:7-15` (the `{% block page_styles %}` override)

**Interfaces:**
- Consumes: existing `--maroon-dark`, `--text-dark` tokens from `static/css/styles.css`.
- Produces: none consumed by later tasks (self-contained).

This page already scopes its own hero override inside `{% block page_styles %}`, so the shared base `.hero-image` rule (used by other pages) is untouched.

- [ ] **Step 1: Replace the gradient/photo hero override with a flat solid banner**

Replace the current block:

```html
{% block page_styles %}
<style>
    .hero-image {
        background: linear-gradient(135deg, rgba(148, 69, 71, 0.85) 0%, rgba(128, 0, 0, 0.9) 100%),
        url('{{ url_for("static", filename="assets/photos/about.png") }}') center/cover;
        min-height: 60vh;
    }
</style>
{% endblock %}
```

with:

```html
{% block page_styles %}
<style>
    .hero-image {
        background: var(--maroon-dark);
        border-bottom: 4px solid var(--text-dark);
        min-height: 60vh;
    }
</style>
{% endblock %}
```

- [ ] **Step 2: Verify the route renders and no photo request remains**

Run: `python api/index.py` (or the project's existing dev-server start command) then `curl -s http://127.0.0.1:5000/donate | grep -o "hero-image"`
Expected: `hero-image` printed (element still present), and no `about.png` reference remains inside the `page_styles` block — confirm with `curl -s http://127.0.0.1:5000/donate | grep -c "about.png"` returning `0`.

- [ ] **Step 3: Manual visual check**

Open `/donate` in a browser at desktop and ~600px width. Expected: solid maroon hero banner, no background photo, thick dark bottom border, heading/CTA buttons still legible and unchanged.

- [ ] **Step 4: Commit**

```bash
git add templates/donate.html
git commit -m "Flatten donate hero to solid neo-brutalist banner"
```

---

### Task 2: Givebutter embed panel — sharp corners, thick border

**Files:**
- Modify: `static/css/styles.css:2759-2765` (`.givebutter-container`)

**Interfaces:**
- Consumes: `--text-dark` token.
- Produces: none.

- [ ] **Step 1: Replace rounded soft container with bordered sharp-corner box**

Replace:

```css
.givebutter-container {
    margin-top: 2rem;
    min-height: 400px;
    width: 100%;
    border-radius: 12px;
    overflow: hidden;
}
```

with:

```css
.givebutter-container {
    margin-top: 2rem;
    min-height: 400px;
    width: 100%;
    border-radius: 0;
    border: 3px solid var(--text-dark);
    overflow: hidden;
}
```

- [ ] **Step 2: Verify no CSS syntax errors**

Run: `python -c "import re; s=open('static/css/styles.css').read(); print(s.count('{') == s.count('}'))"`
Expected: `True`

- [ ] **Step 3: Manual visual check**

Open `/donate`, scroll to the Givebutter embed. Expected: thick dark border box around the iframe, sharp (non-rounded) corners, iframe itself unaffected (still 100% width, 600px height).

- [ ] **Step 4: Commit**

```bash
git add static/css/styles.css
git commit -m "Add thick border to Givebutter embed panel"
```

---

### Task 3: Donation tiers section + tier cards — flat color blocks, hard shadows

**Files:**
- Modify: `static/css/styles.css:1489-1562` (`.donation-tiers`, `.tier-card` and related)

**Interfaces:**
- Consumes: `--bg-light`, `--text-dark`, `--shadow-brutal`, `--accent-gold` tokens.
- Produces: none.

- [ ] **Step 1: Flatten the section background**

Replace:

```css
.donation-tiers {
    padding: 4rem 2rem;
    background: linear-gradient(135deg, #f8f8f8 0%, #ececec 100%);
}
```

with:

```css
.donation-tiers {
    padding: 4rem 2rem;
    background: var(--bg-light);
}
```

- [ ] **Step 2: Convert tier card to sharp corners + persistent hard shadow**

Replace:

```css
.tier-card {
    background: white;
    border-radius: 20px;
    border: 3px solid #1a1a1a;
    padding: 2.5rem 2rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: all 0.4s ease;
}
```

with:

```css
.tier-card {
    background: white;
    border-radius: 0;
    border: 3px solid var(--text-dark);
    box-shadow: var(--shadow-brutal);
    padding: 2.5rem 2rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
```

- [ ] **Step 3: Flatten the top accent stripe gradients to solid colors**

Replace:

```css
.tier-card.bronze::before {
    background: linear-gradient(90deg, #cd7f32, #b87333);
}

.tier-card.silver::before {
    background: linear-gradient(90deg, #c0c0c0, #a8a8a8);
}

.tier-card.gold::before {
    background: linear-gradient(90deg, #ffd700, #ffed4e);
}
```

with:

```css
.tier-card.bronze::before {
    background: #cd7f32;
}

.tier-card.silver::before {
    background: #a8a8a8;
}

.tier-card.gold::before {
    background: var(--accent-gold);
}
```

- [ ] **Step 4: Replace soft lift hover with hard-shadow-grow hover**

Replace:

```css
.tier-card:hover {
    transform: translateY(-10px);
    box-shadow: 15px 15px 0px rgba(148, 69, 71, 0.2);
}
```

with:

```css
.tier-card:hover {
    transform: translate(-4px, -4px);
    box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.25);
}
```

- [ ] **Step 5: Give the tier icon a bordered badge instead of a bare glyph**

Replace:

```css
.tier-icon {
    display: inline-block;
    width: 4rem;
    height: 4rem;
    margin-bottom: 1rem;
}
```

with:

```css
.tier-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 4rem;
    height: 4rem;
    margin-bottom: 1rem;
    border: 3px solid var(--text-dark);
    background: var(--bg-light);
}
```

- [ ] **Step 6: Verify no CSS syntax errors**

Run: `python -c "import re; s=open('static/css/styles.css').read(); print(s.count('{') == s.count('}'))"`
Expected: `True`

- [ ] **Step 7: Manual visual check**

Open `/donate`, scroll to Sponsorship Levels. Expected: three flat white cards, sharp corners, visible hard-offset shadow at rest, solid (non-gradient) top accent stripe per tier, icon shown in a bordered square badge, hover moves the card up-left slightly and grows the shadow (no soft lift).

- [ ] **Step 8: Commit**

```bash
git add static/css/styles.css
git commit -m "Convert donation tier cards to flat neo-brutalist blocks"
```

---

### Task 4: Impact stats — flat maroon cards, remove blur/glass

**Files:**
- Modify: `static/css/styles.css:1975-2013` (`.impact-section`, `.impact-card`)

**Interfaces:**
- Consumes: `--maroon-dark`, `--maroon-light`, `--text-dark` tokens.
- Produces: none.

- [ ] **Step 1: Flatten the section background from gradient to solid**

Replace:

```css
.impact-section {
    padding: 4rem 2rem;
    background: linear-gradient(135deg, var(--maroon-dark), var(--maroon-light));
}
```

with:

```css
.impact-section {
    padding: 4rem 2rem;
    background: var(--maroon-dark);
}
```

- [ ] **Step 2: Replace glass/blur card with a flat bordered card**

Replace:

```css
.impact-card {
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    border: 2px solid rgba(255, 255, 255, 0.2);
}
```

with:

```css
.impact-card {
    background: var(--maroon-light);
    border-radius: 0;
    padding: 2rem;
    text-align: center;
    border: 3px solid var(--text-dark);
    box-shadow: 6px 6px 0px rgba(0, 0, 0, 0.3);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.impact-card:hover {
    transform: translate(-3px, -3px);
    box-shadow: 9px 9px 0px rgba(0, 0, 0, 0.35);
}
```

- [ ] **Step 3: Verify no CSS syntax errors**

Run: `python -c "import re; s=open('static/css/styles.css').read(); print(s.count('{') == s.count('}'))"`
Expected: `True`

- [ ] **Step 4: Manual visual check**

Open `/donate`, scroll to Your Impact. Expected: solid maroon section background (no diagonal gradient), four flat maroon-light cards with thick dark border and hard shadow, no blur, hover moves card up-left and grows shadow.

- [ ] **Step 5: Commit**

```bash
git add static/css/styles.css
git commit -m "Flatten impact stats cards, remove glassmorphism blur"
```

---

### Task 5: Corporate sponsor form — sharp-corner neo-brutalist fields

**Files:**
- Modify: `templates/donate.html:128-159` (`#sponsorForm` markup — remove inline styles, use classes)
- Modify: `static/css/styles.css:4150-4158` (`.sponsor-form` — sharp corners)
- Modify: `static/css/styles.css` (new rule block after line 2903, immediately following `.form-group input:focus, .form-group textarea:focus`) — donate-scoped sharp-corner + select styling

**Interfaces:**
- Consumes: existing `.form-group`, `.form-group label`, `.form-group input`, `.form-group textarea` classes (defined at `static/css/styles.css:2868-2903`) and `--maroon-dark`, `--text-dark`, `--font-body`, `--transition-fast` tokens.
- Produces: none.

The site already has a neo-brutalist `.form-group` pattern (3px border, hard shadow, bold focus state) used elsewhere, but it has rounded 12px corners. This task reuses that pattern for markup/behavior and adds a donate-scoped override for sharp corners so the shared `.form-group` class is unaffected on other pages.

- [ ] **Step 1: Replace inline-styled form fields with `.form-group` markup**

Replace the form body in `templates/donate.html`:

```html
            <form id="sponsorForm">
                <div style="margin-bottom:1rem;">
                    <label style="display:block;margin-bottom:0.5rem;font-weight:bold;">Company Name</label>
                    <input type="text" name="company" required
                        style="width:100%;padding:0.8rem;border:2px solid #ccc;border-radius:8px;">
                </div>
                <div style="margin-bottom:1rem;">
                    <label style="display:block;margin-bottom:0.5rem;font-weight:bold;">Contact Email</label>
                    <input type="email" name="email" required
                        style="width:100%;padding:0.8rem;border:2px solid #ccc;border-radius:8px;">
                </div>
                <div style="margin-bottom:1rem;">
                    <label style="display:block;margin-bottom:0.5rem;font-weight:bold;">Sponsorship Level
                        Interest</label>
                    <select name="level" style="width:100%;padding:0.8rem;border:2px solid #ccc;border-radius:8px;">
                        <option>Bronze ($50+)</option>
                        <option>Silver ($150+)</option>
                        <option>Gold ($500+)</option>
                        <option>Platinum ($1000+)</option>
                        <option>Custom Amount</option>
                    </select>
                </div>
                <div style="margin-bottom:1.5rem;">
                    <label style="display:block;margin-bottom:0.5rem;font-weight:bold;">Message</label>
                    <textarea name="message" rows="4" required
                        style="width:100%;padding:0.8rem;border:2px solid #ccc;border-radius:8px;"></textarea>
                </div>
                <button type="submit" class="cta-button cta-primary" style="width:100%;">Send Inquiry</button>
            </form>
```

with:

```html
            <form id="sponsorForm">
                <div class="form-group">
                    <label>Company Name</label>
                    <input type="text" name="company" required>
                </div>
                <div class="form-group">
                    <label>Contact Email</label>
                    <input type="email" name="email" required>
                </div>
                <div class="form-group">
                    <label>Sponsorship Level Interest</label>
                    <select name="level">
                        <option>Bronze ($50+)</option>
                        <option>Silver ($150+)</option>
                        <option>Gold ($500+)</option>
                        <option>Platinum ($1000+)</option>
                        <option>Custom Amount</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Message</label>
                    <textarea name="message" rows="4" required></textarea>
                </div>
                <button type="submit" class="cta-button cta-primary" style="width:100%;">Send Inquiry</button>
            </form>
```

- [ ] **Step 2: Add donate-scoped sharp-corner override and select styling**

Insert this new rule block in `static/css/styles.css` immediately after the existing block ending at line 2903 (`.form-group input:focus, .form-group textarea:focus { ... }`):

```css

.sponsor-form .form-group input,
.sponsor-form .form-group textarea,
.sponsor-form .form-group select {
    border-radius: 0;
}

.sponsor-form .form-group select {
    width: 100%;
    padding: 1.2rem;
    background: #fdfdfd;
    border: 3px solid var(--text-dark);
    font-family: var(--font-body);
    font-size: 1rem;
    transition: all var(--transition-fast);
    box-shadow: 4px 4px 0px rgba(0, 0, 0, 0.05);
}

.sponsor-form .form-group select:focus {
    outline: none;
    border-color: var(--maroon-dark);
    transform: translate(-2px, -2px);
    box-shadow: 6px 6px 0px rgba(148, 69, 71, 0.2);
    background: #fff;
}
```

- [ ] **Step 3: Sharpen the sponsor form panel corners**

Replace:

```css
.sponsor-form {
    max-width: 600px;
    margin: 2rem auto;
    background: white;
    padding: 2.5rem;
    border: 3px solid #1a1a1a;
    border-radius: 20px;
    box-shadow: 10px 10px 0px rgba(148, 69, 71, 0.15);
}
```

with:

```css
.sponsor-form {
    max-width: 600px;
    margin: 2rem auto;
    background: white;
    padding: 2.5rem;
    border: 3px solid var(--text-dark);
    border-radius: 0;
    box-shadow: 10px 10px 0px rgba(148, 69, 71, 0.15);
}
```

- [ ] **Step 4: Verify markup and CSS are well-formed**

Run: `python -c "import re; s=open('static/css/styles.css').read(); print(s.count('{') == s.count('}'))"`
Expected: `True`

Run: `curl -s http://127.0.0.1:5000/donate | grep -c 'style="width:100%;padding:0.8rem'`
Expected: `0` (no leftover inline field styles)

- [ ] **Step 5: Manual visual check**

Open `/donate`, scroll to Become a Corporate Sponsor. Expected: form panel has sharp corners, all four fields (text/email/select/textarea) show thick dark border and sharp corners, focus state on any field shows the bold border-color shift + hard shadow + slight translate (no glow/blur), submit button still full-width. Fill and check the select dropdown still lists all 5 options.

- [ ] **Step 6: Commit**

```bash
git add templates/donate.html static/css/styles.css
git commit -m "Restyle corporate sponsor form to neo-brutalist fields"
```

---

### Task 6: Sponsors grid — bordered logo boxes, remove soft styling

**Files:**
- Modify: `templates/donate.html:164-186` (sponsors grid markup — remove inline styles, use classes)
- Modify: `static/css/styles.css:1936-1973` (`.sponsors-section`, `.sponsor-logo` and new supporting classes)

**Interfaces:**
- Consumes: `--text-dark`, `--maroon-dark` tokens; existing `sponsors` Jinja context variable with fields `website`, `logo_path`, `name`, `level` (unchanged).
- Produces: none.

- [ ] **Step 1: Replace inline-styled sponsor card markup with classes**

Replace:

```html
<div class="sponsors-grid">
    {% for sponsor in sponsors %}
    <div class="sponsor-card" style="text-align: center;">
        <a href="{{ sponsor.website if sponsor.website else '#' }}" target="_blank" style="text-decoration: none; color: inherit;">
            <div class="sponsor-logo" style="margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: center; background: #eee; border-radius: 8px; overflow: hidden; min-height: 120px;">
                {% if sponsor.logo_path %}
                <img src="{{ get_image_url(sponsor.logo_path) }}" alt="{{ sponsor.name }}" style="max-width: 100%; max-height: 100%; object-fit: contain;">
                {% else %}
                <div style="font-weight: bold; color: #666; padding: 1rem;">{{ sponsor.name }}</div>
                {% endif %}
            </div>
            <div class="sponsor-name" style="font-weight: bold; color: var(--accent-red);">{{ sponsor.name }}</div>
            <div class="sponsor-level" style="font-size: 0.8rem; color: #888;">{{ sponsor.level }} Sponsor</div>
        </a>
    </div>
    {% endfor %}
    {% if not sponsors %}
    <p style="grid-column: 1 / -1; text-align: center; color: #999;">Support our team and see your logo here!</p>
    {% endif %}
</div>
```

with:

```html
<div class="sponsors-grid">
    {% for sponsor in sponsors %}
    <div class="sponsor-card">
        <a href="{{ sponsor.website if sponsor.website else '#' }}" target="_blank" class="sponsor-card-link">
            <div class="sponsor-logo">
                {% if sponsor.logo_path %}
                <img src="{{ get_image_url(sponsor.logo_path) }}" alt="{{ sponsor.name }}" class="sponsor-logo-img">
                {% else %}
                <div class="sponsor-logo-fallback">{{ sponsor.name }}</div>
                {% endif %}
            </div>
            <div class="sponsor-name">{{ sponsor.name }}</div>
            <div class="sponsor-level">{{ sponsor.level }} Sponsor</div>
        </a>
    </div>
    {% endfor %}
    {% if not sponsors %}
    <p class="sponsors-empty">Support our team and see your logo here!</p>
    {% endif %}
</div>
```

- [ ] **Step 2: Replace `.sponsor-logo` soft box + add new supporting classes**

Replace:

```css
.sponsor-logo {
    width: 120px;
    height: 80px;
    background: #f0f0f0;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #999;
    font-size: 0.8rem;
    transition: all 0.3s ease;
}

.sponsor-logo:hover {
    transform: scale(1.1);
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
}
```

with:

```css
.sponsor-card {
    text-align: center;
}

.sponsor-card-link {
    text-decoration: none;
    color: inherit;
}

.sponsor-logo {
    width: 160px;
    height: 120px;
    margin: 0 auto 0.5rem;
    background: var(--bg-light);
    border: 3px solid var(--text-dark);
    border-radius: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    box-shadow: var(--shadow-brutal);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.sponsor-logo:hover {
    transform: translate(-3px, -3px);
    box-shadow: 9px 9px 0px rgba(0, 0, 0, 0.3);
}

.sponsor-logo-img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
}

.sponsor-logo-fallback {
    font-weight: bold;
    color: var(--text-dark);
    padding: 1rem;
}

.sponsor-name {
    font-weight: bold;
    color: var(--maroon-dark);
}

.sponsor-level {
    font-size: 0.8rem;
    color: var(--text-light);
}

.sponsors-empty {
    grid-column: 1 / -1;
    text-align: center;
    color: var(--text-light);
}
```

- [ ] **Step 3: Update the dark-mode override to match the new sharp-corner box**

Replace:

```css
[data-theme="dark"] .sponsor-logo {
    background: #2a2a2a;
    color: #777;
}
```

with:

```css
[data-theme="dark"] .sponsor-logo {
    background: #2a2a2a;
    border-color: #444;
}

[data-theme="dark"] .sponsor-logo-fallback {
    color: #999;
}
```

- [ ] **Step 4: Verify markup and CSS are well-formed**

Run: `python -c "import re; s=open('static/css/styles.css').read(); print(s.count('{') == s.count('}'))"`
Expected: `True`

Run: `curl -s http://127.0.0.1:5000/donate | grep -c 'style="text-align: center;"'`
Expected: `0` (no leftover inline sponsor-card styles)

- [ ] **Step 5: Manual visual check**

Open `/donate`, scroll to Our Sponsors, in both the empty-state (no sponsors seeded) and populated case if test data is available. Expected: logo box is a flat bordered square with hard shadow (no soft grey rounded box), hover moves it up-left and grows the shadow, sponsor name/level text unchanged, empty-state message still centered and still spans the full grid width.

- [ ] **Step 6: Commit**

```bash
git add templates/donate.html static/css/styles.css
git commit -m "Restyle sponsors grid to bordered neo-brutalist logo boxes"
```

---

### Task 7: Full-page regression pass

**Files:**
- None modified — verification only.

**Interfaces:**
- Consumes: all changes from Tasks 1-6.
- Produces: none.

- [ ] **Step 1: Full route check**

Run: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/donate`
Expected: `200`

- [ ] **Step 2: Dark mode check**

Toggle `data-theme="dark"` (via the site's existing theme toggle) on `/donate`. Expected: hero, tier cards, impact cards, sponsor form, and sponsors grid all remain legible with dark-mode colors — no leftover light-only backgrounds clashing, no broken borders.

- [ ] **Step 3: Responsive check**

Resize browser to ~375px, ~768px, and desktop widths on `/donate`. Expected: no horizontal overflow, tier/impact/sponsor grids reflow to single or double columns per existing `auto-fit`/`flex-wrap` rules (unchanged from before this restyle), all borders/shadows remain visible at every width.

- [ ] **Step 4: Console check**

Open browser dev tools console on `/donate`. Expected: no new JS errors (sponsor form has no JS handler in this codebase beyond native submit — confirm none was introduced).

- [ ] **Step 5: Final commit (if any fixups were needed)**

```bash
git add -A
git commit -m "Fix regressions found in donate page restyle pass"
```

(Skip this commit if no fixups were needed.)
