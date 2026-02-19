// ============================================
// MEPHAM ROBOTICS - ENHANCED INTERACTIONS
// ============================================

// --- NAVIGATION TOGGLE ---
function toggleNav() {
    const nav = document.getElementById("mySidenav");
    const overlay = document.getElementById("overlay");
    const { body } = document;

    nav.classList.toggle("active");
    overlay.classList.toggle("active");

    // Prevent body scroll when nav is open
    if (nav.classList.contains("active")) {
        body.style.overflow = 'hidden';
    } else {
        body.style.overflow = '';
    }
}

// --- DROPDOWN TOGGLE ---
function toggleDropdown() {
    const dropdown = document.getElementById("teamDropdown");
    const btn = document.querySelector(".dropdown-btn");
    dropdown.classList.toggle("active");
    btn.classList.toggle("active");
}

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

    window.addEventListener('scroll', () => {
        const windowHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const scrolled = (window.pageYOffset / windowHeight) * 100;
        scrollProgress.style.width = scrolled + '%';
    });



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
    const timelineContainers = document.querySelectorAll('.timeline-container');

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

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

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
    const forms = document.querySelectorAll('form');
    const GOOGLE_FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLScTBQhmC_rGPbEAuEk63TNeFdMIRftG9CkULQqP3t2SBU6S8A/formResponse';

    // Google Form entry IDs provided by user
    const ENTRY_IDS = {
        name: 'entry.354100800',
        email: 'entry.640342432',
        message: 'entry.1090696951'
    };

    forms.forEach(form => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const submitBtn = this.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn ? submitBtn.textContent : 'Submit';

            // Basic validation
            const inputs = this.querySelectorAll('input, textarea, select');
            let isValid = true;

            inputs.forEach(input => {
                if (input.hasAttribute('required') && !input.value.trim()) {
                    isValid = false;
                    input.style.animation = 'shake 0.5s ease';
                    setTimeout(() => input.style.animation = '', 500);
                }
            });

            if (!isValid) {
                showToast('Please fill in all required fields', 'error');
                return;
            }

            // Prepare data for Google Form
            const formData = new FormData();

            // Handle different form types
            if (this.id === 'contact-form') {
                formData.append(ENTRY_IDS.name, this.querySelector('[name="name"]')?.value || this.querySelector('[name*="354100800"]')?.value);
                formData.append(ENTRY_IDS.email, this.querySelector('[name="email"]')?.value || this.querySelector('[name*="640342432"]')?.value);
                formData.append(ENTRY_IDS.message, this.querySelector('[name="message"]')?.value || this.querySelector('[name*="1090696951"]')?.value);
            } else if (this.id === 'sponsorForm') {
                const company = this.querySelector('[name="company"]')?.value || '';
                const email = this.querySelector('[name="email"]')?.value || '';
                const level = this.querySelector('select')?.value || '';
                const message = this.querySelector('textarea')?.value || '';

                formData.append(ENTRY_IDS.name, company);
                formData.append(ENTRY_IDS.email, email);
                formData.append(ENTRY_IDS.message, `Sponsorship Level: ${level}\n\nMessage: ${message}`);
            } else if (this.classList.contains('footer-newsletter-form')) {
                const email = this.querySelector('input[type="email"]')?.value || '';
                formData.append(ENTRY_IDS.name, 'Newsletter Subscriber');
                formData.append(ENTRY_IDS.email, email);
                formData.append(ENTRY_IDS.message, 'Newsletter Subscription Request from Footer');
            } else if (this.id === 'loginForm') {
                // Keep login logic separate or handle elsewhere if needed
                // For now, let's just let it pass or handle explicitly
                return;
            }

            // Submission logic
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Transmitting...';
            }

            fetch(GOOGLE_FORM_URL, {
                method: 'POST',
                body: new URLSearchParams(formData),
                mode: 'no-cors',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            }).then(() => {
                showToast('Success! Data transmitted.', 'success');
                this.reset();

                // Show inline success if it exists (for Contact page legacy support)
                const successMsg = document.getElementById('form-success');
                if (successMsg) {
                    successMsg.style.display = 'block';
                    setTimeout(() => { successMsg.style.display = 'none'; }, 6000);
                }
            }).catch((err) => {
                console.error('Submission error:', err);
                showToast('Transmission failed. Please try again.', 'error');

                const errorMsg = document.getElementById('form-error');
                if (errorMsg) {
                    errorMsg.style.display = 'block';
                    setTimeout(() => { errorMsg.style.display = 'none'; }, 6000);
                }
            }).finally(() => {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalBtnText;
                }
            });
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



// --- IMAGE LAZY LOADING WITH FADE ---
(function initLazyLoad() {
    const images = document.querySelectorAll('img[data-src]');

    if (images.length === 0) return;

    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.style.opacity = '0';
                img.onload = () => {
                    img.style.transition = 'opacity 0.5s ease';
                    img.style.opacity = '1';
                };
                imageObserver.unobserve(img);
            }
        });
    });

    images.forEach(img => imageObserver.observe(img));
})();

