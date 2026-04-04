/**
 * v3 Cracking Workbench — Real-Time Frequency Inversion
 * ======================================================
 * When the German listening post wire is tapped in A-3 mode, this module
 * does real-time frequency inversion using Web Audio API. The student
 * drags a carrier frequency slider and hears the scrambled signal
 * unscramble when they find the right frequency.
 *
 * The math: multiply the signal by cos(2π * carrier * t), then lowpass
 * filter. Same as sigsaly/scrambler.py but in real-time audio nodes.
 */

const CrackingWorkbench = (() => {
    let isActive = false;
    let sourceNode = null;
    let oscillator = null;
    let modulatorGain = null;
    let filterNode = null;
    let outputGain = null;
    let carrierFreq = 1000;

    function init() {
        const slider = document.getElementById('crack-slider');
        if (!slider) return;

        slider.addEventListener('input', (e) => {
            carrierFreq = parseInt(e.target.value);
            const display = document.getElementById('crack-freq-display');
            if (display) display.textContent = carrierFreq;

            // Update audio nodes in real-time
            if (isActive && oscillator) {
                const ctx = AudioEngine.getContext();
                oscillator.frequency.setValueAtTime(carrierFreq, ctx.currentTime);
                filterNode.frequency.setValueAtTime(Math.min(carrierFreq, 4000), ctx.currentTime);
            }

            updateStatus();
        });
    }

    function startCracking(mode) {
        stopCracking();

        const ctx = AudioEngine.getContext();
        if (!ctx) return;

        const bufferName = mode === 'a3' ? 'a3_on_wire' : 'sigsaly_on_wire';
        const buffer = AudioEngine.getBuffer(bufferName);
        if (!buffer) {
            console.warn('CrackingWorkbench: no buffer for', bufferName);
            return;
        }

        // Stop main audio engine
        AudioEngine.stop();

        if (ctx.state === 'suspended') ctx.resume();

        // Source: the intercepted signal, looping
        sourceNode = ctx.createBufferSource();
        sourceNode.buffer = buffer;
        sourceNode.loop = true;

        // Modulation chain for frequency inversion:
        // source → modulatorGain (gain modulated by oscillator) → filter → output

        // The gain node whose gain parameter is modulated by the oscillator
        // This creates ring modulation (AM), which shifts frequencies
        modulatorGain = ctx.createGain();
        modulatorGain.gain.value = 0; // Will be driven by oscillator

        // Oscillator drives the gain parameter
        oscillator = ctx.createOscillator();
        oscillator.type = 'cosine';
        oscillator.frequency.value = carrierFreq;
        oscillator.connect(modulatorGain.gain);

        // Lowpass filter removes the upper sideband
        filterNode = ctx.createBiquadFilter();
        filterNode.type = 'lowpass';
        filterNode.frequency.value = Math.min(carrierFreq, 4000);
        filterNode.Q.value = 0.7;

        // Output gain for volume control
        outputGain = ctx.createGain();
        outputGain.gain.value = 2.0; // Boost — modulation reduces level

        // Wire: source → modulatorGain → filter → outputGain → speakers
        sourceNode.connect(modulatorGain);
        modulatorGain.connect(filterNode);
        filterNode.connect(outputGain);
        outputGain.connect(ctx.destination);

        sourceNode.start(0);
        oscillator.start(0);
        isActive = true;

        updateStatus();
    }

    function stopCracking() {
        try { if (sourceNode) sourceNode.stop(); } catch(e) {}
        try { if (oscillator) oscillator.stop(); } catch(e) {}
        if (sourceNode) { sourceNode.disconnect(); sourceNode = null; }
        if (oscillator) { oscillator.disconnect(); oscillator = null; }
        if (modulatorGain) { modulatorGain.disconnect(); modulatorGain = null; }
        if (filterNode) { filterNode.disconnect(); filterNode = null; }
        if (outputGain) { outputGain.disconnect(); outputGain = null; }
        isActive = false;
    }

    function updateStatus() {
        const el = document.getElementById('crack-status');
        if (!el) return;

        const mode = document.body.dataset.mode || 'a3';
        const actualCarrier = (window.SIGSALY_V3?.params?.carrier_freq) || 2000;

        if (mode !== 'a3') {
            // SIGSALY mode: slider is visible but useless
            if (isActive) {
                el.textContent = 'Nothing... SIGSALY uses random keys, not spectrum inversion. No carrier to find.';
                el.style.color = '#4ecca3';
            } else {
                el.textContent = 'Tap the wire to listen. The slider won\'t help against SIGSALY.';
                el.style.color = '#4ecca3';
            }
            return;
        }

        if (!isActive) {
            el.textContent = 'Tap the wire, then drag to find speech...';
            el.style.color = '';
            return;
        }

        const diff = Math.abs(carrierFreq - actualCarrier);
        if (diff < 100) {
            el.textContent = 'Speech detected - cracked.';
            el.style.color = var_danger();
        } else if (diff < 300) {
            el.textContent = 'Getting warmer... something emerging';
            el.style.color = '#f39c12';
        } else {
            el.textContent = 'Searching... noise only';
            el.style.color = '';
        }
    }

    function var_danger() { return '#e74c3c'; }

    return { init, startCracking, stopCracking, updateStatus, get isActive() { return isActive; } };
})();
