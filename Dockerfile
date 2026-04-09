FROM python:3.12-slim

# Keeps Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Default DB and config paths (override via Railway volume + env vars)
    DB_PATH=/data/polyedge.db \
    CONFIG_PATH=/data/config.toml

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY polyedge/ ./polyedge/
COPY main.py ui.py config.toml ./

# Copy and prepare entrypoint
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Streamlit default port (Railway overrides with $PORT)
EXPOSE 8501

CMD ["/start.sh"]
