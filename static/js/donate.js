// Donate page: a level's "Sponsor at this level" link preselects that level in
// the inquiry form below. The link's own #sponsor jump does the scrolling.
document.addEventListener('click', e => {
    const pick = e.target.closest('[data-tier]');
    if (!pick) return;
    const select = document.getElementById('sponsor-level');
    if (!select) return;
    const option = Array.from(select.options).find(o => o.value === pick.dataset.tier);
    if (!option) return;
    select.value = option.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
});
