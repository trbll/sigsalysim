/**
 * v3 Main Controller — Wire-Tap Model
 * =====================================
 * Audio loops continuously. Users tap wires to hear what's flowing
 * through at that point. Records always spin in SIGSALY mode.
 */

(async function() {
    'use strict';

    await AudioEngine.init();
    VinylInteraction.init();
    CrackingWorkbench.init();

    const mode = () => document.body.dataset.mode || 'a3';
    const listeningText = document.getElementById('listening-text');
    const listeningLabel = document.getElementById('listening-label');

    // Set initial mode
    document.body.dataset.mode = 'a3';

    // ── Mode toggle ────────────────────────────────────────────
    const modeButtons = document.querySelectorAll('.mode-btn');
    const modeHint = document.getElementById('mode-hint');

    const MODE_HINTS = {
        a3: "The Allies' first attempt — simplified frequency inversion. Can the Germans crack it?",
        sigsaly: "The full SIGSALY system — vocoder + one-time pad encryption. Provably unbreakable."
    };

    modeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            document.body.dataset.mode = btn.dataset.mode;
            modeButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (modeHint) modeHint.textContent = MODE_HINTS[btn.dataset.mode] || '';

            // Stop audio and cracking
            AudioEngine.stop();
            CrackingWorkbench.stopCracking();
            clearTapped();
            updateListeningLabel('Click a wire to tap in');

            CrackingWorkbench.updateStatus();
        });
    });

    // ── Wire Taps ──────────────────────────────────────────────
    const allWires = document.querySelectorAll('.wire-tap');

    allWires.forEach(wire => {
        wire.addEventListener('click', () => {
            // Determine variant based on mode
            let variant = wire.dataset.variant;
            let label = wire.dataset.label || '';

            // Cable wires have mode-dependent variants
            if (wire.classList.contains('cable-wire')) {
                variant = mode() === 'a3' ? wire.dataset.variantA3 : wire.dataset.variantSigsaly;
                label = mode() === 'a3' ? (wire.dataset.labelA3 || '') : (wire.dataset.labelSigsaly || '');
            }

            if (!variant) return;

            // Special handling for German post tap — activate cracking workbench
            if (wire.closest('.post-tap')) {
                CrackingWorkbench.startCracking(mode());
                clearTapped();
                wire.classList.add('tapped');
                updateListeningLabel('🎧 Cracking workbench — drag slider to search for carrier');
                return;
            }

            // Stop cracking if switching to a normal wire
            CrackingWorkbench.stopCracking();

            // If tapping the same wire, untap (stop)
            if (wire.classList.contains('tapped')) {
                AudioEngine.stop();
                clearTapped();
                updateListeningLabel('Click a wire to tap in');
                return;
            }

            // Tap this wire
            clearTapped();
            wire.classList.add('tapped');

            // For decrypt wire, use current desync offset
            if (variant === 'sigsaly_decrypted_0') {
                const offset = VinylInteraction.getOffset();
                variant = `sigsaly_decrypted_${offset}`;
                label = offset === 0
                    ? 'Decrypted (perfect sync)'
                    : `Decrypted (${offset} frame offset — DESYNC!)`;
            }

            // Play with looping
            AudioEngine.play(variant, label, true);
            updateListeningLabel('🔊 ' + label);
        });
    });

    // ── Desync changes ─────────────────────────────────────────
    document.addEventListener('desync-change', (e) => {
        const offset = e.detail.offset;

        // Update decrypt wire variant
        const decryptWires = document.querySelectorAll('.sigsaly-only .wire-tap[data-variant^="sigsaly_decrypted"]');
        decryptWires.forEach(w => {
            w.dataset.variant = `sigsaly_decrypted_${offset}`;
            w.dataset.label = offset === 0
                ? 'Decrypted (perfect sync)'
                : `Decrypted (${offset} frame offset — DESYNC!)`;
        });

        // If currently tapped on a decrypt wire, switch audio
        const tappedDecrypt = document.querySelector('.wire-tap.tapped[data-variant^="sigsaly_decrypted"]');
        if (tappedDecrypt) {
            const newVariant = `sigsaly_decrypted_${offset}`;
            const newLabel = offset === 0
                ? 'Decrypted (perfect sync)'
                : `Decrypted (${offset} frame offset — DESYNC!)`;
            AudioEngine.play(newVariant, newLabel, true);
            updateListeningLabel('🔊 ' + newLabel);
        }
    });

    // ── Helpers ─────────────────────────────────────────────────

    function clearTapped() {
        allWires.forEach(w => w.classList.remove('tapped'));
    }

    function updateListeningLabel(text) {
        if (listeningText) listeningText.textContent = text;
        if (listeningLabel) {
            listeningLabel.classList.toggle('active', text.startsWith('🔊') || text.startsWith('🎧'));
        }
    }

})();
