// Team editor: the page layout picker as a 3D ring of layout wireframes
// (circular-carousel.js). The radio buttons stay the source of truth, so the
// autosave in team-editor.js works unchanged; without JavaScript the plain
// grid of radio cards shows instead.
(function () {
    const picker = document.querySelector('.layout-picker[data-carousel]');
    if (!picker || !window.CircularCarousel || !('ResizeObserver' in window) || !('IntersectionObserver' in window)) return;

    const options = Array.from(picker.querySelectorAll('.layout-option'));
    const radios = options.map(option => option.querySelector('input[type="radio"]'));
    const nameOf = option => option.querySelector('.layout-option-name').textContent.trim();
    const items = options.map(option => {
        const note = option.querySelector('.layout-option-note');
        return {
            node: option.querySelector('.layout-thumb'),
            title: nameOf(option),
            subtitle: note ? note.textContent.trim() : '',
            alt: `${nameOf(option)} layout`
        };
    });

    const host = document.createElement('div');
    host.className = 'layout-carousel';
    const status = document.createElement('p');
    status.className = 'layout-carousel-status';
    status.setAttribute('aria-live', 'polite');
    picker.insertBefore(status, picker.firstChild);
    picker.insertBefore(host, status);
    picker.classList.add('has-carousel');

    const checkedIndex = () => radios.findIndex(radio => radio.checked);

    const ring = window.CircularCarousel.create(host, items, {
        preset: 'cylinder',
        intro: 'rise',
        cardWidth: 170,
        aspectRatio: 5 / 6,
        gap: 28,
        speed: 10,
        cornerRadius: 8,
        captions: true,
        start: Math.max(0, checkedIndex()),
        label: 'Page layouts',
        onItemClick: (item, index) => choose(index)
    });

    // Outline the layout in use on every card face, and say which it is.
    function mark() {
        const index = checkedIndex();
        host.querySelectorAll('.circular-carousel__card').forEach(card => {
            card.toggleAttribute('data-selected', Number(card.dataset.ccIndex) === index);
        });
        status.textContent = '';
        if (index >= 0) {
            const current = document.createElement('strong');
            current.textContent = nameOf(options[index]);
            status.append('In use: ', current, ' · Click a card, or press Enter on the one in front, to switch.');
        }
    }

    function choose(index) {
        const radio = radios[index];
        if (!radio.checked) {
            radio.checked = true;
            radio.dispatchEvent(new Event('change', { bubbles: true }));
        }
        // Once someone has picked, the ring rests on their choice instead of drifting on.
        ring.setAutoplay('off');
        ring.focus(index);
        mark();
    }

    // Someone choosing by keyboard needs the front card to hold still until they press Enter.
    host.addEventListener('focus', () => ring.setAutoplay('off'));

    // team-editor.js flags the picker saved or failed; a failed save also puts
    // the old radio back, so re-read the selection whenever that flag changes.
    new MutationObserver(mark).observe(picker, { attributes: true, attributeFilter: ['class'] });
    mark();
})();
