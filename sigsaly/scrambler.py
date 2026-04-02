"""
Simplified A-3-Style Frequency Inversion Scrambler
====================================================
A simplified model of the pre-SIGSALY scrambling approach used by the Allies.
The real wartime A-3 was a more complex multi-band system that split audio
into several bands and shuffled/inverted them. This simulator uses a single
carrier frequency inversion to demonstrate the core vulnerability: speech
spectral structure survives scrambling and can be recovered by analysis.

Historical context:
  The A-3 was used by the Allies for sensitive phone calls, including
  transatlantic conversations between Washington and London. It sounds
  completely unintelligible to a casual listener — like garbled alien speech.

  However, the Germans were routinely cracking A-3 communications by 1941
  at listening stations including one in the Netherlands. Whether the real
  multi-band A-3 or this simplified single-carrier model, the fundamental
  problem is the same: the statistical properties of speech survive the
  transformation, making it vulnerable to spectral analysis.

  This vulnerability directly motivated the development of SIGSALY.

How frequency inversion works:
  The mathematical operation is amplitude modulation (AM):

    scrambled(t) = signal(t) * cos(2π * f_carrier * t)

  This multiplies the signal by a cosine wave at the carrier frequency.
  In the frequency domain, this shifts ("translates") the spectrum both
  up and down by f_carrier. A lowpass filter then removes the upper copy,
  leaving only the frequency-inverted version.

  Crucially, the operation is its own inverse: applying it twice with the
  same carrier frequency recovers the original signal. This means the
  "decryption key" is identical to the "encryption key" — just the carrier
  frequency. There is only one parameter to guess, and speech has such
  distinctive spectral characteristics that finding it is trivial.

Why this matters for security:
  Frequency inversion is "security through obscurity." The algorithm is
  simple, the key space is tiny (just one frequency value), and the
  statistical properties of speech survive the transformation. This is the
  textbook example of why obscurity != security.
"""

import numpy as np
from scipy.signal import butter, sosfilt


def frequency_inversion(signal, sr, carrier_freq=2000):
    """Invert the frequency spectrum around a carrier frequency.

    This is the core operation of the A-3 scrambler. It flips the spectrum:
    a tone at (carrier - X) Hz becomes a tone at X Hz, and vice versa.

    For example, with carrier_freq=2000:
      - A 500 Hz tone becomes 1500 Hz (= 2000 - 500)
      - A 200 Hz tone becomes 1800 Hz (= 2000 - 200)
      - A 1800 Hz tone becomes 200 Hz (= 2000 - 1800)

    Step-by-step:
      1. Multiply signal by cos(2π * carrier * t)
         → This creates two copies of the spectrum: one shifted UP by
           carrier_freq, and one shifted DOWN (and mirrored/inverted).
      2. Lowpass filter at carrier_freq
         → This keeps only the down-shifted (inverted) copy and removes
           the up-shifted one.
      3. Normalize to prevent clipping.

    The operation is self-inverse: scramble(scramble(x)) ≈ x

    Args:
        signal:       Input audio (1D numpy array, mono)
        sr:           Sample rate in Hz
        carrier_freq: Frequency to invert around (Hz).
                      The A-3 used values around 2000-3000 Hz.
                      This single number is the entire "secret key."

    Returns:
        Frequency-inverted signal (same length as input)
    """
    # Create a time axis (one value per sample)
    t = np.arange(len(signal)) / sr

    # Step 1: Amplitude modulation — multiply signal by cosine carrier.
    # In the frequency domain, this creates sum and difference frequencies.
    # If the signal has energy at frequency f, the modulated signal has
    # energy at (carrier + f) and (carrier - f). The (carrier - f) component
    # is the frequency-inverted version we want.
    modulated = signal * np.cos(2 * np.pi * carrier_freq * t)

    # Step 2: Lowpass filter to isolate the inverted baseband.
    # We keep only frequencies below the carrier, discarding the upper
    # sideband (carrier + f). A 6th-order Butterworth gives a sharp enough
    # cutoff to cleanly separate the two.
    cutoff = min(carrier_freq, sr / 2 - 100)  # Stay below Nyquist
    sos = butter(6, cutoff, btype='low', fs=sr, output='sos')
    inverted = sosfilt(sos, modulated)

    # Step 3: Normalize amplitude to prevent clipping
    peak = np.max(np.abs(inverted))
    if peak > 0:
        inverted = inverted / peak * 0.95

    return inverted


