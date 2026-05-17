#!/bin/bash
set -e

echo "[entrypoint] Starting Job Bot container..."

# Export env vars
env >> /etc/environment

# Start the bot scheduler in background (posts 5x/day at natural times)
echo "[entrypoint] Starting bot scheduler (5 posts/day at WIB peak times)..."
python main.py --scheduled >> /var/log/bot.log 2>&1 &

echo "[entrypoint] Bot scheduler started. Launching dashboard on port ${DASHBOARD_PORT:-5000}..."

# Quick sanity check before starting dashboard
python -c "from flask import Flask; print('[entrypoint] Flask OK')" || { echo "[entrypoint] ERROR: Flask not available"; exit 1; }

# Run dashboard as the main foreground process
exec python dashboard.py
