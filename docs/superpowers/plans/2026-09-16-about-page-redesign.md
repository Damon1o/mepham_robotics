# About Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `templates/about.html` into eight sections (Hero, Breadcrumb, Who We Are, What We Stand For, Sub-Teams, Culture & Safety, Our Journey, Team Moments), move every style into `static/css/pages/about.css`, and delete the retired about-only rules from `static/css/styles.css`.

**Architecture:** Template markup changes plus new rules in the per-page stylesheet, which `base.html` loads after `styles.css` (via `{% block page_styles %}`), so equal-specificity rules in `about.css` win. All new classes are prefixed `about-` so nothing collides with shared classes. In particular, `.subteam-card` already exists in `styles.css` and is used by `templates/notebook.html`, so the about page must NOT reuse it. No routes, JS, or data changes. The repo has no test suite; each task verifies with the Flask test client (no server needed), a brace-balance check on edited CSS, and a browser check.

**Tech Stack:** Flask + Jinja2 (`api/index.py`, route `/about` renders `about.html`), plain CSS with custom properties, Lucide icons via `<i data-lucide="name">`, dark mode through a `[data-theme="dark"]` ancestor selector.

## Global Constraints

- CSS never lives in HTML: when you're done, `templates/about.html` has zero `style=` attributes and no `<style>` blocks.
- Reuse existing tokens: `--maroon-dark: #800000`, `--maroon-light: #944547`, `--accent-gold: #ffd700`, `--accent-light: #f1f1f1`, `--text-dark: #1a1a1a`, `--text-light: #666`, `--bg-light: #fafafa`, `--spacing-*`, `--transition-base`. Headings in cards use `'Space Mono', monospace`, matching the existing card rules.
- Card look follows the existing site convention: `border: 3px solid var(--text-dark)`, `border-radius: 16px`, `box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2)`, hover `translate(-4px, -4px)`.
- Dark-mode variants follow the existing convention: card background `#1e1e1e`, border `#444`, card heading `#d4a0a1`, body text `#bbb`. Every new class that sets a color or background gets a `[data-theme="dark"]` variant.
- Full-bleed rule: only sections that paint a background (What We Stand For, Culture & Safety) set `max-width: none; margin-left: 0; margin-right: 0;`. Their inner containers keep `max-width: 1200px; margin: 0 auto;`.
- Breakpoints: two-column bands collapse at `768px` with the image last; the principles grid goes from 3 to 2 columns at `900px` and to 1 at `600px`; the sub-team cards go from 2x2 to 1 column at `600px`.
- Images: use `static/assets/photos/carousel*.jpg` only, always with `loading="lazy"`. Landscape slots use the small files (`carousel1`, `carousel5`, `carousel7`, `carousel8`, `carousel10`). No Jinja `range()` loops for images.
- Copy is carried over verbatim unless this plan gives new copy. Sub-team copy is a draft for the club to edit.
- Commit message style for this repo: short imperative sentence, no `feat:` prefix, ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Shared Verification Commands

Run these from the repo root. Every task refers to them by name.

**RENDER** checks that the page returns 200 and that every `/static/` URL in the HTML resolves:

```bash
python -c "
import re
from api.index import app
c = app.test_client()
r = c.get('/about'); h = r.data.decode()
print('status', r.status_code)
urls = sorted(set(re.findall(r'/static/[^\"\'?) ]+', h)))
bad = [u for u in urls if c.get(u).status_code != 200]
print('static urls', len(urls), 'broken', bad)
"
```

Expected: `status 200` and `broken []`.

**BRACES** checks that a CSS file's braces are balanced (replace the path as needed):

```bash
python -c "s=open('static/css/pages/about.css').read(); print(s.count('{') == s.count('}'))"
```

Expected: `True`.

**HAS** checks that given strings appear in the rendered page (edit the list per task):

```bash
python -c "
from api.index import app
h = app.test_client().get('/about').data.decode()
for s in ['NEEDLE_1', 'NEEDLE_2']: print(s, s in h)
"
```

## File Structure

- Modify `templates/about.html`. Every section is rewritten across Tasks 1–5.
- Modify `static/css/pages/about.css`. It currently holds only the hero background rule, and each task appends one commented block.
- Modify `static/css/styles.css`. Task 6 removes the retired about-only rules.

---

### Task 1: Hero CTA and Who We Are

