/**
 * v3 Main Controller — Wire-Tap Model
 * =====================================
 * Click thick wires to tap in and hear the signal.
 * Audio loops. Records spin. Wires glow.
 */

(async function() {
    'use strict';

    await AudioEngine.init();
    VinylInteraction.init();
    CrackingWorkbench.init();

    const mode = () => document.body.dataset.mode || 'a3';
    const listeningText = document.getElementById('listening-text');
    const listeningLabel = document.getElementById('listening-label');

    document.body.dataset.mode = 'a3';

    // ── Mode toggle ────────────────────────────────────────
    const modeButtons = document.querySelectorAll('.mode-btn');
    const modeHint = document.getElementById('mode-hint');

    const HINTS = {
        a3: "The Allies' first attempt — simplified frequency inversion. Can the Germans crack it?",
        sigsaly: "The full SIGSALY system — vocoder + one-time pad. Provably unbreakable."
    };

    modeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            document.body.dataset.mode = btn.dataset.mode;
            modeButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (modeHint) modeHint.textContent = HINTS[btn.dataset.mode] || '';

            AudioEngine.stop();
            CrackingWorkbench.stopCracking();
            CrackingWorkbench.updateStatus();
            clearTapped();
            setLabel('Click any wire to tap in');
        });
    });

    // ── Wire click handlers ────────────────────────────────
    document.querySelectorAll('.wire-tap').forEach(wire => {
        wire.addEventListener('click', () => {
            // Resolve the variant for this wire
            let variant = wire.dataset.variant;
            let label = wire.dataset.label || '';

            // Mode-dependent wires (cable, german post)
            if (wire.dataset.variantA3) {
                variant = mode() === 'a3' ? wire.dataset.variantA3 : wire.dataset.variantSigsaly;
                label = mode() === 'a3' ? (wire.dataset.labelA3 || '') : (wire.dataset.labelSigsaly || '');
            }

            // German post tap → activate cracking workbench
            if (wire.classList.contains('german-tap')) {
                clearTapped();
                wire.classList.add('tapped');
                CrackingWorkbench.startCracking(mode());
                setLabel('🎧 Cracking active — drag slider to search');
                return;
            }

            // Stop cracking if tapping a normal wire
            CrackingWorkbench.stopCracking();

            // Toggle: tap same wire again → untap
            if (wire.classList.contains('tapped')) {
                AudioEngine.stop();
                clearTapped();
                setLabel('Click any wire to tap in');
                return;
            }

            if (!variant) return;

            // Handle receiver output wire (uses desync offset)
            if (variant === 'sigsaly_decrypted_0' && mode() === 'sigsaly') {
                const offset = VinylInteraction.getOffset();
                variant = `sigsaly_decrypted_${offset}`;
                label = offset === 0
                    ? 'Decrypted (perfect sync)'
                    : `Decrypted (${offset} frame offset — DESYNC!)`;
            }

            clearTapped();
            wire.classList.add('tapped');
            AudioEngine.play(variant, label, true);
            setLabel('🔊 ' + label);
        });
    });

    // ── Desync changes update active audio ──────────────────
    document.addEventListener('desync-change', (e) => {
        const offset = e.detail.offset;
        // If tapped on a decrypt output wire, switch audio
        const tapped = document.querySelector('.wire-tap.tapped');
        if (tapped && tapped.dataset.variant && tapped.dataset.variant.startsWith('sigsaly_decrypted')) {
            const newVariant = `sigsaly_decrypted_${offset}`;
            const newLabel = offset === 0
                ? 'Decrypted (perfect sync)'
                : `Decrypted (${offset} frame offset — DESYNC!)`;
            tapped.dataset.variant = newVariant;
            AudioEngine.play(newVariant, newLabel, true);
            setLabel('🔊 ' + newLabel);
        }
    });

    // ── Helpers ─────────────────────────────────────────────

    function clearTapped() {
        document.querySelectorAll('.wire-tap').forEach(w => w.classList.remove('tapped'));
    }

    function setLabel(text) {
        if (listeningText) listeningText.textContent = text;
        if (listeningLabel) listeningLabel.classList.toggle('active', text.startsWith('🔊') || text.startsWith('🎧'));
    }

})();
