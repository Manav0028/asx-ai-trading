#!/bin/bash
# ASX Trading Scheduler — startup wrapper for cron and launchd

PROJECT="/Users/manavsharma/Documents/IdeaProjects/ClaudeProjects/AITrading"
PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"
PIDFILE="$PROJECT/scheduler.pid"
LOG="$PROJECT/asx_trading.log"

export PYTHONPATH="$PROJECT"
export TZ="Australia/Sydney"
export PATH="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Kill any previous instance
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    kill "$OLD_PID" 2>/dev/null
    sleep 1
fi

cd "$PROJECT"

# Wait for PostgreSQL to be ready (up to 60s)
for i in $(seq 1 12); do
    if /opt/homebrew/opt/postgresql@14/bin/pg_isready -h /tmp -p 5433 -q 2>/dev/null; then
        break
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') Waiting for PostgreSQL... ($i/12)" >> "$LOG"
    sleep 5
done

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting ASX scheduler" >> "$LOG"

# Run and record PID
"$PYTHON" "$PROJECT/main.py" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"

# Wait so launchd/cron tracks us while Python runs
wait
