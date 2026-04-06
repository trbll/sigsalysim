"""
Web Pipeline Orchestration
==========================
Calls the same sigsaly/* modules as the CLI pipeline, but returns
structured data (dicts) instead of printing to stdout. This is what
the Flask app calls to generate all outputs for a given input audio.
"""

import os
import sys
import uuid
import time
import shutil
import tempfile
import numpy as np
import soundfile as sf

# Ensure sigsaly package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigsaly.telephone import simulate_telephone_line
from sigsaly.scrambler import scramble, crack_by_spectral_analysis
from sigsaly.vocoder import (
    analyze, synthesize, frames_to_array, array_to_frames,
    FRAME_RATE, NUM_BANDS, NUM_LEVELS
)
from sigsaly.encryption import (
    encrypt_vocoder_params, decrypt_vocoder_params,
    decrypt_with_offset, encrypted_to_audio
)
from sigsaly.key_generation import generate_key_record, key_to_audio

from web.spectrograms import generate_all_spectrograms


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def create_session():
    """Create a unique temp directory for this pipeline run."""
    session_id = uuid.uuid4().hex[:12]
    session_dir = os.path.join(tempfile.gettempdir(), f'sigsaly_{session_id}')
    os.makedirs(session_dir, exist_ok=True)
    return session_id, session_dir


def cleanup_old_sessions(max_age_seconds=3600):
    """Remove session directories older than max_age_seconds."""
    tmp = tempfile.gettempdir()
    for name in os.listdir(tmp):
        if name.startswith('sigsaly_'):
            path = os.path.join(tmp, name)
            try:
                if time.time() - os.path.getmtime(path) > max_age_seconds:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass


# ============================================================================
# HELPERS
# ============================================================================

def _save_wav(signal, sr, session_dir, filename):
    """Save audio and return metadata."""
    path = os.path.join(session_dir, filename)
    sf.write(path, signal, sr)
    duration = len(signal) / sr
    peak_db = round(float(20 * np.log10(np.max(np.abs(signal)) + 1e-10)), 1)
    return {'filename': filename, 'duration': round(duration, 2), 'peak_db': peak_db}


def _correlation(a, b):
    """Pearson correlation between two signals."""
    min_len = min(len(a), len(b))
    if min_len == 0:
        return 0.0
    return round(float(np.corrcoef(a[:min_len], b[:min_len])[0, 1]), 4)


def _telephone(signal, sr, snr_db=22):
    """Apply telephone line simulation."""
    return simulate_telephone_line(signal, sr, snr_db=snr_db)


