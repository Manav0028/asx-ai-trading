import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "asx_trading")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_TTL_SECONDS = 3600

# ── Supabase (Phase 2) ────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── AI / LLM ──────────────────────────────────────────────────────────────────
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Alerts ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

# ── IBKR (Phase 3) ────────────────────────────────────────────────────────────
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", 7497))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))

# ── Trading parameters ────────────────────────────────────────────────────────
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_THRESHOLD", 75.0))
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", 0.20))  # 20% max per position
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.07))        # 7% stop-loss
PAPER_BROKERAGE = float(os.getenv("PAPER_BROKERAGE", 9.95))
PAPER_SLIPPAGE = float(os.getenv("PAPER_SLIPPAGE", 0.001))     # 0.1%
PORTFOLIO_CAPITAL = float(os.getenv("PORTFOLIO_CAPITAL", 100_000.0))

# ── Signal weights (must sum to 1.0) ─────────────────────────────────────────
WEIGHT_SENTIMENT = 0.30
WEIGHT_FUNDAMENTAL = 0.25
WEIGHT_TECHNICAL = 0.25
WEIGHT_INSIDER = 0.20

# ── Market regime ─────────────────────────────────────────────────────────────
XJO_TICKER = "^AXJO"
REGIME_EMA_DAYS = 200

# ── Schedules ─────────────────────────────────────────────────────────────────
TOP_N_DAILY_REPORT = 10
TOP_N_CLAUDE_BATCH = 20
BACKTESTER_LOOKBACK_MONTHS = 6

# ── Phase flag ────────────────────────────────────────────────────────────────
TRADING_PHASE = int(os.getenv("TRADING_PHASE", 1))  # 1=paper, 3=live
LIVE_TRADING_ENABLED = TRADING_PHASE >= 3