// --- ACTIVE NAV HIGHLIGHTING ---
(function initActiveNav() {
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    const navLinks = document.querySelectorAll('.sidenav a');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPage) {
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
                }
            });
            // Toggle current item
            item.classList.toggle('active');
        });
    });
})();

// --- FILTER TABS ---
(function initFilterTabs() {
    const tabs = document.querySelectorAll('.filter-tab');
    const filterItems = document.querySelectorAll('[data-season]');

    if (tabs.length === 0) return;

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Update active tab
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const filter = tab.dataset.filter;

            // Filter items
            filterItems.forEach(item => {
                if (filter === 'all' || item.dataset.season === filter) {
                    item.style.display = '';
                    item.style.animation = 'fadeIn 0.5s ease';
                } else {
                    item.style.display = 'none';
                }
            });
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

    // Set the date we're counting down to (Example: March 15, 2026)
    const countDownDate = new Date("Feb 22, 2026 07:30:00").getTime();

    const updateTimer = setInterval(function () {
        const now = new Date().getTime();
        const distance = countDownDate - now;

        // Time calculations
        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((distance % (1000 * 60)) / 1000);

        // Display results with leading zeros
        daysEl.innerHTML = days < 10 ? '0' + days : days;
        hoursEl.innerHTML = hours < 10 ? '0' + hours : hours;
        minutesEl.innerHTML = minutes < 10 ? '0' + minutes : minutes;
        secondsEl.innerHTML = seconds < 10 ? '0' + seconds : seconds;

        // If the count down is finished, write some text
        if (distance < 0) {
            clearInterval(updateTimer);
            document.querySelector(".countdown-container").innerHTML = "<h3 style='color:var(--accent-gold)'>COMPETITION DAY!</h3>";
        }
    }, 1000);
})();
// --- PORTAL & AUTH LOGIC ---
(function initAuth() {
    function updateNav() {
        const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';
        const sidenav = document.getElementById('mySidenav');
        if (!sidenav) return;

        // Manage dynamic logout link
        let logoutLink = document.getElementById('dynamic-logout');
        if (isLoggedIn && !logoutLink) {
            const user = localStorage.getItem('user') || 'User';
            logoutLink = document.createElement('a');
            logoutLink.id = 'dynamic-logout';
            logoutLink.href = '#';
            logoutLink.className = 'logout-link';
            logoutLink.innerHTML = `Logout (${user})`;
            logoutLink.onclick = function (e) {
                e.preventDefault();
                localStorage.removeItem('isLoggedIn');
                localStorage.removeItem('user');
                showToast('System Disconnected', 'info');
                setTimeout(() => window.location.href = 'index.html', 800);
            };
            sidenav.appendChild(logoutLink);
        } else if (!isLoggedIn && logoutLink) {
            logoutLink.remove();
        }

        // Update username display on resources page
        const nameDisplay = document.getElementById('userNameDisplay');
        if (nameDisplay && isLoggedIn) {
            nameDisplay.textContent = localStorage.getItem('user').toUpperCase();
        }
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateNav);
    } else {
        updateNav();
    }

    // Export global logout for direct HTML calls
    window.logout = function () {
        localStorage.removeItem('isLoggedIn');
        localStorage.removeItem('user');
        window.location.href = 'login.html';
    };
})();

/* ============================================
   SITE SEARCH
   ============================================ */
