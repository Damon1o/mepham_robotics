// ============================================
// MEPHAM ROBOTICS - ENHANCED INTERACTIONS
// ============================================

// --- LUCIDE ICONS ---
// Call after inserting any markup containing [data-lucide] elements.
function refreshLucideIcons() {
    if (window.lucide) {
        lucide.createIcons();
    }
}
document.addEventListener('DOMContentLoaded', refreshLucideIcons);

// --- NAVIGATION TOGGLE ---
// --- CSRF ---
// Every state-changing request has to echo the token the server put in the
// page, so keep one accessor rather than re-reading the meta tag everywhere.
function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function jsonHeaders() {
    return { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() };
}

function toggleNav(force) {
    const nav = document.getElementById("mySidenav");
    const overlay = document.getElementById("overlay");
    if (!nav || !overlay) return;

    const open = typeof force === 'boolean' ? force : !nav.classList.contains("active");
    nav.classList.toggle("active", open);
    overlay.classList.toggle("active", open);
    document.body.style.overflow = open ? 'hidden' : '';
    document.querySelectorAll('.menu-toggle[aria-expanded]')
        .forEach(btn => btn.setAttribute('aria-expanded', String(open)));
}

// --- DROPDOWN TOGGLE ---
function toggleDropdown() {
    const dropdown = document.getElementById("teamDropdown");
    const btn = document.querySelector(".dropdown-btn");
    if (!dropdown) return;
    const open = !dropdown.classList.contains("active");
    dropdown.classList.toggle("active", open);
    if (btn) {
        btn.classList.toggle("active", open);
        btn.setAttribute('aria-expanded', String(open));
    }
}

document.addEventListener('click', (e) => {
    if (e.target.closest('[data-nav-toggle]')) {
        toggleNav();
    } else if (e.target.closest('[data-dropdown-toggle]')) {
        toggleDropdown();
    } else if (e.target.closest('[data-theme-toggle]')) {
        cycleTheme();
    }
});

// Escape closes the navigation drawer.
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const nav = document.getElementById("mySidenav");
        if (nav && nav.classList.contains('active')) toggleNav(false);
    }
});

// --- THEME TOGGLE ---
const THEME_LABELS = { system: 'System theme', light: 'Light theme', dark: 'Dark theme' };

function paintThemeLabel() {
    if (!window.MephamTheme) return;
    const mode = window.MephamTheme.get();
    document.querySelectorAll('[data-theme-label]').forEach(el => {
        el.textContent = THEME_LABELS[mode] || THEME_LABELS.system;
    });
    document.querySelectorAll('[data-theme-toggle]').forEach(el => {
        el.setAttribute('title', `${THEME_LABELS[mode]} — click to change`);
    });
}

function cycleTheme() {
    if (!window.MephamTheme) return;
    const mode = window.MephamTheme.set(window.MephamTheme.next());
    paintThemeLabel();
    showToast(THEME_LABELS[mode], 'info');
}

document.addEventListener('DOMContentLoaded', paintThemeLabel);

