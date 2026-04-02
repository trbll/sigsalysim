"""
Telephone Line Simulation
=========================
Simulates what voice sounded like over a 1940s long-distance analog
telephone line. This is the baseline for everything in the SIGSALY story:
all audio — whether original, scrambled, or encrypted — traveled over
lines like this. The enemy could tap these lines and hear whatever was sent.

Historical context:
  Transatlantic calls in the 1940s traveled via radio links and undersea
  cables, passing through multiple vacuum-tube amplifier/repeater stations.
  Each station added slight noise and nonlinear distortion. The usable
  bandwidth was limited to about 300-3400 Hz (the "telephone bandwidth"
  standard that persisted into the digital age).

Signal processing chain:
  1. Bandpass filter (300-3400 Hz) — removes frequencies outside phone bandwidth
  2. Soft-clipping distortion — simulates tube amplifier repeater stations
  3. Additive white Gaussian noise — simulates line noise (hiss/crackle)
  4. Normalization — prevents digital clipping in the output file

Key concepts for students:
  - Bandwidth limitation: frequencies below 300 Hz and above 3400 Hz are
    simply gone. This is why phone calls sound "thin" compared to in-person.
  - SNR (Signal-to-Noise Ratio): measured in decibels (dB). Every 10 dB
    increase means noise power is 10x lower. A 1940s long-distance line
    might have 25-35 dB SNR; a modern digital line is >60 dB.
  - Distortion: vacuum tubes introduce "soft clipping" — a gentle
    compression of loud peaks. Sounds warm at low levels, muddy at high.
"""

import numpy as np
from scipy.signal import butter, sosfilt


def bandpass_telephone(signal, sr, low=300, high=3400, order=5):
    """Apply the standard telephone bandwidth bandpass filter.

    Telephones only transmit frequencies between ~300 Hz and ~3400 Hz.
    Everything below (deep bass, chest resonance) and above (sibilance,
    high harmonics) is stripped out. This is why voices on the phone
    sound recognizable but noticeably different from in person.

    Args:
        signal: Input audio samples (1D numpy array)
        sr:     Sample rate in Hz (e.g., 22050)
        low:    Lower cutoff frequency in Hz (standard: 300)
        high:   Upper cutoff frequency in Hz (standard: 3400)
        order:  Filter steepness (higher = sharper cutoff, 5 is typical)

    Returns:
        Bandpass-filtered signal (same length as input)

    Technical note:
        We use a Butterworth IIR filter (maximally flat passband) in
        second-order sections (SOS) form for numerical stability. This
        is the standard approach in audio DSP.
    """
    sos = butter(order, [low, high], btype='band', fs=sr, output='sos')
    return sosfilt(sos, signal)


def add_line_noise(signal, snr_db=30):
    """Add white Gaussian noise at a specified Signal-to-Noise Ratio.

    White noise has equal energy at all frequencies — it sounds like a
    constant hiss. On a real 1940s phone line, noise came from thermal
    fluctuations in the wire, atmospheric interference on radio links,
    and imperfect amplifier stages.

    The SNR formula:
        noise_power = signal_power / 10^(snr_db/10)

    So at 30 dB SNR, noise power is 1/1000th of signal power.
    At 20 dB, noise power is 1/100th (10x more audible).
    At 10 dB, noise power is 1/10th (very noisy, hard to understand).

    Args:
        signal: Input audio samples
        snr_db: Desired signal-to-noise ratio in decibels
                  40 dB = very clean (good modern line)
                  30 dB = typical 1940s domestic long-distance
                  25 dB = typical 1940s transatlantic
                  20 dB = poor connection
                  10 dB = barely usable

    Returns:
        Signal with added noise (same length)
    """
    # Measure the average power (energy per sample) of the signal
    signal_power = np.mean(signal ** 2)

    # Calculate the required noise power from the SNR definition:
    #   SNR_dB = 10 * log10(signal_power / noise_power)
    #   noise_power = signal_power / 10^(SNR_dB / 10)
    noise_power = signal_power / (10 ** (snr_db / 10))

    # Generate Gaussian (normal distribution) noise with the target power.
    # The standard deviation of the noise equals sqrt(noise_power) because
    # for zero-mean Gaussian noise, power = variance = std_dev^2.
    noise = np.random.normal(0, np.sqrt(noise_power), len(signal))

    return signal + noise


def tube_distortion(signal, drive=0.3):
    """Simulate mild soft-clipping from vacuum tube repeater stations.

    Long-distance calls in the 1940s passed through chains of vacuum-tube
    amplifiers ("repeaters") spaced along the transmission path. Each tube
    stage introduces slight nonlinear distortion — loud peaks get gently
    compressed while quiet passages pass through mostly unchanged.

    We model this with a hyperbolic tangent (tanh) function, which is a
    classic soft-clipper: linear for small inputs, smoothly saturating
    for large inputs. This is the same principle behind "tube warmth"
    in audio equipment.

    The math:
        output = tanh(input * (1 + drive)) / tanh(1 + drive)

    The division by tanh(1 + drive) normalizes the output so that a
    unit-amplitude input still produces roughly unit-amplitude output.

    Args:
        signal: Input audio samples
        drive:  Distortion intensity (0 = clean, 0.3 = subtle, 0.8 = heavy)
                0.2 is realistic for a chain of well-maintained repeaters.

    Returns:
        Distorted signal (same length)
    """
    return np.tanh(signal * (1 + drive)) / np.tanh(1 + drive)


