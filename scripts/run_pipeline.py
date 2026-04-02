#!/usr/bin/env python3
"""
SIGSALY Simulator — Full Pipeline
==================================
Runs the complete SIGSALY educational demonstration, generating audio files
at every stage of the signal processing chain. Each file lets students HEAR
the effect of each operation, while diagnostic output explains the
quantitative "why" behind what they're hearing.

Output files (all in output_dir/):

  Stage 0: Original Voice
    0a_original.wav                     — Clean source recording
    0b_original_telephone.wav           — Same voice, over 1940s phone line

  Stage 1: A-3 Frequency Inversion Scrambler (pre-SIGSALY)
    1a_a3_scrambled.wav                 — Scrambled audio (sounds garbled)
    1b_a3_scrambled_telephone.wav       — Scrambled, over phone line
    1c_a3_cracked.wav                   — German spectral analysis recovery!
    1d_a3_cracked_telephone.wav         — Cracked audio, over phone line

  Stage 2: Channel Vocoder Only (no encryption)
    2a_vocoder.wav                      — Vocoder analysis/resynthesis
    2b_vocoder_telephone.wav            — Vocoded, over phone line

  Stage 3: Full SIGSALY (Vocoder + One-Time Pad)
    3a_sigsaly_encrypted.wav            — Encrypted (what eavesdropper hears)
    3b_sigsaly_encrypted_telephone.wav  — Encrypted + phone line noise
    3c_sigsaly_decrypted.wav            — Decrypted with correct key
    3d_sigsaly_decrypted_telephone.wav  — Decrypted, over phone line

  Stage 4: Cracking Attempts
    4a_sigsaly_a3crack_attempt.wav      — A-3 method on SIGSALY (fails!)

  Stage 5: Clock Desynchronization
    5a_desync_1frame.wav                — 1 frame (20ms) offset
    5b_desync_5frames.wav               — 5 frames (100ms) offset
    5c_desync_25frames.wav              — 25 frames (500ms) offset

Usage:
    python scripts/run_pipeline.py [input.wav] [output_dir]
    python scripts/run_pipeline.py                          # uses defaults
    python scripts/run_pipeline.py my_voice.wav results/
"""

import sys
import os
import numpy as np

# Add project root to path so we can import sigsaly modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf
from sigsaly.telephone import simulate_telephone_line
from sigsaly.scrambler import scramble, crack_by_spectral_analysis
from sigsaly.vocoder import (
    analyze, synthesize, frames_to_array, array_to_frames, FRAME_RATE, NUM_BANDS
)
from sigsaly.encryption import (
    encrypt_vocoder_params, decrypt_vocoder_params,
    decrypt_with_offset, encrypted_to_audio, NUM_LEVELS
)
from sigsaly.key_generation import generate_key_record, save_key_record


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def save(signal, sr, filepath, label):
    """Save an audio file and print a summary line.

    Prints the filename, duration, and peak level so students can see
    at a glance what was generated.
    """
    sf.write(filepath, signal, sr)
    duration = len(signal) / sr
    peak_db = 20 * np.log10(np.max(np.abs(signal)) + 1e-10)
    print(f"    ↳ {label:45s} [{os.path.basename(filepath)}] ({duration:.2f}s, peak {peak_db:.1f}dB)")


def telephone_version(signal, sr, snr_db=28):
    """Apply 1940s telephone line simulation to any signal.

    Every signal — original, scrambled, encrypted, or decrypted — would
    have traveled over the same kind of noisy analog phone line. We use
    28 dB SNR, representing a decent-quality wartime long-distance link.
    """
    return simulate_telephone_line(signal, sr, snr_db=snr_db)


