/**
 * v3 Audio Engine
 * ================
 * Loads all pre-computed audio variants as Web Audio API AudioBuffers
 * for instant playback switching. Only one sound plays at a time.
 */

const AudioEngine = (() => {
    let ctx = null;
    let buffers = {};       // variant name -> AudioBuffer
    let currentSource = null;
    let currentVariant = null;
    let startTime = 0;
    let pauseOffset = 0;
    let isPlaying = false;
    let onEndCallback = null;
    let progressInterval = null;

    function getAudioUrl(filename) {
        const cfg = window.SIGSALY_V3;
        if (!cfg || !cfg.sessionId) return null;
        return cfg.audioBaseUrl
            .replace('__SID__', cfg.sessionId)
            .replace('__FILE__', filename);
    }

    async function init() {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        const cfg = window.SIGSALY_V3;
        if (!cfg || !cfg.variants) return;

        // Load all variant WAVs as AudioBuffers
        const loadPromises = Object.entries(cfg.variants).map(async ([name, filename]) => {
            try {
                const url = getAudioUrl(filename);
                const resp = await fetch(url);
                const arrayBuf = await resp.arrayBuffer();
                buffers[name] = await ctx.decodeAudioData(arrayBuf);
            } catch (e) {
                console.warn(`Failed to load audio variant: ${name}`, e);
            }
        });

        await Promise.all(loadPromises);
        console.log(`AudioEngine: loaded ${Object.keys(buffers).length} variants`);
    }

    function play(variantName, label) {
        if (!ctx || !buffers[variantName]) {
            console.warn(`No buffer for variant: ${variantName}`);
            return;
        }

        stop(); // Stop any current playback

        // Resume context if suspended (browser autoplay policy)
        if (ctx.state === 'suspended') ctx.resume();

        currentSource = ctx.createBufferSource();
        currentSource.buffer = buffers[variantName];
        currentSource.connect(ctx.destination);
        currentSource.onended = () => {
            isPlaying = false;
            currentVariant = null;
            _stopProgress();
            if (onEndCallback) onEndCallback();
        };

        currentSource.start(0, pauseOffset);
        startTime = ctx.currentTime - pauseOffset;
        isPlaying = true;
        currentVariant = variantName;
        pauseOffset = 0;

        _startProgress(label);
    }

    function pause() {
        if (!isPlaying || !currentSource) return;
        pauseOffset = ctx.currentTime - startTime;
        currentSource.stop();
        currentSource = null;
        isPlaying = false;
        _stopProgress();
    }

    function stop() {
        if (currentSource) {
            try { currentSource.stop(); } catch (e) {}
            currentSource = null;
        }
        isPlaying = false;
        currentVariant = null;
        pauseOffset = 0;
        startTime = 0;
        _stopProgress();
    }

    function togglePlayPause(variantName, label) {
        if (isPlaying && currentVariant === variantName) {
            pause();
        } else if (!isPlaying && currentVariant === variantName && pauseOffset > 0) {
            play(variantName, label);
        } else {
            pauseOffset = 0;
            play(variantName, label);
        }
    }

    function getDuration(variantName) {
        if (!buffers[variantName]) return 0;
        return buffers[variantName].duration;
    }

    function getCurrentTime() {
        if (!isPlaying || !ctx) return pauseOffset;
        return ctx.currentTime - startTime;
    }

    function _startProgress(label) {
        const npLabel = document.getElementById('np-label');
        const npTime = document.getElementById('np-time');
        const npBar = document.getElementById('np-bar');
        const npPlayPause = document.getElementById('np-play-pause');
        const npStop = document.getElementById('np-stop');

        if (npLabel) npLabel.textContent = label || currentVariant;
        if (npPlayPause) { npPlayPause.disabled = false; npPlayPause.textContent = '⏸'; }
        if (npStop) npStop.disabled = false;

        _stopProgress();
        progressInterval = setInterval(() => {
            if (!isPlaying) return;
            const t = getCurrentTime();
            const d = getDuration(currentVariant);
            if (npTime) npTime.textContent = `${t.toFixed(1)}s / ${d.toFixed(1)}s`;
            if (npBar) npBar.style.width = `${(t / d) * 100}%`;
        }, 100);
    }

    function _stopProgress() {
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }
        const npPlayPause = document.getElementById('np-play-pause');
        if (npPlayPause && !isPlaying) npPlayPause.textContent = '▶';
    }

    function getBuffer(variantName) {
        return buffers[variantName] || null;
    }

    function getContext() {
        return ctx;
    }

    return {
        init, play, pause, stop, togglePlayPause,
        getDuration, getCurrentTime, getBuffer, getContext,
        get isPlaying() { return isPlaying; },
        get currentVariant() { return currentVariant; },
        set onEnd(cb) { onEndCallback = cb; },
    };
})();
