"""
One-Time Pad Encryption (Mod-6 Arithmetic)
===========================================
The core cryptographic operation of SIGSALY. This module implements the
one-time pad — the ONLY encryption method that is mathematically PROVABLY
unbreakable (proved by Claude Shannon in 1949).

How it works:
  Each quantized vocoder parameter is a number from 0 to 5. The key is
  also a number from 0 to 5 (chosen randomly). Encryption subtracts the
  key from the value using MODULAR arithmetic (clock arithmetic):

    encrypted = (voice_level - key_level) mod 6

  Example from the actual SIGSALY documentation:
    voice level = 3, key value = 5
    encrypted = (3 - 5) mod 6 = -2 mod 6 = 4

  Decryption adds the key back:
    decrypted = (4 + 5) mod 6 = 9 mod 6 = 3 ✓

Why is this unbreakable?
  If the key is truly random and each key value is used exactly once:
  - Every encrypted value (0-5) is equally likely regardless of the
    original voice value
  - An eavesdropper sees a stream of random numbers — there is NO
    statistical pattern to exploit
  - Even with infinite computing power, there's nothing to decode
  - This is fundamentally different from A-3 scrambling, where the
    statistical properties of speech survive the transformation

  Shannon proved that a one-time pad achieves "perfect secrecy":
    P(message | ciphertext) = P(message)
  Knowing the ciphertext tells you literally nothing about the message.

The three conditions for unbreakability (all must hold):
  1. The key must be truly random
     (SIGSALY: mercury-vapor tube thermal noise — genuinely random)
  2. The key must be at least as long as the message
     (SIGSALY: 12 minutes of key per vinyl record, matching conversation length)
  3. The key must never be reused
     (SIGSALY: records destroyed after use — "one-time" pad)

  If condition 3 is violated ("two-time pad"), an attacker can subtract
  two ciphertexts to eliminate the key:
    (m1 - k) - (m2 - k) = m1 - m2
  and now they have the difference of two messages — enough to start
  recovering both. This is why key destruction was mandatory.

Historical context:
  The name "pad" comes from pre-SIGSALY one-time pads: actual paper pads
  with random numbers, where each sheet was torn off and burned after use.
  SIGSALY's vinyl records served the same purpose, but at 50 frames/sec
  across 12 channels — far faster than any human could use a paper pad.
"""

import numpy as np
from .vocoder import NUM_LEVELS


def encrypt_bands(band_levels, band_key):
    """Encrypt vocoder band levels using the one-time pad.

    The core operation: subtract the random key value from each band level
    using modulo-6 arithmetic. This maps every integer in [0,5] to another
    integer in [0,5], but which one depends entirely on the random key.

    Mod-6 arithmetic works like a clock with 6 positions:
      0 → 1 → 2 → 3 → 4 → 5 → 0 → 1 → ...

    Subtraction wraps around: 2 - 4 = -2, and -2 mod 6 = 4.

    Example for one band, one frame:
      voice level = 3, key = 5
      encrypted = (3 - 5) % 6 = (-2) % 6 = 4

    The encrypted value (4) gives NO information about the original (3)
    because the key (5) is random and unknown to the eavesdropper.
    Any original value from 0-5 could produce the encrypted value 4,
    each with equal probability.

    Args:
        band_levels: (n_frames, n_bands) int array, values in [0, 5]
        band_key:    (n_frames, n_bands) random int array, values in [0, 5]

    Returns:
        Encrypted band levels — same shape, values in [0, 5]
    """
    n_frames = min(len(band_levels), len(band_key))
    encrypted = (band_levels[:n_frames] - band_key[:n_frames]) % NUM_LEVELS
    return encrypted


