"""
Channel Vocoder (SIGSALY-style)
===============================
The vocoder ("voice coder") is the heart of SIGSALY. It solves a fundamental
problem: how do you encrypt an analog audio signal? You can't do modular
arithmetic on a continuous waveform. SIGSALY's insight was to first DIGITIZE
the speech into a small set of numerical parameters, then encrypt THOSE.

The vocoder decomposes speech into a compact parametric representation:
  - 10 frequency band energy levels (how loud is each frequency range?)
  - Pitch frequency (what note is the speaker's voice at?)
  - Voiced/unvoiced flag (is the speaker making a vowel or a consonant?)

This is sampled 50 times per second (every 20ms), producing just 12 numbers
per frame. Compare this to the raw audio: at 22050 Hz, that's 441 samples
per 20ms frame — a 37:1 compression ratio.

Historical context:
  The vocoder was invented by Homer Dudley at Bell Labs in 1939.
  The SIGSALY system adapted it for secure communications in 1943.
  Churchill reportedly found the vocoder quality acceptable but
  complained it made Roosevelt sound like a "synthetic man."

Analysis (encoder) — what happens to your voice:
  1. Split speech into 10 frequency bands using bandpass filters
     (250-500 Hz, 500-750 Hz, ..., 2700-2950 Hz)
  2. Measure the energy (amplitude envelope) of each band
  3. Detect the fundamental pitch of the voice
  4. Classify each frame as voiced (vowels, nasals) or unvoiced (s, f, sh)
  5. Quantize all values to 6 discrete levels (0-5) with companding

Resynthesis (decoder) — how to reconstruct speech from parameters:
  1. Generate excitation signal:
     - Voiced frames: a pulse train at the detected pitch frequency
     - Unvoiced frames: white noise
  2. Filter the excitation through 10 bandpass filters
  3. Scale each band by its amplitude level
  4. Sum all bands together

The result sounds robotic but intelligible — the characteristic "SIGSALY
sound." The robotic quality comes from the coarse quantization (only 6
levels!) and the simplified excitation model (real speech has richer
harmonic structure than a simple pulse train).

Key concepts for students:
  - Parametric vs. waveform coding: the vocoder doesn't try to reproduce
    the waveform exactly. It extracts PARAMETERS and resynthesizes from
    those. This is fundamentally different from (and much more compressible
    than) approaches like PCM that encode the waveform directly.
  - Companding: non-linear quantization that gives finer resolution to
    quiet signals. Human hearing is logarithmic — a 1 dB change at 40 dB
    is more perceptible than a 1 dB change at 80 dB. Companding matches
    quantization precision to perceptual importance.
  - Analysis-synthesis: a pattern that appears throughout signal processing,
    from vocoders to JPEG to modern neural codecs.
"""

import numpy as np
from scipy.signal import butter, sosfilt, hilbert


# ============================================================================
# SIGSALY VOCODER PARAMETERS
# ============================================================================

# SIGSALY used 10 frequency bands spanning the telephone bandwidth (250-2950 Hz).
# Each band is a bandpass filter that isolates a slice of the frequency spectrum.
# The bands are roughly equal width (~250 Hz each) in the lower range, with
# slightly wider bands in the upper range where speech has less detail.
BAND_EDGES = [
    (250, 500),     # Band 0: Low fundamentals, deep vowel sounds
    (500, 750),     # Band 1: First formant region for many vowels
    (750, 1000),    # Band 2: First formant region (continued)
    (1000, 1250),   # Band 3: Transition between first and second formants
    (1250, 1500),   # Band 4: Second formant region
    (1500, 1750),   # Band 5: Second formant region (continued)
    (1750, 2100),   # Band 6: Second/third formant transition
    (2100, 2400),   # Band 7: Third formant region
    (2400, 2700),   # Band 8: High-frequency consonant energy
    (2700, 2950),   # Band 9: Highest band — sibilance, fricatives
]

