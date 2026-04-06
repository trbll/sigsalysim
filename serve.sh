#!/usr/bin/env bash
#
# SIGSALY Simulator — Multi-User Server
# ======================================
# Runs the web dashboard with gunicorn for classroom use.
# Multiple students can run pipelines simultaneously.
#
# Usage:
#   ./serve.sh                           # 8 workers, port 3001
#   ./serve.sh --workers 12              # more workers for larger classes
#   ./serve.sh --port 8080               # custom port
#   ./serve.sh --workers 12 --port 8080  # both
#
# Each worker handles one pipeline run at a time. With 8 workers,
# 8 students can run pipelines simultaneously; additional requests
# queue and are served as workers become available.
#
# Resource usage per worker (approximate):
#   CPU: 1 core (100% during pipeline run, ~0% idle)
#   RAM: ~200-300 MB peak during pipeline run
#
# Recommended workers by class size:
#   1-5  students: 4 workers
#   5-15 students: 8 workers (default)
#   15-30 students: 12 workers
#   30+  students: 16 workers (if hardware supports it)

set -e

# Defaults
WORKERS=8
PORT=3001
HOST="0.0.0.0"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --workers) WORKERS="$2"; shift 2 ;;
        --port)    PORT="$2";    shift 2 ;;
        --host)    HOST="$2";    shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Ensure we're in the project directory
cd "$(dirname "$0")"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo "gunicorn not found. Installing..."
    pip install gunicorn
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║          SIGSALY Simulator — Classroom Server            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  URL:     http://${HOST}:${PORT}"
echo "  Workers: ${WORKERS} (${WORKERS} concurrent pipeline runs)"
echo "  Timeout: 120s per request"
echo ""
echo "  Students connect to: http://$(hostname -s).local:${PORT}"
echo "  (or use your IP address on the local network)"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

exec gunicorn \
    --workers "$WORKERS" \
    --timeout 120 \
    --no-sendfile \
    --bind "${HOST}:${PORT}" \
    --access-logfile - \
    --error-logfile - \
    web.app:app
