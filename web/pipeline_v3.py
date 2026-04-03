"""
v3 Interactive Pipeline
=======================
Generates all audio variants needed for the interactive visualization
in a single pass. Unlike v2 (which generates stage-by-stage outputs),
v3 produces a flat set of named audio files covering every interactive
state: original, vocoded, scrambled, encrypted, cracked, and multiple
desync offsets.

All variants are WAV files that get loaded as Web Audio API buffers
on the client for instant playback switching.
"""

import os
import sys
import uuid
import time
import shutil
import tempfile
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigsaly.telephone import simulate_telephone_line
from sigsaly.scrambler import scramble, unscramble
from sigsaly.vocoder import (
    analyze, synthesize, frames_to_array, array_to_frames,
    FRAME_RATE, NUM_BANDS, NUM_LEVELS
)
from sigsaly.encryption import (
    encrypt_vocoder_params, decrypt_vocoder_params,
    decrypt_with_offset, encrypted_to_audio
)
from sigsaly.key_generation import generate_key_record, key_to_audio


def create_v3_session():
    session_id = uuid.uuid4().hex[:12]
    session_dir = os.path.join(tempfile.gettempdir(), f'sigsaly_v3_{session_id}')
    os.makedirs(session_dir, exist_ok=True)
    return session_id, session_dir


def cleanup_v3_sessions(max_age_seconds=3600):
    tmp = tempfile.gettempdir()
    for name in os.listdir(tmp):
        if name.startswith('sigsaly_v3_'):
            path = os.path.join(tmp, name)
            try:
                if time.time() - os.path.getmtime(path) > max_age_seconds:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass


def _save(signal, sr, session_dir, filename):
    """Save audio and return metadata."""
    path = os.path.join(session_dir, filename)
    sf.write(path, signal, sr)
    return filename


def _telephone(signal, sr, snr_db=22):
    return simulate_telephone_line(signal, sr, snr_db=snr_db)


def run_v3_pipeline(input_wav_path, params=None):
    """Generate all audio variants for the v3 interactive visualization.

    Returns a manifest dict with session info and all variant filenames.
    """
    params = params or {}
    snr_db = params.get('snr_db', 22)
    carrier_freq = params.get('carrier_freq', 2000)
    key_seed = params.get('key_seed', 42)
    # Desync offsets: always include 0 (perfect) and a range of offsets
    desync_offsets = [0, 1, 2, 5, 10, 25, 50]

    session_id, session_dir = create_v3_session()

    # Load and normalize
    data, sr = sf.read(input_wav_path)
    if len(data.shape) > 1:
        data = data[:, 0]
    data = data / (np.max(np.abs(data)) + 1e-10) * 0.95

    variants = {}

    # ── Original voice ──────────────────────────────────────────
    variants['original'] = _save(data, sr, session_dir, 'original.wav')

    # ── A-3 path ────────────────────────────────────────────────
    scrambled = scramble(data, sr, carrier_freq)
    scrambled_noisy = _telephone(scrambled, sr, snr_db)
    variants['a3_scrambled'] = _save(scrambled, sr, session_dir, 'a3_scrambled.wav')
    variants['a3_on_wire'] = _save(scrambled_noisy, sr, session_dir, 'a3_on_wire.wav')
    # Pre-compute unscrambled (what receiver hears with correct carrier)
    unscrambled = unscramble(scrambled_noisy, sr, carrier_freq)
    variants['a3_unscrambled'] = _save(unscrambled, sr, session_dir, 'a3_unscrambled.wav')

    # ── SIGSALY path: Vocoder ───────────────────────────────────
    frames = analyze(data, sr)
    vocoded = synthesize(frames, sr)
    variants['vocoded'] = _save(vocoded, sr, session_dir, 'vocoded.wav')

    # ── SIGSALY path: Encryption ────────────────────────────────
    bands, pitch, voiced, max_vals = frames_to_array(frames)
    key_duration = len(data) / sr + 5
    key = generate_key_record(key_duration, seed=key_seed)

    enc_bands, enc_pitch = encrypt_vocoder_params(bands, pitch, key)
    encrypted_audio = encrypted_to_audio(enc_bands, enc_pitch, voiced, sr)
    encrypted_noisy = _telephone(encrypted_audio, sr, snr_db)
    variants['sigsaly_encrypted'] = _save(encrypted_audio, sr, session_dir, 'sigsaly_encrypted.wav')
    variants['sigsaly_on_wire'] = _save(encrypted_noisy, sr, session_dir, 'sigsaly_on_wire.wav')

    # ── SIGSALY path: Key record ────────────────────────────────
    key_audio = key_to_audio(key, sr=sr)
    variants['key_record'] = _save(key_audio, sr, session_dir, 'key_record.wav')

    # ── SIGSALY path: Decryption at various offsets ─────────────
    for offset in desync_offsets:
        if offset == 0:
            dec_bands, dec_pitch = decrypt_vocoder_params(enc_bands, enc_pitch, key)
        else:
            dec_bands, dec_pitch = decrypt_with_offset(
                enc_bands, enc_pitch, key, frame_offset=offset
            )
        dec_frames = array_to_frames(
            dec_bands, dec_pitch,
            voiced[:len(dec_bands)], max_vals[:len(dec_bands)]
        )
        dec_audio = synthesize(dec_frames, sr)
        variants[f'sigsaly_decrypted_{offset}'] = _save(
            dec_audio, sr, session_dir, f'sigsaly_decrypted_{offset}.wav'
        )

    return {
        'session_id': session_id,
        'session_dir': session_dir,
        'sr': sr,
        'duration': round(len(data) / sr, 2),
        'params': {
            'snr_db': snr_db,
            'carrier_freq': carrier_freq,
            'key_seed': key_seed,
            'desync_offsets': desync_offsets,
        },
        'variants': variants,
    }