def scramble(signal, sr, carrier_freq=2000):
    """Scramble audio using A-3 frequency inversion.

    This is the "encryption" step — what the Allied operators did before
    transmitting a phone call. The result sounds like garbled noise to
    anyone who doesn't know the carrier frequency.

    Args:
        signal:       Input speech audio
        sr:           Sample rate
        carrier_freq: Secret carrier frequency (the "key")

    Returns:
        Scrambled audio
    """
    return frequency_inversion(signal, sr, carrier_freq)


def unscramble(signal, sr, carrier_freq=2000):
    """Unscramble audio — identical to scrambling.

    Frequency inversion is its own inverse (it's an "involution"):
      invert(invert(x)) = x

    This means the same hardware/software can be used at both ends.
    It also means that if you know the algorithm, you only need to
    find one number (the carrier frequency) to break it.

    Args:
        signal:       Scrambled audio
        sr:           Sample rate
        carrier_freq: Must match the carrier used for scrambling

    Returns:
        Recovered (unscrambled) audio
    """
    return frequency_inversion(signal, sr, carrier_freq)


def crack_by_spectral_analysis(scrambled_signal, sr, freq_range=(1500, 3500),
                                steps=50, verbose=False):
    """Automated cracking of A-3 scrambler by spectral analysis.

    This simulates what the Germans did with spectrum analyzers to
    break Allied A-3 communications. The approach exploits the fact that
    human speech has very distinctive spectral characteristics:

    1. Most energy is concentrated in low frequencies (100-1000 Hz)
    2. Energy falls off roughly as 1/f (higher frequencies have less energy)
    3. Clear formant peaks from vowel resonances

    These properties survive frequency inversion — they just get flipped.
    By trying different carrier frequencies and scoring how "speech-like"
    the result looks, we can find the correct carrier automatically.

    Scoring method:
      For each candidate carrier frequency, we compute:
        - Spectral centroid: the "center of mass" of the frequency spectrum.
          Speech has a low centroid (~500-800 Hz). Random noise has a high
          centroid (near Nyquist/2).
        - Spectral variance: speech has distinctive peaks (formants) that
          create high variance. Noise is relatively flat (low variance).
        - Combined score = variance / centroid — high variance + low
          centroid = speech-like.

    Args:
        scrambled_signal: The intercepted scrambled audio
        sr:               Sample rate
        freq_range:       Range of carrier frequencies to search (Hz)
        steps:            Number of frequencies to test (more = finer search)
        verbose:          Print diagnostic information

    Returns:
        (best_carrier_freq, recovered_signal, all_scores)
        where all_scores is a list of (frequency, score) tuples
    """
    test_freqs = np.linspace(freq_range[0], freq_range[1], steps)
    scores = []

    for freq in test_freqs:
        # Try this carrier frequency: invert the scrambled signal
        candidate = frequency_inversion(scrambled_signal, sr, freq)

        # Compute the frequency spectrum (magnitude only)
        spectrum = np.abs(np.fft.rfft(candidate))
        freqs = np.fft.rfftfreq(len(candidate), 1 / sr)

        # Spectral centroid: energy-weighted average frequency.
        # For speech, this should be LOW (most energy in low frequencies).
        # For noise or wrongly-inverted audio, this will be HIGHER.
        centroid = np.sum(freqs * spectrum) / (np.sum(spectrum) + 1e-10)

        # Spectral variance in the voice band (<4000 Hz).
        # Speech has high variance due to formant peaks and valleys.
        # Noise or incorrect inversions have flatter, lower-variance spectra.
        spectral_var = np.var(spectrum[freqs < 4000])

        # Combined score: we want HIGH variance and LOW centroid.
        score = spectral_var / (centroid + 1)
        scores.append(score)

    # The best carrier frequency is the one that produced the most
    # speech-like spectral characteristics
    best_idx = np.argmax(scores)
    best_freq = test_freqs[best_idx]
    recovered = frequency_inversion(scrambled_signal, sr, best_freq)

    if verbose:
        _print_crack_diagnostics(test_freqs, scores, best_freq, best_idx)

    return best_freq, recovered, list(zip(test_freqs, scores))


