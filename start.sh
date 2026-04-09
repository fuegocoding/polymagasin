#!/bin/bash
set -e

DATA_DIR="${DATA_DIR:-/data}"
CONFIG_PATH="${CONFIG_PATH:-$DATA_DIR/config.toml}"
export CONFIG_PATH
export DB_PATH="${DB_PATH:-$DATA_DIR/polyedge.db}"

mkdir -p "$DATA_DIR"

# Seed config.toml into the volume on first run
if [ ! -f "$CONFIG_PATH" ]; then
  echo "Seeding $CONFIG_PATH from bundled defaults..."
  cp /app/config.toml "$CONFIG_PATH"
else
  # If it exists, ensure it has the correct 'stake = false' if that's what the user wants,
  # or at least notify. Better yet, let's not overwrite user settings but
  # we could merge them. For now, we rely on the UI to toggle it.
  echo "Using existing config at $CONFIG_PATH"
fi

echo "Scanner config: DB=$DB_PATH, CONFIG=$CONFIG_PATH"

# Start the edge scanner in the background
python main.py watch --config "$CONFIG_PATH" &
SCANNER_PID=$!

# Start Streamlit
streamlit run ui.py \
  --server.port="${PORT:-8501}" \
  --server.headless=true \
  --server.address=0.0.0.0 \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false \
  --browser.gatherUsageStats=false &
WEB_PID=$!

echo "Processes started: Scanner ($SCANNER_PID), Web ($WEB_PID)"

# Wait for either to exit
wait -n $SCANNER_PID $WEB_PID

echo "A process exited unexpectedly. Shutting down."
kill $SCANNER_PID $WEB_PID 2>/dev/null || true
exit 1
