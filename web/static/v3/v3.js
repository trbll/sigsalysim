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
        a3: "The Allies' first attempt - simplified frequency inversion. Can the Germans crack it?",
        sigsaly: "The full SIGSALY system - vocoder plus one-time pad. The listening post cannot peel it open."
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

            // German post tap activates the cracking workbench
            if (wire.classList.contains('german-tap')) {
                clearTapped();
                wire.classList.add('tapped');
                CrackingWorkbench.startCracking(mode());
                setLabel('Cracking active - drag the slider to search');
                highlightStages(mode() === 'a3' ? 'a3_scrambled' : 'sigsaly_encrypted');
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
                    : `Decrypted (${offset} frame offset - desync)`;
            }

            clearTapped();
            wire.classList.add('tapped');
            AudioEngine.play(variant, label, true);
            setLabel('Listening: ' + label);
            highlightStages(variant);
        });
    });

    // ── Desync changes ──────────────────────────────────────
    // Vinyl mousedown stops audio, mouseup dispatches this with new offset.
    // We start playback at the new offset and update wire datasets.
    document.addEventListener('desync-change', (e) => {
        const offset = e.detail.offset;
        const newVariant = `sigsaly_decrypted_${offset}`;
        const newLabel = offset === 0
            ? 'Decrypted (perfect sync)'
            : `Decrypted (${offset} frame offset - desync)`;

        // Update receiver output wire datasets
        document.querySelectorAll('.wire-tap').forEach(w => {
            if (w.dataset.variantSigsaly && w.dataset.variantSigsaly.startsWith('sigsaly_decrypted')) {
                w.dataset.variantSigsaly = newVariant;
                w.dataset.labelSigsaly = newLabel;
            }
            if (w.dataset.variant && w.dataset.variant.startsWith('sigsaly_decrypted')) {
                w.dataset.variant = newVariant;
                w.dataset.label = newLabel;
            }
        });

        // Always start playback — vinyl already stopped audio on mousedown
        AudioEngine.stop();
        AudioEngine.play(newVariant, newLabel, true);
        setLabel('Listening: ' + newLabel);
        highlightStages(newVariant);

        // Mark the receiver output wire as tapped
        clearTapped();
        document.querySelectorAll('.wire-tap').forEach(w => {
            const v = w.dataset.variantSigsaly || w.dataset.variant;
            if (v === newVariant) w.classList.add('tapped');
        });
    });

    // ── Stage highlighting ────────────────────────────────────
    // Map each audio variant to which stage blocks should glow.
    // Shows the signal path that produced the audio you're hearing.
    const STAGE_MAP = {
        // A-3 sender
        'original':        [],
        'a3_scrambled':    ['stage-scramble'],
        'a3_on_wire':      ['stage-scramble'],
        'a3_unscrambled':  ['stage-scramble', 'stage-unscramble'],
        // SIGSALY sender
        'vocoded':         ['stage-vocoder'],
        'key_record':      ['stage-sender-key'],
        'sigsaly_encrypted': ['stage-vocoder', 'stage-encrypt', 'stage-sender-key'],
        'sigsaly_on_wire':   ['stage-vocoder', 'stage-encrypt', 'stage-sender-key'],
        // SIGSALY receiver (all decrypted variants)
        'sigsaly_decrypted': ['stage-vocoder', 'stage-encrypt', 'stage-sender-key', 'stage-decrypt', 'stage-receiver-key'],
    };

    function highlightStages(variant) {
        // Clear all
        document.querySelectorAll('.stage-block, .vinyl-block').forEach(el => el.classList.remove('lit'));

        if (!variant) return;

        // Check exact match first, then prefix match (for sigsaly_decrypted_N)
        let stages = STAGE_MAP[variant];
        if (!stages) {
            // Try prefix match
            for (const [key, val] of Object.entries(STAGE_MAP)) {
                if (variant.startsWith(key)) { stages = val; break; }
            }
        }
        if (!stages) return;

        stages.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.add('lit');
        });
    }

    // ── Helpers ─────────────────────────────────────────────

    function clearTapped() {
        document.querySelectorAll('.wire-tap').forEach(w => w.classList.remove('tapped'));
        highlightStages(null);
    }

    function setLabel(text) {
        if (listeningText) listeningText.textContent = text;
        if (listeningLabel) {
            listeningLabel.classList.toggle(
                'active',
                text.startsWith('Listening:') || text.startsWith('Cracking active')
            );
        }
    }

})();