(function initSearch() {
    const pages = [
        { title: 'Home', url: 'index.html', desc: 'Welcome to Mepham Robotics — VEX V5 team homepage, timeline, and stats', keywords: 'home robotics vex v5 team homepage mepham' },
        { title: 'About Us', url: 'about.html', desc: 'Our mission, values, history, and team culture', keywords: 'about mission values history team culture sub-teams diversity' },

        { title: 'Achievements', url: 'achievements.html', desc: 'Awards, competition results, and season highlights', keywords: 'awards achievements competitions results trophies seasons' },
        { title: 'Donate', url: 'donate.html', desc: 'Support our team through sponsorship and donations', keywords: 'donate sponsor support fundraising givebutter tiers' },
        { title: 'Contact', url: 'contact.html', desc: 'Get in touch — contact form, meeting schedule, and FAQ', keywords: 'contact email form meeting schedule faq questions' },
        { title: 'Resources', url: 'resources.html', desc: 'Team resources — programming, mechanics, strategy docs', keywords: 'resources programming mechanics strategy documentation login' },
        { title: '77628D Team', url: '77628D.html', desc: 'Team 77628D robot details and competition info', keywords: '77628D robot team' },
        { title: '77628P Team', url: '77628P.html', desc: 'Team 77628P robot details and competition info', keywords: '77628P robot team' },
        { title: 'Glossary', url: 'glossary.html', desc: 'Robotics terms and definitions from A to Z', keywords: 'glossary terms definitions dictionary pid autonomous drivetrain' },
        { title: 'Branding Guide', url: 'branding.html', desc: 'Official team colors, fonts, and logo usage', keywords: 'branding colors fonts logo maroon gold style guide' },
        { title: 'Design Standards', url: 'standards.html', desc: 'Build standards, code style, and naming conventions', keywords: 'standards design build code style naming conventions' },
        { title: 'Safety Quiz', url: 'safety-quiz.html', desc: 'Interactive safety quiz — test your workshop knowledge', keywords: 'safety quiz test workshop lab rules ppe' },
        { title: 'Engineering Notebook', url: 'notebook.html', desc: 'Public engineering notebook — design process and logs', keywords: 'notebook engineering design process testing iteration' },
        { title: 'Privacy Policy', url: 'privacy.html', desc: 'How we handle your data and privacy', keywords: 'privacy policy data cookies' },
        { title: 'Site Credits', url: 'credits.html', desc: 'Website credits and acknowledgments', keywords: 'credits site acknowledgments technologies' },
        { title: 'Custom 404', url: '404.html', desc: 'Page not found', keywords: '404 error lost' },
    ];

    function doSearch(query) {
        if (!query || query.length < 2) return [];
        const q = query.toLowerCase();
        return pages.filter(p =>
            p.title.toLowerCase().includes(q) ||
            p.desc.toLowerCase().includes(q) ||
            p.keywords.toLowerCase().includes(q)
        );
    }

    document.addEventListener('click', function (e) {
        if (e.target.closest('.nav-search-btn')) {
            e.preventDefault();
            openSearch();
        }
        if (e.target.closest('.search-close')) {
            closeSearch();
        }
    });

    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            openSearch();
        }
        if (e.key === 'Escape') {
            closeSearch();
        }
    });

    function openSearch() {
        const overlay = document.querySelector('.search-overlay');
        if (!overlay) return;
        overlay.classList.add('active');
        const input = overlay.querySelector('input');
        if (input) { input.value = ''; input.focus(); }
        const results = overlay.querySelector('.search-results');
        if (results) results.innerHTML = '';
        // close sidenav if open
        const nav = document.querySelector('.sidenav');
        const ov = document.querySelector('.nav-overlay');
        if (nav) nav.classList.remove('active');
        if (ov) ov.classList.remove('active');
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
            resultsEl.innerHTML = '<div class="search-no-results">No results found.</div>';
            return;
        }
        resultsEl.innerHTML = hits.map(h =>
            `<a href="${h.url}" class="search-result-item">
                <div class="result-title">${h.title}</div>
                <div class="result-desc">${h.desc}</div>
            </a>`
        ).join('');
    });

    // Click outside to close
    document.addEventListener('click', function (e) {
        const overlay = document.querySelector('.search-overlay');
        if (overlay && e.target === overlay) closeSearch();
    });
})();


/* ============================================
   NEWSLETTER FORM HANDLER
   ============================================ */
(function initNewsletter() {
    document.addEventListener('submit', function (e) {
        const form = e.target.closest('.footer-newsletter-form');
        if (!form) return;
        e.preventDefault();
        const email = form.querySelector('input[type="email"]');
        if (email && email.value) {
            if (typeof showToast === 'function') {
                showToast('Thanks for subscribing! 🎉', 'success');
            } else {
                alert('Thanks for subscribing!');
            }
            email.value = '';
        }
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
            <div class="quiz-progress"><div class="quiz-progress-fill" style="width:${progress}%"></div></div>
            <div class="quiz-question-card">
                <div class="quiz-question-num">Question ${current + 1} of ${questions.length}</div>
                <div class="quiz-question-text">${cq.q}</div>
                <div class="quiz-options">
                    ${cq.opts.map((o, i) => `<button class="quiz-option ${answers[current] === i ? 'selected' : ''}" data-idx="${i}">${o}</button>`).join('')}
                </div>
            </div>
            <div class="quiz-nav">
                <button class="quiz-btn" onclick="quizPrev()" ${current === 0 ? 'disabled' : ''}>← Back</button>
                <button class="quiz-btn quiz-btn-primary" onclick="quizNext()" ${answers[current] === -1 ? 'disabled' : ''}>
                    ${current === questions.length - 1 ? 'Finish' : 'Next →'}
                </button>
            </div>
        `;
    }

    container.addEventListener('click', function (e) {
        const opt = e.target.closest('.quiz-option');
        if (!opt) return;
        answers[current] = parseInt(opt.dataset.idx);
        render();
    });

    window.quizNext = function () {
        if (answers[current] === -1) return;
        current++;
        render();
    };

    window.quizPrev = function () {
        if (current > 0) { current--; render(); }
    };

    function showResults() {
        let score = 0;
        questions.forEach((q, i) => { if (answers[i] === q.a) score++; });
        const pct = Math.round((score / questions.length) * 100);
        const pass = pct >= 70;
        container.innerHTML = `
            <div class="quiz-results">
                <div class="quiz-score-circle ${pass ? 'pass' : 'fail'}">${pct}%</div>
                <h2 style="margin-bottom:1rem">${pass ? '🎉 You Passed!' : '❌ Not Quite'}</h2>
                <p style="color:#666;margin-bottom:2rem">You got ${score} out of ${questions.length} correct.
                ${pass ? 'Great job — you know your workshop safety!' : 'Review the safety guidelines and try again.'}</p>
                <button class="quiz-btn quiz-btn-primary" onclick="location.reload()">Try Again</button>
            </div>
        `;
    }

    // Initial render on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
})();
