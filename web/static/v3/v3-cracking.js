/**
 * v3 Cracking Workbench
 * ======================
 * Real-time frequency inversion using Web Audio API.
 * In A-3 mode, the German listening post can sweep a carrier frequency
 * slider and hear the scrambled signal unscramble when they find the
 * right frequency. In SIGSALY mode, no carrier frequency works.
 *
 * The frequency inversion is done entirely client-side:
 *   1. Load the "on wire" audio buffer
 *   2. Create an oscillator at the carrier frequency
 *   3. Modulate the audio with the oscillator (ring modulation)
 *   4. Lowpass filter to keep only the inverted baseband
 *
 * This is the same math as sigsaly/scrambler.py but in real-time Web Audio.
 */

const CrackingWorkbench = (() => {
    let isActive = false;
    let sourceNode = null;
    let oscillator = null;
    let gainNode = null;
    let filterNode = null;
    let carrierFreq = 1000;

    const slider = () => document.getElementById('crack-slider');
    const freqDisplay = () => document.getElementById('crack-freq-display');
    const statusEl = () => document.getElementById('crack-status');

    function init() {
        const s = slider();
        if (!s) return;

        s.addEventListener('input', (e) => {
            carrierFreq = parseInt(e.target.value);
            const d = freqDisplay();
            if (d) d.textContent = carrierFreq;

            if (isActive && oscillator) {
                oscillator.frequency.setValueAtTime(carrierFreq, AudioEngine.getContext().currentTime);
                filterNode.frequency.setValueAtTime(
                    Math.min(carrierFreq, 4000),
                    AudioEngine.getContext().currentTime
                );
            }

            updateStatus();
        });
    }

    function startCracking(mode) {
        stopCracking();

        const ctx = AudioEngine.getContext();
        if (!ctx) return;

        // Get the appropriate "on wire" buffer based on mode
        const bufferName = mode === 'a3' ? 'a3_on_wire' : 'sigsaly_on_wire';
        const buffer = AudioEngine.getBuffer(bufferName);
        if (!buffer) return;

        // Stop the main audio engine playback
        AudioEngine.stop();

        // Resume context
        if (ctx.state === 'suspended') ctx.resume();

        // Create the processing chain:
        // source -> gain(modulate with oscillator) -> lowpass -> destination
        sourceNode = ctx.createBufferSource();
        sourceNode.buffer = buffer;
        sourceNode.loop = true; // Loop for continuous cracking exploration

        // Ring modulation: multiply the signal by a cosine at the carrier frequency
        // Web Audio doesn't have a direct multiply node, so we use a trick:
        // connect source to a gain node whose gain is modulated by an oscillator
        gainNode = ctx.createGain();
        gainNode.gain.value = 0; // Will be modulated by oscillator

        // Oscillator for modulation
        oscillator = ctx.createOscillator();
        oscillator.type = 'cosine';
        oscillator.frequency.value = carrierFreq;

        // Connect oscillator to gain's gain parameter (this creates AM/ring modulation)
        oscillator.connect(gainNode.gain);

        // Lowpass filter to remove the upper sideband
        filterNode = ctx.createBiquadFilter();
        filterNode.type = 'lowpass';
        filterNode.frequency.value = Math.min(carrierFreq, 4000);
        filterNode.Q.value = 0.7;

        // Wire it up: source -> gain (modulated) -> filter -> speakers
        sourceNode.connect(gainNode);
        gainNode.connect(filterNode);
        filterNode.connect(ctx.destination);

        sourceNode.start(0);
        oscillator.start(0);
        isActive = true;

        updateStatus();
    }

    function stopCracking() {
        if (sourceNode) {
            try { sourceNode.stop(); } catch (e) {}
            sourceNode.disconnect();
            sourceNode = null;
        }
        if (oscillator) {
            try { oscillator.stop(); } catch (e) {}
            oscillator.disconnect();
            oscillator = null;
        }
        if (gainNode) {
            gainNode.disconnect();
            gainNode = null;
        }
        if (filterNode) {
            filterNode.disconnect();
            filterNode = null;
        }
        isActive = false;
    }

    function updateStatus() {
        const el = statusEl();
        if (!el) return;

        const mode = document.body.dataset.mode || 'a3';
        const params = window.SIGSALY_V3?.params || {};
        const actualCarrier = params.carrier_freq || 2000;

        if (mode === 'sigsaly') {
            el.textContent = 'No carrier frequency to find — SIGSALY uses random key values, not spectrum inversion.';
            el.style.color = '#4ecca3';
        } else {
            const diff = Math.abs(carrierFreq - actualCarrier);
            if (!isActive) {
                el.textContent = 'Click the headphone jack above, then drag the slider to search for speech...';
                el.style.color = '';
            } else if (diff < 100) {
                el.textContent = '🔓 SPEECH DETECTED — the A-3 scrambler is cracked!';
                el.style.color = '#e74c3c';
            } else if (diff < 300) {
                el.textContent = 'Getting warmer... speech-like patterns emerging';
                el.style.color = '#f39c12';
            } else {
                el.textContent = 'Searching... only noise so far';
                el.style.color = '';
            }
        }
    }

    return { init, startCracking, stopCracking, updateStatus, get isActive() { return isActive; } };
})();
