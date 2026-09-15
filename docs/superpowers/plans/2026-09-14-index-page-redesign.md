# Index Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `templates/index.html` sections from countdown through carousel into one consistent neo-brutalist visual system, reorder sections, and add flanking photos to the hero.

**Architecture:** Pure HTML/CSS edit. `templates/index.html` (markup + `page_styles` block for section-specific CSS) and `static/css/styles.css` (shared hero/countdown card rules). No backend, Jinja data shape, or JS logic changes — countdown timer script and carousel scroll script are untouched.

**Tech Stack:** Flask + Jinja2 templates, plain CSS (no build step), vanilla JS (untouched).

## Global Constraints

- Reuse only existing CSS custom properties: `--maroon-dark`, `--maroon-light`, `--accent-gold`, `--accent-light`, `--bg-light`, `--text-dark`, `--text-light`, `--font-display`, `--shadow-brutal`, `--spacing-*`. No new colors/gradients invented.
- Countdown JS contract (`#days #hours #minutes #seconds`, `window.COUNTDOWN_DATE`) must remain unchanged.
- Carousel JS/markup contract (`.carousel-track`, `.carousel-item`, `.carousel-dots`) must remain unchanged — only visual framing (border/shadow) changes.
- No new image assets — hero side photos reuse `carousel1.jpg` / `carousel2.jpg`.
- Side hero photos hidden below 900px viewport width.
- No automated test suite exists for templates/CSS in this repo. Verification = `flask` dev server render (HTTP 200) + manual visual check in browser at desktop/tablet/mobile widths + console error check.

---

### Task 1: Hero flanking photos

**Files:**
- Modify: `templates/index.html:332-343` (hero markup)
- Modify: `static/css/styles.css` (add `.hero-side-photo` rules near `.hero-image` block, after line 351)

**Interfaces:**
- Produces: `.hero-side-photo` (base), `.hero-side-photo--left`, `.hero-side-photo--right` classes consumed by hero markup only.

- [ ] **Step 1: Add side photo markup to hero**

In `templates/index.html`, replace the hero block:

```html
<!-- HERO SECTION -->
<div class="hero-image">
    <img class="hero-side-photo hero-side-photo--left"
         src="{{ url_for('static', filename='assets/photos/carousel1.jpg') }}" alt="" aria-hidden="true"
         loading="lazy">
    <img class="hero-side-photo hero-side-photo--right"
         src="{{ url_for('static', filename='assets/photos/carousel2.jpg') }}" alt="" aria-hidden="true"
         loading="lazy">
    <div class="hero-content">
        <h1>Mepham Robotics</h1>
        <p>Build. Code. Compete.</p>
        <div class="hero-cta">
            <a href="{{ url_for('about') }}" class="cta-button cta-primary">Learn More</a>
            <a href="{{ url_for('donate') }}" class="cta-button cta-secondary">Support Us</a>
        </div>
    </div>
    <div class="scroll-indicator"></div>
</div>
```

- [ ] **Step 2: Add side photo CSS**

In `static/css/styles.css`, insert after the `.hero-content { ... }` block (after line 358):

```css
.hero-side-photo {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 220px;
    height: 320px;
    object-fit: cover;
    border: 4px solid var(--text-dark);
    box-shadow: 8px 8px 0px rgba(0, 0, 0, 0.35);
    z-index: 5;
}

.hero-side-photo--left {
    left: 4vw;
    transform: translateY(-50%) rotate(-4deg);
}

.hero-side-photo--right {
    right: 4vw;
    transform: translateY(-50%) rotate(4deg);
}

@media (max-width: 900px) {
    .hero-side-photo {
        display: none;
    }
}
```

- [ ] **Step 3: Verify**

