#!/usr/bin/env python3
"""
Pre-compute default pipeline outputs.

Runs the full SIGSALY pipeline on the default sample audio and saves
all outputs (WAVs + spectrograms + results JSON) to web/default_output/.
The web dashboard serves these instantly on first load — no processing wait.

Usage:
    python scripts/precompute_default.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.pipeline import run_web_pipeline

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE = os.path.join(PROJECT_ROOT, 'input', 'sample_speech_eleven.mp3')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'web', 'default_output')


def main():
    print("Pre-computing default pipeline outputs...")
    print(f"  Input: {INPUT_FILE}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # Run the pipeline with default params
    results = run_web_pipeline(INPUT_FILE, params={
        'snr_db': 22,
        'carrier_freq': 2000,
        'desync_offsets': [1, 5, 25],
        'key_seed': 42,
    })

    # Copy all files from the temp session dir to the permanent output dir
    import shutil
    session_dir = results['session_dir']

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    shutil.copytree(session_dir, OUTPUT_DIR)

    # Save the results metadata (everything except session_dir path)
    results['session_dir'] = None  # Will be set at serve time
    results['source_info']['name'] = 'Built-in sample'

    meta_path = os.path.join(OUTPUT_DIR, 'results.json')
    with open(meta_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Count outputs
    wavs = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.wav')]
    pngs = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.png')]

    print(f"Done! {len(wavs)} WAV files, {len(pngs)} spectrograms saved.")
    print(f"  Results metadata: {meta_path}")
    print()
    print("The web dashboard will serve these instantly on first load.")


if __name__ == '__main__':
    main()