NUM_BANDS = len(BAND_EDGES)   # 10 bands total
NUM_LEVELS = 6                 # SIGSALY quantized each band to 6 levels (0-5)
FRAME_RATE = 50                # 50 frames per second = one frame every 20ms


# ============================================================================
# INTERNAL HELPER FUNCTIONS
# ============================================================================

def _bandpass(signal, sr, low, high, order=4):
    """Bandpass filter for a single vocoder channel.

    Isolates frequencies between 'low' and 'high' Hz, removing everything
    else. Each vocoder band uses one of these filters to extract its slice
    of the spectrum.

    We use a Butterworth filter (maximally flat passband) in second-order
    sections (SOS) form for numerical stability. Order 4 gives a reasonably
    sharp cutoff without excessive ringing.
    """
    nyq = sr / 2
    low = max(low, 1)            # Avoid 0 Hz (DC)
    high = min(high, nyq - 1)    # Stay below Nyquist frequency
    sos = butter(order, [low, high], btype='band', fs=sr, output='sos')
    return sosfilt(sos, signal)


def _envelope(signal, sr, cutoff=50):
    """Extract the amplitude envelope of a signal.

    The envelope represents how the loudness of a signal changes over time,
    ignoring the rapid oscillations of individual cycles. Think of it as
    tracing the outline of the waveform.

    Method: Hilbert transform to get the analytic signal, then take the
    magnitude. This gives an instantaneous amplitude estimate. We then
    lowpass filter at 50 Hz (= the vocoder frame rate) to smooth it.

    The Hilbert transform creates a complex-valued "analytic signal" where:
      analytic(t) = signal(t) + j * hilbert_transform(signal(t))
    The magnitude |analytic(t)| is the instantaneous amplitude envelope.
    """
    analytic = hilbert(signal)       # Complex analytic signal
    env = np.abs(analytic)           # Instantaneous amplitude
    # Smooth to the vocoder frame rate (50 Hz) with a lowpass filter
    sos = butter(2, cutoff, btype='low', fs=sr, output='sos')
    return sosfilt(sos, env)


