/**
 * v3 Main Controller
 * ===================
 * Wires together the audio engine, vinyl interaction, cracking workbench,
 * mode toggle, and headphone jack click handlers.
 */

(async function() {
    'use strict';

    // ── Initialize audio engine ────────────────────────────────
    await AudioEngine.init();
    VinylInteraction.init();
    CrackingWorkbench.init();

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
            const mode = btn.dataset.mode;
            document.body.dataset.mode = mode;

            // Update button states
            modeButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update hint
            if (modeHint) modeHint.textContent = MODE_HINTS[mode] || '';

            // Stop any playback
            AudioEngine.stop();
            CrackingWorkbench.stopCracking();
            clearActiveJacks();

            // Update cracking workbench status
            CrackingWorkbench.updateStatus();

            // Update vinyl record visibility/spin
            updateVinylSpin(false);
        });
    });

    // ── Headphone Jacks ────────────────────────────────────────
    // Click a jack → play that variant. Only one jack active at a time.
    const allJacks = document.querySelectorAll('.headphone-jack');

    allJacks.forEach(jack => {
        jack.addEventListener('click', () => {
            const mode = document.body.dataset.mode || 'a3';

            // Stop cracking if active
            CrackingWorkbench.stopCracking();

            // Determine which variant to play
            let variant = jack.dataset.variant;
            let label = '';

            // German post jack has mode-dependent variants
            if (jack.id === 'german-jack') {
                variant = mode === 'a3' ? jack.dataset.variantA3 : jack.dataset.variantSigsaly;
                label = mode === 'a3'
                    ? 'Wire tap: A-3 scrambled + noise (crackable!)'
                    : 'Wire tap: SIGSALY encrypted + noise (just noise)';

                // In A-3 mode, activate cracking workbench when German jack is clicked
                if (mode === 'a3') {
                    CrackingWorkbench.startCracking(mode);
                    setActiveJack(jack);
                    updateNowPlaying('🎧 Cracking workbench active — drag slider to find carrier');
                    return;
                }
                if (mode === 'sigsaly') {
                    // In SIGSALY mode, start cracking too (to show it fails)
                    CrackingWorkbench.startCracking(mode);
                    setActiveJack(jack);
                    updateNowPlaying('🎧 Wire tap: encrypted noise — cracking slider has no effect');
                    return;
                }
            }

            // Output jack maps to mode-dependent variant
            if (variant === '__output__') {
                if (mode === 'a3') {
                    variant = 'a3_unscrambled';
                    label = 'Receiver output: unscrambled speech';
                } else {
                    const offset = VinylInteraction.getOffset();
                    variant = `sigsaly_decrypted_${offset}`;
                    label = offset === 0
                        ? 'Receiver output: decrypted (perfect sync)'
                        : `Receiver output: decrypted (${offset} frame offset — DESYNC)`;
                }
            }

            if (!label) {
                // Generate label from variant name
                label = variant.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            }

            // Toggle: if this jack is already active, stop
            if (jack.classList.contains('active') && AudioEngine.currentVariant === variant) {
                AudioEngine.stop();
                clearActiveJacks();
                updateVinylSpin(false);
                return;
            }

            // Play the variant
            clearActiveJacks();
            setActiveJack(jack);
            AudioEngine.play(variant, label);

            // Spin vinyl records while playing SIGSALY audio
            const isSigsalyAudio = variant.startsWith('sigsaly_') || variant === 'vocoded' || variant === 'key_record';
            updateVinylSpin(isSigsalyAudio);
        });
    });

    // ── Now Playing bar controls ───────────────────────────────
    const npPlayPause = document.getElementById('np-play-pause');
    const npStop = document.getElementById('np-stop');

    if (npPlayPause) {
        npPlayPause.addEventListener('click', () => {
            if (AudioEngine.isPlaying) {
                AudioEngine.pause();
            } else if (AudioEngine.currentVariant) {
                AudioEngine.play(AudioEngine.currentVariant);
            }
        });
    }

    if (npStop) {
        npStop.addEventListener('click', () => {
            AudioEngine.stop();
            CrackingWorkbench.stopCracking();
            clearActiveJacks();
            updateVinylSpin(false);
        });
    }

    AudioEngine.onEnd = () => {
        clearActiveJacks();
        updateVinylSpin(false);
    };

    // ── Helper functions ───────────────────────────────────────

    function clearActiveJacks() {
        allJacks.forEach(j => j.classList.remove('active'));
        document.querySelectorAll('.chain-stage').forEach(s => s.classList.remove('playing'));
    }

    function setActiveJack(jack) {
        clearActiveJacks();
        jack.classList.add('active');
        // Highlight the parent stage
        const stage = jack.closest('.chain-stage');
        if (stage) stage.classList.add('playing');
    }

    function updateVinylSpin(spinning) {
        const senderRecord = document.getElementById('sender-record');
        const receiverRecord = document.getElementById('receiver-record');
        if (senderRecord) {
            senderRecord.classList.toggle('spinning', spinning);
        }
        // Only spin receiver if offset is 0 (in sync)
        if (receiverRecord && VinylInteraction.getOffset() === 0) {
            receiverRecord.classList.toggle('spinning', spinning);
        }
    }

    function updateNowPlaying(text) {
        const npLabel = document.getElementById('np-label');
        if (npLabel) npLabel.textContent = text;
    }

})();