// --- SMOOTH SCROLL FOR ANCHOR LINKS ---
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href !== '#' && document.querySelector(href)) {
            e.preventDefault();
            document.querySelector(href).scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// --- ENHANCED INTERSECTION OBSERVER ---
document.addEventListener('DOMContentLoaded', () => {
    // Fade-in sections with staggered animation
    const fadeInSections = document.querySelectorAll('.fade-in-section');

    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const fadeInObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                // Add staggered delay for multiple elements
                setTimeout(() => {
                    entry.target.classList.add('is-visible');
                }, index * 100);
            }
        });
    }, observerOptions);

    fadeInSections.forEach(section => {
        fadeInObserver.observe(section);
    });



    // --- ENHANCED AWARD CARD INTERACTIONS ---
    const awardBoxes = document.querySelectorAll('.award-box');

    awardBoxes.forEach(box => {
        box.addEventListener('mouseenter', function (e) {
            // Add slight tilt effect based on mouse position
            this.addEventListener('mousemove', tiltCard);
        });

        box.addEventListener('mouseleave', function () {
            this.removeEventListener('mousemove', tiltCard);
            this.style.transform = '';
        });
    });

    function tiltCard(e) {
        const card = e.currentTarget;
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        const rotateX = (y - centerY) / 10;
        const rotateY = (centerX - x) / 10;

        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-8px) scale(1.02)`;
    }

    // --- ANIMATED COUNTER FOR AWARD COUNTS ---
    const animateCounters = () => {
        const counters = document.querySelectorAll('.award-count');

        counters.forEach(counter => {
            const text = counter.textContent;
            const match = text.match(/×(\d+)/);

            if (match && parseInt(match[1]) > 0) {
                const target = parseInt(match[1]);
                let current = 0;
                const increment = target / 30;
                const duration = 1000;
                const stepTime = duration / 30;

                const timer = setInterval(() => {
                    current += increment;
                    if (current >= target) {
                        counter.textContent = `×${target}`;
                        clearInterval(timer);
                    } else {
                        counter.textContent = `×${Math.floor(current)}`;
                    }
                }, stepTime);
            }
        });
    };

    // Trigger counter animation when awards section is visible
    const awardSection = document.querySelector('.award-container');
    if (awardSection) {
        const counterObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    animateCounters();
                    counterObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.3 });

        counterObserver.observe(awardSection);
    }

    // Custom cursor removed per user request
    // --- SCROLL PROGRESS INDICATOR ---
    const scrollProgress = document.createElement('div');
    scrollProgress.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        height: 3px;
        background: linear-gradient(90deg, #800000, #ffd700);
        z-index: 9999;
        transition: width 0.1s ease;
        width: 0;
    `;
    document.body.appendChild(scrollProgress);

    // One layout read and style write per frame, not per scroll event.
    let progressFrame = 0;
    window.addEventListener('scroll', () => {
        if (progressFrame) return;
        progressFrame = requestAnimationFrame(() => {
            progressFrame = 0;
            const windowHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            const scrolled = windowHeight > 0 ? (window.pageYOffset / windowHeight) * 100 : 0;
            scrollProgress.style.width = scrolled + '%';
        });
    }, { passive: true });



    // --- KEYBOARD NAVIGATION ---
    document.addEventListener('keydown', (e) => {
        // ESC key closes navigation
        if (e.key === 'Escape') {
            const nav = document.getElementById("mySidenav");
            const overlay = document.getElementById("overlay");

            if (nav.classList.contains('active')) {
                toggleNav();
            }
        }
    });

    // --- TIMELINE ANIMATION ---
    const timelineContainers = document.querySelectorAll('.timeline-card');

    if (timelineContainers.length > 0) {
        const timelineObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry, index) => {
                if (entry.isIntersecting) {
                    setTimeout(() => {
                        entry.target.style.opacity = '0';
                        entry.target.style.transform = 'translateX(-30px)';
                        entry.target.style.transition = 'opacity 0.6s ease, transform 0.6s ease';

                        setTimeout(() => {
                            entry.target.style.opacity = '1';
                            entry.target.style.transform = 'translateX(0)';
                        }, 50);
                    }, index * 150);
                }
            });
        }, { threshold: 0.2 });

        timelineContainers.forEach(container => {
            timelineObserver.observe(container);
        });
    }

    // --- TEAM CARD STAGGER ANIMATION ---
    const teamCards = document.querySelectorAll('.team-card');

    if (teamCards.length > 0) {
        const teamObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    const cards = entry.target.querySelectorAll('.team-card');
                    cards.forEach((card, index) => {
                        setTimeout(() => {
                            card.style.opacity = '0';
                            card.style.transform = 'translateY(30px) scale(0.9)';
                            card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';

                            setTimeout(() => {
                                card.style.opacity = '1';
                                card.style.transform = 'translateY(0) scale(1)';
                            }, 50);
                        }, index * 150);
                    });
                    teamObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.3 });

        const teamSection = document.querySelector('.team-grid');
        if (teamSection) {
            teamObserver.observe(teamSection);
        }
    }


});

