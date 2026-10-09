// Account page: draw the two-step setup QR code and copy backup codes.

(function drawSetupQr() {
    const box = document.querySelector('[data-qr]');
    if (!box || typeof qrcode !== 'function') return;
    const qr = qrcode(0, 'M');
    qr.addData(box.dataset.qr);
    qr.make();
    // The library builds the SVG from the otpauth link alone, so it is safe to insert.
    box.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
})();

document.querySelectorAll('[data-copy-codes]').forEach(button => {
    button.addEventListener('click', async () => {
        const label = button.querySelector('span');
        try {
            await navigator.clipboard.writeText(button.dataset.copyCodes);
            label.textContent = 'Copied';
        } catch (err) {
            label.textContent = 'Select and copy them above';
        }
    });
});