def decrypt_bands(encrypted_levels, band_key):
    """Decrypt vocoder band levels using the one-time pad.

    The inverse operation: ADD the key value (instead of subtracting).

    Example continuing from above:
      encrypted = 4, key = 5
      decrypted = (4 + 5) % 6 = 9 % 6 = 3 ✓ (matches original!)

    This only works if the receiver uses the EXACT SAME key values
    at the EXACT SAME frame positions. This is why clock synchronization
    was so critical for SIGSALY.

    Args:
        encrypted_levels: (n_frames, n_bands) encrypted int array
        band_key:         (n_frames, n_bands) key array — MUST match sender's

    Returns:
        Decrypted band levels (original values, if key matches)
    """
    n_frames = min(len(encrypted_levels), len(band_key))
    decrypted = (encrypted_levels[:n_frames] + band_key[:n_frames]) % NUM_LEVELS
    return decrypted


def encrypt_pitch(pitch_levels, pitch_key):
    """Encrypt pitch levels using mod-36 arithmetic.

    Pitch uses a larger modulus (36 instead of 6) because SIGSALY encoded
    pitch as a pair of 6-level values (6 × 6 = 36 levels), giving finer
    resolution for pitch, which human hearing is very sensitive to.

    The math is identical to band encryption, just with modulus 36.
    """
    n = min(len(pitch_levels), len(pitch_key))
    return (pitch_levels[:n] - pitch_key[:n]) % 36


def decrypt_pitch(encrypted_pitch, pitch_key):
    """Decrypt pitch levels (mod-36 addition)."""
    n = min(len(encrypted_pitch), len(pitch_key))
    return (encrypted_pitch[:n] + pitch_key[:n]) % 36


def encrypt_vocoder_params(bands, pitch, key, verbose=False):
    """Encrypt all vocoder parameters with a key record.

    This is what SIGSALY did at the sender's terminal: take the quantized
    vocoder parameters and encrypt them with the key record playing on the
    turntable, producing an encrypted data stream for transmission.

    Args:
        bands:   (n_frames, n_bands) quantized band levels from vocoder
        pitch:   (n_frames,) quantized pitch levels from vocoder
        key:     Key record dict from key_generation module
        verbose: Print encryption diagnostics

    Returns:
        (encrypted_bands, encrypted_pitch) — ready for transmission
    """
    enc_bands = encrypt_bands(bands, key['band_key'])
    enc_pitch = encrypt_pitch(pitch, key['pitch_key'])

    if verbose:
        _print_encrypt_diagnostics(bands, enc_bands, pitch, enc_pitch)

    return enc_bands, enc_pitch


def decrypt_vocoder_params(enc_bands, enc_pitch, key, verbose=False):
    """Decrypt all vocoder parameters with a key record.

    This is what SIGSALY did at the receiver's terminal: use the matching
    key record to recover the original vocoder parameters, which are then
    fed into the vocoder resynthesizer to produce audible speech.

    Args:
        enc_bands: Encrypted band levels (from transmission)
        enc_pitch: Encrypted pitch levels (from transmission)
        key:       Key record — must be the identical copy used for encryption
        verbose:   Print decryption diagnostics

    Returns:
        (decrypted_bands, decrypted_pitch) — ready for vocoder resynthesis
    """
    dec_bands = decrypt_bands(enc_bands, key['band_key'])
    dec_pitch = decrypt_pitch(enc_pitch, key['pitch_key'])

    if verbose:
        print()
        print("  ┌─ Decryption Diagnostics ─────────────────────────────")
        print(f"  │ Frames decrypted: {len(dec_bands)}")
        print(f"  │ Using matched key record (correct synchronization)")
        print(f"  │ All values recovered via: decrypted = (encrypted + key) mod 6")
        print(f"  └──────────────────────────────────────────────────────")
        print()

    return dec_bands, dec_pitch


