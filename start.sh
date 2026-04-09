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
fi

echo "Scanner config: DB=$DB_PATH, CONFIG=$CONFIG_PATH"

# Start the edge scanner in the background (explicit config path so it reads from volume)
python main.py watch --config "$CONFIG_PATH" &
SCANNER_PID=$!

# Start Streamlit on Railway's PORT (fallback 8501)
streamlit run ui.py \
  --server.port="${PORT:-8501}" \
  --server.headless=true \
  --server.address=0.0.0.0 \
  --browser.gatherUsageStats=false &
WEB_PID=$!

# If either process dies, kill the other and exit
wait -n $SCANNER_PID $WEB_PID
echo "A process exited unexpectedly — shutting down."
kill $SCANNER_PID $WEB_PID 2>/dev/null || true
exit 1