// Throttle function for scroll events
function throttle(func, limit) {
    let inThrottle;
    return function () {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// --- PERFORMANCE OPTIMIZATION ---
// Reduce animations on low-performance devices
if (navigator.hardwareConcurrency < 4) {
    document.documentElement.style.setProperty('--transition-slow', '0.3s ease');
    document.documentElement.style.setProperty('--transition-base', '0.2s ease');
}

// Respect user's motion preferences
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.documentElement.style.setProperty('--transition-fast', '0.01s');
    document.documentElement.style.setProperty('--transition-base', '0.01s');
    document.documentElement.style.setProperty('--transition-slow', '0.01s');
}

// --- ANIMATED STAT COUNTERS (ENHANCED) ---
(function initStatCounters() {
    const statNumbers = document.querySelectorAll('.stat-number');

    if (statNumbers.length === 0) return;

    const animateNumber = (element) => {
        const text = element.textContent;
        const hasPlus = text.includes('+');
        const cleanNumber = parseInt(text.replace(/[^0-9]/g, ''));

        if (isNaN(cleanNumber) || cleanNumber === 0) return;

        let current = 0;
        const duration = 2000;
        const increment = cleanNumber / (duration / 16);
        const startTime = performance.now();

        element.classList.add('counting');

        const updateCounter = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Easing function for smooth animation
            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            current = Math.floor(cleanNumber * easeOutQuart);

            element.textContent = current + (hasPlus ? '+' : '');

            if (progress < 1) {
                requestAnimationFrame(updateCounter);
            } else {
                element.textContent = cleanNumber + (hasPlus ? '+' : '');
                element.classList.remove('counting');
            }
        };

        requestAnimationFrame(updateCounter);
    };

    const statsSection = document.querySelector('.stats-section');
    if (statsSection) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    statNumbers.forEach(num => animateNumber(num));
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        observer.observe(statsSection);
    }
})();

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = 'info') {
    // Remove existing toast if any
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    const ICONS_BY_TYPE = { success: 'circle-check-big', error: 'circle-x', info: 'info' };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icon = document.createElement('i');
    icon.setAttribute('data-lucide', ICONS_BY_TYPE[type] || ICONS_BY_TYPE.info);
    toast.appendChild(icon);

    const text = document.createElement('span');
    text.textContent = message;
    toast.appendChild(text);

    document.body.appendChild(toast);
    refreshLucideIcons();

    // Trigger show animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Auto hide after 3 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// --- ENHANCED FORM HANDLING ---
(function initFormHandling() {
    // Forms that post to the server themselves, or that own their submit
    // handler elsewhere in this file.
    const isSelfHandled = (form) =>
        form.hasAttribute('data-native-submit') ||
        form.id === 'contact-form' ||
        form.id === 'chatbot-form' ||
        (form.getAttribute('action') || '').startsWith('/admin');

    const shake = (input) => {
        input.style.animation = 'shake 0.5s ease';
        setTimeout(() => input.style.animation = '', 500);
    };

    const firstEmpty = (form) => {
        const required = form.querySelectorAll('[required]');
        let missing = null;
        required.forEach(input => {
            if (!input.value.trim()) {
                shake(input);
                missing = missing || input;
            }
        });
        return missing;
    };

    async function postJson(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: jsonHeaders(),
            body: JSON.stringify(body)
        });
        let data = {};
        try {
            data = await response.json();
        } catch (err) {
            /* non-JSON error page */
        }
        if (!response.ok) {
            throw new Error(data.error || 'Something went wrong. Please try again.');
        }
        return data;
    }

    // Maps a form to the endpoint and payload it should send.
    function describe(form) {
        if (form.id === 'sponsorForm') {
            return {
                url: '/api/contact',
                success: "Thanks! We'll be in touch about sponsorship.",
                payload: {
                    name: form.querySelector('[name="company"]')?.value || '',
                    email: form.querySelector('[name="email"]')?.value || '',
                    topic: 'sponsor',
                    website: form.querySelector('[name="website"]')?.value || '',
                    message: `Sponsorship level: ${form.querySelector('select')?.value || 'unspecified'}\n\n` +
                        (form.querySelector('textarea')?.value || '')
                }
            };
        }
        if (form.classList.contains('footer-newsletter-form')) {
            return {
                url: '/api/newsletter',
                success: "You're on the list!",
                payload: {
                    email: form.querySelector('input[type="email"]')?.value || '',
                    website: form.querySelector('[name="website"]')?.value || ''
                }
            };
        }
        return null;
    }

    document.querySelectorAll('form').forEach(form => {
        if (isSelfHandled(form)) return;
        const target = describe(form);
        if (!target) return;

        form.addEventListener('submit', async function (e) {
            e.preventDefault();

            const missing = firstEmpty(this);
            if (missing) {
                showToast('Please fill in all required fields', 'error');
                missing.focus();
                return;
            }

            const submitBtn = this.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn ? submitBtn.textContent : 'Submit';
            const status = this.parentElement?.querySelector('[role="status"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Sending…';
            }

            const spec = describe(this);
            try {
                const data = await postJson(spec.url, spec.payload);
                const message = data.message || spec.success;
                showToast(message, 'success');
                if (status) status.textContent = message;
                this.reset();
            } catch (err) {
                showToast(err.message, 'error');
                if (status) status.textContent = err.message;
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalBtnText;
                }
            }
        });
    });

    // Add shake animation keyframes
    const shakeStyle = document.createElement('style');
    shakeStyle.textContent = `
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            20% { transform: translateX(-10px); }
            40% { transform: translateX(10px); }
            60% { transform: translateX(-10px); }
            80% { transform: translateX(10px); }
        }
    `;
    document.head.appendChild(shakeStyle);
})();



