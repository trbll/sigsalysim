/**
 * v3 Vinyl Record Interaction
 * ============================
 * Makes the receiver's vinyl record draggable to simulate clock
 * desynchronization. Dragging rotates the record and maps the
 * rotation to a frame offset, switching between pre-computed
 * desync audio variants.
 */

const VinylInteraction = (() => {
    let isDragging = false;
    let startAngle = 0;
    let currentOffset = 0;
    let recordEl = null;
    let displayEl = null;

    // Available pre-computed offsets (must match pipeline_v3.py)
    const AVAILABLE_OFFSETS = [0, 1, 2, 5, 10, 25, 50];

    function init() {
        recordEl = document.getElementById('receiver-record');
        displayEl = document.getElementById('desync-display');
        const resetBtn = document.getElementById('desync-reset');

        if (!recordEl) return;

        recordEl.addEventListener('mousedown', onMouseDown);
        recordEl.addEventListener('touchstart', onTouchStart, { passive: false });
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onMouseUp);

        if (resetBtn) {
            resetBtn.addEventListener('click', () => setOffset(0));
        }
    }

    function onMouseDown(e) {
        isDragging = true;
        startAngle = getAngle(e);
        recordEl.classList.remove('spinning');
        e.preventDefault();
    }

    function onTouchStart(e) {
        if (e.touches.length === 1) {
            isDragging = true;
            startAngle = getAngle(e.touches[0]);
            recordEl.classList.remove('spinning');
            e.preventDefault();
        }
    }

    function onMouseMove(e) {
        if (!isDragging) return;
        const angle = getAngle(e);
        const delta = angle - startAngle;
        startAngle = angle;

        // Map rotation to offset: ~7.2 degrees per frame
        // Full rotation (360°) = 50 frames
        currentOffset = Math.max(0, Math.min(50, currentOffset + delta / 7.2));
        updateDisplay();
    }

    function onTouchMove(e) {
        if (!isDragging || e.touches.length !== 1) return;
        onMouseMove(e.touches[0]);
        e.preventDefault();
    }

    function onMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        // Snap to nearest available offset
        const snapped = snapToNearest(Math.round(currentOffset));
        setOffset(snapped);
    }

    function getAngle(e) {
        const rect = recordEl.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        return Math.atan2(e.clientY - cy, e.clientX - cx) * (180 / Math.PI);
    }

    function snapToNearest(value) {
        let closest = AVAILABLE_OFFSETS[0];
        let minDist = Math.abs(value - closest);
        for (const o of AVAILABLE_OFFSETS) {
            const dist = Math.abs(value - o);
            if (dist < minDist) {
                closest = o;
                minDist = dist;
            }
        }
        return closest;
    }

    function setOffset(offset) {
        currentOffset = offset;
        updateDisplay();

        // Record always spins — at offset it spins from a rotated start position
        // using CSS animation-delay to visually offset it from the sender record
        if (recordEl) {
            recordEl.classList.add('spinning');
            // Use negative animation-delay to offset the phase of the spin
            // This makes the record visually "ahead" or "behind" the sender
            recordEl.style.animationDelay = `${-offset * 0.04}s`;
        }

        // If currently playing decrypt audio, switch to new offset
        if (AudioEngine.isPlaying && AudioEngine.currentVariant &&
            AudioEngine.currentVariant.startsWith('sigsaly_decrypted_')) {
            AudioEngine.play(`sigsaly_decrypted_${offset}`,
                offset === 0 ? 'Decrypted (perfect sync)' : `Decrypted (${offset} frame offset — DESYNC)`);
        }

        // Dispatch custom event for other components
        document.dispatchEvent(new CustomEvent('desync-change', { detail: { offset } }));
    }

    function updateDisplay() {
        if (displayEl) {
            const rounded = Math.round(currentOffset);
            displayEl.textContent = rounded;
        }
    }

    function getOffset() {
        return snapToNearest(Math.round(currentOffset));
    }

    return { init, setOffset, getOffset };
})();