Run: `python app.py` (or repo's existing dev-server command), then load `/` in browser.
Expected: two rotated framed photos flank hero text at desktop width (>900px), disappear below 900px, no layout shift/overlap with `hero-content`.

- [ ] **Step 4: Commit**

```bash
git add templates/index.html static/css/styles.css
git commit -m "feat: add flanking side photos to hero section"
```

---

### Task 2: Reorder sections + move countdown/timeline/stats/carousel/donate into new order

**Files:**
- Modify: `templates/index.html` (reorder `<section>` blocks in `content` block, lines ~345-473)

**Interfaces:**
- Consumes: existing Jinja context vars `competition`, `stats`, `upcoming_events` — unchanged shape.
- Produces: section order Hero → Countdown → Timeline → Stats → Carousel → Donate, used by Tasks 3-7 for restyling in place.

- [ ] **Step 1: Rewrite `content` block section order**

Replace everything from `<!-- COUNTDOWN SECTION -->` through the end of the `content` block with (styling classes unchanged for now — restyle happens in later tasks):

```html
<!-- COUNTDOWN SECTION -->
<section class="countdown-section fade-in-section">
    <div class="text-center">
        <h2 class="ripple" style="color:white; margin-bottom: 2rem;">Next Competition In:</h2>
    </div>
    <div class="countdown-container">
        <div class="countdown-item">
            <span id="days" class="countdown-number">00</span>
            <span class="countdown-label">Days</span>
        </div>
        <div class="countdown-item">
            <span id="hours" class="countdown-number">00</span>
            <span class="countdown-label">Hours</span>
        </div>
        <div class="countdown-item">
            <span id="minutes" class="countdown-number">00</span>
            <span class="countdown-label">Mins</span>
        </div>
        <div class="countdown-item">
            <span id="seconds" class="countdown-number">00</span>
            <span class="countdown-label">Secs</span>
        </div>
    </div>
    <p class="countdown-event">{{ competition.name if competition else "TBD" }}</p>
    {% if competition %}
    <script>
        window.COUNTDOWN_DATE = "{{ competition.date.isoformat() }}";
    </script>
    {% endif %}
</section>

<section class="timeline">
    <h2>Upcoming Events</h2>
    <div class="timeline-wrapper">
        {% for event in upcoming_events %}
        <div class="timeline-card">
            <div class="date-pill">{{ event.month }} {{ event.day }}</div>
            <div class="timeline-content">
                <h3>{{ event.name }}</h3>
                <div class="info-row">
                    <p class="location">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                            <circle cx="12" cy="10" r="3"></circle>
                        </svg>
                        <span>{{ event.location or 'TBA' }}</span>
                    </p>
                </div>
                <div class="info-row">
                    <p class="location">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        <span>{{ event.time }}</span>
                    </p>
                </div>
            </div>
        </div>
        {% endfor %}
        {% if not upcoming_events %}
        <p style="text-align: center; color: var(--accent-light); opacity: 0.7; padding: 2rem;">No upcoming events
            scheduled at this time. Check back soon!</p>
        {% endif %}
    </div>
</section>

<!-- STATS SECTION -->
<section class="stats-section fade-in-section">
    <div class="stats-container">
        <div class="stat-item">
            <div class="stat-number">{{ stats.teams_count }}</div>
            <div class="stat-label">Teams</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">{{ stats.members_count }}</div>
            <div class="stat-label">Members</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">{{ stats.awards_count }}</div>
            <div class="stat-label">Awards</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">{{ stats.hours_built }}+</div>
            <div class="stat-label">Hours Built</div>
        </div>
    </div>
</section>

<!-- PHOTO CAROUSEL -->
<section class="photo-carousel-section fade-in-section">
    <h2 class="ripple">Team Gallery</h2>
    <div class="carousel-container">
        <div class="carousel-track">
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel1.jpg') }}" alt="Team Photo 1"
                    loading="lazy">
            </div>
            {% for i in range(2, 9) %}
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/other/base.png') }}" alt="Team Photo {{ i }}"
                    loading="lazy">
            </div>
            {% endfor %}
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel2.jpg') }}" alt="Team Photo 2"
                    loading="lazy">
            </div>
            {% for i in range(2, 9) %}
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/other/base.png') }}" alt="Team Photo {{ i }}"
                    loading="lazy">
            </div>
            {% endfor %}
        </div>
    </div>
</section>

<!-- DONATION CTA -->
<section class="donation-cta fade-in-section">
    <div class="donate-container">
        <h2 class="ripple">Want to Support Us?</h2>
        <p>Your donation helps us compete at the highest level, acquire new parts, and continue building innovative
            robots.</p>
        <a href="{{ url_for('donate') }}" class="cta-donate-btn">Donate Now</a>
    </div>
</section>
{% endblock %}
```

- [ ] **Step 2: Verify**

Run: `python app.py`, load `/`.
Expected: sections appear in order Hero, Countdown, Timeline ("Upcoming Events"), Stats, Carousel ("Team Gallery"), Donate ("Want to Support Us?"). No missing/duplicated sections, no Jinja errors in server log.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "refactor: reorder index sections to countdown, timeline, stats, carousel, donate"
```

---

### Task 3: Restyle countdown to brutalist tiles

**Files:**
- Modify: `static/css/styles.css:1889-1948` (`.countdown-section`, `.countdown-container`, `.countdown-item`, `.countdown-number`, `.countdown-label`, `.countdown-event`)

**Interfaces:**
- Consumes: markup from Task 2 (`.countdown-section`, `.countdown-container`, `.countdown-item`, `#days/#hours/#minutes/#seconds`, `.countdown-label`, `.countdown-event`) — class names unchanged, CSS rules only.

- [ ] **Step 1: Replace countdown CSS block**

Replace `static/css/styles.css` lines 1889-1948 with:

```css
.countdown-section {
    padding: 6rem 2rem;
    background: var(--maroon-dark);
    text-align: center;
    color: white;
    border-top: 4px solid var(--text-dark);
    border-bottom: 4px solid var(--text-dark);
    position: relative;
    overflow: hidden;
}

.countdown-container {
    display: flex;
    justify-content: center;
    gap: 2rem;
    flex-wrap: wrap;
    margin-bottom: 2rem;
}

.countdown-item {
    background: var(--accent-light);
    padding: 2rem 1.5rem;
    border-radius: 12px;
    border: 3px solid var(--text-dark);
    min-width: 150px;
    box-shadow: var(--shadow-brutal);
    transition: var(--transition-base);
}

.countdown-item:hover {
    transform: translate(-3px, -3px) rotate(-2deg);
    box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.3);
    border-color: var(--accent-gold);
}

.countdown-number {
    display: block;
    font-family: 'Space Mono', monospace;
    font-size: 4rem;
    font-weight: 700;
    color: var(--maroon-dark);
}

.countdown-label {
    text-transform: uppercase;
    font-size: 0.8rem;
    letter-spacing: 3px;
    color: var(--text-light);
    font-weight: 700;
}

.countdown-event {
    font-size: 1.1rem;
    color: var(--accent-gold);
    font-family: 'Space Mono', monospace;
    margin-top: 2rem;
    opacity: 0.9;
}
```

- [ ] **Step 2: Verify**

Load `/` in browser. Expected: countdown section has solid maroon background, four cream tiles with thick black borders and hard offset shadow, gold event name below, hover lifts+rotates a tile slightly. No `backdrop-filter`/blur remnants.

- [ ] **Step 3: Commit**

```bash
git add static/css/styles.css
git commit -m "style: restyle countdown tiles to neo-brutalist"
```

---

### Task 4: Restyle timeline date tags/borders to heavier brutalist scale

**Files:**
- Modify: `templates/index.html:139-247` (`.timeline-card`, `.date-tag`, `.timeline-wrapper::before` rules in `page_styles` block)

**Interfaces:**
- Consumes: markup from Task 2 (`.timeline-wrapper`, `.timeline-card`, `.date-pill` note: existing CSS selector is `.date-tag` but markup uses `.date-pill` — fix mismatch as part of this task) unchanged otherwise.

- [ ] **Step 1: Fix date tag selector mismatch and bump border/shadow weight**

In `templates/index.html`, within the `<style>` block, replace the `.date-tag` rule (lines 178-191) with (renamed to match markup's `.date-pill`, kept as class list `.date-pill` in both CSS and template):

```css
    .date-pill {
        position: absolute;
        top: -14px;
        right: var(--spacing-md);
        background: var(--accent-gold);
        color: var(--text-dark);
        font-weight: 700;
        font-size: 0.9rem;
        padding: 0.4rem 1rem;
        border: 3px solid var(--text-dark);
        border-radius: 8px;
        transform: rotate(2deg);
        z-index: 3;
    }
```

Replace `.timeline-card` rule (lines 139-151) with:

```css
    .timeline-card {
        position: relative;
        background: white;
        border: 3px solid var(--text-dark);
        border-radius: 12px;
        padding: var(--spacing-md);
        margin-left: var(--spacing-md);
        text-decoration: none;
        color: var(--text-dark);
        box-shadow: var(--shadow-brutal);
        transition: var(--transition-base);
        display: block;
    }
```

Replace `.timeline-card:hover` rule (lines 167-171) with:

```css
    .timeline-card:hover {
        transform: translate(-3px, -3px);
        box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.3);
        border-color: var(--maroon-dark);
    }
```

- [ ] **Step 2: Verify**

Load `/`. Expected: each event card shows a gold sticker date tag (top-right, rotated) that was previously invisible (selector mismatch meant `.date-tag` CSS never matched `.date-pill` markup), thick black border, hard shadow, hover shifts card + darkens border.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "fix: correct date-pill selector mismatch and bump timeline brutalist weight"
```

---

### Task 5: Restyle stats cards from glass to solid brutalist

**Files:**
- Modify: `templates/index.html:249-311` (`.stats-section`, `.stat-item`, `.stat-number`, `.stat-label` in `page_styles` block)

**Interfaces:**
- Consumes: markup from Task 2 (`.stats-section`, `.stats-container`, `.stat-item`, `.stat-number`, `.stat-label`) unchanged.

- [ ] **Step 1: Replace stats CSS block**

Replace lines 249-311 (`.stats-section` through `.stat-label`) with:

```css
    /* --- STATS SECTION --- */
    .stats-section {
        background: var(--bg-light);
        padding: 5rem 2rem;
        position: relative;
    }

    .stats-container {
        max-width: 1200px;
        margin: 0 auto;
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 2.5rem;
    }

    .stat-item {
        text-align: center;
        padding: 2rem;
        background: white;
        border: 3px solid var(--text-dark);
        border-radius: 12px;
        box-shadow: var(--shadow-brutal);
        transition: var(--transition-base);
    }

    .stat-item:hover {
        transform: translateY(-6px);
        box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.25);
        border-color: var(--accent-gold);
    }

    .stat-number {
        font-size: 3.5rem;
        font-weight: 700;
        font-family: 'Space Mono', monospace;
        color: var(--maroon-dark);
        margin-bottom: 0.5rem;
    }

    .stat-label {
        font-size: 1.1rem;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: var(--text-light);
    }
```

- [ ] **Step 2: Verify**

Load `/`. Expected: stats section has plain light background (no dark gradient/dot texture), four white cards with thick borders and hard shadow, maroon numbers, hover lifts card.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "style: convert stats cards from glassmorphism to solid brutalist"
```

---

### Task 6: Restyle carousel item framing

**Files:**
- Modify: `static/css/styles.css:921-960` (`.carousel-item`, `.carousel-item:hover`, `.carousel-item::after`, `.carousel-item:hover::after`)

**Interfaces:**
- Consumes: markup from Task 2 (`.carousel-track`, `.carousel-item`, `img`) unchanged; `.carousel-dots`/scroll JS untouched.

- [ ] **Step 1: Replace carousel item CSS**

Replace `static/css/styles.css` lines 921-960 with:

```css
.carousel-item {
    flex-shrink: 0;
    width: 350px;
    height: 250px;
    border-radius: 12px;
    overflow: hidden;
    border: 4px solid var(--accent-light);
    transition: all var(--transition-base);
    position: relative;
}

.carousel-item img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform var(--transition-slow);
}

.carousel-item:hover {
    border-color: var(--accent-gold);
    transform: translate(-4px, -4px);
    box-shadow: 8px 8px 0px rgba(0, 0, 0, 0.4);
}

.carousel-item:hover img {
    transform: scale(1.08);
}
```

(This drops the soft glow overlay `::after` rules — no replacement needed, brutalist hard shadow replaces the glow.)

- [ ] **Step 2: Verify**

Load `/`, scroll to Team Gallery. Expected: photos scroll automatically (unchanged JS), items have solid cream border, hover shifts item diagonally with hard shadow instead of soft glow/scale-only. Dots still functional, auto-scroll still pauses on hover.

- [ ] **Step 3: Commit**

```bash
git add static/css/styles.css
git commit -m "style: restyle carousel item framing to neo-brutalist"
```

---

### Task 7: Simplify donate CTA panel (drop pulse animation, move to closing section)

**Files:**
- Modify: `templates/index.html:15-99` (`.donation-cta`, `.donation-cta::before`, `.donate-container h2/p` in `page_styles` block)

**Interfaces:**
- Consumes: markup from Task 2 (`.donation-cta`, `.donate-container`, `.cta-donate-btn`) unchanged. `.cta-donate-btn` rules (lines 61-98) are kept as-is per spec (button style unchanged).

- [ ] **Step 1: Replace donation-cta background block**

Replace lines 15-43 (`.donation-cta` through `.donate-container` opening, i.e. the `::before` pulse rule and container) with:

```css
    /* --- DONATION CTA SECTION --- */
    .donation-cta {
        background: var(--accent-light);
        padding: 5rem 2rem;
        border-top: 4px solid var(--maroon-dark);
        border-bottom: 4px solid var(--maroon-dark);
    }

    .donate-container {
        max-width: 800px;
        margin: 0 auto;
        text-align: center;
    }
```

(Removes the `::before` radial-dot pulse layer and its `backgroundPulse` keyframe reference entirely — no replacement needed.)

- [ ] **Step 2: Verify**

Load `/`, scroll to bottom. Expected: donate section is the last section on the page, flat cream background with maroon top/bottom border, no animated dot texture, existing brutalist donate button unchanged in style/position.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "style: simplify donate CTA background, confirm as closing section"
```

---

### Task 8: Full-page verification pass

**Files:** none (verification only)

- [ ] **Step 1: Start dev server and check route**

Run: `python app.py` (background), then `curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/`
Expected: `200`

- [ ] **Step 2: Manual visual check at 3 widths**

In browser dev tools, check `/` at ~375px (mobile), ~900px (tablet, hero side photos should just disappear at/below this), ~1440px (desktop).
Expected: no horizontal overflow, hero side photos visible only >900px, section order is Hero → Countdown → Timeline → Stats → Carousel → Donate, all brutalist borders/shadows render, no visual regression in unrelated sections (nav/footer).

- [ ] **Step 3: Console/JS check**

Open browser console, reload `/`, watch countdown numbers tick and carousel auto-scroll for ~10s, hover a carousel item and a dot.
Expected: zero console errors, countdown updates every second, carousel pauses on hover and resumes, dots remain clickable.

- [ ] **Step 4: Stop dev server**

Kill the `python app.py` process started in Step 1.