def _print_crack_diagnostics(test_freqs, scores, best_freq, best_idx):
    """Print detailed diagnostics about the cracking process."""
    scores_arr = np.array(scores)
    sorted_indices = np.argsort(scores_arr)[::-1]

    print()
    print("  ┌─ A-3 Cracking Diagnostics ───────────────────────────")
    print(f"  │ Search range: {test_freqs[0]:.0f} - {test_freqs[-1]:.0f} Hz ({len(test_freqs)} candidates)")
    print(f"  │ Best carrier found: {best_freq:.0f} Hz (score: {scores_arr[best_idx]:.6f})")
    print(f"  │")
    print(f"  │ Top 5 candidates:")
    for rank, idx in enumerate(sorted_indices[:5]):
        marker = " ◄── BEST" if idx == best_idx else ""
        print(f"  │   {rank+1}. {test_freqs[idx]:7.1f} Hz  (score: {scores_arr[idx]:.6f}){marker}")
    print(f"  │")

    # How confident is the result? Compare best to second-best
    if len(sorted_indices) > 1:
        best_score = scores_arr[sorted_indices[0]]
        second_score = scores_arr[sorted_indices[1]]
        ratio = best_score / (second_score + 1e-10)
        print(f"  │ Confidence: best/2nd-best ratio = {ratio:.2f}x")
        if ratio > 2.0:
            print(f"  │ → HIGH confidence (clear winner)")
        elif ratio > 1.3:
            print(f"  │ → MEDIUM confidence (likely correct)")
        else:
            print(f"  │ → LOW confidence (ambiguous — might need finer search)")

    print(f"  │")
    print(f"  │ Why this works: speech has a characteristic spectral shape")
    print(f"  │ (low centroid, high variance from formant peaks). Only the")
    print(f"  │ correct carrier frequency produces this shape. The entire")
    print(f"  │ 'key space' is just one continuous parameter — trivial to search.")
    print(f"  └──────────────────────────────────────────────────────")
    print()


if __name__ == '__main__':
    import sys
    import soundfile as sf

    if len(sys.argv) < 4:
        print("Usage: python -m sigsaly.scrambler <mode> input.wav output.wav [carrier_freq]")
        print()
        print("Modes:")
        print("  scramble    — Apply A-3 frequency inversion")
        print("  unscramble  — Reverse A-3 (requires knowing the carrier freq)")
        print("  crack       — Automatically find the carrier and recover speech")
        print()
        print("Examples:")
        print("  python -m sigsaly.scrambler scramble input/speech.wav output/scrambled.wav 2000")
        print("  python -m sigsaly.scrambler crack output/scrambled.wav output/cracked.wav")
        sys.exit(1)

    mode = sys.argv[1]
    data, sr = sf.read(sys.argv[2])
    if len(data.shape) > 1:
        data = data[:, 0]

    if mode == 'scramble':
        carrier = float(sys.argv[4]) if len(sys.argv) > 4 else 2000
        print(f"A-3 Frequency Inversion Scrambler")
        print(f"  Input:   {sys.argv[2]} ({len(data)/sr:.2f}s, {sr} Hz)")
        print(f"  Carrier: {carrier} Hz (this is the entire 'secret key')")

        result = scramble(data, sr, carrier)
        sf.write(sys.argv[3], result, sr)

        print(f"  Output:  {sys.argv[3]}")
        print()
        print(f"  The scrambled audio sounds garbled, but the ONLY secret is the")
        print(f"  carrier frequency ({carrier} Hz). An attacker just needs to try")
        print(f"  different frequencies until speech appears — typically seconds")
        print(f"  of work with a spectrum analyzer.")

    elif mode == 'unscramble':
        carrier = float(sys.argv[4]) if len(sys.argv) > 4 else 2000
        print(f"A-3 Unscrambler (known carrier)")
        print(f"  Input:   {sys.argv[2]}")
        print(f"  Carrier: {carrier} Hz")

        result = unscramble(data, sr, carrier)
        sf.write(sys.argv[3], result, sr)
        print(f"  Output:  {sys.argv[3]}")

    elif mode == 'crack':
        print(f"A-3 Cracker — Automated Spectral Analysis")
        print(f"  Input: {sys.argv[2]} ({len(data)/sr:.2f}s)")
        print(f"  Searching for carrier frequency...")

        best_freq, recovered, scores = crack_by_spectral_analysis(
            data, sr, verbose=True
        )

        sf.write(sys.argv[3], recovered, sr)
        print(f"  Recovered audio: {sys.argv[3]}")
        print()
        print(f"  The A-3 scrambler has been broken. The attacker now hears")
        print(f"  the original speech. This is exactly what the Germans did,")
        print(f"  which is why SIGSALY was developed as a replacement.")