def simulate_telephone_line(signal, sr, snr_db=30, drive=0.2, verbose=False):
    """Full 1940s long-distance telephone line simulation.

    Applies the complete signal degradation chain that any signal would
    experience traveling over a wartime long-distance connection:
    bandpass filtering, tube distortion, and line noise.

    Args:
        signal:  Input audio (numpy array, mono, float values in [-1, 1])
        sr:      Sample rate in Hz
        snr_db:  Signal-to-noise ratio in dB (25-35 typical for 1940s)
        drive:   Tube distortion amount (0 = none, 0.2 = realistic)
        verbose: If True, print diagnostic information

    Returns:
        Signal as it would sound over a 1940s long-distance phone line
    """
    # ── Step 1: Bandpass to telephone bandwidth ──
    # This removes all frequencies outside 300-3400 Hz. For speech,
    # this strips out the low rumble and high sibilance, leaving the
    # core intelligibility range intact but sounding "tinny."
    out = bandpass_telephone(signal, sr)

    # ── Step 2: Tube repeater distortion ──
    # Subtle soft-clipping from vacuum tube amplifier stages.
    # At drive=0.2, this is barely perceptible but contributes to
    # the characteristic "vintage telephone" quality.
    out = tube_distortion(out, drive=drive)

    # ── Step 3: Line noise ──
    # Additive white Gaussian noise simulating thermal noise,
    # atmospheric interference, and amplifier hiss.
    out = add_line_noise(out, snr_db=snr_db)

    # ── Step 4: Normalize ──
    # Prevent digital clipping by scaling the output so the loudest
    # sample reaches 95% of full scale.
    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / peak * 0.95

    if verbose:
        _print_diagnostics(signal, out, sr, snr_db, drive)

    return out


def _print_diagnostics(original, processed, sr, snr_db, drive):
    """Print quantitative diagnostics about the telephone simulation.

    This helps students understand exactly what changed and by how much.
    """
    print()
    print("  ┌─ Telephone Line Diagnostics ──────────────────────────")

    # Bandwidth reduction
    from scipy.signal import welch
    freqs_orig, psd_orig = welch(original, sr, nperseg=1024)
    freqs_proc, psd_proc = welch(processed, sr, nperseg=1024)

    # Energy outside telephone band in original
    total_energy_orig = np.sum(psd_orig)
    in_band_mask = (freqs_orig >= 300) & (freqs_orig <= 3400)
    in_band_energy_orig = np.sum(psd_orig[in_band_mask])
    lost_pct = (1 - in_band_energy_orig / total_energy_orig) * 100 if total_energy_orig > 0 else 0

    print(f"  │ Bandwidth: 300-3400 Hz (telephone standard)")
    print(f"  │ Energy lost to bandpass filter: {lost_pct:.1f}% of original spectrum")
    print(f"  │ Line noise: SNR = {snr_db} dB (noise power is 1/{10**(snr_db/10):.0f}th of signal)")
    print(f"  │ Tube distortion: drive = {drive} ({'subtle' if drive < 0.3 else 'noticeable' if drive < 0.6 else 'heavy'})")

    # Correlation between original and processed (similarity measure)
    min_len = min(len(original), len(processed))
    correlation = np.corrcoef(original[:min_len], processed[:min_len])[0, 1]
    print(f"  │ Signal correlation with original: {correlation:.4f} (1.0 = identical)")
    print(f"  │")
    print(f"  │ Why it sounds different: the bandpass filter removes low bass")
    print(f"  │ and high frequencies, making speech sound 'thin.' The noise adds")
    print(f"  │ a constant background hiss. The distortion subtly compresses peaks.")
    print(f"  └──────────────────────────────────────────────────────")
    print()


if __name__ == '__main__':
    import sys
    import soundfile as sf

    if len(sys.argv) < 3:
        print("Usage: python -m sigsaly.telephone input.wav output.wav [snr_db]")
        print()
        print("Simulates a 1940s long-distance telephone line.")
        print("  snr_db: Signal-to-noise ratio (default: 30, range: 10-40)")
        print()
        print("Examples:")
        print("  python -m sigsaly.telephone input/speech.wav output/phone.wav")
        print("  python -m sigsaly.telephone input/speech.wav output/noisy.wav 20")
        sys.exit(1)

    data, sr = sf.read(sys.argv[1])
    if len(data.shape) > 1:
        data = data[:, 0]

    snr = float(sys.argv[3]) if len(sys.argv) > 3 else 30

    print(f"Telephone Line Simulation")
    print(f"  Input:  {sys.argv[1]} ({len(data)/sr:.2f}s, {sr} Hz)")
    print(f"  SNR:    {snr} dB")

    result = simulate_telephone_line(data, sr, snr_db=snr, verbose=True)

    sf.write(sys.argv[2], result, sr)
    print(f"  Output: {sys.argv[2]}")