**Files:**
- Modify: `templates/about.html` (the hero `.hero-cta` block and the `<section id="about">` block)
- Modify: `static/css/pages/about.css` (append)

**Interfaces:**
- Consumes: the existing `.about-content`, `.about-text`, and `[data-theme="dark"] .about-text` rules in `styles.css`, which are kept.
- Produces: the `.about-photo` class and the `#subteams` anchor target that Task 3 must create.

- [ ] **Step 1: Retarget the hero secondary CTA**

In `templates/about.html` replace:

```html
            <a href="#process" class="cta-button cta-secondary">Our Process</a>
```

with:

```html
            <a href="#subteams" class="cta-button cta-secondary">Our Teams</a>
```

- [ ] **Step 2: Replace the Who We Are section**

Replace the whole `<section id="about" class="fade-in-section">…</section>` block with:

```html
<section id="about" class="fade-in-section">
    <div class="about-content">
        <div class="about-text">
            <h2 class="about-heading">Who We Are</h2>
            <p>We are a <strong>student-led robotics club</strong> competing in the <strong>VEX V5 Robotics
                    Competition</strong>. Our members learn hands-on mechanical design, electrical engineering, and
                complex C++ / Python programming.</p>
            <p>Through intense competition and collaboration, we push the boundaries of what high school students
                can achieve in robotics and engineering.</p>
            <p>Our teams work year-round to design, build, and program competitive robots that can tackle the
                season's challenges with precision and creativity.</p>
        </div>
        <figure class="about-photo">
            <img src="{{ url_for('static', filename='assets/photos/carousel1.jpg') }}"
                alt="Mepham Robotics members working on a robot" loading="lazy">
        </figure>
    </div>
</section>
```

- [ ] **Step 3: Append the CSS**

Append to `static/css/pages/about.css`:

```css

/* Who We Are */
.about-heading {
    font-family: 'Space Mono', monospace;
    color: var(--maroon-dark);
    text-align: left;
    margin-bottom: 1rem;
}

[data-theme="dark"] .about-heading {
    color: #d4a0a1;
}

.about-photo {
    margin: 0;
    border: 3px solid var(--text-dark);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2);
}

.about-photo img {
    display: block;
    width: 100%;
    aspect-ratio: 4 / 3;
    object-fit: cover;
}

[data-theme="dark"] .about-photo {
    border-color: #444;
}
```

`.about-content` already collapses to one column at 768px in `styles.css`. The figure comes after the text in the markup, so the image already lands last on mobile.

- [ ] **Step 4: Verify**

Run BRACES on `static/css/pages/about.css` and expect `True`. Run RENDER and expect `status 200` and `broken []`. Run HAS with `['href="#subteams"', 'Our Teams', 'about-photo', 'carousel1.jpg']` and expect all four `True`. Also run HAS with `['vexrobotics.png', '#process']` and expect both `False`.

- [ ] **Step 5: Commit**

```bash
git add templates/about.html static/css/pages/about.css
git commit -m "Swap about page hero CTA to Our Teams and frame a real team photo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: What We Stand For (replaces Mission and Values)

**Files:**
- Modify: `templates/about.html` (delete the `mission-section` and `values-section` sections, insert the new band where `mission-section` was)
- Modify: `static/css/pages/about.css` (append)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `.about-values`, `.about-values-inner`, `.about-values-grid`, `.about-value-card`, `.about-value-icon`. Task 6 relies on the old `.mission-*`, `.values-list`, and `.value-item` classes no longer appearing in the template.

- [ ] **Step 1: Replace the markup**

Delete the entire `<section class="mission-section fade-in-section">…</section>` and `<section class="values-section fade-in-section">…</section>` blocks. The `di-section` block between them stays until Task 4. In place of the mission section, directly after the Who We Are section, insert:

```html
<section class="about-values fade-in-section">
    <div class="about-values-inner">
        <h2 class="ripple">What We Stand For</h2>
        <div class="about-values-grid">
            <div class="about-value-card">
                <i data-lucide="target" class="about-value-icon"></i>
                <h3>Excellence</h3>
                <p>We strive for excellence in every aspect of robotics - from mechanical design to autonomous
                    programming.</p>
            </div>
            <div class="about-value-card">
                <i data-lucide="lightbulb" class="about-value-icon"></i>
                <h3>Innovation</h3>
                <p>We encourage creative thinking and innovative solutions to complex engineering challenges.</p>
            </div>
            <div class="about-value-card">
                <i data-lucide="handshake" class="about-value-icon"></i>
                <h3>Collaboration</h3>
                <p>Teamwork is at our core. The best solutions come from diverse minds working together, and we
                    carry that spirit into our school and local community by giving back.</p>
            </div>
            <div class="about-value-card">
                <i data-lucide="mountain" class="about-value-icon"></i>
                <h3>Perseverance</h3>
                <p>We embrace challenges and learn from failures, constantly improving our robots and ourselves.</p>
            </div>
            <div class="about-value-card">
                <i data-lucide="scale" class="about-value-icon"></i>
                <h3>Integrity</h3>
                <p>We compete with honesty and fairness, upholding the highest standards of sportsmanship.</p>
            </div>
            <div class="about-value-card">
                <i data-lucide="graduation-cap" class="about-value-icon"></i>
                <h3>Mentorship</h3>
                <p>Experienced members guide new team members, fostering a culture of continuous learning.</p>
            </div>
        </div>
    </div>
