#!/usr/bin/env python3
"""
Pre-compute v3 default audio variants for instant page load.
"""

import sys
import os
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.pipeline_v3 import run_v3_pipeline

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE = os.path.join(PROJECT_ROOT, 'input', 'sample_speech_eleven.mp3')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'web', 'v3_default_output')


def main():
    print("Pre-computing v3 default audio variants...")
    print(f"  Input: {INPUT_FILE}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    results = run_v3_pipeline(INPUT_FILE)

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    shutil.copytree(results['session_dir'], OUTPUT_DIR)

    # Save manifest
    results['session_dir'] = None
    manifest_path = os.path.join(OUTPUT_DIR, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(results, f, indent=2)

    wavs = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.wav')]
    print(f"Done! {len(wavs)} audio variants saved.")
    for w in sorted(wavs):
        size_kb = os.path.getsize(os.path.join(OUTPUT_DIR, w)) // 1024
        print(f"  {w} ({size_kb} KB)")


if __name__ == '__main__':
    main()