def _tip(term, explanation):
    """Create an HTML tooltip span for use in stage descriptions."""
    return (f'<span class="tooltip">{term}'
            f'<span class="tooltip-text">{explanation}</span></span>')


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_web_pipeline(input_wav_path, params=None):
    """Run the full SIGSALY pipeline and return structured results."""
    params = params or {}
    snr_db = params.get('snr_db', 22)
    carrier_freq = params.get('carrier_freq', 2000)
    desync_offsets = params.get('desync_offsets', [1, 5, 25])
    key_seed = params.get('key_seed', 42)

    session_id, session_dir = create_session()

    # Load and normalize input
    data, sr = sf.read(input_wav_path)
    if len(data.shape) > 1:
        data = data[:, 0]
    data = data / (np.max(np.abs(data)) + 1e-10) * 0.95

    source_info = {
        'samples': len(data),
        'sr': sr,
        'duration': round(len(data) / sr, 2),
        'nyquist': sr // 2
    }

    audio_signals = {}
    stages = []

    # ── STAGE 0: Original Voice ─────────────────────────────────
    telephone_data = _telephone(data, sr, snr_db)
    meta_0a = _save_wav(data, sr, session_dir, '0a_original.wav')
    meta_0b = _save_wav(telephone_data, sr, session_dir, '0b_original_telephone.wav')
    audio_signals['0a_original.wav'] = (data, 'Original (clean)')
    audio_signals['0b_original_telephone.wav'] = (telephone_data, 'Original (over HF radio)')

    corr_telephone = _correlation(data, telephone_data)
    stages.append({
        'id': 0,
        'title': 'The Problem: Open Lines',
        'description': (
            'During WWII, Allied leaders needed to coordinate across the Atlantic '
            '-- but long-distance phone calls traveled over '
            + _tip('HF radio', 'Transatlantic voice calls used high-frequency (shortwave) radio '
                   'bounced off the ionosphere. Undersea cables existed but could only carry '
                   'telegraph pulses — the first transatlantic telephone cable (TAT-1) wasn\'t '
                   'laid until 1956. Radio signals could be intercepted by anyone with a '
                   'receiver tuned to the right frequency.')
            + ' that anyone could intercept. Here\'s the original voice, and what it sounded like '
            'after traveling over a 1940s HF radio link: '
            + _tip('bandlimited', 'A bandpass filter removes all frequencies outside a range. '
                   'Telephone lines only carried 300-3400 Hz -- enough for speech intelligibility, '
                   'but it strips out the deep bass and crisp high frequencies, making voices sound "thin."')
            + ' to 300-3400 Hz, '
            'degraded by '
            + _tip('tube amplifier distortion', 'Long-distance calls passed through chains of vacuum tube '
                   'amplifier "repeaters" spaced along the line. Each tube adds slight nonlinear distortion -- '
                   'loud peaks get gently compressed. Think of it like a photocopy of a photocopy.')
            + f', and buried under noise (SNR = {snr_db} dB). '
            'Distorted, but perfectly intelligible. An eavesdropper on the line hears everything.'
        ),
        'outputs': [
            {**meta_0a, 'label': 'Original (clean)', 'spectrogram': '0a_original.png'},
            {**meta_0b, 'label': f'Over HF radio (SNR={snr_db} dB)', 'spectrogram': '0b_original_telephone.png'},
        ],
        'diagnostics': {
            'correlation_telephone': corr_telephone,
            'text': (
                f'Signal correlation (original vs over-the-air): {corr_telephone}\n'
                f'SNR: {snr_db} dB (noise power is 1/{10**(snr_db/10):.0f}th of signal)\n'
                f'Bandwidth: 300-3400 Hz (voice channel standard)'
            ),
        }
    })

    # ── STAGE 1: A-3 Scrambler ──────────────────────────────────
    scrambled = scramble(data, sr, carrier_freq)
    scrambled_tel = _telephone(scrambled, sr, snr_db)
    meta_1a = _save_wav(scrambled, sr, session_dir, '1a_a3_scrambled.wav')
    meta_1b = _save_wav(scrambled_tel, sr, session_dir, '1b_a3_scrambled_telephone.wav')
    audio_signals['1a_a3_scrambled.wav'] = (scrambled, 'A-3 Scrambled')
    audio_signals['1b_a3_scrambled_telephone.wav'] = (scrambled_tel, 'A-3 Scrambled (wire)')

    best_freq, cracked, scores = crack_by_spectral_analysis(scrambled, sr)
    cracked_tel = _telephone(cracked, sr, snr_db)
    meta_1c = _save_wav(cracked, sr, session_dir, '1c_a3_cracked.wav')
    meta_1d = _save_wav(cracked_tel, sr, session_dir, '1d_a3_cracked_telephone.wav')
    audio_signals['1c_a3_cracked.wav'] = (cracked, 'A-3 CRACKED')
    audio_signals['1d_a3_cracked_telephone.wav'] = (cracked_tel, 'A-3 Cracked (wire)')

    corr_scrambled = _correlation(data, scrambled)
    corr_cracked = _correlation(data, cracked)
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)[:5]

    stages.append({
        'id': 1,
        'title': 'First Attempt: A-3 Scrambler',
        'description': (
            'The Allies\' first solution was the A-3 scrambler. The real wartime A-3 was a '
            'multi-band system; this simulator models the core idea with a simplified '
            + _tip('frequency inversion', 'Multiplying a signal by a cosine wave at the carrier frequency '
                   'flips the spectrum: a 500 Hz tone becomes (carrier - 500) Hz. It\'s like looking at '
                   'a photo negative -- everything is reversed, but the structure is preserved. '
                   'The real A-3 split audio into multiple bands and shuffled/inverted them, but '
                   'the fundamental vulnerability was the same.')
            + f' demo (carrier = {carrier_freq} Hz). '
            'Listen to the scrambled audio: it sounds like garbled alien noise. '
            'Surely no one could understand that? '
            'But the Germans could. By 1941, they were routinely cracking A-3 calls using '
            + _tip('spectral analysis', 'Examining the frequency content of a signal over time. '
                   'Speech has a very distinctive spectral "fingerprint" -- most energy below 1000 Hz, '
                   'clear formant peaks from vowel resonances, and a 1/f energy rolloff. These patterns '
                   'survive scrambling transformations that preserve spectral structure.')
            + '. Whether the real multi-band A-3 or our simplified one-carrier demo, the core problem '
            'is the same: the spectral structure of speech survives the transformation. '
            'Speech has such distinctive '
            + _tip('formant patterns', 'Formants are resonant frequencies of the vocal tract. '
                   'Different vowels have different formant patterns (e.g., "ee" has formants around '
                   '270 and 2300 Hz, "ah" around 730 and 1090 Hz). These patterns create recognizable '
                   'peaks in the spectrogram that persist through any structure-preserving scramble.')
            + ' that an analyst can recover the original. '
            'Listen to the cracked output -- the speech is recovered. The A-3 was '
            + _tip('security through obscurity', 'A system that relies on keeping its method secret '
                   'rather than on mathematical guarantees. If the attacker learns how the system works '
                   '(which they always eventually do), the security evaporates. Modern cryptography '
                   'follows Kerckhoffs\'s principle: the system should be secure even if everything '
                   'about it is public knowledge, except the key.')
            + ', and it had failed. The Allies needed something fundamentally different.'
        ),
        'output_groups': [
            {
                'heading': 'What the Allies sent (scrambled)',
                'outputs': [
                    {**meta_1a, 'label': 'A-3 Scrambled', 'spectrogram': '1a_a3_scrambled.png'},
                    {**meta_1b, 'label': 'Scrambled (over HF radio)', 'spectrogram': '1b_a3_scrambled_telephone.png'},
                ],
            },
            {
                'heading': 'What the Germans recovered (cracked)',
                'outputs': [
                    {**meta_1c, 'label': 'A-3 CRACKED', 'spectrogram': '1c_a3_cracked.png'},
                    {**meta_1d, 'label': 'Cracked (over HF radio)', 'spectrogram': '1d_a3_cracked_telephone.png'},
                ],
            },
        ],
        'outputs': [],
        'diagnostics': {
            'carrier_freq_actual': carrier_freq,
            'carrier_freq_found': round(best_freq),
            'correlation_scrambled': corr_scrambled,
            'correlation_cracked': corr_cracked,
            'text': (
                f'Carrier frequency used: {carrier_freq} Hz\n'
                f'Carrier found by cracker: {best_freq:.0f} Hz\n'
                f'Top candidates: {", ".join(f"{f:.0f} Hz" for f, _ in sorted_scores)}\n'
                f'Correlation (original vs scrambled): {corr_scrambled}\n'
                f'Correlation (original vs cracked): {corr_cracked}\n'
                f'\nHistorical context:\n'
                f'  The Germans operated listening stations (including one in the\n'
                f'  Netherlands) that intercepted and broke A-3 calls in real time.\n'
                f'  The real A-3 was more complex than this demo (multi-band shuffling),\n'
                f'  but the vulnerability was the same: speech structure survived.\n'
                f'\n'
                f'How this simulator models the crack:\n'
                f'  Our automated cracker tries {len(sorted_scores)*10} carrier frequencies and\n'
                f'  scores each for speech-likeness (low spectral centroid + high spectral\n'
                f'  variance = speech). The exact frequency doesn\'t need to match\n'
                f'  perfectly -- close enough recovers intelligible speech.'
            ),
        }
    })

    # ── STAGE 2: Vocoder ────────────────────────────────────────
    frames = analyze(data, sr)
    vocoded = synthesize(frames, sr)
    vocoded_tel = _telephone(vocoded, sr, snr_db)
    meta_2a = _save_wav(vocoded, sr, session_dir, '2a_vocoder.wav')
    meta_2b = _save_wav(vocoded_tel, sr, session_dir, '2b_vocoder_telephone.wav')
    audio_signals['2a_vocoder.wav'] = (vocoded, 'Vocoder')
    audio_signals['2b_vocoder_telephone.wav'] = (vocoded_tel, 'Vocoder (wire)')

    n_voiced = sum(1 for f in frames if f.voiced)
    corr_vocoded = _correlation(data, vocoded)
    bands, pitch, voiced, max_vals = frames_to_array(frames)

    level_counts = {lv: int(np.sum(bands == lv)) for lv in range(NUM_LEVELS)}
    total_values = bands.size
    compression_ratio = source_info["sr"] / (12 * FRAME_RATE)

    stages.append({
        'id': 2,
        'title': 'The Key Insight: Digitize First',
        'description': (
            'The A-3 failed because it scrambled the '
            + _tip('analog waveform', 'A continuous signal -- the raw audio wave with infinite '
                   'possible amplitude values at each instant. You can\'t do modular arithmetic '
                   'on a continuous wave. Digitization converts it to discrete numbers.')
            + ' -- the spectral shape of speech survived the transformation. SIGSALY\'s breakthrough was to '
            'first DIGITIZE the speech using a '
            + _tip('vocoder', '"Voice coder" -- invented by Homer Dudley at Bell Labs in 1939. '
                   'It models speech as a source (vocal cords vibrating or turbulent air) filtered '
                   'through a shape (the vocal tract). By capturing just the filter shape and source '
                   'parameters, it compresses speech dramatically.')
            + ' ("voice coder"). The vocoder '
            f'splits audio into {NUM_BANDS} '
            + _tip('frequency bands', 'Like an equalizer on a stereo: each band captures the energy '
                   'in a slice of the frequency spectrum. Band 1 covers 250-500 Hz (deep vowel sounds), '
                   'band 10 covers 2700-2950 Hz (crisp consonants like "s" and "t"). Together they '
                   'capture the spectral "shape" of speech.')
            + f' and measures the energy in each, {FRAME_RATE} times per second. Each measurement is '
            + _tip('quantized', 'Rounding a continuous value to the nearest discrete level. Like '
                   'rounding 3.7 to 4. With only 6 levels, each step is coarse (~4.3 dB), which '
                   'is why vocoded speech sounds "robotic." But 6 levels is enough for intelligibility '
                   'and -- critically -- small enough for modular arithmetic encryption.')
            + f' to just {NUM_LEVELS} discrete levels (0-5) using '
            + _tip('companding', 'COMpressing + exPANDING: a nonlinear quantization scheme that gives '
                   'finer resolution to quiet signals (where human hearing is most sensitive) and coarser '
                   'resolution to loud signals. The same principle used in telephone PCM systems '
                   '(mu-law in North America, A-law in Europe).')
            + '. The result sounds robotic but is '
            'perfectly intelligible -- and crucially, it\'s now a stream of small integers '
            'that can be encrypted with mathematics.'
        ),
        'outputs': [
            {**meta_2a, 'label': 'Vocoder', 'spectrogram': '2a_vocoder.png'},
            {**meta_2b, 'label': 'Vocoder (wire)', 'spectrogram': '2b_vocoder_telephone.png'},
        ],
        'diagnostics': {
            'n_frames': len(frames),
            'n_voiced': n_voiced,
            'n_unvoiced': len(frames) - n_voiced,
            'compression_ratio': f'{compression_ratio:.0f}:1',
            'correlation_vocoded': corr_vocoded,
            'level_distribution': level_counts,
            'text': (
                f'Frames: {len(frames)} at {FRAME_RATE} fps ({len(frames)/FRAME_RATE:.2f}s)\n'
                f'Voiced: {n_voiced}/{len(frames)} ({100*n_voiced/len(frames):.0f}%), '
                f'Unvoiced: {len(frames)-n_voiced}/{len(frames)} ({100*(len(frames)-n_voiced)/len(frames):.0f}%)\n'
                f'Compression: {compression_ratio:.0f}:1 '
                f'({source_info["sr"]} samples/sec -> {12*FRAME_RATE} values/sec)\n'
                f'Quantization: {NUM_LEVELS} levels per band ({NUM_BANDS} bands)\n'
                f'Level distribution: {", ".join(f"L{k}={v}" for k,v in level_counts.items())}\n'
                f'Correlation (original vs vocoded): {corr_vocoded}\n'
                f'\nThe robotic quality comes from coarse quantization ({NUM_LEVELS} levels\n'
                f'vs ~65,000 in 16-bit audio) and simplified excitation (pulse train\n'
                f'instead of real glottal waveform).'
            ),
        }
    })

    # ── STAGE 3: The Key Record ─────────────────────────────────
    key_duration = len(data) / sr + 5
    key = generate_key_record(key_duration, seed=key_seed)
    key_audio = key_to_audio(key, sr=sr)

    meta_3e = _save_wav(key_audio, sr, session_dir, '3e_key_record_audio.wav')
    audio_signals['3e_key_record_audio.wav'] = (key_audio, 'Key Record (vinyl)')

    key_n_frames = key['metadata']['n_frames']
    key_n_values = key_n_frames * NUM_BANDS + key_n_frames

    stages.append({
        'id': 3,
        'title': 'The Key: Vinyl Records of Random Noise',
        'description': (
            'To encrypt the vocoder\'s integer stream, SIGSALY needed a source of '
            + _tip('true randomness', 'Not pseudorandom (algorithmically generated, deterministic) '
                   'but physically random -- derived from an unpredictable natural process. '
                   'Pseudorandom generators like those in computers follow a pattern that could '
                   'theoretically be predicted if you knew the seed. True randomness has no seed, '
                   'no pattern, no way to predict the next value.')
            + '. Bell Labs generated noise using '
            + _tip('mercury-vapor vacuum tubes', 'Large glass tubes filled with mercury vapor. When '
                   'heated, the mercury ionizes and creates a plasma. The thermal motion of ions '
                   'produces electrical noise that is genuinely random -- governed by quantum '
                   'mechanical processes that are fundamentally unpredictable. This was state-of-the-art '
                   'random number generation in the 1940s.')
            + ' -- the thermal chaos of hot ionized gas, sampled and quantized into '
            'values from 0 to 5. This noise was recorded onto '
            + _tip('vinyl phonograph records', 'Standard 33 1/3 RPM records, but instead of music, '
                   'the grooves encoded random noise values. Each record held 12 minutes of key material. '
                   'Think of it as a physical random number table -- except read by a turntable at '
                   '50 values per second instead of by a human.')
            + '. Identical copies were pressed and shipped '
            'by armed military courier to each terminal -- one for Washington, one for London. '
            'Used records were destroyed immediately. Listen to what a key record '
            'sounded like: pure noise. No pattern, no structure -- just randomness. '
            'This is the physical embodiment of a '
            + _tip('one-time pad', 'A provably unbreakable encryption scheme where each message '
                   'value is masked by a random key value. "One-time" because each key value is used '
                   'for exactly one message value and then discarded. Reusing key values (a "two-time pad") '
                   'allows an attacker to cancel out the key by subtracting two ciphertexts.')
            + '.'
        ),
        'outputs': [
            {**meta_3e, 'label': 'Key record (vinyl sound)', 'spectrogram': '3e_key_record_audio.png'},
        ],
        'diagnostics': {
            'text': (
                f'Key record: {key_n_frames} frames at {FRAME_RATE} fps '
                f'({key["metadata"]["duration_seconds"]:.1f}s)\n'
                f'Encrypted streams: {NUM_BANDS} band keys (mod {NUM_LEVELS}) + 1 pitch key (mod 36)\n'
                f'Total key values: {key_n_values:,} '
                f'({key_n_frames} frames x ({NUM_BANDS} bands + 1 pitch))\n'
                f'Each value: independently, uniformly random\n'
                f'Note: the voiced/unvoiced flag is not encrypted in this simulator\n'
                f'\nThree requirements for unbreakable encryption (all must hold):\n'
                f'  1. Key must be truly random (SIGSALY: vacuum tube thermal noise)\n'
                f'  2. Key must be at least as long as the message (12-min records)\n'
                f'  3. Key must never be reused (records destroyed after use)\n'
                + (f'\nDemo note: this run uses seed={key_seed} for reproducible results.\n'
                   f'Real SIGSALY used physical noise with no seed -- truly unpredictable.'
                   if key_seed is not None else
                   f'\nThis run uses unseeded randomness (no fixed seed) -- closer to how\n'
                   f'real SIGSALY generated keys from physical vacuum tube noise.')
            ),
        }
    })

    # ── STAGE 4: Encryption ─────────────────────────────────────
    enc_bands, enc_pitch = encrypt_vocoder_params(bands, pitch, key)
    encrypted_audio = encrypted_to_audio(enc_bands, enc_pitch, voiced, sr)
    encrypted_tel = _telephone(encrypted_audio, sr, snr_db)

    meta_4a = _save_wav(encrypted_audio, sr, session_dir, '4a_sigsaly_encrypted.wav')
    meta_4b = _save_wav(encrypted_tel, sr, session_dir, '4b_sigsaly_encrypted_telephone.wav')
    audio_signals['4a_sigsaly_encrypted.wav'] = (encrypted_audio, 'SIGSALY Encrypted')
    audio_signals['4b_sigsaly_encrypted_telephone.wav'] = (encrypted_tel, 'Encrypted (wire)')

    corr_encrypted = _correlation(data, encrypted_audio)
    enc_level_counts = {lv: int(np.sum(enc_bands == lv)) for lv in range(NUM_LEVELS)}
    enc_correlation = round(float(np.corrcoef(
        bands.flatten().astype(float), enc_bands.flatten().astype(float)
    )[0, 1]), 4)

    stages.append({
        'id': 4,
        'title': 'Encryption: Vocoder + Key = Noise',
        'description': (
            'Now SIGSALY combines the two pieces. For each vocoder parameter (a number '
            'from 0 to 5), it subtracts the corresponding key value using '
            + _tip('modular arithmetic', 'Arithmetic that "wraps around" like a clock. Mod 6 means '
                   'the result always stays in the range 0-5. If you go below 0, you wrap to the top: '
                   '-1 mod 6 = 5, -2 mod 6 = 4. Think of a clock with 6 hours instead of 12. '
                   'This is sometimes called "clock arithmetic."')
            + ': encrypted = (voice - key) mod 6. For example, if the voice level is 3 and the '
            'key value is 5: (3 - 5) mod 6 = -2 mod 6 = 4. The encrypted value (4) reveals '
            'nothing about the original (3) because the key (5) is '
            + _tip('uniformly random', 'Each value 0-5 is equally likely (probability 1/6). '
                   'This means the encrypted value is also uniformly distributed, regardless '
                   'of what the original speech value was. There is no statistical pattern '
                   'for an attacker to exploit -- the encrypted stream looks identical whether '
                   'the speaker said "hello" or stayed silent.')
            + ' and unknown to the eavesdropper. Listen to the result -- the encrypted output is '
            'pure noise. Compare its '
            + _tip('spectrogram', 'A visual representation of frequency content over time. The '
                   'x-axis is time, y-axis is frequency, and color intensity is energy. Speech shows '
                   'clear horizontal bands (formants) and vertical gaps (silences). Encrypted audio '
                   'shows uniform color -- no structure at all.')
            + ' to the original: no speech structure remains. This is what '
            'gets transmitted over HF radio.'
        ),
        'outputs': [
            {**meta_4a, 'label': 'Encrypted (eavesdropper hears)', 'spectrogram': '4a_sigsaly_encrypted.png'},
            {**meta_4b, 'label': 'Encrypted (over HF radio)', 'spectrogram': '4b_sigsaly_encrypted_telephone.png'},
        ],
        'diagnostics': {
            'correlation_encrypted': corr_encrypted,
            'original_encrypted_correlation': enc_correlation,
            'encrypted_distribution': enc_level_counts,
            'text': (
                f'Correlation (original vs encrypted audio): {corr_encrypted} (should be ~0.0)\n'
                f'Correlation (original params vs encrypted params): {enc_correlation}\n'
                f'Encrypted level distribution: {", ".join(f"L{k}={v}" for k,v in enc_level_counts.items())}\n'
                f'  (Should be ~uniform: ~{total_values//NUM_LEVELS} each)\n'
                f'\nThe encrypted values are uniformly distributed -- every level (0-5)\n'
                f'appears with roughly equal frequency, regardless of what the original\n'
                f'speech contained. This is the hallmark of good encryption.'
            ),
        }
    })

    # ── STAGE 5: Decryption ─────────────────────────────────────
    # In real SIGSALY, the FSK demodulator recovers the discrete integer
    # parameters from the noisy radio signal. Because the levels are discrete
    # (0-5), moderate noise doesn't corrupt them — the demodulator snaps to
    # the nearest level. So decryption operates on clean parameters.
    dec_bands, dec_pitch = decrypt_vocoder_params(enc_bands, enc_pitch, key)
    dec_frames = array_to_frames(dec_bands, dec_pitch, voiced[:len(dec_bands)], max_vals[:len(dec_bands)])
    decrypted = synthesize(dec_frames, sr)

    # The "over HF radio" version simulates what the final audio sounded
    # like through the receiver's local equipment — adding the characteristic
    # radio-quality degradation to the vocoded output.
    decrypted_radio = _telephone(decrypted, sr, snr_db)

    meta_5a = _save_wav(decrypted, sr, session_dir, '5a_sigsaly_decrypted.wav')
    meta_5b = _save_wav(decrypted_radio, sr, session_dir, '5b_sigsaly_decrypted_telephone.wav')
    audio_signals['5a_sigsaly_decrypted.wav'] = (decrypted, 'SIGSALY Decrypted')
    audio_signals['5b_sigsaly_decrypted_telephone.wav'] = (decrypted_radio, 'Decrypted (radio quality)')

    band_match = bool(np.array_equal(dec_bands, bands[:len(dec_bands)]))
    pitch_match = bool(np.array_equal(dec_pitch, pitch[:len(dec_pitch)]))

    # Compare decrypted audio to what was sent (vocoded audio from Stage 2)
    corr_decrypted_vs_vocoded = _correlation(decrypted, vocoded)
    # Also compare to the original (will be lower — vocoder is lossy)
    corr_decrypted_vs_original = _correlation(decrypted, data)

    stages.append({
        'id': 5,
        'title': 'Decryption: Recovering the Voice',
        'description': (
            'At the receiving terminal in London, the '
            + _tip('identical copy', 'Bit-for-bit identical. Both records were pressed from the '
                   'same master at the manufacturing facility. Any difference between the sender\'s '
                   'and receiver\'s key -- even a single value off -- would cause that frame to '
                   'decrypt incorrectly. This is why key distribution was a military-grade logistics operation.')
            + ' of the vinyl key record plays in perfect synchronization. Decryption is '
            'simply the '
            + _tip('inverse operation', 'Encryption subtracts the key (mod 6), so decryption adds '
                   'it back (mod 6). Subtraction and addition are inverses in modular arithmetic, '
                   'just like in regular math: if x - 5 = 4, then 4 + 5 = x. The modular wrap-around '
                   'doesn\'t change this -- (3 - 5) mod 6 = 4, and (4 + 5) mod 6 = 3.')
            + ': add the key value back. decrypted = (encrypted + key) mod 6. Continuing the '
            'example: (4 + 5) mod 6 = 9 mod 6 = 3 -- the original value is recovered '
            'exactly. The decrypted parameters are fed into the vocoder\'s '
            + _tip('resynthesizer', 'The decoder half of the vocoder. It takes the numerical '
                   'parameters (band amplitudes + pitch) and generates audible audio: a pulse train '
                   '(for voiced sounds like vowels) or white noise (for unvoiced sounds like "s"), '
                   'filtered through the 10 frequency bands at the specified amplitudes.')
            + ', which reconstructs audible speech. Listen: the voice is back, with the '
            'characteristic robotic quality of vocoded audio. This is what Churchill and '
            'Roosevelt actually heard during their secure wartime conversations.'
        ),
        'outputs': [
            {**meta_5a, 'label': 'Decrypted (correct key)', 'spectrogram': '5a_sigsaly_decrypted.png'},
            {**meta_5b, 'label': 'Decrypted (radio quality)', 'spectrogram': '5b_sigsaly_decrypted_telephone.png'},
        ],
        'diagnostics': {
            'roundtrip_bands': band_match,
            'roundtrip_pitch': pitch_match,
            'correlation_decrypted_vs_vocoded': corr_decrypted_vs_vocoded,
            'correlation_decrypted_vs_original': corr_decrypted_vs_original,
            'text': (
                f'Roundtrip verification:\n'
                f'  Band levels:  {"PERFECT -- every value matches" if band_match else "FAILED"}\n'
                f'  Pitch levels: {"PERFECT -- every value matches" if pitch_match else "FAILED"}\n'
                f'  Total values checked: {total_values} bands + {len(pitch)} pitch = {total_values + len(pitch)}\n'
                f'\nAudio waveform similarity:\n'
                f'  Decrypted vs vocoded (Stage 2):  {corr_decrypted_vs_vocoded}\n'
                f'  Decrypted vs original (Stage 0): {corr_decrypted_vs_original}\n'
                f'\n  Why isn\'t decrypted-vs-vocoded closer to 1.0? The vocoder\n'
                f'  PARAMETERS are recovered perfectly (verified above), but the audio\n'
                f'  waveform differs because the resynthesizer uses random white noise\n'
                f'  for unvoiced sounds ("s", "f", "sh"). Each synthesis run generates\n'
                f'  different noise samples, so the waveforms aren\'t identical even\n'
                f'  though they sound the same to human ears. This is the nature of\n'
                f'  parametric coding: the parameters are exact, the rendering varies.\n'
                f'  (Listen to both -- they should sound essentially identical.)'
            ),
        }
    })

    # ── STAGE 6: Cracking Attempt ───────────────────────────────
    _, crack_attempt, _ = crack_by_spectral_analysis(encrypted_audio, sr)
    meta_6a = _save_wav(crack_attempt, sr, session_dir, '6a_sigsaly_a3crack_attempt.wav')
    audio_signals['6a_sigsaly_a3crack_attempt.wav'] = (crack_attempt, 'A-3 Crack on SIGSALY (FAILS)')

    corr_crack_attempt = _correlation(data, crack_attempt)

    stages.append({
        'id': 6,
        'title': 'Why It\'s Unbreakable',
        'description': (
            'What if the Germans applied their spectral analysis technique to SIGSALY? '
            'Listen: it fails completely. With A-3, the spectral shape of speech survived '
            'the transformation (just mirrored), so there was a pattern to find. With the '
            'one-time pad, each encrypted value is '
            + _tip('statistically independent', 'Knowing one encrypted value tells you nothing '
                   'about the next one, or about the original value. This is because each key value '
                   'is independently random. Compare to A-3, where the relationship between '
                   'adjacent frequencies is preserved -- that\'s the pattern the Germans exploited.')
            + ' of the original -- '
            f'the key has {key_n_values:,} independently random values, compared to the '
            'tiny structured key space of scrambling systems like A-3. '
            + _tip('Claude Shannon', 'The father of information theory. His 1949 paper '
                   '"Communication Theory of Secrecy Systems" laid the mathematical foundations '
                   'of cryptography. He proved that perfect secrecy requires a key at least as '
                   'long as the message -- exactly what SIGSALY provides with its vinyl records.')
            + ' proved in 1949 that a one-time pad achieves '
            + _tip('"perfect secrecy"', 'Formally: P(message | ciphertext) = P(message). '
                   'In plain English: seeing the encrypted output does not change your belief '
                   'about what the original message might be. Every possible original message '
                   'is equally consistent with the ciphertext. No algorithm, no matter how '
                   'powerful, can narrow down the possibilities.')
            + ': knowing the '
            + _tip('ciphertext', 'The encrypted output -- what the eavesdropper intercepts. '
                   'In SIGSALY, this is the stream of encrypted vocoder parameters (the noise '
                   'you heard in Stage 4). The corresponding unencrypted data is called the "plaintext."')
            + ' tells you literally nothing about the message, even with infinite computing power.'
        ),
        'outputs': [
            {**meta_6a, 'label': 'A-3 crack attempt (FAILS)', 'spectrogram': '6a_sigsaly_a3crack_attempt.png'},
        ],
        'diagnostics': {
            'correlation_crack_attempt': corr_crack_attempt,
            'text': (
                f'Correlation (original vs crack attempt): {corr_crack_attempt}\n'
                f'Compare to successful A-3 crack: {corr_cracked}\n'
                f'\nThe spectral analysis technique that broke A-3 finds nothing here.\n'
                f'There is no single parameter to guess -- the key has {key_n_values:,}\n'
                f'independent random values. Brute-forcing all possibilities would\n'
                f'require trying {NUM_LEVELS}^{key_n_values} combinations -- a number\n'
                f'far larger than the atoms in the observable universe.\n'
                f'\nSee: Shannon, C.E. (1949). "Communication Theory of Secrecy Systems."\n'
                f'https://pages.cs.wisc.edu/~rist/642-spring-2014/shannon-secrecy.pdf'
            ),
        }
    })

    # ── STAGE 7: Clock Desynchronization ────────────────────────
    desync_outputs = []
    desync_table = []
    correct_total = int(np.sum(dec_bands == bands[:len(dec_bands)]))
    frame_duration_ms = 1000 / FRAME_RATE

    for offset in desync_offsets:
        desync_bands, desync_pitch = decrypt_with_offset(
            enc_bands, enc_pitch, key, frame_offset=offset
        )
        desync_frames = array_to_frames(
            desync_bands, desync_pitch,
            voiced[:len(desync_bands)], max_vals[:len(desync_bands)]
        )
        desync_audio = synthesize(desync_frames, sr)

        plural = 's' if offset > 1 else ''
        filename = f'7_desync_{offset}frame{plural}.wav'
        time_ms = offset * 1000 // FRAME_RATE
        label = f'Desync: {offset} frame{plural} ({time_ms}ms)'

        meta = _save_wav(desync_audio, sr, session_dir, filename)
        audio_signals[filename] = (desync_audio, label)

        match = int(np.sum(desync_bands == bands[:len(desync_bands)]))
        match_pct = round(100 * match / total_values, 1)

        desync_outputs.append({
            **meta, 'label': label,
            'spectrogram': filename.replace('.wav', '.png')
        })
        desync_table.append({
            'offset': offset, 'time_ms': time_ms,
            'match': match, 'total': total_values, 'pct': match_pct
        })

    random_chance = round(100 / NUM_LEVELS, 1)

    sep = '-' * 20
    desync_text_lines = [
        f'What is a "frame"?\n'
        f'  The vocoder samples speech {FRAME_RATE} times per second.\n'
        f'  1 frame = 1/{FRAME_RATE}th of a second = {frame_duration_ms:.0f} milliseconds.\n'
        f'  That\'s roughly the duration of a single consonant sound.\n',
        f'{"Offset":<20} {"Correct":>8} {"Accuracy":>10} {"Random Chance":>14}',
        f'{sep} {sep[:8]} {sep[:10]} {sep[:14]}',
        f'{"0 (perfect sync)":<20} {correct_total:>8} {"100.0%":>10} {"--":>14}',
    ]
    for row in desync_table:
        label = f'{row["offset"]} frame(s) ({row["time_ms"]}ms)'
        desync_text_lines.append(
            f'{label:<20} {row["match"]:>8} {row["pct"]:>9.1f}% {f"~{random_chance}%":>14}'
        )
    desync_text_lines.append(
        f'\nAll offsets converge to ~{random_chance}% accuracy = random chance (1/{NUM_LEVELS}).\n'
        f'Whether the turntable is off by {frame_duration_ms:.0f}ms or 2 full seconds,\n'
        f'the result is equally useless. The one-time pad is all-or-nothing.'
    )

    stages.append({
        'id': 7,
        'title': 'The Engineering Challenge: Synchronization',
        'description': (
            'The one-time pad is mathematically perfect -- but it demands perfect logistics. '
            'Both terminals must play their vinyl key records at exactly the same speed, '
            'starting at exactly the same moment. The vocoder produces one '
            + _tip('frame', 'One complete set of vocoder parameters, produced 50 times per second '
                   '(every 20 milliseconds). Each frame contains 10 band amplitudes and a pitch value '
                   'that are encrypted, plus a voiced/unvoiced flag that is carried separately. '
                   'The key record supplies one matching set of random values per frame.')
            + f' every {frame_duration_ms:.0f} milliseconds ({FRAME_RATE} frames per second). If the '
            'receiver\'s turntable '
            + _tip('drifts', 'In practice, clocks and turntable motors are never perfectly precise. '
                   'Crystal oscillators drift by a few parts per million. Over a 12-minute conversation, '
                   'even 1 ppm of clock error accumulates to ~0.7ms -- approaching 1/30th of a frame. '
                   'SIGSALY used matched precision clocks to keep drift below this threshold.')
            + ' by even a single frame, it reads the wrong key value '
            'for that frame and every frame after it. Since adjacent key values are '
            'independently random, using the wrong one is no better than using a completely '
            'different key. Listen to what happens with increasing misalignment: 1 frame '
            f'({frame_duration_ms:.0f}ms) sounds just as destroyed as 25 frames '
            f'({25 * frame_duration_ms:.0f}ms). '
            'This is why SIGSALY required '
            + _tip('precision time-of-day clocks', 'High-accuracy quartz crystal clocks synchronized '
                   'to a reference time standard. Both terminals had to agree on exactly when to start '
                   'playing each record. The clocks had to maintain synchronization over the full '
                   '12-minute record duration without drifting by more than a fraction of a frame.')
            + ' at both terminals, '
            'and why the complete system weighed over 50 tons and filled 40 equipment racks. '
            'The '
            + _tip('key management problem', 'The practical challenge of creating, copying, '
                   'distributing, synchronizing, and destroying encryption keys. SIGSALY\'s key '
                   'management was a massive logistics operation: manufacturing records, armed courier '
                   'transport across the Atlantic, secure storage, precise playback timing, and '
                   'immediate destruction after use. This same fundamental challenge exists in all '
                   'encryption systems today -- the math may be easy, but managing the keys is hard.')
            + ' -- manufacturing, duplicating, shipping by armed courier, '
            'synchronizing playback, and destroying used records -- was as critical to security '
            'as the mathematics.'
        ),
        'outputs': desync_outputs,
        'diagnostics': {
            'desync_table': desync_table,
            'random_chance_pct': random_chance,
            'text': '\n'.join(desync_text_lines),
        }
    })

    # ── Generate all spectrograms ───────────────────────────────
    spectrogram_map = generate_all_spectrograms(audio_signals, sr, session_dir)

    # ── Summary ─────────────────────────────────────────────────
    summary = {
        'a3_crack_correlation': corr_cracked,
        'sigsaly_encrypted_correlation': corr_encrypted,
        'sigsaly_crack_attempt_correlation': corr_crack_attempt,
        'roundtrip_perfect': band_match and pitch_match,
    }

    # ── Modern Security Context ──────────────────────────────────
    modern_security = {
        'title': 'From SIGSALY to Modern Cryptography',
        'intro': (
            'SIGSALY was a landmark -- the first system to achieve provably secure voice '
            'communication. Many of the concepts it pioneered in 1943 remain foundational '
            'to how we secure communications today. Here\'s what carried forward, what '
            'changed, and how it connects to the cryptography you encounter every day.'
        ),
        'sections': [
            {
                'heading': 'What\'s Still the Same',
                'text': (
                    '<strong>Digitize, then encrypt.</strong> SIGSALY\'s core insight -- '
                    'convert analog information to digital form before encrypting -- is exactly '
                    'what every modern system does. Your phone call, text message, and web '
                    'browsing all follow this pattern: digitize the data, then apply mathematical '
                    'encryption to the resulting numbers.'
                    '<br><br>'
                    '<strong>Key management is still the hardest problem.</strong> SIGSALY needed '
                    'armed couriers and vinyl records. Today we use '
                    + _tip('key exchange protocols', 'Algorithms like Diffie-Hellman (1976) that '
                           'allow two parties to establish a shared secret key over an insecure '
                           'channel -- without ever transmitting the key itself. This solved SIGSALY\'s '
                           'biggest logistical problem: you no longer need a physical courier.')
                    + ', but the fundamental challenge remains: both parties need the same secret, '
                    'and keeping secrets is hard.'
                    '<br><br>'
                    '<strong>Modular arithmetic is everywhere.</strong> SIGSALY\'s mod-6 operation '
                    'is a simple case of the same mathematical structure underlying '
                    + _tip('AES', 'Advanced Encryption Standard (2001). The most widely used symmetric '
                           'encryption algorithm today. It operates on 128-bit blocks using modular arithmetic '
                           'in GF(2^8) -- a finite field, which is the same concept as SIGSALY\'s mod-6 but '
                           'with a much larger number space. AES is used in HTTPS, Wi-Fi (WPA2/3), disk '
                           'encryption, VPNs, and virtually every secure system.')
                    + ', '
                    + _tip('RSA', 'Rivest-Shamir-Adleman (1977). A public-key encryption algorithm based '
                           'on modular exponentiation with very large primes. The "public-key" innovation '
                           'means you can encrypt a message for someone using their PUBLIC key, and only '
                           'their PRIVATE key can decrypt it -- no shared secret needed. This would have '
                           'eliminated SIGSALY\'s courier problem entirely.')
                    + ', and virtually all modern cryptography.'
                ),
            },
            {
                'heading': 'What Changed',
                'text': (
                    '<strong>One-time pads gave way to '
                    + _tip('symmetric-key algorithms', 'Encryption where the same key is used for both '
                           'encryption and decryption (like SIGSALY). Modern symmetric algorithms (AES, '
                           'ChaCha20) use short, reusable keys (128-256 bits) instead of SIGSALY\'s '
                           'message-length one-time pads. They\'re not provably unbreakable like a true '
                           'one-time pad, but they\'re computationally secure -- breaking them would '
                           'take billions of years with current technology.')
                    + '.</strong> '
                    'SIGSALY\'s one-time pad is provably unbreakable, but it requires a key as long as '
                    'the message -- impractical for modern internet traffic. AES uses a short key '
                    '(128 or 256 bits) that can encrypt unlimited data. It\'s not mathematically '
                    'perfect like a one-time pad, but breaking it would take longer than the age of '
                    'the universe.'
                    '<br><br>'
                    '<strong>'
                    + _tip('Public-key cryptography', 'Invented in the 1970s by Diffie, Hellman, Rivest, '
                           'Shamir, and Adleman. Uses a pair of mathematically linked keys: a public key '
                           '(shared openly) and a private key (kept secret). Anyone can encrypt with the '
                           'public key, but only the private key holder can decrypt. This eliminated the '
                           'need for a secure channel to exchange keys -- SIGSALY\'s biggest weakness.')
                    + ' eliminated the courier.</strong> '
                    'SIGSALY required physically shipping identical key records to both terminals. '
                    'Public-key systems (RSA, elliptic curves) let two parties establish a shared '
                    'secret over an open channel. When you visit an HTTPS website, your browser and '
                    'the server perform a key exchange in milliseconds -- no armed courier needed.'
                    '<br><br>'
                    '<strong>Vocoders evolved into modern '
                    + _tip('audio codecs', 'Algorithms that compress audio for efficient transmission. '
                           'Modern codecs (Opus, AAC, AMR) are descendants of the vocoder concept -- '
                           'parametric models of speech that transmit a compact representation rather '
                           'than the raw waveform. Your phone calls use codecs that are conceptually '
                           'similar to SIGSALY\'s vocoder, just with much higher fidelity.')
                    + '.</strong> '
                    'SIGSALY\'s 10-band, 6-level vocoder was the ancestor of modern speech codecs. '
                    'Today\'s mobile phone codecs (AMR, EVS) use the same analysis-synthesis principle '
                    'but with thousands of parameters instead of 12, producing near-transparent quality.'
                ),
            },
            {
                'heading': 'SIGSALY\'s Lasting Legacy',
                'text': (
                    'SIGSALY demonstrated three principles that remain central to security engineering:'
                    '<br><br>'
                    '<strong>1. Security must be mathematical, not obscurity-based.</strong> '
                    'The A-3 scrambler relied on hiding its method. SIGSALY\'s security came from '
                    'mathematical proof. This is now '
                    + _tip('Kerckhoffs\'s principle', 'A cryptographic system should be secure even if '
                           'everything about the system, except the key, is public knowledge. Named after '
                           'Auguste Kerckhoffs (1883). SIGSALY embodied this: even if the enemy knew '
                           'exactly how the system worked, they couldn\'t break it without the key records.')
                    + ' -- the foundation of all modern cryptography.'
                    '<br><br>'
                    '<strong>2. The weakest link is usually not the algorithm.</strong> '
                    'SIGSALY\'s math was perfect, but security depended on couriers, clocks, and '
                    'record destruction. Today, most security breaches exploit implementation flaws, '
                    'human error, or key management failures -- not the underlying algorithms.'
                    '<br><br>'
                    '<strong>3. Practical security requires engineering, not just theory.</strong> '
                    '50 tons of equipment, 40 racks, 30 kilowatts, two turntables, precision clocks, '
                    'armed couriers -- all to support an elegant mathematical idea. The gap between '
                    '"provably secure in theory" and "secure in practice" is an engineering problem, '
                    'and it\'s still the hardest part of building secure systems.'
                ),
            },
        ],
    }

    return {
        'session_id': session_id,
        'session_dir': session_dir,
        'source_info': source_info,
        'params': {
            'snr_db': snr_db,
            'carrier_freq': carrier_freq,
            'desync_offsets': desync_offsets,
            'key_seed': key_seed,
        },
        'stages': stages,
        'summary': summary,
        'modern_security': modern_security,
    }
