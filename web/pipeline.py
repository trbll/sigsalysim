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


def _telephone(signal, sr, snr_db=28):
    """Apply telephone line simulation."""
    return simulate_telephone_line(signal, sr, snr_db=snr_db)


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_web_pipeline(input_wav_path, params=None):
    """Run the full SIGSALY pipeline and return structured results.

    Args:
        input_wav_path: Path to input WAV file
        params: Optional dict with:
            snr_db (float): telephone SNR, default 28
            carrier_freq (int): A-3 carrier, default 2000
            desync_offsets (list): frame offsets, default [1, 5, 25]
            key_seed (int): key generation seed, default 42

    Returns:
        Structured dict with all stages, outputs, spectrograms, and diagnostics
    """
    params = params or {}
    snr_db = params.get('snr_db', 28)
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

    # Collect all audio signals for batch spectrogram generation
    audio_signals = {}
    stages = []

    # ── STAGE 0: Original Voice ─────────────────────────────────
    telephone_data = _telephone(data, sr, snr_db)
    meta_0a = _save_wav(data, sr, session_dir, '0a_original.wav')
    meta_0b = _save_wav(telephone_data, sr, session_dir, '0b_original_telephone.wav')
    audio_signals['0a_original.wav'] = (data, 'Original (clean)')
    audio_signals['0b_original_telephone.wav'] = (telephone_data, 'Original (over the wire)')

    corr_telephone = _correlation(data, telephone_data)
    stages.append({
        'id': 0,
        'title': 'Original Voice',
        'description': (
            'The starting point — what the speaker actually said. '
            'The telephone version shows what a listener (or eavesdropper) '
            'on the phone line would hear: bandlimited to 300-3400 Hz, '
            f'with noise (SNR={snr_db} dB) and tube distortion.'
        ),
        'outputs': [
            {**meta_0a, 'label': 'Original (clean)', 'spectrogram': '0a_original.png'},
            {**meta_0b, 'label': f'Over the wire (SNR={snr_db} dB)', 'spectrogram': '0b_original_telephone.png'},
        ],
        'diagnostics': {
            'correlation_telephone': corr_telephone,
            'text': (
                f'Signal correlation (original vs telephone): {corr_telephone}\n'
                f'SNR: {snr_db} dB (noise power is 1/{10**(snr_db/10):.0f}th of signal)\n'
                f'Bandwidth: 300-3400 Hz (telephone standard)'
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

    # Crack
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
        'title': 'A-3 Frequency Inversion Scrambler',
        'description': (
            f'Flips the spectrum around a carrier frequency ({carrier_freq} Hz). '
            'Sounds garbled, but the Germans cracked it routinely via spectral analysis. '
            'The entire "key" is just one number — the carrier frequency.'
        ),
        'outputs': [
            {**meta_1a, 'label': 'A-3 Scrambled', 'spectrogram': '1a_a3_scrambled.png'},
            {**meta_1b, 'label': 'A-3 Scrambled (wire)', 'spectrogram': '1b_a3_scrambled_telephone.png'},
            {**meta_1c, 'label': 'A-3 CRACKED', 'spectrogram': '1c_a3_cracked.png'},
            {**meta_1d, 'label': 'A-3 Cracked (wire)', 'spectrogram': '1d_a3_cracked_telephone.png'},
        ],
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
                f'\nThe cracker finds the carrier by trying different frequencies\n'
                f'and scoring how "speech-like" each result sounds (low spectral\n'
                f'centroid + high variance = speech). One parameter to guess.'
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

    # Quantization level distribution
    level_counts = {lv: int(np.sum(bands == lv)) for lv in range(NUM_LEVELS)}
    total_values = bands.size

    stages.append({
        'id': 2,
        'title': 'Channel Vocoder (no encryption)',
        'description': (
            f'Decomposes speech into {NUM_BANDS} frequency bands + pitch, '
            f'sampled {FRAME_RATE}x/sec. Each parameter quantized to {NUM_LEVELS} '
            f'levels (0-5). Sounds robotic but intelligible — the "SIGSALY sound."'
        ),
        'outputs': [
            {**meta_2a, 'label': 'Vocoder', 'spectrogram': '2a_vocoder.png'},
            {**meta_2b, 'label': 'Vocoder (wire)', 'spectrogram': '2b_vocoder_telephone.png'},
        ],
        'diagnostics': {
            'n_frames': len(frames),
            'n_voiced': n_voiced,
            'n_unvoiced': len(frames) - n_voiced,
            'compression_ratio': f'{source_info["samples"] / (len(frames) * 12):.0f}:1',
            'correlation_vocoded': corr_vocoded,
            'level_distribution': level_counts,
            'text': (
                f'Frames: {len(frames)} at {FRAME_RATE} fps ({len(frames)/FRAME_RATE:.2f}s)\n'
                f'Voiced: {n_voiced}/{len(frames)} ({100*n_voiced/len(frames):.0f}%), '
                f'Unvoiced: {len(frames)-n_voiced}/{len(frames)} ({100*(len(frames)-n_voiced)/len(frames):.0f}%)\n'
                f'Compression: {source_info["samples"]//len(frames)//12 * 12}:1 '
                f'({source_info["sr"]} samples/sec → {12*FRAME_RATE} values/sec)\n'
                f'Quantization: {NUM_LEVELS} levels per band ({NUM_BANDS} bands)\n'
                f'Level distribution: {", ".join(f"L{k}={v}" for k,v in level_counts.items())}\n'
                f'Correlation (original vs vocoded): {corr_vocoded}\n'
                f'\nThe robotic quality comes from coarse quantization ({NUM_LEVELS} levels\n'
                f'vs ~65,000 in 16-bit audio) and simplified excitation (pulse train\n'
                f'instead of real glottal waveform).'
            ),
        }
    })

    # ── STAGE 3: Full SIGSALY ───────────────────────────────────
    key_duration = len(data) / sr + 5
    key = generate_key_record(key_duration, seed=key_seed)

    # Encrypt
    enc_bands, enc_pitch = encrypt_vocoder_params(bands, pitch, key)
    encrypted_audio = encrypted_to_audio(enc_bands, enc_pitch, voiced, sr)
    encrypted_tel = _telephone(encrypted_audio, sr, snr_db)

    # Decrypt with correct key
    dec_bands, dec_pitch = decrypt_vocoder_params(enc_bands, enc_pitch, key)
    dec_frames = array_to_frames(dec_bands, dec_pitch, voiced[:len(dec_bands)], max_vals[:len(dec_bands)])
    decrypted = synthesize(dec_frames, sr)
    decrypted_tel = _telephone(decrypted, sr, snr_db)

    # Key audio
    key_audio = key_to_audio(key, sr=sr)

    meta_3a = _save_wav(encrypted_audio, sr, session_dir, '3a_sigsaly_encrypted.wav')
    meta_3b = _save_wav(encrypted_tel, sr, session_dir, '3b_sigsaly_encrypted_telephone.wav')
    meta_3c = _save_wav(decrypted, sr, session_dir, '3c_sigsaly_decrypted.wav')
    meta_3d = _save_wav(decrypted_tel, sr, session_dir, '3d_sigsaly_decrypted_telephone.wav')
    meta_3e = _save_wav(key_audio, sr, session_dir, '3e_key_record_audio.wav')

    audio_signals['3a_sigsaly_encrypted.wav'] = (encrypted_audio, 'SIGSALY Encrypted')
    audio_signals['3b_sigsaly_encrypted_telephone.wav'] = (encrypted_tel, 'Encrypted (wire)')
    audio_signals['3c_sigsaly_decrypted.wav'] = (decrypted, 'SIGSALY Decrypted')
    audio_signals['3d_sigsaly_decrypted_telephone.wav'] = (decrypted_tel, 'Decrypted (wire)')
    audio_signals['3e_key_record_audio.wav'] = (key_audio, 'Key Record (vinyl)')

    corr_encrypted = _correlation(data, encrypted_audio)
    band_match = bool(np.array_equal(dec_bands, bands[:len(dec_bands)]))
    pitch_match = bool(np.array_equal(dec_pitch, pitch[:len(dec_pitch)]))

    # Encryption uniformity
    enc_level_counts = {lv: int(np.sum(enc_bands == lv)) for lv in range(NUM_LEVELS)}
    enc_correlation = round(float(np.corrcoef(
        bands.flatten().astype(float), enc_bands.flatten().astype(float)
    )[0, 1]), 4)

    stages.append({
        'id': 3,
        'title': 'Full SIGSALY (Vocoder + One-Time Pad)',
        'description': (
            'The complete system: vocoder digitizes speech, then each parameter '
            'is encrypted with a random key value using mod-6 arithmetic. '
            'The encrypted output is provably indistinguishable from random noise.'
        ),
        'outputs': [
            {**meta_3a, 'label': 'Encrypted (eavesdropper hears)', 'spectrogram': '3a_sigsaly_encrypted.png'},
            {**meta_3b, 'label': 'Encrypted (over the wire)', 'spectrogram': '3b_sigsaly_encrypted_telephone.png'},
            {**meta_3c, 'label': 'Decrypted (correct key)', 'spectrogram': '3c_sigsaly_decrypted.png'},
            {**meta_3d, 'label': 'Decrypted (over the wire)', 'spectrogram': '3d_sigsaly_decrypted_telephone.png'},
            {**meta_3e, 'label': 'Key record (vinyl sound)', 'spectrogram': '3e_key_record_audio.png'},
        ],
        'diagnostics': {
            'correlation_encrypted': corr_encrypted,
            'original_encrypted_correlation': enc_correlation,
            'roundtrip_bands': band_match,
            'roundtrip_pitch': pitch_match,
            'encrypted_distribution': enc_level_counts,
            'text': (
                f'Correlation (original vs encrypted): {corr_encrypted} (should be ~0.0)\n'
                f'Correlation (original params vs encrypted params): {enc_correlation}\n'
                f'Encrypted level distribution: {", ".join(f"L{k}={v}" for k,v in enc_level_counts.items())}\n'
                f'  (Should be ~uniform: {total_values//NUM_LEVELS} each)\n'
                f'Roundtrip verification: bands={"PERFECT" if band_match else "FAILED"}, '
                f'pitch={"PERFECT" if pitch_match else "FAILED"}\n'
                f'\nShannon\'s perfect secrecy: each encrypted value is equally likely\n'
                f'to be any number 0-5, regardless of the original. An eavesdropper\n'
                f'learns NOTHING from the encrypted stream.'
            ),
        }
    })

    # ── STAGE 4: Cracking Attempt ───────────────────────────────
    _, crack_attempt, _ = crack_by_spectral_analysis(encrypted_audio, sr)
    meta_4a = _save_wav(crack_attempt, sr, session_dir, '4a_sigsaly_a3crack_attempt.wav')
    audio_signals['4a_sigsaly_a3crack_attempt.wav'] = (crack_attempt, 'A-3 Crack on SIGSALY (FAILS)')

    corr_crack_attempt = _correlation(data, crack_attempt)

    stages.append({
        'id': 4,
        'title': 'Cracking Attempt — A-3 Method on SIGSALY',
        'description': (
            'What happens when the Germans try spectral analysis on SIGSALY? '
            'It fails completely — there is no carrier frequency to find because '
            'the encryption uses random key values, not a simple spectrum flip.'
        ),
        'outputs': [
            {**meta_4a, 'label': 'A-3 crack attempt (FAILS)', 'spectrogram': '4a_sigsaly_a3crack_attempt.png'},
        ],
        'diagnostics': {
            'correlation_crack_attempt': corr_crack_attempt,
            'text': (
                f'Correlation (original vs crack attempt): {corr_crack_attempt}\n'
                f'Compare to successful A-3 crack: {corr_cracked}\n'
                f'\nThe spectral analysis technique that broke A-3 finds nothing.\n'
                f'There is no single parameter to guess — the key has\n'
                f'{total_values} independent random values.'
            ),
        }
    })

    # ── STAGE 5: Clock Desynchronization ────────────────────────
    desync_outputs = []
    desync_table = []
    correct_total = int(np.sum(dec_bands == bands[:len(dec_bands)]))

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
        filename = f'5_desync_{offset}frame{plural}.wav'
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

    desync_text_lines = [
        f'{"Offset":<20} {"Correct":>8} {"Accuracy":>10} {"Random Chance":>14}',
        f'{"─"*20} {"─"*8} {"─"*10} {"─"*14}',
        f'{"0 (perfect sync)":<20} {correct_total:>8} {"100.0%":>10} {"—":>14}',
    ]
    for row in desync_table:
        label = f'{row["offset"]} frame(s) ({row["time_ms"]}ms)'
        desync_text_lines.append(
            f'{label:<20} {row["match"]:>8} {row["pct"]:>9.1f}% {f"~{random_chance}%":>14}'
        )
    desync_text_lines.append(
        f'\nAll offsets → ~{random_chance}% accuracy (random chance = 1/{NUM_LEVELS}).\n'
        f'The one-time pad makes ANY timing error equivalent to a wrong key.'
    )

    stages.append({
        'id': 5,
        'title': 'Clock Desynchronization Demo',
        'description': (
            'What happens when the receiver\'s turntable is out of sync? '
            'Even a tiny offset means different key values are used for every frame, '
            'completely destroying decryption.'
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
    }
