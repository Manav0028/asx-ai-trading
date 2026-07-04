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
AUTO_PAPER_TRADE = os.getenv("AUTO_PAPER_TRADE", "false").lower() == "true"
RTC_TRADING_MODE = os.getenv("RTC_TRADING_MODE", "paper")
RTC_SIGNAL_THRESHOLD = float(os.getenv("RTC_SIGNAL_THRESHOLD", 65.0))

# ── Watchlist (Phase 1: single ticker; Phase 3: multiple, comma-separated) ────────
RTC_TICKERS = [t.strip() for t in os.getenv("RTC_TICKERS", "BHP.AX").split(",") if t.strip()]

# ── Composite score weights (must sum to 1.0) — see plan doc §7 ──────────────────
WEIGHT_PATTERN_CONFIDENCE = 0.35
WEIGHT_TREND_ALIGNMENT = 0.20
WEIGHT_VOLUME_CONFIRMATION = 0.15
WEIGHT_MTF_CONFLUENCE = 0.15
WEIGHT_SMC_ZONE_QUALITY = 0.15