def decrypt_with_offset(enc_bands, enc_pitch, key, frame_offset=0, verbose=False):
    """Decrypt with a timing offset — simulates clock desynchronization.

    If the receiver's vinyl record starts even slightly out of sync with
    the sender's, the wrong key values are used for every frame. The result
    is complete garbage — the decrypted values bear no relation to the
    original speech.

    This is why SIGSALY required precision time-of-day clocks at both
    terminals. The turntables had to start at EXACTLY the same moment.

    The math explains why any offset destroys the signal:
      Correct:  decrypt(frame[t]) = (enc[t] + key[t]) mod 6 = original[t]  ✓
      Offset N: decrypt(frame[t]) = (enc[t] + key[t+N]) mod 6 = ????      ✗

    Since key[t] and key[t+N] are independently random, key[t+N] has no
    relationship to key[t], so the "decrypted" value is effectively random.

    Args:
        enc_bands:    Encrypted band levels
        enc_pitch:    Encrypted pitch levels
        key:          Key record
        frame_offset: How many frames (at 50fps) the receiver is off by.
                      1 frame = 20ms. Even this small offset ruins decryption.
        verbose:      Print diagnostics

    Returns:
        (decrypted_bands, decrypted_pitch) — garbage if offset != 0
    """
    # Shift the key array by the offset amount.
    # np.roll wraps around, so key[0] becomes key[offset], etc.
    offset_band_key = np.roll(key['band_key'], frame_offset, axis=0)
    offset_pitch_key = np.roll(key['pitch_key'], frame_offset)

    dec_bands = decrypt_bands(enc_bands, offset_band_key)
    dec_pitch = decrypt_pitch(enc_pitch, offset_pitch_key)

    if verbose:
        _print_offset_diagnostics(enc_bands, dec_bands, key, frame_offset)

    return dec_bands, dec_pitch


def encrypted_to_audio(enc_bands, enc_pitch, voiced, sr):
    """Convert encrypted parameters to audible audio.

    This produces what an eavesdropper would hear if they somehow
    reconstructed audio from the encrypted data stream. Since the
    encrypted values are effectively random (thanks to the one-time pad),
    the result sounds like random vocoder noise — completely unintelligible.

    In the real SIGSALY, the encrypted values were transmitted as FSK
    (Frequency Shift Keying) tones, which would sound like a series of
    electronic warbles to anyone tapping the line. Here we take the
    encrypted parameters and run them through the vocoder resynthesizer
    to hear what the "content" of those random values sounds like.
    """
    from .vocoder import array_to_frames, synthesize
    max_vals = np.ones(len(enc_bands))
    frames = array_to_frames(enc_bands, enc_pitch, voiced, max_vals)
    return synthesize(frames, sr)


def _print_encrypt_diagnostics(orig_bands, enc_bands, orig_pitch, enc_pitch):
    """Print detailed diagnostics about the encryption process."""
    n_frames = len(enc_bands)
    n_values = enc_bands.size

    print()
    print("  ┌─ Encryption Diagnostics ─────────────────────────────")
    print(f"  │ Frames encrypted: {n_frames}")
    print(f"  │ Total values encrypted: {n_values} band + {len(enc_pitch)} pitch = {n_values + len(enc_pitch)}")
    print(f"  │")

    # Show the distribution of encrypted values (should be uniform)
    print(f"  │ Encrypted band value distribution (should be ~uniform for good encryption):")
    for lv in range(NUM_LEVELS):
        count = np.sum(enc_bands == lv)
        pct = 100 * count / n_values
        expected = 100 / NUM_LEVELS
        bar = '█' * int(pct / 2)
        print(f"  │   Level {lv}: {count:5d} ({pct:5.1f}%, expected ~{expected:.1f}%) {bar}")

    # Chi-squared test for uniformity
    observed = np.array([np.sum(enc_bands == lv) for lv in range(NUM_LEVELS)])
    expected_count = n_values / NUM_LEVELS
    chi_sq = np.sum((observed - expected_count) ** 2 / expected_count)
    print(f"  │")
    print(f"  │ Uniformity (chi-squared): {chi_sq:.2f} (lower = more uniform)")
    if chi_sq < 11.07:  # Critical value for 5 df, p=0.05
        print(f"  │ → GOOD: Distribution is statistically uniform (p > 0.05)")
    else:
        print(f"  │ → Note: Some deviation from uniform (this is OK for short messages)")

    # Correlation between original and encrypted (should be near zero)
    flat_orig = orig_bands.flatten().astype(float)
    flat_enc = enc_bands.flatten().astype(float)
    correlation = np.corrcoef(flat_orig, flat_enc)[0, 1]
    print(f"  │")
    print(f"  │ Correlation between original and encrypted: {correlation:.4f}")
    print(f"  │ (0.0 = no relationship — this is what we want)")
    print(f"  │ (For comparison, A-3 scrambling preserves spectral correlations)")
    print(f"  │")

    # Show a few example frames
    print(f"  │ Example frames (first 3):")
    for i in range(min(3, n_frames)):
        o = [int(x) for x in orig_bands[i]]
        e = [int(x) for x in enc_bands[i]]
        print(f"  │   Frame {i}: original={o} → encrypted={e}")

    print(f"  │")
    print(f"  │ Shannon's perfect secrecy: each encrypted value is equally")
    print(f"  │ likely to be any number 0-5, regardless of the original.")
    print(f"  │ An eavesdropper learns NOTHING from the encrypted stream.")
    print(f"  └──────────────────────────────────────────────────────")
    print()


