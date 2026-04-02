"""
Spectrogram Generation
======================
Server-side spectrogram rendering using matplotlib with the Agg backend
(no GUI required). Produces PNG images for each audio output so students
can visually compare the frequency content across pipeline stages.

Spectrograms are one of the most compelling visual tools for this project:
  - Original speech shows clear formant bands and harmonic structure
  - A-3 scrambled shows the SAME structure but mirrored (why it's crackable)
  - Vocoded speech shows the 10-band quantized structure
  - SIGSALY encrypted shows uniform noise (no structure at all)
  - Desync outputs show random vocoder artifacts
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server-side rendering

import matplotlib.pyplot as plt
import numpy as np


def generate_spectrogram(signal, sr, output_path, title='', max_freq=4500):
    """Render a spectrogram as a PNG image.

    Args:
        signal:      Audio samples (1D numpy array)
        sr:          Sample rate in Hz
        output_path: Where to save the PNG
        title:       Title text for the spectrogram
        max_freq:    Maximum frequency to display (Hz). 4500 covers the
                     telephone bandwidth plus a little headroom.

    Returns:
        The output_path (for convenience)
    """
    fig, ax = plt.subplots(1, 1, figsize=(8, 2.5))

    # Generate spectrogram with settings tuned for speech
    ax.specgram(
        signal, NFFT=1024, Fs=sr, noverlap=512,
        cmap='inferno',
        vmin=-80, vmax=-10  # dB range — keeps spectrograms visually consistent
    )

    ax.set_ylim(0, max_freq)
    ax.set_xlabel('Time (s)', fontsize=9)
    ax.set_ylabel('Frequency (Hz)', fontsize=9)
    ax.tick_params(labelsize=8)

    if title:
        ax.set_title(title, fontsize=10, fontweight='bold', pad=6)

    fig.tight_layout(pad=0.8)
    fig.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)  # Prevent memory leaks

    return output_path


def generate_all_spectrograms(audio_dict, sr, session_dir):
    """Generate spectrograms for all pipeline outputs.

    Args:
        audio_dict: dict mapping filename (str) -> (signal, label)
                    e.g. {'0a_original.wav': (numpy_array, 'Original (clean)')}
        sr:         Sample rate
        session_dir: Directory to save PNG files

    Returns:
        dict mapping wav_filename -> spectrogram_png_filename
    """
    import os
    spectrogram_map = {}

    for wav_filename, (signal, label) in audio_dict.items():
        png_filename = wav_filename.replace('.wav', '.png')
        png_path = os.path.join(session_dir, png_filename)
        generate_spectrogram(signal, sr, png_path, title=label)
        spectrogram_map[wav_filename] = png_filename

    return spectrogram_map