</section>
```

- [ ] **Step 2: Append the CSS**

```css

/* What We Stand For: painted, full-bleed */
.about-values {
    max-width: none;
    margin-left: 0;
    margin-right: 0;
    background: var(--maroon-dark);
    padding: var(--spacing-xl) var(--spacing-md);
}

.about-values-inner {
    max-width: 1200px;
    margin: 0 auto;
}

.about-values h2 {
    color: #fff;
}

.about-values-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2rem;
}

.about-value-card {
    background: #fff;
    border: 3px solid var(--text-dark);
    border-radius: 16px;
    padding: 2rem;
    box-shadow: 8px 8px 0px rgba(0, 0, 0, 0.25);
    transition: transform var(--transition-base), box-shadow var(--transition-base);
}

.about-value-card:hover {
    transform: translate(-4px, -4px);
    box-shadow: 12px 12px 0px rgba(0, 0, 0, 0.3);
}

.about-value-icon {
    width: 2.5rem;
    height: 2.5rem;
    color: var(--maroon-dark);
    margin-bottom: 1rem;
}

.about-value-card h3 {
    font-family: 'Space Mono', monospace;
    font-size: 1.4rem;
    color: var(--maroon-dark);
    margin-bottom: 0.75rem;
}

.about-value-card p {
    color: var(--text-light);
    line-height: 1.7;
}

[data-theme="dark"] .about-values {
    background: #3a0a0b;
}

[data-theme="dark"] .about-values h2 {
    color: #fff;
}

[data-theme="dark"] .about-value-card {
    background: #1e1e1e;
    border-color: #444;
}

[data-theme="dark"] .about-value-icon,
[data-theme="dark"] .about-value-card h3 {
    color: #d4a0a1;
}

[data-theme="dark"] .about-value-card p {
    color: #bbb;
}

