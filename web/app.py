"""
SIGSALY Simulator — Flask Web Dashboard (v2)
=============================================
A simple web interface for the SIGSALY educational pipeline.
Upload audio (or use the built-in sample), tweak parameters,
and hear/see all outputs with audio players and spectrograms.

Usage:
    python web/app.py                    # default port 3001
    python web/app.py --port 8080        # custom port
"""

import os
import sys
import argparse
import tempfile

# Add project root to path so sigsaly package is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import soundfile as sf

from web.pipeline import run_web_pipeline, cleanup_old_sessions

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit

# Default sample audio path
DEFAULT_SAMPLE = os.path.join(PROJECT_ROOT, 'input', 'sample_speech.wav')


@app.route('/')
def index():
    """Render the main page (upload form, no results yet)."""
    return render_template('index.html', results=None)


@app.route('/run', methods=['POST'])
def run_pipeline():
    """Accept audio input, run the SIGSALY pipeline, return results."""
    # Clean up old sessions
    cleanup_old_sessions()

    # Determine input audio source
    input_path = None

    if 'audio_file' in request.files and request.files['audio_file'].filename:
        # User uploaded a file
        uploaded = request.files['audio_file']
        tmp_input = os.path.join(tempfile.gettempdir(), f'sigsaly_upload_{uploaded.filename}')
        uploaded.save(tmp_input)

        # Validate it's a readable audio file
        try:
            info = sf.info(tmp_input)
            input_path = tmp_input
        except Exception as e:
            return render_template('index.html', results=None,
                                   error=f'Invalid audio file: {e}')
    else:
        # Use default sample
        input_path = DEFAULT_SAMPLE

    # Extract parameters from sliders
    params = {
        'snr_db': float(request.form.get('snr_db', 28)),
        'carrier_freq': int(request.form.get('carrier_freq', 2000)),
        'desync_offsets': [1, 5, int(request.form.get('desync_max', 25))],
        'key_seed': 42,
    }

    # Run the pipeline
    try:
        results = run_web_pipeline(input_path, params)
    except Exception as e:
        return render_template('index.html', results=None,
                               error=f'Pipeline error: {e}')

    return render_template('index.html', results=results)


@app.route('/session/<session_id>/audio/<filename>')
def serve_audio(session_id, filename):
    """Serve a WAV file from a session's temp directory."""
    session_dir = os.path.join(tempfile.gettempdir(), f'sigsaly_{session_id}')
    if not os.path.isdir(session_dir):
        return 'Session not found', 404
    return send_from_directory(session_dir, filename, mimetype='audio/wav')


@app.route('/session/<session_id>/spectrogram/<filename>')
def serve_spectrogram(session_id, filename):
    """Serve a spectrogram PNG from a session's temp directory."""
    session_dir = os.path.join(tempfile.gettempdir(), f'sigsaly_{session_id}')
    if not os.path.isdir(session_dir):
        return 'Session not found', 404
    return send_from_directory(session_dir, filename, mimetype='image/png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SIGSALY Simulator Web Dashboard')
    parser.add_argument('--port', type=int, default=3001, help='Port to run on (default: 3001)')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    print(f"SIGSALY Simulator — Web Dashboard")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Default sample: {DEFAULT_SAMPLE}")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)
