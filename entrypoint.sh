#!/bin/bash
set -e

# Export all env vars to a file so cron can access them
printenv | grep -v "no_proxy" >> /etc/environment

# Setup cron job (every 60 minutes)
echo "0 * * * * . /etc/environment; cd /app && /usr/local/bin/python main.py >> /var/log/bot.log 2>&1" > /etc/cron.d/bot-cron
chmod 0644 /etc/cron.d/bot-cron
crontab /etc/cron.d/bot-cron

# Start cron in background
cron

# Run bot once on startup (background, non-blocking)
cd /app && python main.py >> /var/log/bot.log 2>&1 &

# Start dashboard as FOREGROUND process (so container stays alive and port 5000 is served)
cd /app && exec python dashboard.py
