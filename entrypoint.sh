#!/bin/bash
# Export all env vars to a file so cron can access them
printenv | grep -v "no_proxy" >> /etc/environment

# Setup cron job (every 60 minutes)
echo "0 * * * * . /etc/environment; cd /app && /usr/local/bin/python main.py >> /var/log/bot.log 2>&1" > /etc/cron.d/bot-cron
chmod 0644 /etc/cron.d/bot-cron
crontab /etc/cron.d/bot-cron

# Run once immediately on startup
cd /app && python main.py >> /var/log/bot.log 2>&1 &

# Start dashboard in background
cd /app && python dashboard.py >> /var/log/dashboard.log 2>&1 &

# Start cron and tail logs
cron && tail -f /var/log/bot.log /var/log/dashboard.log