// --- CONTACT FORM (posts to the Flask API, not Google Forms) ---
(function initContactForm() {
    const form = document.getElementById('contact-form');
    if (!form) return;

    const successBanner = document.getElementById('form-success');
    const errorBanner = document.getElementById('form-error');
    let hideTimer = null;

    function showBanner(banner, text) {
        [successBanner, errorBanner].forEach(el => el?.classList.remove('is-visible'));
        if (!banner) return;
        if (text) banner.textContent = text;
        banner.classList.add('is-visible');
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => banner.classList.remove('is-visible'), 6000);
    }

    // --- Live character counter on the message field ---
    const messageField = form.querySelector('[name="message"]');
    const counter = form.querySelector('[data-counter-current]');
    if (messageField && counter) {
        const limit = Number(messageField.getAttribute('maxlength')) || 4000;
        const updateCounter = () => {
            const used = messageField.value.length;
            counter.textContent = used;
            counter.parentElement.classList.toggle('is-near-limit', used > limit * 0.9);
        };
        messageField.addEventListener('input', updateCounter);
        updateCounter();
    }

    // --- Inline field validation ---
    function fieldError(name, value) {
        const text = value.trim();
        if (name === 'name') {
            return text ? '' : 'Please enter your name.';
        }
        if (name === 'email') {
            if (!text) return 'Please enter your email address.';
            // Same shape check the API applies, so the user sees it before the round trip.
            const at = text.indexOf('@');
            const local = at > -1 ? text.slice(0, at) : '';
            const domain = at > -1 ? text.slice(at + 1) : '';
            if (!local || !domain.includes('.') || domain.startsWith('.') || domain.endsWith('.')) {
                return 'Please enter a valid email address.';
            }
            return '';
        }
        if (name === 'message') {
            return text ? '' : 'Please enter a message.';
        }
        return '';
    }

    function setFieldError(field, message) {
        const slot = form.querySelector(`[data-error-for="${field.name}"]`);
        field.classList.toggle('has-error', Boolean(message));
        field.setAttribute('aria-invalid', message ? 'true' : 'false');
        if (slot) {
            slot.textContent = message;
            slot.classList.toggle('is-visible', Boolean(message));
        }
    }

    const validatedFields = ['name', 'email', 'message']
        .map(name => form.querySelector(`[name="${name}"]`))
        .filter(Boolean);

    validatedFields.forEach(field => {
        field.addEventListener('blur', () => setFieldError(field, fieldError(field.name, field.value)));
        field.addEventListener('input', () => {
            if (field.classList.contains('has-error')) {
                setFieldError(field, fieldError(field.name, field.value));
            }
        });
    });

    // --- Channel switch rewrites the form's guidance and the message label ---
    const CHANNELS = {
        join: {
            lede: "Tell us your grade and what you're curious about \u2014 building, coding, driving, or design. " +
                'No experience needed, and you can join mid-season.',
            label: 'What would you like to know?'
        },
        sponsor: {
            lede: 'Let us know what you have in mind \u2014 funding, parts, machining time, or mentoring. ' +
                'We can send the sponsorship packet and this season\'s budget.',
            label: 'What would you like to support?'
        },
        general: {
            lede: 'Press, outreach invites, event requests, or anything that does not fit a box. ' +
                'Include dates and a location if you are inviting us somewhere.',
            label: 'How can we help?'
        }
    };

    const channelInputs = [...document.querySelectorAll('[name="topic"]')];
    const ledeEl = document.querySelector('[data-channel-lede]');
    const messageLabel = document.querySelector('[data-message-label]');

    function applyChannel(value) {
        const channel = CHANNELS[value] || CHANNELS.general;
        if (ledeEl) ledeEl.textContent = channel.lede;
        if (messageLabel) messageLabel.textContent = channel.label;
    }

    channelInputs.forEach(input => {
        input.addEventListener('change', () => applyChannel(input.value));
    });

    applyChannel(channelInputs.find(i => i.checked)?.value || 'join');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Stop at the first invalid field rather than making the user wait on a round trip.
        let firstInvalid = null;
        validatedFields.forEach(field => {
            const message = fieldError(field.name, field.value);
            setFieldError(field, message);
            if (message && !firstInvalid) firstInvalid = field;
        });
        if (firstInvalid) {
            firstInvalid.focus();
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalHTML = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Transmitting...';
        }

        const payload = {
            name: form.querySelector('[name="name"]')?.value || '',
            email: form.querySelector('[name="email"]')?.value || '',
            message: form.querySelector('[name="message"]')?.value || '',
            // The channel radios sit outside the <form> and join it via form="contact-form".
            topic: document.querySelector('[name="topic"]:checked')?.value || '',
            website: form.querySelector('[name="website"]')?.value || ''
        };

        try {
            const response = await fetch('/api/contact', {
                method: 'POST',
                headers: jsonHeaders(),
                body: JSON.stringify(payload)
            });
            const data = await response.json().catch(() => ({}));

            if (response.ok) {
                form.reset();
                if (counter) {
                    counter.textContent = '0';
                    counter.parentElement.classList.remove('is-near-limit');
                }
                validatedFields.forEach(field => setFieldError(field, ''));
                showBanner(successBanner);
                showToast('Message sent!', 'success');
            } else {
                showBanner(errorBanner, data.error || 'Something went wrong. Please try again.');
                showToast(data.error || 'Message not sent.', 'error');
            }
        } catch (err) {
            console.error('Contact submission error:', err);
            showBanner(errorBanner, 'Could not reach the server. Please try again later.');
            showToast('Could not reach the server.', 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalHTML;
                window.lucide?.createIcons();
            }
        }
    });
})();

// --- MEETING STATUS (is the lab open right now?) ---
(function initMeetingStatus() {
    const badge = document.querySelector('[data-meeting-status]');
    if (!badge) return;

    const text = badge.querySelector('.status-text');
    const MEETING_DAYS = [2, 5]; // Tuesday, Friday
    const START_HOUR = 15;
    const END_HOUR = 17;
    const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    function render() {
        const now = new Date();
        const isMeetingDay = MEETING_DAYS.includes(now.getDay());
        const hour = now.getHours();

        if (isMeetingDay && hour >= START_HOUR && hour < END_HOUR) {
            badge.classList.add('is-open');
            text.textContent = 'In the lab right now — until 5:00 PM';
            return;
        }

        badge.classList.remove('is-open');

        // Walk forward to the next meeting day, counting today only if it hasn't started yet.
        for (let offset = 0; offset <= 7; offset++) {
            const day = (now.getDay() + offset) % 7;
            if (!MEETING_DAYS.includes(day)) continue;
            if (offset === 0 && hour >= START_HOUR) continue;

            const when = offset === 0 ? 'today' : offset === 1 ? 'tomorrow' : DAY_NAMES[day];
            text.textContent = `Next meeting ${when} at 3:00 PM`;
            return;
        }
    }

    render();
    setInterval(render, 60000);
})();

// --- MAP FACADE (only contacts Google once the visitor asks for the map) ---
(function initMapFacade() {
    const facade = document.querySelector('.contact-map-facade');
    if (!facade) return;

    const button = facade.querySelector('.contact-map-load');
    button?.addEventListener('click', () => {
        const iframe = document.createElement('iframe');
        iframe.src = facade.dataset.mapSrc;
        iframe.className = 'map-embed';
        iframe.title = 'Mepham High School location map';
        iframe.loading = 'lazy';
        iframe.referrerPolicy = 'no-referrer-when-downgrade';
        iframe.allowFullscreen = true;
        facade.replaceChildren(iframe);
        facade.classList.add('is-loaded');
    });
})();


