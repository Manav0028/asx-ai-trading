"""
realtime_chart_ai — own config module, isolated from config/settings.py.
Loads realtime_chart_ai/.env specifically (not the root .env) so this project
stays fully standalone-runnable.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Database (same Postgres server as the main system, separate rtc_* tables) ─
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://manavsharma@localhost:5433/asx_trading"
)

# ── Claude ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", 250))

# ── IBKR TWS ────────────────────────────────────────────────────────────────────
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", 7497))
IBKR_CLIENT_ID_REALTIME = int(os.getenv("IBKR_CLIENT_ID_REALTIME", 50))

# ── Data source selection ────────────────────────────────────────────────────────
PRIMARY_SOURCE = os.getenv("PRIMARY_SOURCE", "ibkr")
FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "yfinance_delayed")
EXECUTION_TIMEFRAME_SECONDS = int(os.getenv("EXECUTION_TIMEFRAME_SECONDS", 60))
CONTEXT_TIMEFRAMES = os.getenv("CONTEXT_TIMEFRAMES", "5m,15m,1d").split(",")

# ── Server ────────────────────────────────────────────────────────────────────────
RTC_HOST = os.getenv("RTC_HOST", "0.0.0.0")
RTC_PORT = int(os.getenv("RTC_PORT", 8800))

# ── Trading / journal ──────────────────────────────────────────────────────────────
# AUTO_TRADE_ENABLED_DEFAULT only seeds the starting state at process boot — the
# real control is the runtime toggle (trading/state.py + POST /api/auto-trade).
AUTO_TRADE_ENABLED_DEFAULT = os.getenv("AUTO_TRADE_ENABLED_DEFAULT", "false").lower() == "true"
RTC_TRADING_MODE = os.getenv("RTC_TRADING_MODE", "paper")  # only "paper" is implemented
RTC_SIGNAL_THRESHOLD = float(os.getenv("RTC_SIGNAL_THRESHOLD", 65.0))
RTC_HIGH_ALERT_THRESHOLD = float(os.getenv("RTC_HIGH_ALERT_THRESHOLD", 85.0))  # Phase 3: cross-ticker popup alert

# ── Automated trading: position sizing (dollar-risk, scaled by composite score) ───
RTC_CAPITAL_POOL = float(os.getenv("RTC_CAPITAL_POOL", 20000.0))       # isolated sizing-reference pool
# 0.5% (not the EOD daily system's 1.5%) — intraday stops are much tighter
# (2-8% vs the EOD's 3-12%), and dollar-risk sizing produces a larger implied
# position the tighter the stop is. At 1.5% base risk, RTC_MAX_POSITION_PCT
# ends up binding at every composite score once the stop is anywhere near the
# tight end of the range, which silently erases the score-driven sizing this
# feature exists to provide. 0.5% keeps the position-value cap a genuine
# backstop for extreme cases rather than the constantly-binding constraint.
RTC_BASE_RISK_PCT = float(os.getenv("RTC_BASE_RISK_PCT", 0.005))
RTC_MAX_POSITION_PCT = float(os.getenv("RTC_MAX_POSITION_PCT", 0.40))  # cap position at 40% of the pool
RTC_SCORE_MULT_FLOOR = float(os.getenv("RTC_SCORE_MULT_FLOOR", 0.5))   # composite == threshold -> 0.5x risk
RTC_SCORE_MULT_CEIL = float(os.getenv("RTC_SCORE_MULT_CEIL", 1.5))     # composite == 100 -> 1.5x risk

# ── Automated trading: simulated fill ─────────────────────────────────────────────
RTC_PAPER_SLIPPAGE = float(os.getenv("RTC_PAPER_SLIPPAGE", 0.001))     # 0.1%
RTC_PAPER_BROKERAGE = float(os.getenv("RTC_PAPER_BROKERAGE", 9.95))    # flat fee per leg

# ── Automated trading: ATR-based stop/target/trailing-stop ───────────────────────
RTC_MIN_STOP_PCT = float(os.getenv("RTC_MIN_STOP_PCT", 0.02))
RTC_MAX_STOP_PCT = float(os.getenv("RTC_MAX_STOP_PCT", 0.08))
RTC_MIN_RR_RATIO = float(os.getenv("RTC_MIN_RR_RATIO", 1.5))
RTC_TRAIL_ACTIVATE_MULT = float(os.getenv("RTC_TRAIL_ACTIVATE_MULT", 1.0))
RTC_TRAIL_DISTANCE_MULT = float(os.getenv("RTC_TRAIL_DISTANCE_MULT", 1.5))
RTC_TRAIL_MIN_PCT = float(os.getenv("RTC_TRAIL_MIN_PCT", 0.01))
RTC_TRAIL_MAX_PCT = float(os.getenv("RTC_TRAIL_MAX_PCT", 0.05))

# ── Watchlist (Phase 1: single ticker; Phase 3: multiple, comma-separated) ────────
RTC_TICKERS = [t.strip() for t in os.getenv("RTC_TICKERS", "BHP.AX").split(",") if t.strip()]

# ── Composite score weights (must sum to 1.0) — see plan doc §7 ──────────────────
WEIGHT_PATTERN_CONFIDENCE = 0.35
WEIGHT_TREND_ALIGNMENT = 0.20
WEIGHT_VOLUME_CONFIRMATION = 0.15
WEIGHT_MTF_CONFLUENCE = 0.15
WEIGHT_SMC_ZONE_QUALITY = 0.15