@media (max-width: 900px) {
    .about-values-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 600px) {
    .about-values-grid {
        grid-template-columns: 1fr;
    }
}
```

`[data-theme="dark"] .about-values h2` is required because `styles.css` has `[data-theme="dark"] h2 { color: #d4a0a1; }`, which has the same specificity as `.about-values h2` and would otherwise decide the color by source order alone.

- [ ] **Step 3: Verify**

Run BRACES on `about.css` and expect `True`. Run RENDER and expect `status 200` and `broken []`. Run HAS with `['What We Stand For', 'data-lucide="mountain"', 'data-lucide="scale"', 'data-lucide="graduation-cap"']` and expect all `True`. Run HAS with `['mission-card', 'value-item', 'Our Mission', 'Our Values']` and expect all `False`. Count the cards:

```bash
python -c "from api.index import app; print(app.test_client().get('/about').data.decode().count('class=\"about-value-card\"'))"
```

Expected: `6`.

- [ ] **Step 4: Commit**

```bash
git add templates/about.html static/css/pages/about.css
git commit -m "Merge about page Mission and Values into What We Stand For band

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Sub-Teams section

**Files:**
- Modify: `templates/about.html` (insert after the `about-values` section)
- Modify: `static/css/pages/about.css` (append)

**Interfaces:**
- Consumes: the `#subteams` target that the Task 1 hero CTA links to, and `.about-photo` from Task 1.
- Produces: `.about-subteams`, `.about-subteams-layout`, `.about-subteam-grid`, `.about-subteam-card`, `.about-subteam-icon`. These deliberately avoid the shared `.subteam-card` and `.subteam-grid` classes used by `notebook.html`.

- [ ] **Step 1: Insert markup** directly after the closing `</section>` of `about-values`:

```html
<section id="subteams" class="about-subteams fade-in-section">
    <h2 class="ripple">Our Sub-Teams</h2>
    <div class="about-subteams-layout">
        <figure class="about-photo">
            <img src="{{ url_for('static', filename='assets/photos/carousel7.jpg') }}"
                alt="Mepham Robotics sub-teams at work" loading="lazy">
        </figure>
        <div class="about-subteam-grid">
            <div class="about-subteam-card">
                <i data-lucide="cog" class="about-subteam-icon"></i>
                <h3>Mechanical</h3>
                <p>CAD, fabrication, drivetrain and manipulator design.</p>
            </div>
            <div class="about-subteam-card">
                <i data-lucide="zap" class="about-subteam-icon"></i>
                <h3>Electrical</h3>
                <p>Wiring, sensors, and V5 brain configuration.</p>
            </div>
            <div class="about-subteam-card">
                <i data-lucide="code" class="about-subteam-icon"></i>
                <h3>Programming</h3>
                <p>C++ and Python, autonomous routines, odometry.</p>
            </div>
            <div class="about-subteam-card">
                <i data-lucide="notebook-pen" class="about-subteam-icon"></i>
                <h3>Notebook &amp; Outreach</h3>
                <p>Engineering notebook, judging interviews, community events.</p>
            </div>
        </div>
    </div>
</section>
```

- [ ] **Step 2: Append the CSS**

```css

/* Sub-Teams: photo left, 2x2 cards right */
.about-subteams {
    padding: var(--spacing-xl) var(--spacing-md);
}

.about-subteams-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3rem;
    align-items: center;
}

.about-subteam-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1.5rem;
}

.about-subteam-card {
    background: #fff;
    border: 3px solid var(--text-dark);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2);
    transition: transform var(--transition-base), box-shadow var(--transition-base);
}

.about-subteam-card:hover {
    transform: translate(-4px, -4px);
    box-shadow: 12px 12px 0px rgba(148, 69, 71, 0.3);
}

.about-subteam-icon {
    width: 2rem;
    height: 2rem;
    color: var(--maroon-dark);
    margin-bottom: 0.75rem;
}

.about-subteam-card h3 {
    font-family: 'Space Mono', monospace;
    font-size: 1.15rem;
    color: var(--maroon-dark);
    margin-bottom: 0.5rem;
}

.about-subteam-card p {
    color: var(--text-light);
    line-height: 1.6;
    font-size: 0.95rem;
}

[data-theme="dark"] .about-subteam-card {
    background: #1e1e1e;
    border-color: #444;
}

[data-theme="dark"] .about-subteam-icon,
[data-theme="dark"] .about-subteam-card h3 {
    color: #d4a0a1;
}

[data-theme="dark"] .about-subteam-card p {
    color: #bbb;
}

@media (max-width: 768px) {
    .about-subteams-layout {
        grid-template-columns: 1fr;
    }

    /* image last on mobile */
    .about-subteams-layout .about-photo {
        order: 2;
    }
}

@media (max-width: 600px) {
    .about-subteam-grid {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 3: Verify**

Run BRACES on `about.css` and expect `True`. Run RENDER and expect `status 200` and `broken []`. Run HAS with `['id="subteams"', 'Our Sub-Teams', 'data-lucide="notebook-pen"', 'carousel7.jpg']` and expect all `True`. To confirm that `notebook.html` is untouched, run `git diff --stat -- templates/notebook.html static/css/styles.css` and expect empty output.

- [ ] **Step 4: Commit**

```bash
git add templates/about.html static/css/pages/about.css
git commit -m "Add Sub-Teams section to about page

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Culture & Safety (merges D&I and Safety Captain, removes inline styles)

**Files:**
- Modify: `templates/about.html` (delete the `di-section` and `safety-captain-section` sections, insert the new band after `about-subteams`)
- Modify: `static/css/pages/about.css` (append)

**Interfaces:**
- Consumes: the `url_for('safety_quiz')` route, which exists, and the shared `.cta-button .cta-primary` classes.
- Produces: `.about-culture`, `.about-culture-inner`, `.about-culture-card`, `.about-culture-icon`, `.about-culture-cta`. After this task the template has no `di-statement` and no `style=`, which Task 6 depends on.

- [ ] **Step 1: Replace the markup**

Delete the `<section class="di-section fade-in-section">…</section>` and `<section class="safety-captain-section fade-in-section" style="…">…</section>` blocks. Directly after the closing `</section>` of `about-subteams`, insert:

```html
<section class="about-culture fade-in-section">
    <div class="about-culture-inner">
        <h2 class="ripple">Culture &amp; Safety</h2>
        <div class="about-culture-grid">
            <div class="about-culture-card">
                <i data-lucide="globe" class="about-culture-icon"></i>
                <h3>Diversity &amp; Inclusion</h3>
                <p>Mepham Robotics is committed to fostering an inclusive environment where students of all
                    backgrounds can thrive in STEM. We believe that diverse perspectives lead to better engineering
                    solutions and a stronger community.</p>
            </div>
            <div class="about-culture-card">
                <i data-lucide="hard-hat" class="about-culture-icon"></i>
                <h3>Team Safety Captain</h3>
                <p>Our dedicated Safety Captain ensures all team members adhere to safety protocols, manages the
                    safety manual, and conducts regular workshop inspections.</p>
                <div class="about-culture-cta">
                    <a href="{{ url_for('safety_quiz') }}" class="cta-button cta-primary">Take Safety Quiz</a>
                </div>
            </div>
        </div>
    </div>
</section>
```

- [ ] **Step 2: Append the CSS**

```css

/* Culture & Safety: painted, full-bleed, two columns */
.about-culture {
    max-width: none;
    margin-left: 0;
    margin-right: 0;
    background: var(--accent-light);
    padding: var(--spacing-xl) var(--spacing-md);
}

.about-culture-inner {
    max-width: 1200px;
    margin: 0 auto;
}

.about-culture-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
}

.about-culture-card {
    background: #fff;
    border: 3px solid var(--text-dark);
    border-radius: 16px;
    padding: 2.5rem;
    box-shadow: 8px 8px 0px rgba(148, 69, 71, 0.2);
}

.about-culture-icon {
    width: 3rem;
    height: 3rem;
    color: var(--maroon-dark);
    margin-bottom: 1rem;
}

.about-culture-card h3 {
    font-family: 'Space Mono', monospace;
    font-size: 1.5rem;
    color: var(--maroon-dark);
    margin-bottom: 1rem;
}

.about-culture-card p {
    color: var(--text-light);
    line-height: 1.8;
    font-size: 1.05rem;
}

.about-culture-cta {
    margin-top: 1.5rem;
}

[data-theme="dark"] .about-culture {
    background: #1a1a1a;
}

[data-theme="dark"] .about-culture-card {
    background: #1e1e1e;
    border-color: #444;
}

[data-theme="dark"] .about-culture-icon,
[data-theme="dark"] .about-culture-card h3 {
    color: #d4a0a1;
}

[data-theme="dark"] .about-culture-card p {
    color: #bbb;
}

@media (max-width: 768px) {
    .about-culture-grid {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 3: Verify**

Run BRACES on `about.css` and expect `True`. Run RENDER and expect `status 200` and `broken []`. Run HAS with `['Culture &amp; Safety', 'data-lucide="hard-hat"', 'Take Safety Quiz']` and expect all `True`. Run HAS with `['di-statement', 'safety-captain-section']` and expect both `False`. Then run:

```bash
grep -c 'style="' templates/about.html
```

Expected: `0`. `grep` exits 1 when the count is zero, which is fine.

- [ ] **Step 4: Commit**

```bash
git add templates/about.html static/css/pages/about.css
git commit -m "Merge about page D&I and Safety Captain into Culture & Safety band

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Restyle Our Journey and fix Team Moments photos

**Files:**
- Modify: `templates/about.html` (add a class to the timeline section, replace the carousel track)
- Modify: `static/css/pages/about.css` (append)

**Interfaces:**
- Consumes: the shared `.history-timeline`, `.timeline-*`, and `.photo-carousel-section .carousel-*` rules in `styles.css`, whose mobile timeline rules are kept.
- Produces: the `.about-journey` modifier class.

- [ ] **Step 1: Tag the timeline section**

Replace:

```html
<section class="history-timeline fade-in-section">
```

with:

```html
<section class="history-timeline about-journey fade-in-section">
```

Leave the four `timeline-item` blocks unchanged.

- [ ] **Step 2: Replace the carousel track contents**

Replace everything between `<div class="carousel-track">` and its closing `</div>` (both `{% for i in range(...) %}` loops) with:

```html
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel1.jpg') }}" alt="Team photo 1"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel2.jpg') }}" alt="Team photo 2"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel3.jpg') }}" alt="Team photo 3"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel4.jpg') }}" alt="Team photo 4"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel5.jpg') }}" alt="Team photo 5"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel6.jpg') }}" alt="Team photo 6"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel7.jpg') }}" alt="Team photo 7"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel8.jpg') }}" alt="Team photo 8"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel9.jpg') }}" alt="Team photo 9"
                    loading="lazy">
            </div>
            <div class="carousel-item">
                <img src="{{ url_for('static', filename='assets/photos/carousel10.jpg') }}" alt="Team photo 10"
                    loading="lazy">
            </div>
```

This matches the Team Gallery markup in `templates/index.html`.

- [ ] **Step 3: Append the timeline restyle**

Our Journey sits between two painted neighbors, so it drops the shared grey gradient and uses the page background. The track becomes a solid maroon line, and the year becomes a gold label on a maroon tag.

```css

/* Our Journey: unpainted, flat track, year tags */
.about-journey {
    background: transparent;
    padding: var(--spacing-xl) var(--spacing-md);
}

.about-journey .timeline-vertical::before {
    background: var(--maroon-dark);
}

.about-journey .timeline-year {
    display: inline-block;
    background: var(--maroon-dark);
    color: var(--accent-gold);
    font-size: 1.1rem;
    padding: 0.15rem 0.75rem;
    border-radius: 8px;
}

[data-theme="dark"] .about-journey {
    background: transparent;
}

[data-theme="dark"] .about-journey .timeline-year {
    color: var(--accent-gold);
}
```

The dark variants are required: `styles.css` sets `[data-theme="dark"] .history-timeline` (a background) and `[data-theme="dark"] .timeline-year` (a color), and both beat the light-mode rules above on specificity.

- [ ] **Step 4: Verify**

Run BRACES on `about.css` and expect `True`. Run RENDER and expect `status 200` and `broken []`. Then run:

```bash
python -c "
from api.index import app
h = app.test_client().get('/about').data.decode()
print('carousel imgs', sum(f'carousel{i}.jpg\" alt=\"Team photo {i}\"' in h for i in range(1, 11)))
print('base.png', 'base.png' in h, 'about-journey', 'about-journey' in h)
"
```

Expected: `carousel imgs 10`, `base.png False`, and `about-journey True`. Also run `grep -c "range(" templates/about.html` and expect `0`.

- [ ] **Step 5: Commit**

```bash
git add templates/about.html static/css/pages/about.css
git commit -m "Restyle about page timeline and load real Team Moments photos

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Remove retired about-only rules from styles.css

**Files:**
- Modify: `static/css/styles.css`

**Interfaces:**
- Consumes: Tasks 2 and 4 removed every use of these classes from `templates/about.html`.
- Produces: nothing new.

Retired classes: `.mission-grid`, `.mission-card`, `.mission-icon`, `.values-list`, `.value-item`, `.di-statement` (including `.di-icon` inside it), `.about-image-container`, and `.animated-cube-img`. The last two became dead in Task 1. Keep `.about-content`, `.about-text`, and the `@keyframes float` rule, because they are still used or may be shared.

- [ ] **Step 1: Guard grep, and do not delete if anything matches**

```bash
grep -rnE "mission-(grid|card|icon)|values-list|value-item|di-statement|di-icon|about-image-container|animated-cube-img" templates static/js
```

Expected: no output. If any file matches, stop and report it instead of deleting.

- [ ] **Step 2: Fix the full-bleed selector list (near line 330)**

Replace:

```css
.team-awards,
.di-statement {
    max-width: none;
```

with:

```css
.team-awards {
    max-width: none;
```

- [ ] **Step 3: Delete the old ABOUT PAGE rules (near lines 2692–2786)**

Under `/* --- ABOUT PAGE --- */`, delete these whole rule blocks: `.about-image-container`, `.animated-cube-img`, `.animated-cube-img:hover`, `.mission-grid`, `.mission-card`, `.mission-card:hover`, `.mission-icon`, `.mission-card h3`, `.mission-card p`, `.values-list`, `.value-item`, `.value-item:hover`, and `.value-item h4`. Then change the media query that follows from:

```css
@media (max-width: 768px) {
    .about-content {
        grid-template-columns: 1fr;
        gap: 3rem;
    }

    .mission-grid {
        grid-template-columns: 1fr;
    }
}
```

to:

```css
@media (max-width: 768px) {
    .about-content {
        grid-template-columns: 1fr;
        gap: 3rem;
    }
}
```

- [ ] **Step 4: Remove the retired selectors from the dark-mode lists (near lines 3312–3348)**

Delete exactly these selector lines, and leave each rule's other selectors and its declarations intact:

```css
[data-theme="dark"] .mission-card,
[data-theme="dark"] .value-item,
```

```css
[data-theme="dark"] .mission-card h3,
[data-theme="dark"] .value-item h4,
```

```css
[data-theme="dark"] .mission-card p,
```

- [ ] **Step 5: Delete the D&I Statement block (near lines 4243–4286)**

Delete from the `/* D&I Statement */` comment through the end of `[data-theme="dark"] .di-statement p { … }`, stopping just before `/* Sponsor inquiry form */`. That removes `.di-statement`, `[data-theme="dark"] .di-statement`, `.di-statement .di-icon`, `.di-statement h3`, `[data-theme="dark"] .di-statement h3`, `.di-statement p`, and `[data-theme="dark"] .di-statement p`.

- [ ] **Step 6: Verify**

```bash
grep -nE "mission-(grid|card|icon)|values-list|value-item|di-statement|di-icon|about-image-container|animated-cube-img" static/css/styles.css
```

Expected: no output. Run BRACES on `static/css/styles.css` and expect `True`. Run RENDER and expect `status 200`. Check pages that share the edited dark-mode lists:

```bash
python -c "
from api.index import app
c = app.test_client()
for p in ['/', '/donate', '/about', '/notebook']: print(p, c.get(p).status_code)
"
```

Expected: `200` for `/`, `/donate`, and `/about`. `/notebook` is behind `@role_required('member')`, so a `302` redirect counts as a pass. What matters is that it isn't a `500`. Check notebook visually as a logged-in member in Task 7.

- [ ] **Step 7: Commit**

```bash
git add static/css/styles.css
git commit -m "Remove retired about page rules from styles.css

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Browser verification pass

**Files:**
- Only if a defect is found: `static/css/pages/about.css`

**Interfaces:**
- Consumes: all previous tasks.

- [ ] **Step 1: Start the dev server**

```bash
python api/index.py
```

Open `http://127.0.0.1:5000/about`.

- [ ] **Step 2: Check the three widths** (1440px, 768px, 375px) in the light theme

At each width, confirm there is no horizontal scroll: `document.documentElement.scrollWidth <= window.innerWidth` in the console returns `true`. Confirm the section order is Hero, Breadcrumb, Who We Are, What We Stand For (maroon band edge to edge), Sub-Teams, Culture & Safety (light band edge to edge), Our Journey, Team Moments. At 1440px the principles show 3 columns. At 768px they show 2 columns, and the Who We Are, Sub-Teams, and Culture bands are one column with images after the text or cards. At 375px the principles and sub-team cards are one column.

- [ ] **Step 3: Check the dark theme at 1440px and 375px**

Toggle the site theme. Every heading, card body, the timeline year tags, and the "What We Stand For" heading on the maroon band must be legible. No card should keep a white background.

- [ ] **Step 4: Check the notebook page for regressions**

Log in as a member, open `/notebook`, and confirm its `.subteam-card` grid looks the same as before this work, in both themes.

- [ ] **Step 5: Check the hero CTA and network**

Click "Our Teams". The page should smooth-scroll to the Sub-Teams section. In the DevTools Network tab, filtered to `Img`, reload and confirm there are no 404s.

- [ ] **Step 6: Fix and commit only if needed**

If a defect is found, fix it in `static/css/pages/about.css` only, rerun BRACES and RENDER, then:

```bash
git add static/css/pages/about.css
git commit -m "Fix about page layout issues found in browser pass

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
