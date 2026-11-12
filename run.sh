#!/bin/sh
# Fetch the lidar terrain (if needed) and open the viewer.
#
#   ./run.sh                      use existing data, or fetch with the defaults
#   ./run.sh --size 4096          re-fetch with these options (see fetch_dem.py --help)
#   PORT=9000 ./run.sh            serve on another port (default 8765)
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8765}"

# one-time setup of the Python environment
if [ ! -x .venv/bin/python ]; then
  echo "Setting up Python environment..."
  python3 -m venv .venv
  .venv/bin/pip -q install --upgrade pip
  .venv/bin/pip -q install rasterio numpy
fi

# fetch when options are given or no data exists yet
if [ $# -gt 0 ] || [ ! -f data/dem.u16 ]; then
  .venv/bin/python fetch_dem.py "$@"
fi

URL="http://127.0.0.1:$PORT/"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already serving - opening $URL"
  open "$URL"
  exit 0
fi

echo "Viewer at $URL  (Ctrl+C to stop)"
(sleep 1 && open "$URL") &
exec .venv/bin/python -m http.server "$PORT" --bind 127.0.0.1