def _print_offset_diagnostics(enc_bands, dec_bands, key, frame_offset):
    """Print diagnostics about clock desynchronization effects."""
    # To measure accuracy, we'd need the original — use the correct key
    # to decrypt and compare
    correct = decrypt_bands(enc_bands, key['band_key'])
    n_values = dec_bands.size
    match = np.sum(dec_bands == correct[:len(dec_bands)])
    match_pct = 100 * match / n_values
    expected_random = 100 / NUM_LEVELS  # ~16.7% for random chance

    print()
    print("  ┌─ Clock Desync Diagnostics ───────────────────────────")
    print(f"  │ Frame offset: {frame_offset} frames ({frame_offset * 1000 / 50:.0f}ms)")
    print(f"  │ Values matching correct decryption: {match}/{n_values} ({match_pct:.1f}%)")
    print(f"  │ Random chance would give: ~{expected_random:.1f}%")

    if frame_offset == 0:
        print(f"  │ → PERFECT: No offset, all values correct!")
    elif match_pct < expected_random * 1.5:
        print(f"  │ → CATASTROPHIC: Accuracy is at random chance level.")
        print(f"  │   The one-time pad turns misalignment into complete noise.")
    else:
        print(f"  │ → DEGRADED: Some accidental matches, but speech is destroyed.")

    print(f"  │")
    print(f"  │ Why: key[t] and key[t+{frame_offset}] are independently random.")
    print(f"  │ Using the wrong key position is exactly like using a wrong key.")
    print(f"  │ This is why SIGSALY needed precision clocks at both terminals.")
    print(f"  └──────────────────────────────────────────────────────")
    print()


if __name__ == '__main__':
    print("One-Time Pad Encryption — Mod-6 Arithmetic Demo")
    print("=" * 55)
    print()
    print("The complete mod-6 encryption/decryption table:")
    print("(Every cell shows: encrypted → decrypted, ✓ if roundtrip works)")
    print()
    print("        Key:  0    1    2    3    4    5")
    print("Voice  ─────────────────────────────────")
    for v in range(6):
        row = f"  {v}  │ "
        for k in range(6):
            enc = (v - k) % 6
            dec = (enc + k) % 6
            check = "✓" if dec == v else "✗"
            row += f"{enc}→{dec}{check} "
        print(row)

    print()
    print("Key insight: every column (key value) produces a different")
    print("PERMUTATION of 0-5. Without knowing the key, any encrypted")
    print("value could correspond to any original value with equal probability.")
    print()
    print("This is Shannon's 'perfect secrecy' — the ciphertext reveals")
    print("NOTHING about the plaintext. No amount of analysis can break it.")