// --- ACTIVE NAV HIGHLIGHTING ---
(function initActiveNav() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidenav a');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (href === '/' && currentPath === '/')) {
            link.style.color = '#ffd700';
            link.style.borderLeftColor = '#ffd700';
        }
    });
})();

// --- FAQ ACCORDION ---
(function initFAQ() {
    const faqItems = document.querySelectorAll('.faq-item');

    if (faqItems.length === 0) return;

    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        question.addEventListener('click', () => {
            // Close other items
            faqItems.forEach(other => {
                if (other !== item) {
                    other.classList.remove('active');
                    other.querySelector('.faq-question')?.setAttribute('aria-expanded', 'false');
                }
            });
            // Toggle current item
            const nowOpen = item.classList.toggle('active');
            question.setAttribute('aria-expanded', String(nowOpen));
        });
    });
})();


// --- PROGRESS BAR ANIMATION ---
(function initProgressBars() {
    const progressBars = document.querySelectorAll('.progress-fill');

    if (progressBars.length === 0) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const bar = entry.target;
                const width = bar.dataset.progress || '0';
                bar.style.width = width + '%';
                observer.unobserve(bar);
            }
        });
    }, { threshold: 0.5 });

    progressBars.forEach(bar => {
        bar.style.width = '0';
        observer.observe(bar);
    });
})();
// --- COUNTDOWN TIMER ---
(function initCountdown() {
    const daysEl = document.getElementById('days');
    const hoursEl = document.getElementById('hours');
    const minutesEl = document.getElementById('minutes');
    const secondsEl = document.getElementById('seconds');

    if (!daysEl) return;

    const dateEl = document.querySelector('[data-countdown-date]');
    if (!dateEl) {
        document.querySelector('.countdown-section')?.setAttribute('hidden', '');
        return;
    }

    // The next competition's date comes from the template as a data attribute
    // (an inline script would be blocked by the public page CSP).
    const dateStr = dateEl.dataset.countdownDate;
    const countDownDate = new Date(dateStr).getTime();

    const updateTimer = setInterval(function () {
        const now = new Date().getTime();
        const distance = countDownDate - now;

        // Time calculations
        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((distance % (1000 * 60)) / 1000);

        // Display results with leading zeros
        daysEl.textContent = days < 10 ? '0' + days : days;
        hoursEl.textContent = hours < 10 ? '0' + hours : hours;
        minutesEl.textContent = minutes < 10 ? '0' + minutes : minutes;
        secondsEl.textContent = seconds < 10 ? '0' + seconds : seconds;

        // If the count down is finished, write some text
        if (distance < 0) {
            clearInterval(updateTimer);
            const day = document.createElement('h3');
            day.className = 'countdown-today';
            day.textContent = 'COMPETITION DAY!';
            document.querySelector('.countdown-container').replaceChildren(day);
        }
    }, 1000);
})();
// --- PORTAL & AUTH LOGIC ---
(function initAuth() {
    function updateNav() {
        const sidenav = document.getElementById('mySidenav');
        if (!sidenav) return;

        // Check if the server injected a logged-in user via data attribute
        const currentUser = document.body.dataset.currentUser;
        const isLoggedIn = !!currentUser;

        // Managing dynamic logout link removed - now handled purely by server-side templates

        // Update username display on resources page
        const nameDisplay = document.getElementById('userNameDisplay');
        if (nameDisplay && isLoggedIn) {
            nameDisplay.textContent = currentUser.toUpperCase();
        }
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateNav);
    } else {
        updateNav();
    }

    // Export global logout
    window.logout = function () {
        fetch('/logout', { method: 'POST' }).then(() => {
            window.location.href = '/login';
        });
    };
})();

/* ============================================
   SITE SEARCH
   ============================================ */
