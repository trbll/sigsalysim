"""
SIGSALY Simulator — Flask Web Dashboard (v2)
=============================================
A simple web interface for the SIGSALY educational pipeline.
Upload audio (or use the built-in sample), tweak parameters,
and hear/see all outputs with audio players and spectrograms.

Usage (single user / local development):
    python web/app.py                    # default port 3001
    python web/app.py --port 8080        # custom port

Usage (multi-user / classroom):
    ./serve.sh                           # 8 workers on port 3001
    ./serve.sh --workers 12 --port 8080  # custom
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

# Maximum audio duration in seconds. Longer clips take proportionally longer
# to process (vocoder analysis, cracking search, spectrogram generation).
# 120s is generous for educational demos — most speech clips are 5-30s.
MAX_AUDIO_DURATION = 120

# Default sample audio path
DEFAULT_SAMPLE = os.path.join(PROJECT_ROOT, 'input', 'sample_speech.wav')


@app.route('/')
def index():
    """Render the main page (upload form, no results yet)."""
    # Provide default sample info so the preview player works before running
    default_info = sf.info(DEFAULT_SAMPLE)
    default_source = {
        'name': 'Built-in sample',
        'duration': round(default_info.duration, 2),
        'sr': default_info.samplerate,
    }
    return render_template('index.html', results=None, default_source=default_source,
                           max_duration=MAX_AUDIO_DURATION)


@app.route('/run', methods=['POST'])
def run_pipeline():
    """Accept audio input, run the SIGSALY pipeline, return results."""
    # Clean up old sessions
    cleanup_old_sessions()

    # Determine input audio source
    input_path = None
    source_name = 'Built-in sample'

    if 'audio_file' in request.files and request.files['audio_file'].filename:
        # User uploaded a file
        uploaded = request.files['audio_file']
        tmp_input = os.path.join(tempfile.gettempdir(), f'sigsaly_upload_{uploaded.filename}')
        uploaded.save(tmp_input)

        # Validate it's a readable audio file
        try:
            info = sf.info(tmp_input)
        except Exception as e:
            return render_template('index.html', results=None,
                                   error=f'Invalid audio file: {e}',
                                   max_duration=MAX_AUDIO_DURATION)

        # Enforce duration limit
        if info.duration > MAX_AUDIO_DURATION:
            os.unlink(tmp_input)
            return render_template('index.html', results=None,
                                   error=(f'Audio too long: {info.duration:.1f}s '
                                          f'(maximum {MAX_AUDIO_DURATION}s). '
                                          f'Please trim your audio and try again.'),
                                   max_duration=MAX_AUDIO_DURATION)

        input_path = tmp_input
        source_name = uploaded.filename
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
                               error=f'Pipeline error: {e}',
                               max_duration=MAX_AUDIO_DURATION)

    # Include source name for the preview player
    results['source_info']['name'] = source_name

    return render_template('index.html', results=results,
                           max_duration=MAX_AUDIO_DURATION)


@app.route('/default-sample')
def serve_default_sample():
    """Serve the built-in default sample audio for the preview player."""
    return send_from_directory(
        os.path.join(PROJECT_ROOT, 'input'), 'sample_speech.wav',
        mimetype='audio/wav'
    )


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
    parser.add_argument('--port', type=int, default=3001,
                        help='Port to run on (default: 3001)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    args = parser.parse_args()

    print(f"SIGSALY Simulator — Web Dashboard (single-user mode)")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Max audio duration: {MAX_AUDIO_DURATION}s")
    print(f"  Default sample: {DEFAULT_SAMPLE}")
    print()
    print(f"  For multi-user (classroom), use: ./serve.sh")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)
