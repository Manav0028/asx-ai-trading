"""
ASX regular trading session: 10:00-16:00, Australia/Sydney time, Monday-
Friday. Deliberately does not account for ASX public holidays (that needs a
maintained holiday calendar, out of scope here) — a documented
simplification, not a claim of perfect accuracy. Mirrors the frontend's
isAsxMarketOpen() (Header.tsx) so the UI's LIVE/MARKET CLOSED indicator and
the actual automated-entry gate below always agree with each other.

Found via direct user report: automated entries had NO market-hours check
at all — only the manual auto-trade on/off toggle gated them, so a signal
firing well after the 16:00 close (against stale/after-hours delayed data)
could still open a new paper position if the toggle happened to be left on.
engine/signal_engine.py now calls is_asx_market_open() before every
automated entry; manual entries (an explicit, deliberate user action) are
NOT gated by this — a user should be able to test-trade at any time.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def is_asx_market_open(now: datetime = None) -> bool:
    now = (now or datetime.now(SYDNEY_TZ)).astimezone(SYDNEY_TZ)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    minutes_since_midnight = now.hour * 60 + now.minute
    return 10 * 60 <= minutes_since_midnight < 16 * 60