(function initSearch() {
    const pages = [
        { title: 'Home', url: '/', desc: 'Welcome to Mepham Robotics — VEX V5 team homepage, timeline, and stats', keywords: 'home robotics vex v5 team homepage mepham' },
        { title: 'About Us', url: '/about', desc: 'Our mission, values, history, and team culture', keywords: 'about mission values history team culture sub-teams diversity' },
        { title: 'Achievements', url: '/achievements', desc: 'Awards, competition results, and season highlights', keywords: 'awards achievements competitions results trophies seasons' },
        { title: 'Donate', url: '/donate', desc: 'Support our team through sponsorship and donations', keywords: 'donate sponsor support fundraising givebutter tiers' },
        { title: 'Contact', url: '/contact', desc: 'Get in touch — contact form, meeting schedule, and FAQ', keywords: 'contact email form meeting schedule faq questions' },
        { title: '77628D Team', url: '/team/77628D', desc: 'Team 77628D robot details and competition info', keywords: '77628D robot team' },
        { title: '77628P Team', url: '/team/77628P', desc: 'Team 77628P robot details and competition info', keywords: '77628P robot team' },
        { title: 'Glossary', url: '/glossary', desc: 'Robotics terms and definitions from A to Z', keywords: 'glossary terms definitions dictionary pid autonomous drivetrain', members: true },
        { title: 'Branding Guide', url: '/branding', desc: 'Official team colors, fonts, and logo usage', keywords: 'branding colors fonts logo maroon gold style guide', members: true },
        { title: 'Design Standards', url: '/standards', desc: 'Build standards, code style, and naming conventions', keywords: 'standards design build code style naming conventions', members: true },
        { title: 'Member Resources', url: '/resources', desc: 'Guides, links, and tooling for team members', keywords: 'resources guides links tools members downloads', members: true },
        { title: 'Safety Quiz', url: '/safety-quiz', desc: 'Interactive safety quiz — test your workshop knowledge', keywords: 'safety quiz test workshop lab rules ppe' },
        { title: 'Engineering Notebook', url: '/notebook', desc: 'Public engineering notebook — design process and logs', keywords: 'notebook engineering design process testing iteration', members: true },
        { title: 'Privacy Policy', url: '/privacy', desc: 'How we handle your data and privacy', keywords: 'privacy policy data cookies' },
        { title: 'Site Credits', url: '/credits', desc: 'Website credits and acknowledgments', keywords: 'credits site acknowledgments technologies' },
    ];

    const signedIn = () => document.body.hasAttribute('data-current-user');

    function doSearch(query) {
        if (!query || query.length < 2) return [];
        const q = query.toLowerCase();
        return pages.filter(p => (!p.members || signedIn()) && (
            p.title.toLowerCase().includes(q) ||
            p.desc.toLowerCase().includes(q) ||
            p.keywords.toLowerCase().includes(q)
        ));
    }

    document.addEventListener('click', function (e) {
        if (e.target.closest('.search-close')) {
            closeSearch();
        }
    });

    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            openSearch();
        }
        if (e.key === 'Escape') {
            closeSearch();
        }
        // Enter on the search box opens the first result.
        if (e.key === 'Enter' && e.target.closest('.search-input-wrapper input')) {
            e.preventDefault();
            document.querySelector('.search-result-item')?.click();
        }
    });

    function openSearch() {
        const overlay = document.querySelector('.search-overlay');
        if (!overlay) return;
        overlay.classList.add('active');
        const input = overlay.querySelector('input');
        if (input) { input.value = ''; input.focus(); }
        const results = overlay.querySelector('.search-results');
        if (results) results.textContent = '';
        // Close the side nav if it is open, then lock page scroll for the overlay.
        toggleNav(false);
        document.body.style.overflow = 'hidden';
    }

    function closeSearch() {
        const overlay = document.querySelector('.search-overlay');
        if (!overlay) return;
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    document.addEventListener('input', function (e) {
        if (!e.target.closest('.search-input-wrapper input')) return;
        const q = e.target.value.trim();
        const resultsEl = document.querySelector('.search-results');
        if (!resultsEl) return;
        const hits = doSearch(q);
        if (q.length < 2) {
            resultsEl.innerHTML = '';
            return;
        }
        if (hits.length === 0) {
            resultsEl.textContent = '';
            const empty = document.createElement('div');
            empty.className = 'search-no-results';
            empty.textContent = 'No results found.';
            resultsEl.appendChild(empty);
            return;
        }
        resultsEl.textContent = '';
        hits.forEach(h => {
            const item = document.createElement('a');
            item.className = 'search-result-item';
            item.href = h.url;

            const title = document.createElement('div');
            title.className = 'result-title';
            title.textContent = h.title;

            const desc = document.createElement('div');
            desc.className = 'result-desc';
            desc.textContent = h.desc;

            item.append(title, desc);
            resultsEl.appendChild(item);
        });
    });

    // Click outside to close
    document.addEventListener('click', function (e) {
        const overlay = document.querySelector('.search-overlay');
        if (overlay && e.target === overlay) closeSearch();
    });
})();


/* ============================================
   GLOSSARY SEARCH / FILTER
   ============================================ */
(function initGlossarySearch() {
    document.addEventListener('input', function (e) {
        const input = e.target.closest('#glossarySearch');
        if (!input) return;
        const q = input.value.toLowerCase().trim();
        const terms = document.querySelectorAll('.glossary-term');
        const sections = document.querySelectorAll('.glossary-section');

        terms.forEach(function (term) {
            const dt = term.querySelector('dt');
            const dd = term.querySelector('dd');
            const text = (dt ? dt.textContent : '') + ' ' + (dd ? dd.textContent : '');
            term.style.display = text.toLowerCase().includes(q) || q === '' ? '' : 'none';
        });

        // Hide empty sections
        sections.forEach(function (sec) {
            const visible = sec.querySelectorAll('.glossary-term:not([style*="display: none"])');
            sec.style.display = visible.length > 0 || q === '' ? '' : 'none';
        });
    });
})();

/* ============================================
   SAFETY QUIZ ENGINE
   ============================================ */
