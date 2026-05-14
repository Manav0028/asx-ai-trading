#!/bin/bash
# ASX Trading Scheduler — startup wrapper
# Uses exec so Python replaces bash; launchd/cron tracks the Python process directly.

PROJECT="/Users/manavsharma/Documents/IdeaProjects/ClaudeProjects/AITrading"
PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"
PIDFILE="$PROJECT/scheduler.pid"
LOG="$PROJECT/asx_trading.log"

export PYTHONPATH="$PROJECT"
export TZ="Australia/Sydney"
export PATH="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Kill any previous instance cleanly
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') Stopping previous scheduler (PID $OLD_PID)" >> "$LOG"
        kill "$OLD_PID" 2>/dev/null
        sleep 2
    fi
fi

# Write our own PID before exec (bash PID, which becomes Python's PID after exec)
echo $$ > "$PIDFILE"

cd "$PROJECT"

# Wait for PostgreSQL (up to 60s)
for i in $(seq 1 12); do
    /opt/homebrew/opt/postgresql@14/bin/pg_isready -h /tmp -p 5433 -q 2>/dev/null && break
    echo "$(date '+%Y-%m-%d %H:%M:%S') Waiting for PostgreSQL ($i/12)..." >> "$LOG"
    sleep 5
done

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting ASX Trading Scheduler" >> "$LOG"

# exec replaces this bash process with Python — launchd tracks the Python PID
exec "$PYTHON" "$PROJECT/main.py" >> "$LOG" 2>&1