def correlation_between(signal_a, signal_b):
    """Compute Pearson correlation between two signals.

    Returns a value from -1 to +1:
      +1.0 = identical signals
       0.0 = no relationship (independent/random)
      -1.0 = perfectly inverted

    Useful for measuring how much one signal resembles another.
    """
    min_len = min(len(signal_a), len(signal_b))
    if min_len == 0:
        return 0.0
    a = signal_a[:min_len]
    b = signal_b[:min_len]
    return float(np.corrcoef(a, b)[0, 1])


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_pipeline(input_wav, output_dir):
    """Run the complete SIGSALY demonstration pipeline."""

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║              SIGSALY SIMULATOR — FULL PIPELINE          ║")
    print("║     WWII Secure Voice Communication (1943-1946)         ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  Input:  {input_wav}")
    print(f"  Output: {output_dir}/")
    print()

    os.makedirs(output_dir, exist_ok=True)

    # ── Load and normalize input audio ──
    data, sr = sf.read(input_wav)
    if len(data.shape) > 1:
        data = data[:, 0]  # Convert stereo to mono
    data = data / (np.max(np.abs(data)) + 1e-10) * 0.95  # Normalize to ~0 dBFS

    print(f"  Source audio: {len(data):,} samples, {sr} Hz, {len(data)/sr:.2f}s")
    print(f"  Nyquist frequency: {sr//2} Hz")
    print()


    # ══════════════════════════════════════════════════════════════
    # STAGE 0: ORIGINAL VOICE
    # ══════════════════════════════════════════════════════════════
    print("━" * 60)
    print("STAGE 0: Original Voice")
    print("━" * 60)
    print("  The starting point — what the speaker actually said.")
    print("  The telephone version shows what a listener (or eavesdropper)")
    print("  on the phone line would hear: bandlimited, noisy, slightly distorted.")
    print()

    save(data, sr, f"{output_dir}/0a_original.wav",
         "Original (clean)")
    telephone_data = telephone_version(data, sr)
    save(telephone_data, sr, f"{output_dir}/0b_original_telephone.wav",
         "Original (over the wire)")

    # Diagnostic: how much does the phone line change the signal?
    corr = correlation_between(data, telephone_data)
    print(f"\n  📊 Signal correlation (original vs telephone): {corr:.4f}")
    print(f"     The phone line preserves most speech content but adds noise and")
    print(f"     removes frequencies outside 300-3400 Hz.")
    print()


    # ══════════════════════════════════════════════════════════════
    # STAGE 1: A-3 FREQUENCY INVERSION SCRAMBLER
    # ══════════════════════════════════════════════════════════════
    print("━" * 60)
    print("STAGE 1: A-3 Frequency Inversion Scrambler")
    print("━" * 60)
    print("  The pre-SIGSALY approach. Flips the frequency spectrum around a")
    print("  carrier frequency — low sounds become high and vice versa.")
    print("  Sounds unintelligible, but the Germans cracked it routinely.")
    print()

    carrier_freq = 2000  # Hz — the single "secret" of the A-3 system
    scrambled = scramble(data, sr, carrier_freq)

    save(scrambled, sr, f"{output_dir}/1a_a3_scrambled.wav",
         "A-3 scrambled")
    save(telephone_version(scrambled, sr), sr, f"{output_dir}/1b_a3_scrambled_telephone.wav",
         "A-3 scrambled (over the wire)")

    # Diagnostic: scrambled signal statistics
    corr_scram = correlation_between(data, scrambled)
    print(f"\n  📊 Correlation (original vs scrambled): {corr_scram:.4f}")
    print(f"     The waveform looks completely different, but the SPECTRAL")
    print(f"     properties of speech (formant patterns, energy distribution)")
    print(f"     are preserved — just mirrored. This is what makes it crackable.")

    # ── German cracking ──
    print(f"\n  🔓 CRACKING: Automated spectral analysis attack...")
    print(f"     Searching carrier frequencies 1500-3500 Hz ({50} candidates)...")
    best_freq, cracked, scores = crack_by_spectral_analysis(scrambled, sr, verbose=True)

    save(cracked, sr, f"{output_dir}/1c_a3_cracked.wav",
         "A-3 CRACKED (speech recovered!)")
    save(telephone_version(cracked, sr), sr, f"{output_dir}/1d_a3_cracked_telephone.wav",
         "A-3 cracked (over the wire)")

    corr_cracked = correlation_between(data, cracked)
    print(f"  📊 Carrier found: {best_freq:.0f} Hz (actual was {carrier_freq} Hz)")
    print(f"     Correlation (original vs cracked): {corr_cracked:.4f}")
    print(f"     The cracked audio resembles the original — attack succeeded!")
    print(f"     The entire 'key space' was just one number (the carrier frequency).")
    print(f"     THIS is why SIGSALY was needed.\n")


    # ══════════════════════════════════════════════════════════════
    # STAGE 2: VOCODER (NO ENCRYPTION)
    # ══════════════════════════════════════════════════════════════
    print("━" * 60)
    print("STAGE 2: Channel Vocoder (no encryption)")
    print("━" * 60)
    print(f"  Decomposes speech into {NUM_BANDS} frequency bands + pitch, sampled {FRAME_RATE}x/sec.")
    print(f"  Each parameter quantized to just {NUM_LEVELS} levels (0-5).")
    print(f"  Sounds robotic but intelligible — the 'SIGSALY sound.'")
    print()

    # Analyze: speech → vocoder parameters
    frames = analyze(data, sr, verbose=True)
    # Resynthesize: vocoder parameters → audio
    vocoded = synthesize(frames, sr, verbose=True)

    save(vocoded, sr, f"{output_dir}/2a_vocoder.wav",
         "Vocoder resynthesis")
    save(telephone_version(vocoded, sr), sr, f"{output_dir}/2b_vocoder_telephone.wav",
         "Vocoder (over the wire)")

    corr_vocoded = correlation_between(data, vocoded)
    print(f"  📊 Correlation (original vs vocoded): {corr_vocoded:.4f}")
    print(f"     Lower than telephone ({corr:.4f}) because the vocoder is a lossy")
    print(f"     parametric model — it captures the SHAPE of speech, not the exact")
    print(f"     waveform. But it's intelligible, which is what matters.")
    print()


    # ══════════════════════════════════════════════════════════════
    # STAGE 3: FULL SIGSALY (VOCODER + ONE-TIME PAD)
    # ══════════════════════════════════════════════════════════════
    print("━" * 60)
    print("STAGE 3: Full SIGSALY (Vocoder + One-Time Pad Encryption)")
    print("━" * 60)
    print("  The complete system: vocoder digitizes speech, then each parameter")
    print("  is encrypted with a random key value using modular arithmetic.")
    print("  The encrypted stream is provably indistinguishable from random noise.")
    print()

    # ── Generate key record ("press the vinyl") ──
    key_duration = len(data) / sr + 5  # Add margin
    key = generate_key_record(key_duration, seed=42, verbose=True)
    save_key_record(key, f"{output_dir}/key_record_sender.npz")

    # ── Render the key as audio (what the vinyl record sounded like) ──
    from sigsaly.key_generation import key_to_audio
    key_audio = key_to_audio(key, sr=sr)
    save(key_audio, sr, f"{output_dir}/3e_key_record_audio.wav",
         "Key record (vinyl phonograph sound)")
    print(f"     (This is what the vinyl key record sounded like — pure noise)")

    # ── Encrypt ──
    bands, pitch, voiced, max_vals = frames_to_array(frames)
    enc_bands, enc_pitch = encrypt_vocoder_params(bands, pitch, key, verbose=True)

    # ── What the encrypted signal sounds like ──
    encrypted_audio = encrypted_to_audio(enc_bands, enc_pitch, voiced, sr)
    save(encrypted_audio, sr, f"{output_dir}/3a_sigsaly_encrypted.wav",
         "SIGSALY encrypted (eavesdropper hears)")
    save(telephone_version(encrypted_audio, sr), sr, f"{output_dir}/3b_sigsaly_encrypted_telephone.wav",
         "SIGSALY encrypted (over the wire)")

    corr_encrypted = correlation_between(data, encrypted_audio)
    print(f"  📊 Correlation (original vs encrypted audio): {corr_encrypted:.4f}")
    print(f"     Effectively zero — the encrypted signal has NO resemblance to the")
    print(f"     original speech. Compare to A-3 scrambling where spectral")
    print(f"     properties were preserved.")

    # ── Decrypt with correct key ──
    print(f"\n  🔑 Decrypting with correct key (perfect synchronization)...")
    dec_bands, dec_pitch = decrypt_vocoder_params(enc_bands, enc_pitch, key, verbose=True)
    dec_frames = array_to_frames(
        dec_bands, dec_pitch,
        voiced[:len(dec_bands)], max_vals[:len(dec_bands)]
    )
    decrypted = synthesize(dec_frames, sr)

    save(decrypted, sr, f"{output_dir}/3c_sigsaly_decrypted.wav",
         "SIGSALY decrypted (correct key)")
    save(telephone_version(decrypted, sr), sr, f"{output_dir}/3d_sigsaly_decrypted_telephone.wav",
         "SIGSALY decrypted (over the wire)")

    # Verify perfect roundtrip
    band_match = np.array_equal(dec_bands, bands[:len(dec_bands)])
    pitch_match = np.array_equal(dec_pitch, pitch[:len(dec_pitch)])
    print(f"  📊 Encryption roundtrip verification:")
    print(f"     Band levels:  {'✅ PERFECT (every value matches)' if band_match else '❌ MISMATCH'}")
    print(f"     Pitch levels: {'✅ PERFECT (every value matches)' if pitch_match else '❌ MISMATCH'}")
    print(f"     The one-time pad is perfectly reversible when the same key is used.")
    print()


    # ══════════════════════════════════════════════════════════════
    # STAGE 4: CRACKING ATTEMPT ON SIGSALY
    # ══════════════════════════════════════════════════════════════
    print("━" * 60)
    print("STAGE 4: Cracking Attempt — A-3 Method on SIGSALY")
    print("━" * 60)
    print("  What happens when the Germans try their spectral analysis technique")
    print("  on SIGSALY-encrypted audio? It should fail completely.")
    print()

    print("  🔓 Attempting A-3-style spectral analysis crack on SIGSALY...")
    _, sigsaly_crack_attempt, crack_scores = crack_by_spectral_analysis(
        encrypted_audio, sr, verbose=True
    )
    save(sigsaly_crack_attempt, sr, f"{output_dir}/4a_sigsaly_a3crack_attempt.wav",
         "A-3 crack on SIGSALY (FAILS!)")

    corr_crack_attempt = correlation_between(data, sigsaly_crack_attempt)
    print(f"  📊 Correlation (original vs crack attempt): {corr_crack_attempt:.4f}")
    print(f"     Compare to A-3 crack correlation: {corr_cracked:.4f}")
    print(f"     The crack attempt on SIGSALY produces noise, not speech.")
    print(f"     There is NO carrier frequency to find because the 'scrambling'")
    print(f"     was done with random key values, not a simple spectrum flip.")
    print()


    # ══════════════════════════════════════════════════════════════
    # STAGE 5: CLOCK DESYNCHRONIZATION
    # ══════════════════════════════════════════════════════════════
    print("━" * 60)
    print("STAGE 5: Clock Desynchronization Demo")
    print("━" * 60)
    print("  What happens when the receiver's turntable is slightly out of sync?")
    print("  Even a tiny timing error means different key values are used,")
    print("  destroying the decryption completely.")
    print()

    offsets = [
        (1,  "20ms",  'a'),
        (5,  "100ms", 'b'),
        (25, "500ms", 'c'),
    ]

    for offset, time_label, suffix in offsets:
        desync_bands, desync_pitch = decrypt_with_offset(
            enc_bands, enc_pitch, key, frame_offset=offset, verbose=True
        )
        desync_frames = array_to_frames(
            desync_bands, desync_pitch,
            voiced[:len(desync_bands)], max_vals[:len(desync_bands)]
        )
        desync_audio = synthesize(desync_frames, sr)

        plural = 's' if offset > 1 else ''
        filename = f"5{suffix}_desync_{offset}frame{plural}.wav"
        save(desync_audio, sr, f"{output_dir}/{filename}",
             f"Desync: {offset} frame{plural} ({time_label})")

    # Summary comparison table
    print(f"\n  📊 Desynchronization Summary:")
    print(f"  {'Offset':<20} {'Correct Values':<20} {'Accuracy':<12} {'Expected Random'}")
    print(f"  {'─'*20} {'─'*20} {'─'*12} {'─'*15}")

    # Correct key baseline
    correct_match = np.sum(dec_bands == bands[:len(dec_bands)])
    total = dec_bands.size
    print(f"  {'0 (perfect sync)':<20} {correct_match:>6}/{total:<13} {100*correct_match/total:>5.1f}%      —")

    for offset, time_label, _ in offsets:
        desync_b, _ = decrypt_with_offset(enc_bands, enc_pitch, key, frame_offset=offset)
        match = np.sum(desync_b == bands[:len(desync_b)])
        pct = 100 * match / desync_b.size
        print(f"  {f'{offset} frame(s) ({time_label})':<20} {match:>6}/{desync_b.size:<13} {pct:>5.1f}%      ~{100/NUM_LEVELS:.1f}%")

    print(f"\n  Key insight: all offset values hover around {100/NUM_LEVELS:.1f}% accuracy —")
    print(f"  exactly random chance (1/{NUM_LEVELS} = {100/NUM_LEVELS:.1f}%). The one-time pad makes")
    print(f"  ANY timing error equivalent to using a completely wrong key.")
    print(f"  This is why SIGSALY needed precision time-of-day clocks.")


    # ══════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════════════════════════
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                   PIPELINE COMPLETE                     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  All outputs saved to: {output_dir}/")
    print()
    print("  📀 Listening Guide:")
    print("  ┌────────┬────────────────────────────────────────────────┐")
    print("  │ Files  │ What You'll Hear                               │")
    print("  ├────────┼────────────────────────────────────────────────┤")
    print("  │ 0a/0b  │ Original voice (clean / phone line)            │")
    print("  │ 1a/1b  │ A-3 scrambled (garbled but crackable)          │")
    print("  │ 1c/1d  │ A-3 CRACKED — speech recovered by attacker!    │")
    print("  │ 2a/2b  │ Vocoder only (robotic but intelligible)        │")
    print("  │ 3a/3b  │ SIGSALY encrypted (pure random noise)          │")
    print("  │ 3c/3d  │ SIGSALY decrypted (vocoded speech restored)    │")
    print("  │ 3e     │ Key record — what the vinyl sounded like       │")
    print("  │ 4a     │ A-3 crack on SIGSALY — FAILS (still noise)     │")
    print("  │ 5a-c   │ Clock desync — even 20ms ruins decryption      │")
    print("  └────────┴────────────────────────────────────────────────┘")
    print()
    print("  📊 Security Comparison:")
    print(f"     A-3 scrambler: cracked ✗ (correlation with original: {corr_cracked:.3f})")
    print(f"     SIGSALY OTP:   secure ✓  (correlation with original: {corr_encrypted:.3f})")
    print()


if __name__ == '__main__':
    input_wav = sys.argv[1] if len(sys.argv) > 1 else 'input/sample_speech.wav'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'output'
    run_pipeline(input_wav, output_dir)