(function initSafetyQuiz() {
    if (!document.getElementById('quizContainer')) return;

    const questions = [
        { q: 'What should you always wear when operating power tools?', opts: ['Sandals', 'Safety glasses and closed-toe shoes', 'Headphones', 'A cape'], a: 1 },
        { q: 'What is the first thing you should do in case of a fire in the workshop?', opts: ['Continue working', 'Alert others and evacuate', 'Try to extinguish it alone', 'Take a photo'], a: 1 },
        { q: 'Which of these is NOT proper workshop attire?', opts: ['Closed-toe shoes', 'Safety glasses', 'Loose-hanging jewelry', 'Tied-back long hair'], a: 2 },
        { q: 'What should you do before using any power tool?', opts: ['Skip the manual', 'Inspect the tool and ensure it is in working order', 'Let a friend try it first', 'Guess how it works'], a: 1 },
        { q: 'Where should chemicals and solvents be stored?', opts: ['Next to food', 'In a ventilated, labeled cabinet', 'Under a desk', 'In a backpack'], a: 1 },
        { q: 'What does PPE stand for?', opts: ['Pretty Perfect Equipment', 'Personal Protective Equipment', 'Professional Power Electronics', 'Portable Precision Engine'], a: 1 },
        { q: 'When should you report an injury in the workshop?', opts: ['Never', 'Only if it is serious', 'Immediately, no matter how small', 'Next week'], a: 2 },
        { q: 'What is the proper way to carry scissors or sharp tools?', opts: ['Run with them', 'Point-down at your side', 'Toss them to your teammate', 'In your pocket'], a: 1 },
        { q: 'What should the workshop floor be free of?', opts: ['Robots', 'Tripping hazards and spills', 'Tables', 'Students'], a: 1 },
        { q: 'Who is responsible for safety in the workshop?', opts: ['Only the teacher', 'Only the safety captain', 'Everyone', 'The principal'], a: 2 },
    ];

    let current = 0;
    let answers = new Array(questions.length).fill(-1);
    const container = document.getElementById('quizContainer');

    function render() {
        if (current >= questions.length) {
            showResults();
            return;
        }
        const cq = questions[current];
        const progress = ((current) / questions.length) * 100;
        container.innerHTML = `
            <div class="quiz-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(progress)}"><div class="quiz-progress-fill"></div></div>
            <div class="quiz-question-card">
                <div class="quiz-question-num">Question ${current + 1} of ${questions.length}</div>
                <div class="quiz-question-text">${cq.q}</div>
                <div class="quiz-options">
                    ${cq.opts.map((o, i) => `<button type="button" class="quiz-option ${answers[current] === i ? 'selected' : ''}" data-idx="${i}" aria-pressed="${answers[current] === i}">${o}</button>`).join('')}
                </div>
            </div>
            <div class="quiz-nav">
                <button type="button" class="quiz-btn" data-quiz-nav="prev" ${current === 0 ? 'disabled' : ''}><i data-lucide="arrow-left"></i> Back</button>
                <button type="button" class="quiz-btn quiz-btn-primary" data-quiz-nav="next" ${answers[current] === -1 ? 'disabled' : ''}>
                    ${current === questions.length - 1 ? 'Finish' : 'Next <i data-lucide="arrow-right"></i>'}
                </button>
            </div>
        `;
        // Set through the DOM rather than an inline style attribute.
        container.querySelector('.quiz-progress-fill').style.width = `${progress}%`;
        refreshLucideIcons();
    }

    // One delegated listener for answers and navigation. The public page runs
    // under a CSP with no inline script, so injected onclick= attributes are
    // blocked; data attributes plus this handler are not.
    container.addEventListener('click', function (e) {
        const opt = e.target.closest('.quiz-option');
        if (opt) {
            answers[current] = parseInt(opt.dataset.idx, 10);
            render();
            return;
        }

        const nav = e.target.closest('[data-quiz-nav]');
        if (!nav || nav.disabled) return;
        const action = nav.dataset.quizNav;
        if (action === 'next' && answers[current] !== -1) {
            current++;
        } else if (action === 'prev' && current > 0) {
            current--;
        } else if (action === 'restart') {
            current = 0;
            answers = new Array(questions.length).fill(-1);
        } else {
            return;
        }
        render();
        container.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });

    function showResults() {
        let score = 0;
        questions.forEach((q, i) => { if (answers[i] === q.a) score++; });
        const pct = Math.round((score / questions.length) * 100);
        const pass = pct >= 70;
        container.innerHTML = `
            <div class="quiz-results">
                <div class="quiz-score-circle ${pass ? 'pass' : 'fail'}">${pct}%</div>
                <h2 class="quiz-results-title">${pass ? '<i data-lucide="party-popper"></i> You Passed!' : '<i data-lucide="circle-x"></i> Not Quite'}</h2>
                <p class="quiz-results-text">You got ${score} out of ${questions.length} correct.
                ${pass ? 'Great job — you know your workshop safety!' : 'Review the safety guidelines and try again.'}</p>
                <button type="button" class="quiz-btn quiz-btn-primary" data-quiz-nav="restart">Try Again</button>
            </div>
        `;
        refreshLucideIcons();
    }

    // Initial render on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
})();

/* ============================================
   ROBOTEVENTS MATCH RESULTS (via backend proxy — key stays server-side)
   ============================================ */
