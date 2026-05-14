#!/bin/bash
# NSE Trading Scheduler — startup wrapper (IST timezone)

PROJECT="/Users/manavsharma/Documents/IdeaProjects/ClaudeProjects/AITrading"
PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"
PIDFILE="$PROJECT/scheduler_nse.pid"
LOG="$PROJECT/nse_trading.log"

export PYTHONPATH="$PROJECT"
export EXCHANGE="nse"
export TZ="Asia/Kolkata"
export PATH="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Kill any previous NSE instance
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') Stopping previous NSE scheduler (PID $OLD_PID)" >> "$LOG"
        kill "$OLD_PID" 2>/dev/null
        sleep 2
    fi
fi

echo $$ > "$PIDFILE"
cd "$PROJECT"

# Wait for PostgreSQL
for i in $(seq 1 12); do
    /opt/homebrew/opt/postgresql@14/bin/pg_isready -h /tmp -p 5433 -q 2>/dev/null && break
    sleep 5
done

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting NSE Trading Scheduler" >> "$LOG"
exec "$PYTHON" "$PROJECT/main.py" >> "$LOG" 2>&1
