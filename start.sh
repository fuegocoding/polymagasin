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

# Monitor processes
while true; do
  if ! kill -0 $SCANNER_PID 2>/dev/null; then
    echo "Scanner process died. Restarting..."
    python main.py watch --config "$CONFIG_PATH" &
    SCANNER_PID=$!
  fi
  if ! kill -0 $WEB_PID 2>/dev/null; then
    echo "Web process died. Restarting..."
    streamlit run ui.py \
      --server.port="${PORT:-8501}" \
      --server.headless=true \
      --server.address=0.0.0.0 \
      --server.enableCORS=false \
      --server.enableXsrfProtection=false \
      --browser.gatherUsageStats=false &
    WEB_PID=$!
  fi
  sleep 10
done