(function initRobotEvents() {
    const resultsBody = document.getElementById('live-results-body');
    if (!resultsBody) return;

    function showStatus(message) {
        resultsBody.innerHTML = `<tr><td colspan="4" class="results-status">${escapeHtml(message)}</td></tr>`;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    async function updateMatches() {
        let data;
        try {
            const response = await fetch('/api/matches');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            data = await response.json();
        } catch (error) {
            console.error('Match fetch error:', error);
            showStatus('Match results are unavailable right now.');
            return;
        }

        const matches = data.matches || [];
        if (matches.length === 0) {
            showStatus('No recent matches found.');
            return;
        }

        resultsBody.innerHTML = matches.map(match => {
            const scoreDisplay = match.score || 'Pending';
            const statusClass = match.score ? 'match-score' : 'match-status-live';

            return `
                <tr>
                    <td>${escapeHtml(match.name)}</td>
                    <td class="alliance-red">${escapeHtml(match.red_teams)}</td>
                    <td class="alliance-blue">${escapeHtml(match.blue_teams)}</td>
                    <td class="${statusClass}">${escapeHtml(scoreDisplay)}</td>
                </tr>
            `;
        }).join('');
    }

    updateMatches();
    setInterval(updateMatches, 300000);
})();

/* ============================================
   CUSTOM CHATBOT UI & LOGIC
   ============================================ */
(function initCustomChatbot() {
    const bubble = document.getElementById('chatbot-bubble');
    const windowEl = document.getElementById('chatbot-window');
    const closeBtn = document.getElementById('chatbot-close');
    const form = document.getElementById('chatbot-form');
    const input = document.getElementById('chatbot-input');
    const messagesContainer = document.getElementById('chatbot-messages');

    if (!bubble || !windowEl) return;

    let isTyping = false;

    // marked and DOMPurify only render bot replies, so they are fetched the
    // first time the chat opens instead of on every page. Same pinned
    // versions and SRI hashes as before; the CSP already allows both CDNs.
    const RENDERER_SCRIPTS = [
        ['https://cdn.jsdelivr.net/npm/marked@9.1.6/marked.min.js',
            'sha384-odPBjvtXVM/5hOYIr3A1dB+flh0c3wAT3bSesIOqEGmyUA4JoKf/YTWy0XKOYAY7'],
        ['https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.1.6/purify.min.js',
            'sha384-+VfUPEb0PdtChMwmBcBmykRMDd+v6D/oFmB3rZM/puCMDYcIvF968OimRh4KQY9a'],
    ];
    let rendererReady = null;

    function loadRenderer() {
        if (!rendererReady) {
            rendererReady = Promise.all(RENDERER_SCRIPTS.map(([src, integrity]) => new Promise(resolve => {
                const script = document.createElement('script');
                script.src = src;
                script.integrity = integrity;
                script.crossOrigin = 'anonymous';
                // A failed load resolves too: addMessage falls back to plain text.
                script.onload = script.onerror = () => resolve();
                document.head.appendChild(script);
            })));
        }
        return rendererReady;
    }

    // Toggle Window
    bubble.addEventListener('click', () => {
        windowEl.classList.toggle('active');
        if (windowEl.classList.contains('active')) {
            loadRenderer();
            input.focus();
        }
    });

    closeBtn.addEventListener('click', () => {
        windowEl.classList.remove('active');
    });

    // Helper: Add Message to UI
    function addMessage(text, sender) {
        const containerDiv = document.createElement('div');
        containerDiv.className = `chatbot-msg-container ${sender}`;

        const msgDiv = document.createElement('div');
        msgDiv.className = `chatbot-msg ${sender}`;

        // Parse markdown for the bot, sanitized against XSS before insertion
        // Model output is steerable by whoever types the prompt, so it is only
        // rendered as HTML when the sanitizer is actually present. If the
        // DOMPurify CDN failed to load, show plain text instead of raw HTML.
        if (sender === 'bot' && window.marked && window.DOMPurify) {
            msgDiv.innerHTML = DOMPurify.sanitize(marked.parse(text));
        } else {
            msgDiv.textContent = text;
        }

        containerDiv.appendChild(msgDiv);

        if (sender === 'bot') {
            const footerDiv = document.createElement('div');
            footerDiv.className = 'chatbot-bot-footer';
            footerDiv.innerHTML = '<i data-lucide="sparkles"></i> This conversation is handled by Steven.';
            containerDiv.appendChild(footerDiv);
        }

        messagesContainer.appendChild(containerDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        refreshLucideIcons();
    }

    // Helper: Add/Remove Typing Indicator
    function setTyping(typing) {
        isTyping = typing;
        if (typing) {
            const containerDiv = document.createElement('div');
            containerDiv.className = 'chatbot-msg-container bot chatbot-typing-container';
            containerDiv.id = 'chatbot-typing-indicator';

            const typingDiv = document.createElement('div');
            typingDiv.className = 'chatbot-msg bot chatbot-typing';
            typingDiv.textContent = 'Steven is thinking...';

            containerDiv.appendChild(typingDiv);

            messagesContainer.appendChild(containerDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        } else {
            const ind = document.getElementById('chatbot-typing-indicator');
            if (ind) ind.remove();
        }
    }

    // Handle Submit
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (isTyping) return;

        const text = input.value.trim();
        if (!text) return;

        // 1. Add User Message
        addMessage(text, 'user');
        input.value = '';

        // 2. Show Typing
        setTyping(true);

        // 3. Fetch from Backend
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: jsonHeaders(),
                body: JSON.stringify({ message: text })
            });

            const data = await response.json().catch(() => ({}));
            // Make sure the renderer has had its chance before the reply shows.
            await loadRenderer();
            setTyping(false);

            if (!response.ok) {
                addMessage(data.error || 'Sorry, I encountered an error connecting to the server.', 'bot');
                return;
            }

            if (data.reply) {
                addMessage(data.reply, 'bot');
            } else {
                addMessage('Sorry, I did not understand that.', 'bot');
            }

        } catch (error) {
            console.error('Chatbot Error:', error);
            setTyping(false);
            addMessage('Sorry, there was a network error.', 'bot');
        }
    });
})();
