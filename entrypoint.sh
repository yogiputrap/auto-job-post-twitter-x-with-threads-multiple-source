#!/bin/bash
set -e

echo "[entrypoint] Starting Job Bot container..."

# Export env vars for cron
env >> /etc/environment

# Setup cron job (every 60 minutes)
echo "0 * * * * . /etc/environment; cd /app && /usr/local/bin/python main.py >> /var/log/bot.log 2>&1" > /etc/cron.d/bot-cron
chmod 0644 /etc/cron.d/bot-cron
crontab /etc/cron.d/bot-cron

# Start cron daemon in background
service cron start || cron

echo "[entrypoint] Cron started. Launching dashboard on port ${DASHBOARD_PORT:-5000}..."

# Quick sanity check before starting dashboard
python -c "from flask import Flask; print('[entrypoint] Flask OK')" || { echo "[entrypoint] ERROR: Flask not available"; exit 1; }

# Run dashboard as the main foreground process
exec python dashboard.py