def _detect_pitch(signal, sr, frame_size, hop_size):
    """Detect the fundamental pitch frequency using autocorrelation.

    Pitch is the fundamental frequency (F0) of voiced speech — it's what
    makes a voice sound high or low. SIGSALY needed to transmit this so
    the receiver could generate the correct excitation signal.

    Method: Autocorrelation
      For each frame, we compute the signal's correlation with delayed
      copies of itself. Voiced speech is quasi-periodic, so the
      autocorrelation has a strong peak at a delay (lag) equal to one
      pitch period. The pitch frequency is then sr / lag.

    SIGSALY's pitch range was roughly 50-250 Hz:
      - 50 Hz  = very deep male voice
      - 250 Hz = high female voice or child

    The voiced/unvoiced decision is based on the autocorrelation peak
    strength. Voiced sounds (vowels, nasals) have strong periodicity
    (high correlation). Unvoiced sounds (s, f, sh) are noise-like
    (low correlation).

    Args:
        signal:     Input audio
        sr:         Sample rate
        frame_size: Analysis window size in samples
        hop_size:   Step between frames in samples

    Returns:
        pitches: Array of pitch frequencies per frame (Hz, 0 = unvoiced)
        voiced:  Boolean array indicating voiced/unvoiced per frame
    """
    n_frames = (len(signal) - frame_size) // hop_size + 1
    pitches = np.zeros(n_frames)
    voiced = np.zeros(n_frames, dtype=bool)

    # Lag range corresponding to 50-250 Hz pitch range
    min_lag = int(sr / 250)  # Shortest period (highest pitch, 250 Hz)
    max_lag = int(sr / 50)   # Longest period (lowest pitch, 50 Hz)

    for i in range(n_frames):
        start = i * hop_size
        frame = signal[start:start + frame_size]

        # Skip silent frames (amplitude too low to analyze)
        if np.max(np.abs(frame)) < 0.01:
            pitches[i] = 0
            voiced[i] = False
            continue

        # Remove DC offset (mean) before autocorrelation
        frame = frame - np.mean(frame)

        # Compute autocorrelation: how well does the signal match
        # a delayed copy of itself? Full (non-circular) correlation.
        corr = np.correlate(frame, frame, mode='full')
        # Take only the right half (positive lags)
        corr = corr[len(corr) // 2:]
        # Normalize so corr[0] = 1.0 (perfect self-match at zero lag)
        if corr[0] > 0:
            corr = corr / corr[0]

        # Search for the strongest peak in the valid pitch range
        if max_lag < len(corr):
            search_region = corr[min_lag:max_lag]
            if len(search_region) > 0:
                peak_idx = np.argmax(search_region) + min_lag
                peak_val = corr[peak_idx]

                # Voicing decision: if the autocorrelation peak is strong
                # (> 0.3), the sound is periodic → voiced. Otherwise → unvoiced.
                if peak_val > 0.3:
                    pitches[i] = sr / peak_idx  # Convert lag to frequency
                    voiced[i] = True
                else:
                    pitches[i] = 0
                    voiced[i] = False

    return pitches, voiced


# ============================================================================
# QUANTIZATION (THE KEY TO MAKING ENCRYPTION POSSIBLE)
# ============================================================================

def compand_quantize(values, num_levels=NUM_LEVELS):
    """Quantize continuous values to discrete levels with companding.

    This is one of SIGSALY's most important innovations. The vocoder
    produces continuous amplitude values, but encryption requires discrete
    integers. SIGSALY quantized each band amplitude to just 6 levels (0-5).

    The naive approach (linear quantization) would waste precision on loud
    signals and starve quiet ones. SIGSALY used COMPANDING (compressing +
    expanding) — a nonlinear mapping that gives finer resolution to quiet
    signals where human hearing is most sensitive.

    This is the same principle later standardized as mu-law (North America)
    and A-law (Europe) for digital telephony.

    The mu-law compression formula:
        compressed = log(1 + μ * x) / log(1 + μ)

    Where μ = num_levels - 1 = 5 for SIGSALY's 6-level system.

    Effect: Level 0 covers a wide range of very quiet signals (fine detail
    where it matters). Level 5 covers a wide range of loud signals (coarse
    detail where it doesn't matter as much perceptually).

    Args:
        values:     Continuous amplitude values (1D numpy array, ≥ 0)
        num_levels: Number of discrete levels (6 for SIGSALY)

    Returns:
        quantized: Integer array with values in [0, num_levels-1]
        max_val:   The normalization factor (needed for dequantization)
    """
    # Normalize input to [0, 1] range
    max_val = np.max(values) if np.max(values) > 0 else 1.0
    normalized = np.clip(values / max_val, 0, 1)

    # Apply mu-law compression (μ = 5 for 6 levels)
    # This "compresses" the dynamic range — quiet values get boosted,
    # loud values get attenuated, so quantization errors are more
    # perceptually uniform.
    mu = num_levels - 1
    compressed = np.log1p(mu * normalized) / np.log1p(mu)

    # Quantize to nearest integer level
    quantized = np.round(compressed * (num_levels - 1)).astype(int)

    return quantized, max_val


def dequantize_expand(quantized, max_val, num_levels=NUM_LEVELS):
    """Inverse of compand_quantize: integer levels back to amplitudes.

    Applies mu-law expansion (the inverse of compression) to recover
    approximate continuous amplitude values from quantized levels.

    The expansion formula:
        expanded = (exp(compressed * log(1 + μ)) - 1) / μ

    Note: information is permanently lost in quantization. The recovered
    values are only APPROXIMATE. With 6 levels, the quantization error
    is significant — this is a major contributor to the "robotic" quality
    of vocoder-reconstructed speech.

    Args:
        quantized:  Integer levels (0 to num_levels-1)
        max_val:    Normalization factor from compand_quantize
        num_levels: Must match the quantization parameter

    Returns:
        Approximate continuous amplitude values
    """
    mu = num_levels - 1
    # Map integer levels back to [0, 1] compressed space
    compressed = quantized.astype(float) / (num_levels - 1)
    # Apply mu-law expansion to recover approximate original values
    normalized = (np.exp(compressed * np.log1p(mu)) - 1) / mu
    return normalized * max_val


# ============================================================================
# VOCODER FRAME — THE DATA STRUCTURE THAT GETS ENCRYPTED
# ============================================================================

class VocoderFrame:
    """One frame of vocoder parameters, captured every 20ms.

    This is the atomic unit of data in SIGSALY. Each frame contains:
      - band_levels: 10 integers (0-5), one per frequency band
      - pitch_level: 1 integer (0-35), quantized pitch
      - voiced:      1 boolean, voiced/unvoiced classification
      - band_max:    float, normalization factor (for dequantization)
      - pitch_hz:    float, raw pitch before quantization

    Each frame has 10 band levels + 1 pitch level + 1 voiced flag = 12 fields.
    Of these, band_levels (10) and pitch_level (1) are the encrypted streams;
    the voiced/unvoiced flag is carried separately in this implementation.
    At 50 frames/sec, the vocoder produces 600 field values/sec vs raw audio
    at 22050 samples/sec — roughly a 37:1 compression.
    """
    def __init__(self):
        self.band_levels = np.zeros(NUM_BANDS, dtype=int)  # 10 x [0-5]
        self.pitch_level = 0          # [0-35] quantized pitch
        self.voiced = False           # True = vowel-like, False = noise-like
        self.band_max = 1.0           # Normalization factor for dequantization
        self.pitch_hz = 0.0           # Raw pitch frequency in Hz


# ============================================================================
# VOCODER ANALYSIS (ENCODER)
# ============================================================================

def analyze(signal, sr, verbose=False):
    """Vocoder analysis: decompose speech into frames of parameters.

    This is the SIGSALY encoder. It takes raw audio and produces a stream
    of VocoderFrame objects — the compact parametric representation that
    can be quantized, encrypted, and transmitted.

    Processing steps for each frame:
      1. Filter signal through 10 bandpass filters → 10 band signals
      2. Extract amplitude envelope of each band → 10 continuous values
      3. Quantize each envelope to 6 levels (0-5) with companding → 10 ints
      4. Detect pitch and voiced/unvoiced → 1 int + 1 bool

    Args:
        signal:  Input audio (mono float array)
        sr:      Sample rate in Hz
        verbose: Print diagnostic information about the analysis

    Returns:
        List of VocoderFrame objects (one per 20ms of input audio)
    """
    hop_size = sr // FRAME_RATE     # Samples per frame (e.g., 441 at 22050 Hz)
    frame_size = hop_size * 2       # Double-length window for pitch detection
    n_frames = len(signal) // hop_size

    # ── Step 1: Extract band envelopes ──
    # For each of the 10 frequency bands, filter the input signal to isolate
    # that band, then extract its amplitude envelope.
    band_envelopes = []
    for low, high in BAND_EDGES:
        filtered = _bandpass(signal, sr, low, high)   # Isolate this band
        env = _envelope(filtered, sr, cutoff=FRAME_RATE)  # Get amplitude contour
        band_envelopes.append(env)

    # ── Step 2: Detect pitch and voicing ──
    pitches, voiced = _detect_pitch(signal, sr, frame_size, hop_size)

    # ── Step 3: Build vocoder frames ──
    frames = []
    for i in range(min(n_frames, len(pitches))):
        frame = VocoderFrame()
        sample_idx = i * hop_size

        # Sample each band's envelope at this frame's time position
        band_values = np.array([
            env[min(sample_idx, len(env) - 1)] for env in band_envelopes
        ])

        # Quantize the 10 band amplitudes to 6 levels using companding.
        # This is where continuous analog values become discrete integers
        # that can be encrypted with modular arithmetic.
        frame.band_levels, frame.band_max = compand_quantize(band_values)

        # Record pitch and voicing information
        frame.voiced = voiced[i]
        frame.pitch_hz = pitches[i]
        if frame.voiced and frame.pitch_hz > 0:
            # Quantize pitch: map 50-250 Hz range to 0-35 (36 levels).
            # In SIGSALY, pitch was encoded as a pair of 6-level values
            # (6 x 6 = 36 total levels), giving finer resolution than
            # the band amplitudes because pitch perception is very sensitive.
            pitch_norm = np.clip((frame.pitch_hz - 50) / 200, 0, 1)
            frame.pitch_level = int(round(pitch_norm * 35))
        else:
            frame.pitch_level = 0

        frames.append(frame)

    if verbose:
        _print_analysis_diagnostics(frames, signal, sr, hop_size)

    return frames


def _print_analysis_diagnostics(frames, signal, sr, hop_size):
    """Print quantitative diagnostics about vocoder analysis."""
    n_frames = len(frames)
    n_voiced = sum(1 for f in frames if f.voiced)
    n_unvoiced = n_frames - n_voiced

    # Collect all band levels for statistics
    all_levels = np.array([f.band_levels for f in frames])
    level_counts = [np.sum(all_levels == lv) for lv in range(NUM_LEVELS)]
    total_values = all_levels.size

    # Pitch statistics for voiced frames
    voiced_pitches = [f.pitch_hz for f in frames if f.voiced and f.pitch_hz > 0]
    pitch_levels = [f.pitch_level for f in frames if f.voiced]

    # Compression ratio
    raw_samples = len(signal)
    param_count = n_frames * (NUM_BANDS + 1 + 1)  # bands + pitch + voiced flag

    print()
    print("  ┌─ Vocoder Analysis Diagnostics ────────────────────────")
    print(f"  │ Input: {len(signal)} samples at {sr} Hz ({len(signal)/sr:.2f}s)")
    print(f"  │ Output: {n_frames} frames at {FRAME_RATE} fps (every {1000/FRAME_RATE:.0f}ms)")
    print(f"  │")
    print(f"  │ Compression:")
    print(f"  │   Raw audio:  {raw_samples} samples/frame × {sr//hop_size} fps = {sr} values/sec")
    print(f"  │   Vocoder:    {NUM_BANDS} bands + 1 pitch + 1 voiced = 12 values/frame × {FRAME_RATE} fps = {12*FRAME_RATE} values/sec")
    print(f"  │   Ratio:      {raw_samples / param_count:.0f}:1 (before quantization)")
    print(f"  │")
    print(f"  │ Voicing: {n_voiced}/{n_frames} voiced ({100*n_voiced/n_frames:.0f}%), "
          f"{n_unvoiced}/{n_frames} unvoiced ({100*n_unvoiced/n_frames:.0f}%)")
    if voiced_pitches:
        print(f"  │ Pitch range: {min(voiced_pitches):.0f} - {max(voiced_pitches):.0f} Hz "
              f"(mean: {np.mean(voiced_pitches):.0f} Hz)")
    print(f"  │")
    print(f"  │ Quantization levels (6 levels, 0-5):")
    print(f"  │   Total values: {total_values} ({n_frames} frames × {NUM_BANDS} bands)")
    for lv in range(NUM_LEVELS):
        pct = 100 * level_counts[lv] / total_values
        bar = '█' * int(pct / 2)
        print(f"  │   Level {lv}: {level_counts[lv]:5d} ({pct:5.1f}%) {bar}")
    print(f"  │")
    print(f"  │ With only 6 levels, each band amplitude has ~4.3 dB resolution.")
    print(f"  │ This coarse quantization is the main reason vocoded speech")
    print(f"  │ sounds 'robotic' — but it's what makes encryption possible.")
    print(f"  │ (You can do mod-6 arithmetic on integers, not on analog signals!)")
    print(f"  └──────────────────────────────────────────────────────")
    print()


# ============================================================================
# VOCODER RESYNTHESIS (DECODER)
# ============================================================================

def synthesize(frames, sr, verbose=False):
    """Vocoder resynthesis: reconstruct audio from vocoder frames.

    This is the SIGSALY decoder. It takes a stream of VocoderFrame objects
    (after decryption) and generates audible speech.

    For each frame:
      1. Generate excitation signal:
         - Voiced: pulse train at the pitch frequency (simulates vocal cord vibration)
         - Unvoiced: white noise (simulates turbulent airflow for s, f, sh sounds)
      2. Filter excitation through 10 bandpass filters (one per vocoder band)
      3. Scale each band by its amplitude level (from dequantized frame data)
      4. Sum all 10 band signals together

    The result is recognizable speech, but with a distinctive robotic quality.
    The robot sound comes from:
      - Coarse quantization (6 levels instead of continuous amplitudes)
      - Simplified excitation (pulse train vs. real glottal waveform)
      - Frame-by-frame processing (20ms steps instead of continuous)
      - Loss of fine spectral detail (only 10 bands)

    Args:
        frames:  List of VocoderFrame objects
        sr:      Sample rate in Hz
        verbose: Print diagnostic information

    Returns:
        Reconstructed audio signal (1D numpy array)
    """
    hop_size = sr // FRAME_RATE    # Samples per frame
    n_samples = len(frames) * hop_size
    output = np.zeros(n_samples)

    for i, frame in enumerate(frames):
        start = i * hop_size
        end = start + hop_size

        # ── Step 1: Dequantize band amplitudes ──
        # Convert integer levels (0-5) back to approximate continuous
        # amplitude values using mu-law expansion.
        band_amps = dequantize_expand(frame.band_levels, frame.band_max)

        # ── Step 2: Generate excitation signal ──
        if frame.voiced and frame.pitch_level > 0:
            # VOICED excitation: a train of impulses at the pitch frequency.
            # This simulates the periodic vibration of the vocal cords.
            # In real speech, the glottal waveform is more complex, but
            # a simple pulse train captures the essential periodicity.
            pitch_hz = 50 + (frame.pitch_level / 35) * 200
            period = int(sr / pitch_hz) if pitch_hz > 0 else hop_size
            excitation = np.zeros(hop_size)
            for j in range(0, hop_size, max(period, 1)):
                excitation[j] = 1.0
        else:
            # UNVOICED excitation: white noise.
            # Unvoiced sounds (s, f, sh, th) are produced by turbulent
            # airflow, which is inherently noise-like. White noise is
            # a good approximation.
            excitation = np.random.normal(0, 0.3, hop_size)

        # ── Step 3: Filter and scale each band ──
        # The excitation signal is broadband (has energy at all frequencies).
        # We filter it through each band's bandpass filter and scale the
        # result by that band's amplitude level. This shapes the spectrum
        # to match the original speech's spectral envelope.
        frame_signal = np.zeros(hop_size)
        for b, (low, high) in enumerate(BAND_EDGES):
            band_signal = _bandpass(excitation, sr, low, high)
            frame_signal += band_signal * band_amps[b]

        # ── Step 4: Accumulate into output ──
        output[start:end] += frame_signal

    # Normalize to prevent clipping
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.95

    if verbose:
        _print_synthesis_diagnostics(frames, output, sr)

    return output


def _print_synthesis_diagnostics(frames, output, sr):
    """Print diagnostics about vocoder resynthesis."""
    n_frames = len(frames)
    duration = len(output) / sr

    print()
    print("  ┌─ Vocoder Resynthesis Diagnostics ─────────────────────")
    print(f"  │ Frames processed: {n_frames} ({duration:.2f}s of audio)")
    print(f"  │ Excitation breakdown:")
    n_voiced = sum(1 for f in frames if f.voiced)
    print(f"  │   Pulse train (voiced): {n_voiced} frames ({100*n_voiced/n_frames:.0f}%)")
    print(f"  │   White noise (unvoiced): {n_frames - n_voiced} frames ({100*(n_frames-n_voiced)/n_frames:.0f}%)")
    print(f"  │")
    print(f"  │ Why it sounds robotic:")
    print(f"  │   - Only {NUM_LEVELS} amplitude levels (vs ~65,000 in 16-bit audio)")
    print(f"  │   - Only {NUM_BANDS} frequency bands (vs ~10,000 in a spectrogram)")
    print(f"  │   - Pulse train excitation (vs complex glottal waveform)")
    print(f"  │   - {1000/FRAME_RATE:.0f}ms frame steps (vs continuous variation)")
    print(f"  └──────────────────────────────────────────────────────")
    print()


# ============================================================================
# FRAME ↔ ARRAY CONVERSION (FOR ENCRYPTION)
# ============================================================================

def frames_to_array(frames):
    """Convert vocoder frames to numpy arrays for encryption.

    The encryption module operates on arrays of integers, not VocoderFrame
    objects. This function extracts the quantized values into arrays that
    can be fed into the one-time pad encryption.

    Returns:
        bands:    (n_frames, 10) int array — band levels, each 0-5
        pitch:    (n_frames,) int array — pitch levels, each 0-35
        voiced:   (n_frames,) bool array — voiced/unvoiced flags
        max_vals: (n_frames,) float array — normalization factors
    """
    bands = np.array([f.band_levels for f in frames])
    pitch = np.array([f.pitch_level for f in frames])
    voiced = np.array([f.voiced for f in frames])
    max_vals = np.array([f.band_max for f in frames])
    return bands, pitch, voiced, max_vals


def array_to_frames(bands, pitch, voiced, max_vals):
    """Reconstruct VocoderFrame list from arrays (after decryption).

    This is the inverse of frames_to_array. After decryption recovers
    the original integer parameters, this rebuilds VocoderFrame objects
    that can be fed into the synthesizer.
    """
    frames = []
    for i in range(len(bands)):
        f = VocoderFrame()
        f.band_levels = bands[i]
        f.pitch_level = pitch[i]
        f.voiced = voiced[i]
        f.band_max = max_vals[i]
        frames.append(f)
    return frames


# ============================================================================
# STANDALONE CLI
# ============================================================================

if __name__ == '__main__':
    import sys
    import soundfile as sf

    if len(sys.argv) < 3:
        print("Usage: python -m sigsaly.vocoder input.wav output.wav")
        print()
        print("Analyzes speech with the SIGSALY vocoder and resynthesizes it.")
        print("The output will sound robotic but intelligible — this is the")
        print("characteristic 'SIGSALY sound' heard by Churchill and Roosevelt.")
        print()
        print("Examples:")
        print("  python -m sigsaly.vocoder input/speech.wav output/vocoded.wav")
        sys.exit(1)

    data, sr = sf.read(sys.argv[1])
    if len(data.shape) > 1:
        data = data[:, 0]

    print(f"SIGSALY Vocoder")
    print(f"  Input: {sys.argv[1]} ({len(data)/sr:.2f}s, {sr} Hz)")

    print(f"\nAnalyzing...")
    frames = analyze(data, sr, verbose=True)

    print(f"Resynthesizing...")
    output = synthesize(frames, sr, verbose=True)

    sf.write(sys.argv[2], output, sr)
    print(f"  Output: {sys.argv[2]}")
