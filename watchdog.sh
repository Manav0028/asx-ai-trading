#!/bin/bash
# Watchdog — checks scheduler every 5 minutes, restarts if dead
PROJECT="/Users/manavsharma/Documents/IdeaProjects/ClaudeProjects/AITrading"
PIDFILE="$PROJECT/scheduler.pid"
LOG="$PROJECT/asx_trading.log"
PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"

export PYTHONPATH="$PROJECT"
export TZ="Australia/Sydney"
export PATH="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin:/opt/homebrew/bin:/usr/bin:/bin"

echo "$(date '+%Y-%m-%d %H:%M:%S') Watchdog started" >> "$LOG"

while true; do
    sleep 300  # check every 5 minutes

    PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') Scheduler not running — restarting" >> "$LOG"
        cd "$PROJECT"
        "$PYTHON" "$PROJECT/main.py" >> "$LOG" 2>&1 &
        echo $! > "$PIDFILE"
        echo "$(date '+%Y-%m-%d %H:%M:%S') Scheduler restarted (PID $(cat $PIDFILE))" >> "$LOG"
    fi
done
