// Site editor (/admin/site): every setting saves itself.
//
// Each .setting-row carries data-key ("section.field") and data-kind. Single
// values save on change (text on blur or Enter); lists save the whole list a
// moment after the last edit; images upload as soon as they are picked, then
// save like any other value. The server validates everything and answers with
// the stored value and whether it now differs from the original.

(function () {
    const root = document.getElementById('siteEditor');
    if (!root) return;

    const status = document.getElementById('saveStatus');
    const listTimers = new Map();
    let inFlight = 0;
    let failed = false;

    // --- Status and toasts ----------------------------------------------------------

    function setStatus() {
        if (inFlight > 0) {
            status.textContent = 'Saving…';
            status.dataset.state = 'saving';
        } else if (failed) {
            status.textContent = 'Some changes did not save';
            status.dataset.state = 'error';
        } else {
            status.textContent = 'All changes saved';
            status.dataset.state = 'saved';
        }
    }

    function toast(message, category = 'info') {
        const stack = document.getElementById('toast-stack');
        const node = document.createElement('div');
        node.className = `status-msg ${category}`;
        const text = document.createElement('span');
        text.textContent = message;
        node.append(text);
        stack.append(node);
        setTimeout(() => {
            node.classList.add('is-leaving');
            node.addEventListener('animationend', () => node.remove(), { once: true });
        }, category === 'error' ? 8000 : 4000);
    }

    function mark(node, state) {
        node.classList.remove('is-saving', 'is-saved', 'is-error');
        if (state) node.classList.add(`is-${state}`);
    }

    async function send(url, options) {
        let response;
        try {
            response = await fetch(url, Object.assign({ credentials: 'same-origin' }, options));
        } catch (err) {
            throw new Error('Could not reach the server. Check your connection.');
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `Save failed (${response.status}).`);
        return data;
    }

    const post = (url, body) => send(url, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(body) });

    function track(node, promise) {
        inFlight++;
        failed = false;
        mark(node, 'saving');
        setStatus();
        return promise
            .then(data => {
                mark(node, 'saved');
                return data;
            })
            .catch(err => {
                failed = true;
                mark(node, 'error');
                toast(err.message, 'error');
                throw err;
            })
            .finally(() => {
                inFlight--;
                setStatus();
            });
    }

    // --- Reading a row's value --------------------------------------------------------

    function scalarValue(row) {
        const kind = row.dataset.kind;
        if (kind === 'days') {
            return Array.from(row.querySelectorAll('[data-day]:checked')).map(box => Number(box.value));
        }
        if (kind === 'image') {
            return JSON.parse(row.querySelector('.site-image').dataset.image || 'null');
        }
        const radio = row.querySelector('input[type="radio"][data-value]:checked');
        if (radio) return radio.value;
        const input = row.querySelector('[data-value]');
        if (!input) return null;
        return input.type === 'checkbox' ? input.checked : input.value;
    }

    function itemValue(control) {
        if (control.classList.contains('site-image')) return JSON.parse(control.dataset.image || 'null');
        if (control.type === 'checkbox') return control.checked;
        return control.value;
    }

    function listValue(row) {
        return Array.from(row.querySelectorAll('[data-row]')).map(item => {
            const out = {};
            item.querySelectorAll('[data-item]').forEach(control => {
                out[control.dataset.item] = itemValue(control);
            });
            return out;
        });
    }

    function afterSave(row, data) {
        row.querySelector('.custom-chip').hidden = !data.custom;
        row.querySelector('.reset-btn').hidden = !data.custom;
        row.dataset.saved = JSON.stringify(data.value);
    }

    // The element that shows the saving/saved/error state for a row.
    function target(row) {
        return row.querySelector('.segmented, .day-picker, .list-editor, .site-image, .switch, [data-value]') || row;
    }

    function save(row) {
        // A photo still uploading has no stored image yet; its upload saves the list when done.
        if (row.dataset.kind === 'list' && row.querySelector('.site-image.is-saving')) return;
        const value = row.dataset.kind === 'list' ? listValue(row) : scalarValue(row);
        if (JSON.stringify(value) === row.dataset.saved) return;
        track(target(row), post('/admin/api/site', { key: row.dataset.key, value }))
            .then(data => afterSave(row, data))
            .catch(() => {});
    }

    function scheduleList(row, delay = 900) {
        clearTimeout(listTimers.get(row));
        listTimers.set(row, setTimeout(() => {
            listTimers.delete(row);
            save(row);
        }, delay));
    }

    // Remember what the page loaded with, so unchanged fields are never re-sent.
    root.querySelectorAll('.setting-row').forEach(row => {
        row.dataset.saved = JSON.stringify(row.dataset.kind === 'list' ? listValue(row) : scalarValue(row));
    });

    // --- Editing ----------------------------------------------------------------------

    root.addEventListener('change', e => {
        const row = e.target.closest('.setting-row');
        if (!row || e.target.matches('[data-image-input]')) return;
        if (e.target.matches('[data-icon-select]')) {
            const preview = e.target.parentElement.querySelector('.icon-preview');
            if (preview) {
                const fresh = document.createElement('i');
                fresh.className = 'icon-preview';
                fresh.setAttribute('data-lucide', e.target.value);
                fresh.setAttribute('aria-hidden', 'true');
                preview.replaceWith(fresh);
                refreshLucideIcons();
            }
        }
        if (e.target.type === 'checkbox' && e.target.closest('.switch')) {
            const text = e.target.closest('.switch').querySelector('[data-switch-text]');
            if (text) text.textContent = e.target.checked ? 'On' : 'Off';
        }
        if (row.dataset.kind === 'list') scheduleList(row, 300);
        else save(row);
    });

    root.addEventListener('input', e => {
        if (e.target.type === 'file') return;
        const counter = e.target.closest('.text-with-count')?.querySelector('.char-count');
        if (counter) counter.textContent = `${e.target.value.length} / ${e.target.maxLength}`;
        const row = e.target.closest('.setting-row');
        if (row?.dataset.kind === 'list') scheduleList(row);
        const clear = row?.querySelector('[data-action="clear-value"]');
        if (clear) clear.hidden = !e.target.value;
    });

    root.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || !e.target.matches('input[type="text"], input[type="url"], input[type="email"]')) return;
        e.preventDefault();
        e.target.blur();
    });

    // --- Lists: add, remove, reorder --------------------------------------------------

    function refreshListButtons(row) {
        const list = row.querySelector('[data-list]');
        const rows = Array.from(list.querySelectorAll('[data-row]'));
        rows.forEach((item, i) => {
            item.querySelector('[data-action="row-up"]').disabled = i === 0;
            item.querySelector('[data-action="row-down"]').disabled = i === rows.length - 1;
        });
        row.querySelector('[data-action="row-add"]').disabled = rows.length >= Number(list.dataset.max);
    }

    function addRow(row) {
        const item = row.querySelector('[data-row-template]').content.firstElementChild.cloneNode(true);
        row.querySelector('[data-list]').append(item);
        refreshLucideIcons();
        refreshListButtons(row);
        return item;
    }

    root.addEventListener('click', e => {
        const button = e.target.closest('[data-action]');
        if (!button) return;
        const row = button.closest('.setting-row');
        const action = button.dataset.action;

        if (action === 'row-add') {
            addRow(row).querySelector('input:not([type="file"]), textarea, select')?.focus();
            // Saved once something is typed; an empty new row would fail validation.
        } else if (action === 'row-remove') {
            button.closest('[data-row]').remove();
            refreshListButtons(row);
            scheduleList(row, 100);
        } else if (action === 'row-up' || action === 'row-down') {
            const item = button.closest('[data-row]');
            const sibling = action === 'row-up' ? item.previousElementSibling : item.nextElementSibling;
            if (!sibling) return;
            if (action === 'row-up') sibling.before(item);
            else sibling.after(item);
            refreshListButtons(row);
            button.focus();
            scheduleList(row, 300);
        } else if (action === 'reset') {
            track(target(row), post('/admin/api/site/reset', { key: row.dataset.key }))
                .then(data => {
                    const kind = row.dataset.kind;
                    // Lists and images are simplest to redraw from the server.
                    if (kind === 'list' || kind === 'image' || kind === 'days') {
                        location.hash = row.closest('.settings-section').id;
                        location.reload();
                        return;
                    }
                    const radio = row.querySelector(`input[type="radio"][value="${CSS.escape(String(data.value))}"]`);
                    if (radio) radio.checked = true;
                    const input = row.querySelector('[data-value]:not([type="radio"])');
                    if (input && input.type === 'checkbox') input.checked = Boolean(data.value);
                    else if (input) input.value = data.value ?? '';
                    afterSave(row, data);
                    toast('Put back to the original.', 'success');
                })
                .catch(() => {});
        } else if (action === 'clear-value') {
            row.querySelector('[data-value]').value = '';
            button.hidden = true;
            save(row);
        } else if (action === 'clear-image') {
            setImage(row.querySelector('.site-image'), null);
            save(row);
        }
    });

    // --- Images ---------------------------------------------------------------------------

    // Big photos are shrunk in the browser before upload: production has no image
    // library, and phone photos are often 4000px wide.
    const MAX_SIDE = 2000;

    function loadImage(file) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error('That file could not be read as an image.'));
            img.src = URL.createObjectURL(file);
        });
    }

    async function prepare(file) {
        const img = await loadImage(file);
        let { naturalWidth: width, naturalHeight: height } = img;
        const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
        if (scale === 1 && file.size < 1.5 * 1024 * 1024) return { blob: file, name: file.name, width, height };
        width = Math.round(width * scale);
        height = Math.round(height * scale);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        canvas.getContext('2d').drawImage(img, 0, 0, width, height);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/webp', 0.85));
        if (!blob || blob.type !== 'image/webp') {
            const jpeg = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
            return { blob: jpeg, name: 'photo.jpg', width, height };
        }
        return { blob, name: 'photo.webp', width, height };
    }

    function setImage(holder, image, localUrl) {
        const preview = holder.querySelector('.site-image-preview');
        const label = holder.querySelector('[data-image-label]');
        if (image || localUrl) {
            preview.src = localUrl || image.src;
            preview.hidden = false;
            label.textContent = 'Replace';
        } else {
            preview.hidden = true;
            preview.removeAttribute('src');
            label.textContent = 'Drop a photo or browse';
        }
        holder.dataset.image = JSON.stringify(image || null);
        const clear = holder.querySelector('[data-action="clear-image"]');
        if (clear) clear.hidden = !image;
    }

    async function upload(holder, file) {
        if (!file) return;
        const row = holder.closest('.setting-row');
        let prepared;
        try {
            prepared = await prepare(file);
        } catch (err) {
            toast(err.message, 'error');
            return;
        }
        const form = new FormData();
        form.append('file', prepared.blob, prepared.name);
        form.append('width', String(prepared.width));
        form.append('height', String(prepared.height));
        setImage(holder, null, URL.createObjectURL(prepared.blob));
        track(holder, send('/admin/api/site/image', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken() }, body: form }))
            .then(data => {
                setImage(holder, data.image);
                holder.closest('[data-row]')?.removeAttribute('data-fresh');
                if (row.dataset.kind === 'list') scheduleList(row, 100);
                else save(row);
            })
            .catch(() => {
                // A photo added by dropping several at once goes again if it could not be stored.
                const item = holder.closest('[data-row][data-fresh]');
                if (!item) {
                    setImage(holder, null);
                    return;
                }
                item.remove();
                refreshListButtons(row);
                scheduleList(row, 100);
            });
    }

    // Dropped and pasted files arrive as a change on the input too (controls.js puts them there).
    root.addEventListener('change', e => {
        if (e.target.matches('[data-image-input]')) upload(e.target.closest('.site-image'), e.target.files[0]);
    });

    // A description from the file name ("robot-at-worlds.jpg" is "Robot at worlds"). Camera
    // names like IMG_2041 say nothing, so those get a plain one to change.
    function describeFile(file) {
        const words = file.name.replace(/\.[^.]+$/, '').replace(/[_\-.]+/g, ' ').replace(/\s+/g, ' ').trim();
        const meaningful = words.replace(/\b(img|dsc|dscn|pxl|mvimg|photo|image|screenshot|screen shot|whatsapp image)\b/gi, '')
            .replace(/[\d\s]+/g, '');
        if (meaningful.length < 3) return 'Team photo';
        return (words.charAt(0).toUpperCase() + words.slice(1)).slice(0, 150);
    }

    // Photos dropped on a photo list, rather than on one of its photos, become new entries.
    root.addEventListener('ctl:files', e => {
        const row = e.target;
        if (!row.matches('.setting-row[data-kind="list"]')) return;
        e.preventDefault();
        const list = row.querySelector('[data-list]');
        const max = Number(list.dataset.max);
        const room = Math.max(0, max - list.querySelectorAll('[data-row]').length);
        const files = e.detail.files.slice(0, room);
        if (!files.length) {
            toast(`This list is full (${max} photos). Remove one to make room.`, 'error');
            return;
        }
        const added = files.map(file => {
            const item = addRow(row);
            item.dataset.fresh = '';
            const alt = item.querySelector('[data-item="alt"]');
            if (alt) alt.value = describeFile(file);
            upload(item.querySelector('.site-image'), file);
            return item;
        });
        added[0].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        const left = e.detail.files.length - files.length;
        toast(`Adding ${files.length} photo${files.length === 1 ? '' : 's'}. Check each description.`
            + (left ? ` ${left} did not fit: the most is ${max}.` : ''), left ? 'error' : 'success');
    });

    // --- Section nav --------------------------------------------------------------------

    const navLinks = Array.from(root.querySelectorAll('.settings-nav a'));
    if ('IntersectionObserver' in window && navLinks.length) {
        const observer = new IntersectionObserver(entries => {
            entries.filter(entry => entry.isIntersecting).forEach(entry => {
                navLinks.forEach(link => {
                    const current = link.getAttribute('href') === `#${entry.target.id}`;
                    link.classList.toggle('is-current', current);
                    if (current) link.setAttribute('aria-current', 'true');
                    else link.removeAttribute('aria-current');
                });
            });
        }, { rootMargin: '-15% 0px -75% 0px' });
        root.querySelectorAll('.settings-section').forEach(section => observer.observe(section));
    }

    root.querySelectorAll('.setting-row[data-kind="list"]').forEach(refreshListButtons);

    window.addEventListener('beforeunload', e => {
        if (inFlight > 0 || listTimers.size > 0) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    setStatus();
})();
