/**
 * v3 Vinyl Record Interaction
 * ============================
 * Drag receiver record to simulate desync.
 * Simple model: mousedown stops audio, mouseup calculates offset and restarts.
 */

const VinylInteraction = (() => {
    let isDragging = false;
    let startAngle = 0;
    let currentOffset = 0;
    let recordEl = null;
    let displayEl = null;

    const AVAILABLE_OFFSETS = [0, 1, 2, 5, 10, 25, 50];

    function init() {
        recordEl = document.getElementById('receiver-record');
        displayEl = document.getElementById('desync-display');
        const resetBtn = document.getElementById('desync-reset');

        if (!recordEl) return;

        recordEl.addEventListener('mousedown', onDown);
        recordEl.addEventListener('touchstart', onTouchDown, { passive: false });
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onUp);

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                // Stop, reset, restart
                AudioEngine.stop();
                currentOffset = 0;
                updateVisual();
                updateDisplay();
                // Dispatch so v3.js restarts audio at offset 0
                dispatch(0);
            });
        }
    }

    function onDown(e) {
        isDragging = true;
        startAngle = getAngle(e);
        // Stop audio immediately on grab
        AudioEngine.stop();
        recordEl.classList.remove('spinning');
        e.preventDefault();
    }

    function onTouchDown(e) {
        if (e.touches.length === 1) {
            isDragging = true;
            startAngle = getAngle(e.touches[0]);
            AudioEngine.stop();
            recordEl.classList.remove('spinning');
            e.preventDefault();
        }
    }

    function onMove(e) {
        if (!isDragging) return;
        const angle = getAngle(e);
        const delta = angle - startAngle;
        startAngle = angle;
        currentOffset = Math.max(0, Math.min(50, currentOffset + delta / 7.2));
        updateDisplay();
        // Show rotation while dragging
        if (recordEl) {
            recordEl.style.transform = `rotate(${currentOffset * 7.2}deg)`;
        }
    }

    function onTouchMove(e) {
        if (!isDragging || e.touches.length !== 1) return;
        onMove(e.touches[0]);
        e.preventDefault();
    }

    function onUp() {
        if (!isDragging) return;
        isDragging = false;

        // Snap to nearest available offset
        const snapped = snapToNearest(Math.round(currentOffset));
        currentOffset = snapped;
        updateDisplay();
        updateVisual();

        // Dispatch event — v3.js will start playback at new offset
        dispatch(snapped);
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
            if (Math.abs(value - o) < minDist) {
                closest = o;
                minDist = Math.abs(value - o);
            }
        }
        return closest;
    }

    function updateVisual() {
        if (!recordEl) return;
        recordEl.classList.add('spinning');
        recordEl.style.transform = '';
        recordEl.style.animationDelay = `${-currentOffset * 0.04}s`;
    }

    function updateDisplay() {
        if (displayEl) displayEl.textContent = Math.round(currentOffset);
    }

    function dispatch(offset) {
        document.dispatchEvent(new CustomEvent('desync-change', { detail: { offset } }));
    }

    function getOffset() { return snapToNearest(Math.round(currentOffset)); }

    return { init, getOffset };
})();
