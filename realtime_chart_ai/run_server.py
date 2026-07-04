"""
Entry point — own process, own port, no shared state with main.py/dashboard.
Run: PYTHONPATH=. python realtime_chart_ai/run_server.py
     PYTHONPATH=. python realtime_chart_ai/run_server.py --init-db   (create rtc_* tables and exit)
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # so `import settings`/`import engine...` resolve

import uvicorn

from settings import RTC_HOST, RTC_PORT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-db", action="store_true", help="Create rtc_* tables and exit")
    args = parser.parse_args()

    if args.init_db:
        from journal.db import init_db
        init_db()
        return

    # NOTE: uvicorn.run()/Server.run() wrap asyncio.run(..., loop_factory=...) —
    # on Python <3.12 this shim creates a second, mismatched event loop that
    # breaks ib_insync's internal Future/loop bookkeeping ("attached to a
    # different loop" on connectAsync). Driving server.serve() under a plain
    # asyncio.run() avoids the extra loop entirely.
    from server.app import app
    config = uvicorn.Config(app, host=RTC_HOST, port=RTC_PORT, log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
