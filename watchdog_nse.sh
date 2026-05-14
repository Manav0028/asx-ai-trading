#!/bin/bash
# Watchdog for NSE scheduler — checks every 5 minutes, restarts if dead

PROJECT="/Users/manavsharma/Documents/IdeaProjects/ClaudeProjects/AITrading"
PIDFILE="$PROJECT/scheduler_nse.pid"
LOG="$PROJECT/nse_trading.log"
PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"

export PYTHONPATH="$PROJECT"
export EXCHANGE="nse"
export TZ="Asia/Kolkata"
export PATH="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin:/opt/homebrew/bin:/usr/bin:/bin"

echo "$(date '+%Y-%m-%d %H:%M:%S') NSE Watchdog started" >> "$LOG"

while true; do
    sleep 300
    PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') NSE scheduler not running — restarting" >> "$LOG"
        cd "$PROJECT"
        EXCHANGE=nse "$PYTHON" "$PROJECT/main.py" >> "$LOG" 2>&1 &
        echo $! > "$PIDFILE"
        echo "$(date '+%Y-%m-%d %H:%M:%S') NSE scheduler restarted (PID $(cat $PIDFILE))" >> "$LOG"
    fi
done
