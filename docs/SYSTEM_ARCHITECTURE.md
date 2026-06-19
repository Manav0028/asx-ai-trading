# AITrading Platform — Technical & Functional Architecture
### Low-Level Design (LLD) Reference Document
*Version: June 2026 · Exchange Coverage: ASX 200 + NSE NIFTY 100*

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Infrastructure & Configuration](#2-infrastructure--configuration)
3. [Data Models (PostgreSQL Schema)](#3-data-models-postgresql-schema)
4. [Data Ingestion Layer](#4-data-ingestion-layer)
5. [AI Engine — Scoring Components](#5-ai-engine--scoring-components)
6. [Signal Aggregation & Scoring](#6-signal-aggregation--scoring)
7. [Strategy Selection & Validation](#7-strategy-selection--validation)
8. [Risk Parameters & Position Sizing](#8-risk-parameters--position-sizing)
9. [Execution Layer](#9-execution-layer)
10. [Scheduler & Job Orchestration](#10-scheduler--job-orchestration)
11. [Cloud Sync (Supabase)](#11-cloud-sync-supabase)
12. [Dashboard Data Layer](#12-dashboard-data-layer)
13. [Alerts & Reporting](#13-alerts--reporting)
14. [End-to-End Data Flow](#14-end-to-end-data-flow)
15. [Key Thresholds & Parameters Reference](#15-key-thresholds--parameters-reference)
16. [Phase Progression (Paper → Live)](#16-phase-progression-paper--live)
17. [Project Directory Structure](#17-project-directory-structure)

---

## 1. System Overview

AITrading is a **multi-exchange algorithmic trading framework** that runs two parallel pipelines — one for the Australian Securities Exchange (ASX 200) and one for India's National Stock Exchange (NSE NIFTY 100). It uses a **multi-factor scoring model** (sentiment + fundamental + technical + insider) to rank stocks daily, applies per-stock strategy validation via walk-forward backtesting, and executes paper or live orders through a pluggable execution layer.

### Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                     LOCAL MAC (Scheduler)                   │
│                                                             │
│  ASX Scheduler (EXCHANGE=asx)   NSE Scheduler (EXCHANGE=nse)│
│  ┌────────────────────┐         ┌────────────────────┐     │
│  │ APScheduler (cron) │         │ APScheduler (cron) │     │
│  │ TZ: Australia/Syd  │         │ TZ: Asia/Kolkata   │     │
│  └────────┬───────────┘         └────────┬───────────┘     │
│           │                              │                  │
│  ┌────────▼──────────────────────────────▼──────────┐      │
│  │            Shared Pipeline Modules               │      │
│  │  data_ingestion → ai_engine → signals →          │      │
│  │  strategies → execution → storage               │      │
│  └────────────────────┬──────────────────────────────┘      │
│                       │                                     │
│  ┌────────────────────▼──────────────────────────────┐      │
│  │    Local PostgreSQL (port 5433) + Redis Cache     │      │
│  └────────────────────┬──────────────────────────────┘      │
└───────────────────────┼─────────────────────────────────────┘
                        │ supabase_sync.py (REST API)
                        ▼
         ┌──────────────────────────────────┐
         │  Supabase Cloud (Dual Instance)  │
         │  Primary DB: bhztefmozidvfqmjepwa│
         │  New DB:     lhzjtiojresodcizajut│
         └──────────────────┬───────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │   Streamlit Cloud Dashboard      │
         │   (app_v2.py — public URL)       │
         └──────────────────────────────────┘
```

### Operating Phases

| Phase | Mode | Executor | Fill Source | Account |
|-------|------|----------|-------------|---------|
| **1** (current) | Internal paper | `execution/paper_trader.py` | yfinance daily close | Simulated AUD 100k |
| **2** | IBKR paper | `execution/ibkr_paper_trader.py` | TWS real-time (port 7497) | IBKR paper account |
| **3** | IBKR live | `execution/ibkr_trader.py` | TWS real-time (port 7496) | Real money |

Switch phases via `TRADING_PHASE=1|2|3` in `.env`.

---

## 2. Infrastructure & Configuration

### 2.1 Environment Variables (`.env`)

```ini
# ── PostgreSQL (local, Homebrew, port 5433) ───────────────────
DATABASE_URL=postgresql://user@localhost:5433/asx_trading

# ── Redis Cache ───────────────────────────────────────────────
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# ── AI / LLM ──────────────────────────────────────────────────
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1          # local LLM for sentiment
ANTHROPIC_API_KEY=...          # Claude API for weekly summaries
CLAUDE_MODEL=claude-sonnet-4-6

# ── Supabase (dual-instance) ──────────────────────────────────
SUPABASE_URL=https://bhztefmozidvfqmjepwa.supabase.co   # primary (legacy)
SUPABASE_KEY=<service_role_key>
SUPABASE_URL_B=https://lhzjtiojresodcizajut.supabase.co  # new (clean)
SUPABASE_KEY_B=<service_role_key_b>

# ── Alerts ────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# ── Trading Parameters ────────────────────────────────────────
TRADING_PHASE=1
SIGNAL_THRESHOLD=65.0          # minimum composite score to trade
MAX_POSITION_PCT=0.20          # max 20% of capital per position
STOP_LOSS_PCT=0.07             # hard stop at -7%
PORTFOLIO_CAPITAL=20000        # base capital (AUD)
EXCHANGE=asx                   # set per scheduler process
TZ=Australia/Sydney            # set per scheduler process
```

### 2.2 Exchange Registry (`config/exchange_registry.py`)

Each exchange is registered as an `Exchange` dataclass:

```python
@dataclass
class Exchange:
    id: str                     # "asx" | "nse"
    name: str                   # "ASX 200" | "NSE NIFTY 100"
    tickers: List[str]          # 200 (ASX) | 100 (NSE)
    index_ticker: str           # "^AXJO" | "^NSEI"
    index_name: str
    timezone: str               # "Australia/Sydney" | "Asia/Kolkata"
    currency_code: str          # "AUD" | "INR"
    market_open: tuple          # (10, 0) | (9, 15)
    market_close: tuple         # (16, 0) | (15, 30)
    pre_market_hour: int        # 9 (ASX) | 8 (NSE)
    gnews_hl/gl/ceid            # Google News localisation
    news_query_fn: Callable     # builds RSS search query
    announcement_fetcher        # ASX/NSE filing parser
    insider_fetcher             # director/promoter trade scraper
```

Active exchange resolved at runtime from `$EXCHANGE` env var. This enables true parallel operation — both schedulers run the same codebase reading different `$EXCHANGE` values.

### 2.3 Signal Weights (`config/settings.py`)

```python
WEIGHT_SENTIMENT    = 0.375     # 37.5% — LLM news analysis
WEIGHT_FUNDAMENTAL  = 0.3125    # 31.25% — financial health
WEIGHT_TECHNICAL    = 0.3125    # 31.25% — chart indicators
WEIGHT_INSIDER      = 0.0       # 0% — ASX Form 604 unreliable
```

---

## 3. Data Models (PostgreSQL Schema)

All tables live in a local PostgreSQL instance (port 5433, db `asx_trading`). SQLAlchemy ORM in `storage/models.py`.

### 3.1 `prices` — OHLCV Candlestick Data

```sql
CREATE TABLE prices (
    id          SERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL,
    date        DATE NOT NULL,
    open        FLOAT,
    high        FLOAT,
    low         FLOAT,
    close       FLOAT,
    volume      BIGINT,
    fetched_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (ticker, date)
);
```

Source: `yfinance` batch download. Updated daily at market open.

### 3.2 `news` — News Items & Sentiment

```sql
CREATE TABLE news (
    id               SERIAL PRIMARY KEY,
    ticker           TEXT NOT NULL,
    source           TEXT,           -- "google_news" | "asx_rss"
    headline         TEXT NOT NULL,
    url              TEXT,
    published_at     TIMESTAMP,
    fetched_at       TIMESTAMP DEFAULT NOW(),
    sentiment_score  FLOAT,          -- raw Ollama score (-1.0 to +1.0)
    sentiment_label  TEXT,           -- "positive" | "neutral" | "negative"
    UNIQUE (ticker, headline, source)
);
```

### 3.3 `director_trades` — Insider Transactions

```sql
CREATE TABLE director_trades (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    director_name   TEXT,
    trade_date      DATE,
    trade_type      TEXT,     -- "buy" | "sell"
    shares          FLOAT,
    price           FLOAT,
    value           FLOAT
);
```

Source: ASX Form 604 (directors' interests), NSE SAST filings.

### 3.4 `macro` — Economic Indicators

```sql
CREATE TABLE macro (
    id          SERIAL PRIMARY KEY,
    date        DATE NOT NULL,
    indicator   TEXT NOT NULL,   -- "rba_rate" | "aud_usd" | "nifty_index"
    value       FLOAT,
    UNIQUE (date, indicator)
);
```

### 3.5 `signals` — Daily Multi-Factor Scores (Core Output)

```sql
CREATE TABLE signals (
    id                  SERIAL PRIMARY KEY,
    ticker              TEXT NOT NULL,
    date                DATE NOT NULL,
    sentiment_score     FLOAT,          -- 0-100
    fundamental_score   FLOAT,          -- 0-100
    technical_score     FLOAT,          -- 0-100
    insider_score       FLOAT,          -- 0-100
    composite_score     FLOAT,          -- 0-100 weighted average
    regime_ok           BOOLEAN,
    kelly_fraction      FLOAT,
    position_size_aud   FLOAT,          -- AUD to invest (0 if blocked)
    entry_price         FLOAT,
    target_price        FLOAT,          -- ATR-based profit target
    stop_loss_price     FLOAT,          -- ATR-based stop
    strategy_name       TEXT,
    direction           TEXT DEFAULT 'long',
    strategy_fires      BOOLEAN DEFAULT FALSE,
    generated_at        TIMESTAMP DEFAULT NOW(),
    UNIQUE (ticker, date)
);
```

**Key logic**: `position_size_aud > 0` only when ALL gates pass (quality + liquidity + validated strategy + composite ≥ threshold).

### 3.6 `strategy_assignments` — Per-Stock Strategy Allocation

```sql
CREATE TABLE strategy_assignments (
    id                  SERIAL PRIMARY KEY,
    ticker              TEXT UNIQUE NOT NULL,
    strategy_name       TEXT,
    direction           TEXT DEFAULT 'long',
    validated           BOOLEAN DEFAULT FALSE,
    bt_trades           INT,
    bt_win_rate         FLOAT,
    bt_profit_factor    FLOAT,
    bt_max_drawdown_pct FLOAT,
    fw_trades           INT,
    fw_win_rate         FLOAT,
    fw_profit_factor    FLOAT,
    fw_total_return_pct FLOAT,
    rank_score          FLOAT,
    assigned_at         TIMESTAMP
);
```

Updated weekly every Sunday via walk-forward backtest.

### 3.7 `watchlist` — Open Positions (Live Tracking)

```sql
CREATE TABLE watchlist (
    id                  SERIAL PRIMARY KEY,
    ticker              TEXT UNIQUE NOT NULL,
    entry_date          DATE,
    entry_price         FLOAT,
    current_price       FLOAT,
    target_price        FLOAT,
    stop_loss_price     FLOAT,
    shares              FLOAT,
    position_size_aud   FLOAT,
    unrealised_pnl      FLOAT,
    unrealised_pnl_pct  FLOAT,
    days_held           INT,
    signal_score        FLOAT,
    is_active           BOOLEAN DEFAULT TRUE,
    trading_mode        TEXT DEFAULT 'paper',
    direction           TEXT DEFAULT 'long',
    strategy_name       TEXT,
    updated_at          TIMESTAMP
);
```

### 3.8 `trades` — Closed Trade History

```sql
CREATE TABLE trades (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    trade_type      TEXT,     -- "buy" | "sell" | "short" | "cover"
    mode            TEXT,     -- "paper" | "ibkr_paper" | "live"
    entry_date      DATE,
    exit_date       DATE,
    entry_price     FLOAT,
    exit_price      FLOAT,
    shares          FLOAT,
    gross_pnl       FLOAT,   -- (exit - entry) × shares
    net_pnl         FLOAT,   -- gross - (2 × brokerage)
    brokerage       FLOAT,
    exit_reason     TEXT,    -- "stop_loss" | "target" | "stale" | "regime"
    signal_score    FLOAT
);
```

---

## 4. Data Ingestion Layer

### 4.1 Price Fetcher (`data_ingestion/price_fetcher.py`)

```
Job: job_fetch_prices  → runs at pre_market_hour:00 (09:00 ASX / 08:00 NSE)

Process:
  1. Batch download via yfinance.download(tickers, period="5d")
  2. Handle MultiIndex columns (yfinance ≥0.2 quirk)
  3. Upsert to prices table (merge-duplicates on ticker+date)
  4. Fallback: per-ticker retry if batch fails
  5. Store: open, high, low, close, volume

Also fetches macro indicators:
  ASX: RBA cash rate, AUD/USD, iron ore price, ^AXJO index
  NSE: USD/INR, Brent crude, ^NSEI index
```

### 4.2 News Fetcher (`data_ingestion/news_fetcher.py`)

```
Job: job_news_refresh  → runs every 2 hours (24/7)

Process:
  1. Build Google News RSS URL per ticker:
     URL = GNEWS_RSS.format(query=exchange.news_query_fn(ticker),
                            hl=exchange.gnews_hl,  gl=exchange.gnews_gl,
                            ceid=exchange.gnews_ceid)
     
     ASX query: "{TICKER} ASX stock"  (hl=en-AU, gl=AU, ceid=AU:en)
     NSE query: "{TICKER} NSE share"  (hl=en-IN, gl=IN, ceid=IN:en)
  
  2. Fetch feed with 8-second timeout per ticker (requests.get)
     ⚠ Critical: feedparser.parse(url) has no timeout — always use
       requests.get first then feedparser.parse(resp.content)
  
  3. Dedup by (ticker, headline, source) before insert
  4. Store: headline, url, published_at (UTC)
  5. Max 10 headlines per ticker per fetch

Also: _check_held_position_news()
  After fetch, re-score news for all positions in watchlist
  If sentiment < 20 → send Telegram warning alert
```

### 4.3 ASX/NSE Announcements (`data_ingestion/nse_announcements.py`)

```
Job: job_fetch_announcements → runs at pre_market_hour:20

ASX: Fetches official exchange disclosure PDFs (annual reports, half-yearly)
NSE: Fetches SEBI corporate action feed (dividends, results, bonus issues)
Stored in news table with source="asx_announcement" | "nse_announcement"
```

### 4.4 Insider Trade Scraper (`data_ingestion/nse_insider_scraper.py`)

```
Job: job_fetch_insider_trades → runs at pre_market_hour:40

NSE: Queries SAST (Substantial Acquisition of Shares and Takeovers)
     regulatory disclosures via NSE API
ASX: Parses ASX Form 604 (director interest notices)
Stored in director_trades table
Timeframe: last 90 days
```

---

## 5. AI Engine — Scoring Components

### 5.1 Sentiment Scorer (`ai_engine/sentiment.py`)

**Purpose**: NLP score from recent news headlines via local LLM (Ollama / llama3.1).

**Pipeline**:
```
1. get_recent_headlines(ticker, hours=72)  → last 5–15 headlines
2. Build prompt with ticker, company name, market context
3. POST to Ollama /api/generate
4. Parse JSON response: {score: float, label: str, key_theme: str, reasoning: str}
5. Normalize: normalized = (raw_score + 1.0) / 2.0 * 100   (→ 0-100)
6. Cache in Redis (1-hour TTL)
7. Update NewsItem.sentiment_score in DB
```

**Scoring Scale** (from Ollama):
```
-1.0 → 0    (very bearish / catastrophic news)
-0.5 → 25   (clearly negative)
 0.0 → 50   (neutral/no news)
+0.5 → 75   (positive earnings / contract win)
+1.0 → 100  (exceptional positive catalyst)
```

**Parallelism**: 3-worker ThreadPoolExecutor to avoid Ollama timeout under load.

**Fallback**: If Ollama unavailable → return 50 (neutral).

### 5.2 Fundamental Scorer (`ai_engine/fundamental_scorer.py`)

**Purpose**: Quantitative financial health assessment from yfinance metrics.

**8 Dimensions** (weighted composite):

| Metric | Weight | Data Source | Scoring Bands |
|--------|--------|-------------|---------------|
| P/E Ratio | 22% | `info["trailingPE"]` | 8–14→95, 14–20→80, 20–28→60, 28–40→38, >40→18 |
| Forward P/E | 13% | `info["forwardPE"]` | ≤12→95, 12–18→78, 18–25→58, >25→35 |
| ROE | 20% | `info["returnOnEquity"]` | ≥30%→100, 20–30%→85, 12–20%→65, 5–12%→45, <5%→20 |
| EPS Growth | 18% | TTM vs forward EPS | ≥25%→100, 12–25%→82, 3–12%→63, <0%→20 |
| Debt/Equity | 12% | `info["debtToEquity"]` | <0.2→100, 0.2–0.5→82, 0.5–1.0→62, >2.0→18 |
| Net Margin | 8% | `info["profitMargins"]` | ≥25%→95, 12–25%→75, <0%→15 |
| Revenue Growth | 5% | YoY % | ≥20%→90, 8–20%→70, <0%→30 |
| Dividend Yield | 2% | `info["dividendYield"]` | ≥5%→85, 3–5%→70, 1–3%→55 |

**Formula**:
```python
composite = (pe_score*0.22 + fpe_score*0.13 + roe_score*0.20 +
             eps_score*0.18 + debt_score*0.12 + mgn_score*0.08 +
             rev_score*0.05 + div_score*0.02)
```

**Caching**: 6-hour Redis TTL (fundamentals don't change intraday).

### 5.3 Technical Engine (`ai_engine/technical_engine.py`)

**Purpose**: Chart pattern and indicator analysis.

**8 Indicators** (weighted composite):

| Indicator | Weight | Period | Scoring Logic |
|-----------|--------|--------|---------------|
| RSI | 22% | 14-day | <25→90 (oversold), 25–35→78, 45–55→55 (neutral), >75→18 (overbought) |
| MACD | 20% | 12/26/9 EMA | Bullish crossover→85, Bearish→15, Bullish sustained→65 |
| Bollinger Bands | 18% | 20-day, 2σ | Below lower→88, Above upper→15, Mid zone→52 |
| EMA Crossover | 15% | 20/50-day | Golden cross→90, Death cross→10, Above 50→65 |
| Volume Spike | 10% | 20-day avg | ≥3×avg→90, 2–3×→75, 1.3–2×→60, <0.5×→35 |
| Stochastic RSI | 15% | 14-day | <20→85, 20–40→65, 60–80→35, >80→15 |

**ADX Modulation** (trend strength):
```python
# After raw composite computed:
if adx >= 40: multiplier = 1.10   # strong trend → higher confidence
elif adx < 25: multiplier = 0.95  # choppy → slight confidence penalty
else: multiplier = 1.0
composite = raw * multiplier
```

**ATR-Based Risk Parameters** (computed here, consumed by risk_params.py):
```python
stop_price   = latest_close - (2.0 × ATR14)    # 2× ATR stop
target_price = latest_close + (3.5 × ATR14)    # 3.5× ATR target (1:1.75 R:R)
```

### 5.4 Regime Filter (`ai_engine/regime_filter.py`)

**Purpose**: Market-wide risk classification — determines if macro environment favours new entries.

```python
def is_regime_ok() -> bool:
    """
    Fetch last 220 days of index price history.
    Calculate 200-day EMA.
    If current_index > ema_200 → RISK-ON (True)
    Else → RISK-OFF (False)
    
    4-hour cache (regime rarely flips intraday).
    """
    
    # Exchange-specific index:
    # ASX: ^AXJO (ASX 200)
    # NSE: ^NSEI (NIFTY 100)
```

**Impact on Trading**:
- RISK-OFF → position sizes **halved** in `risk_params.compute_position_size()`
- Regime does NOT block orders — size reduction is the control mechanism
- Held positions: NOT auto-exited on regime flip; Telegram alert sent

---

## 6. Signal Aggregation & Scoring

**File**: `signals/aggregator.py`

### 6.1 Core Scoring Formula

```python
def compute_signal(ticker: str, today: date = None) -> Dict:
    
    # Step 1: Gather component scores (0-100 each)
    s = score_sentiment(ticker)              # ai_engine/sentiment.py
    f = score_fundamental(ticker)            # ai_engine/fundamental_scorer.py
    t = score_technical(ticker)              # ai_engine/technical_engine.py
    i = score_insider(ticker)                # ai_engine/insider_pattern.py
    
    # Step 2: Weighted composite
    composite = (s * 0.375 + f * 0.3125 + t * 0.3125 + i * 0.0)
    composite = round(max(0.0, min(100.0, composite)), 2)   # clamp 0-100
    
    # Step 3: Strategy evaluation
    strat = get_strategy_signal(ticker)      # strategies/selector.py
    strategy_ok = strat["fires"] and strat["validated"]
    
    # Step 4: Quality gate (all dims must exceed minimums)
    quality_ok, quality_reason = _quality_check(s, f, t, i)
    #   MIN_SENTIMENT   = 30.0  (blocks "very negative news" stocks)
    #   MIN_FUNDAMENTAL = 35.0  (rejects financial distress)
    #   MIN_TECHNICAL   = 28.0  (rejects freefall / collapsing charts)
    
    # Step 5: Liquidity gate
    liquid_ok = _liquidity_check(ticker)
    #   Minimum avg daily turnover = $500,000 AUD
    #   Computed from 20-day avg (volume × close price)
    
    # Step 6: Actionability flag
    if direction == "long":
        actionable = quality_ok and liquid_ok and strategy_ok and composite >= SIGNAL_THRESHOLD
    elif direction == "short":
        actionable = liquid_ok and strategy_ok and (100 - composite) >= SIGNAL_THRESHOLD
    
    # Step 7: Position sizing (only if actionable)
    position_size_aud = 0.0
    if actionable:
        position_size_aud = compute_position_size(
            entry_price, stop_price, fundamental_score=f, regime_ok=is_regime_ok()
        )
    
    # Step 8: Persist to DB + return
    ...
```

### 6.2 Actionability Gate — The Full Decision Tree

```
                    ticker
                      │
               compute_signal()
                      │
          ┌───────────┴────────────┐
          │                        │
    quality_check              liquidity_check
    (s≥30, f≥35, t≥28)        (turnover ≥ $500k)
          │                        │
          └───────────┬────────────┘
                      │ both pass
                      ▼
             strategy validated?
             (StrategyAssignment.validated=True)
                      │
                      │ YES
                      ▼
               strategy fires today?
               (entry condition met)
                      │
                      │ YES
                      ▼
            composite ≥ SIGNAL_THRESHOLD (65)?
                      │
                      │ YES
                      ▼
                ACTIONABLE ✓
              position_size_aud > 0
              order will be placed
```

### 6.3 `run_full_scan(tickers)` — Batch Processing

Called by `job_signal_scan` (daily) and `job_rescan_and_trade` (market open):

```python
def run_full_scan(tickers: List[str]) -> List[Dict]:
    results = [compute_signal(t) for t in tickers]
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results
```

After scan, scheduler calls:
- `sync_signals_to_supabase()` — push to cloud
- `sync_regime_to_supabase()` — push regime status

---

## 7. Strategy Selection & Validation

**File**: `strategies/selector.py`

### 7.1 Available Strategies (`strategies/library.py`)

Each strategy defines:
- `name: str` — unique identifier
- `direction: "long" | "short"`
- `fires(ohlcv_df) -> bool` — entry signal for TODAY
- `stop_mult: float` — ATR stop multiplier override
- `target_mult: float` — ATR target multiplier override
- `max_hold_days: int` — stale exit override

**Built-in Strategies**:
| Strategy | Logic | Direction |
|----------|-------|-----------|
| `momentum_pullback` | Price retraced to EMA20 in uptrend, StochRSI oversold | Long |
| `shooting_star` | Bearish reversal candle at resistance (high wick) | Short |
| `oversold_bounce` | RSI < 30, close > previous day close | Long |
| `trend_follow` | 20-day EMA > 50-day EMA, price breakout above 20d high | Long |
| `bear_engulf` | Bearish engulfing candle, RSI > 60 (extended) | Short |
| `breakout` | Price closes above 52-week high with volume spike | Long |
| `breakdown` | Price closes below 52-week low with volume spike | Short |
| `mean_reversion` | RSI < 25, Bollinger below lower band, stochastic < 20 | Long |
| `hammer` | Hammer candlestick pattern at support | Long |
| `high_52w` | Stock near 52-week high, momentum | Long |
| `bull_engulf` | Bullish engulfing candle at support | Long |

### 7.2 Walk-Forward Backtest

```python
def select_for_ticker(ticker: str) -> Dict:
    """
    1. Load 760 days of price history (≈ 2 years via yfinance)
    2. Require ≥ 120 bars minimum
    3. Split: 70% in-sample (backtest) / 30% out-of-sample (forward test)
    4. For each strategy in ALL_STRATEGIES:
       a. Run backtest on 70% data — count trades, win rate, P/F, drawdown
       b. Run forward test on 30% data — same metrics
       c. Check validation gates (see below)
    5. Rank validated strategies by composite rank_score
    6. Assign best → StrategyAssignment (upsert)
    """
```

**Validation Gates** (`strategies/backtest.py`):

```
BACKTEST GATE (in-sample, 70% of data):
  ≥ 8 trades
  win_rate ≥ 45%
  profit_factor ≥ 1.5   (gross_profit / gross_loss)
  max_drawdown ≤ 25%

FORWARD TEST GATE (out-of-sample, 30% of data):
  ≥ 4 trades
  win_rate ≥ 35%
  profit_factor ≥ 1.3

BOTH gates must pass → validated = True
```

**Rank Score**:
```python
rank_score = (fw_profit_factor * 0.40 +
              fw_win_rate      * 0.30 +
              fw_total_return  * 0.20 +
              (1 / max(fw_drawdown, 0.01)) * 0.10)
```

### 7.3 Daily Strategy Signal Check

```python
def get_strategy_signal(ticker: str) -> Dict:
    """
    Priority order:
    1. Fetch StrategyAssignment for ticker
    2. If primary strategy fires today AND is validated → return it
    3. If primary is silent → scan ALL strategies for alternatives:
       - If any alternative fires AND has inline validation → use it
       (prevents missing entries when primary pattern isn't set up)
    4. If unvalidated → return {validated: False} → blocks order
    5. If unassigned → return None → composite-only path
    
    Returns: {strategy, direction, validated, fires, reason,
              stop_mult, target_mult, max_hold_days}
    """
```

**Stale-Out**: Assignments older than 21 days treated as unassigned.

**When `job_rescan_and_trade` is used instead of `job_place_orders`**:
1. Re-run `run_strategy_selection()` first — refreshes `validated` flags
2. Re-run `run_full_scan()` — now computes `position_size_aud > 0`
3. THEN call `job_place_orders()` — signals are fresh and actionable

---

## 8. Risk Parameters & Position Sizing

### 8.1 Position Sizing (`signals/risk_params.py`)

```python
def compute_position_size(
    entry_price: float,
    stop_price: float,
    fundamental_score: float = 50.0,
    regime_ok: bool = True,
    atr: Optional[float] = None,
) -> float:
    """
    Dollar-risk model with quality and regime adjustments.
    
    1. Base risk = PORTFOLIO_CAPITAL × 1.5%
       = $20,000 × 1.5% = $300 per trade
    
    2. Fundamental quality multiplier:
       score ≥ 75 → ×1.20 (strong business)
       score < 55 → ×0.80 (weaker quality)
    
    3. Regime penalty:
       RISK-OFF → halve risk ($300 → $150)
    
    4. stop_distance = abs(entry_price - stop_price)
    
    5. shares = adjusted_risk / stop_distance
    
    6. position_aud = shares × entry_price
    
    7. Cap: min(position_aud, PORTFOLIO_CAPITAL × MAX_POSITION_PCT)
       = min(position_aud, $20,000 × 20%) = max $4,000 per position
    """
```

### 8.2 ATR-Based Stop/Target (`signals/risk_params.py`)

```python
def compute_stop_target(entry_price, atr, regime_ok,
                        stop_mult=None, target_mult=None, direction="long"):
    """
    Default multipliers (can be overridden by strategy):
    
    LONG:
      stop_price   = entry - (2.0 × ATR)    # 2× ATR below entry
      target_price = entry + (3.5 × ATR)    # 3.5× ATR above (1:1.75 R:R)
    
    SHORT:
      stop_price   = entry + (2.0 × ATR)    # 2× ATR above entry
      target_price = entry - (3.5 × ATR)    # 3.5× ATR below
    
    Hard constraints:
      MIN_STOP_PCT = 3%    (never tighter than 3% from entry)
      MAX_STOP_PCT = 12%   (never wider than 12%)
    """
```

### 8.3 Kelly Sizing (`signals/kelly_sizer.py`)

```python
def compute_kelly_size(composite_score: float) -> (float, float):
    """
    Maps composite score → win probability and reward ratio:
    
    win_prob = 0.35 + (score/100 × 0.40)    # 35% to 75%
    reward   = 1.0 + (score/100 × 2.0)      # 1.0x to 3.0x
    
    Kelly: f* = (reward × win_prob - loss_prob) / reward
    Position: half_kelly = f* / 2    (half-Kelly for safety)
    Final: min(half_kelly, MAX_POSITION_PCT) × PORTFOLIO_CAPITAL
    
    Example (score=70):
      win_prob = 0.35 + 0.28 = 0.63
      reward   = 1.0 + 1.40  = 2.40
      f* = (2.40×0.63 - 0.37)/2.40 = 0.458
      half_kelly = 0.229 → position = min(22.9%, 20%) = 20%
      $20,000 × 20% = $4,000
    """
```

### 8.4 Trailing Stop (`execution/stop_loss.py`)

```python
# Activation threshold: 1.0 × ATR gain above entry
trail_activate_pct = atr / entry_price    # typically 2-5%

# Trail distance: 1.5 × ATR below peak close
trail_distance_pct = 1.5 × atr / entry_price

# Redis cache: peak close tracked per ticker
# Updated daily at market close
# 90-day TTL in cache
```

### 8.5 Stale Position Exit

```python
def compute_stale_days(adx: float) -> int:
    """
    ADX ≥ 30 (trending)    → 65 days (ride trends longer)
    ADX < 20 (choppy)      → 28 days (cut sideways sooner)
    Default                → 45 days
    """

def check_stale_positions() -> List[Dict]:
    """Exit if days_held > stale_days AND abs(pnl_pct) < 2%"""
```

---

## 9. Execution Layer

### 9.1 Phase 1 — Internal Paper Trader (`execution/paper_trader.py`)

```python
def execute_buy(signal: Dict) -> Dict:
    """
    1. Check effective composite ≥ SIGNAL_THRESHOLD
       (longs: composite ≥ 65; shorts: 100 - composite ≥ 65)
    2. Verify position_size_aud > 0 (all gates passed upstream)
    3. Verify ticker not already in watchlist
    4. Get latest price from yfinance (most recent close)
    5. Simulate fill: fill_price = price × (1 + 0.001)  [0.1% slippage]
    6. Deduct brokerage: $9.95 per leg
    7. actual_cost = shares × fill_price + brokerage
    8. Add WatchlistItem row (is_active=True)
    9. Add Trade row (exit_date=None)
    10. Log + return fill dict
    """

def execute_sell(ticker: str, reason: str) -> Dict:
    """
    1. Fetch WatchlistItem for ticker
    2. Get latest price from yfinance
    3. Simulate fill: fill_price = price × (1 - 0.001)  [0.1% slippage]
    4. Compute P&L:
       LONG:  net_pnl = (fill - entry) × shares - 2 × brokerage
       SHORT: net_pnl = (entry - fill) × shares - 2 × brokerage
    5. Update Trade row with exit_date, exit_price, net_pnl
    6. Remove WatchlistItem (is_active=False)
    7. Send Telegram exit alert
    8. Return {ticker, fill_price, net_pnl, exit_reason}
    """

def process_new_signals(signals: List[Dict]) -> List[Dict]:
    """Batch: attempt execute_buy for each signal not already held."""
```

### 9.2 Exit Management (`execution/stop_loss.py`)

Called twice daily: once intraday (every 30 min via `job_intraday_check`), once EOD (via `job_market_close`).

```python
def evaluate_exits(live_prices: Dict = None) -> tuple:
    """
    For each active WatchlistItem:
    
    LONG exits:
      Hard stop:      current ≤ stop_loss_price → sell("stop_loss")
      Trailing stop:  peak updated if current > previous peak
                      current ≤ peak - trail_distance → sell("trailing_stop")
      Target:         current ≥ target_price → sell("target")
    
    SHORT exits:
      Hard stop:      current ≥ stop_loss_price → sell("stop_loss")
      Target:         current ≤ target_price → sell("target")
    
    EOD only: update current_price, unrealised_pnl, days_held
    """
```

---

## 10. Scheduler & Job Orchestration

**File**: `scheduler/main_scheduler.py` | Engine: APScheduler `BlockingScheduler`

### 10.1 Full Job Schedule

#### Exchange-Adaptive Timing

```python
ph  = exchange.pre_market_hour    # ASX=9, NSE=8
mo_h, mo_m = exchange.market_open # ASX=(10,0), NSE=(9,15)
mc_h, mc_m = exchange.market_close# ASX=(16,0), NSE=(15,30)

pipeline_done_min = (ph + 1) * 60 + 50    # pipeline finishes ~ph+1:50
market_open_min   = mo_h * 60 + mo_m + 45 # market open + 45 min liquidity wait
rescan_total_min  = max(pipeline_done_min, market_open_min)
rescan_h = rescan_total_min // 60
rescan_m = rescan_total_min % 60
```

**Resulting Times**:
| Job | ASX (AEST) | NSE (IST) |
|-----|-----------|-----------|
| `job_fetch_prices` | 09:00 | 08:00 |
| `job_fetch_announcements` | 09:20 | 08:20 |
| `job_fetch_insider_trades` | 09:40 | 08:40 |
| `job_ai_sentiment_fundamental` | 10:00 | 09:00 |
| `job_technical_regime` | 10:15 | 09:50 |
| `job_signal_scan` | 10:20 | 10:20 |
| `job_daily_report` | 10:30 | 10:30 |
| **`job_rescan_and_trade`** | **10:45** | **10:50** |
| `job_intraday_check` | every 30 min | every 30 min |
| `job_market_close` | 16:00 | 15:30 |
| `job_news_refresh` | every 2 hrs | every 2 hrs |
| `job_strategy_selection` | Sun 07:00 | Sun 07:00 |
| `job_weekly_sunday` | Sun 08:00 | Sun 08:00 |

### 10.2 Job Descriptions

#### `job_fetch_prices()`
Calls `fetch_prices()` + `fetch_macro()`. Stores OHLCV and economic indicators. Pre-market data for the day.

#### `job_ai_sentiment_fundamental()`
Runs `batch_score_sentiment()` (3 threads) + `score_fundamental()` for all tickers. Results cached in Redis. Slowest step (~45-60 min for 100-200 tickers).

#### `job_technical_regime()`
Runs `score_technical()` for all tickers + `is_regime_ok()`. Computes ATR, RSI, MACD, etc. Results cached.

#### `job_signal_scan()`
```python
def job_signal_scan():
    results = run_full_scan(exchange.tickers)
    sync_signals_to_supabase()
    sync_regime_to_supabase()
    job_signal_decay_check()   # warn if held position scores dropped < 45
```

#### `job_rescan_and_trade()` ← KEY JOB
```python
def job_rescan_and_trade():
    """
    Atomic: validate → rescore → sync → trade.
    
    Fixes the core problem: signals stored earlier may have
    position_size_aud=0 because strategy wasn't validated yet.
    This job re-validates first, then re-scores so sizes are correct.
    """
    # Step 1: Re-validate strategies (refreshes validated flags)
    run_strategy_selection(tickers)
    
    # Step 2: Re-score all tickers with fresh validated flags
    run_full_scan(tickers)    # now actionable signals have position_size_aud > 0
    
    # Step 3: Sync everything to both Supabase DBs
    sync_signals_to_supabase()
    sync_regime_to_supabase()
    sync_strategy_assignments_to_supabase()
    sync_trades_to_supabase()     # keep closed-trade history current
    
    # Step 4: Place orders (watchlist sync happens inside)
    job_place_orders()
```

#### `job_place_orders()`
```python
def job_place_orders():
    signals = get_top_signals(n=20)
    
    if LIVE_TRADING_ENABLED:             # Phase 3
        place_market_buy(ticker, shares) # IBKR live
    elif IBKR_PAPER_ENABLED:             # Phase 2
        ibkr_process_new_signals(signals)
    else:                                # Phase 1
        fills = process_new_signals(signals)
    
    # Telegram alerts for all fills + volume spikes
    # sync_watchlist_to_supabase()
```

#### `job_intraday_check()`
Every 30 min during market hours. Fetches live 1-min prices via yfinance and checks stops/targets using `intraday_evaluate_exits()`. Sends intraday Telegram alerts for triggered exits.

#### `job_market_close()`
EOD evaluation: `evaluate_exits()` with close prices, `check_stale_positions()`. Sync watchlist + trades to Supabase.

#### `job_strategy_selection()` (Sunday 07:00)
Run `run_strategy_selection()` for all tickers → walk-forward backtest, validate, assign. Sync to Supabase. This is the most compute-intensive job (~3-4 hours for 200 ASX tickers).

#### `job_signal_decay_check()`
After signal scan, check all held positions. If `composite_score < 45` → send Telegram alert "Position decaying, consider review." Does NOT auto-exit.

#### `job_weekly_sunday()` (Sunday 08:00)
- Run aggregate walk-forward backtest (50-ticker sample, 6-month window)
- Generate Claude LLM weekly summaries for top holdings
- Send weekly Telegram summary
- `sync_backtest_to_supabase(results)`

### 10.3 launchd Auto-Start (macOS)

Two plist files in `~/Library/LaunchAgents/`:

```xml
<!-- com.asx.trading.plist -->
StartCalendarInterval:
  Mon-Sat, Hour=5, Minute=50  (AEST)
ProgramArguments: asx_start_scheduler.sh
StandardOutPath: logs/launchd_asx.log

<!-- com.nse.trading.plist -->  
StartCalendarInterval:
  Mon-Fri, Hour=13, Minute=0  (AEST = 8:30 IST)
ProgramArguments: nse_start_scheduler.sh
StandardOutPath: logs/launchd_nse.log
```

Startup scripts set `EXCHANGE`, `TZ`, wait for PostgreSQL, then exec `python main.py`.

---

## 11. Cloud Sync (Supabase)

**File**: `storage/supabase_sync.py`

### 11.1 Architecture

```
Local PostgreSQL  →  supabase_sync.py  →  Primary Supabase (legacy)
                  ↘                    ↘  New Supabase (AITrading-V2)
```

**Transport**: Direct REST API (`requests.post` to PostgREST endpoints). No supabase-py to avoid dependency conflicts. Upsert via `Prefer: resolution=merge-duplicates` header.

**Design principles**:
- Fire-and-forget: sync failures NEVER crash the scheduler
- All sync functions: `try/except → logger.warning + return False`
- 30-second timeout per request

### 11.2 Dual-Write Logic

```python
NEW_DB_EPOCH = date(2026, 6, 19)  # fresh account start date

def _all_db_configs():
    """Yield (url, key, label) for both configured DBs."""
    for label in ("primary", "new"):
        url, key = _get_config(label)
        if url:
            yield url, key, label
```

**New DB Filtering** (watchlist + trades):
```python
# In sync_watchlist_to_supabase:
if label == "new":
    rows = [r for r in payload if (r.get("entry_date") or "") >= str(NEW_DB_EPOCH)]

# In sync_trades_to_supabase:
if label == "new":
    rows = [r for r in payload if (r.get("entry_date") or "") >= str(NEW_DB_EPOCH)]
```

Signals, regime, strategy assignments: NO epoch filter — these are point-in-time data, not historical records.

### 11.3 Supabase Schema (Cloud Tables)

All 6 tables in both Supabase instances:

| Table | PK | Purpose |
|-------|-----|---------|
| `signals` | (ticker, date) | Daily scores for all tickers |
| `watchlist` | ticker | Active open positions |
| `trades` | (ticker, trade_type, entry_date) | Closed trade history |
| `regime` | exchange | Current market regime status |
| `strategy_assignments` | (ticker, strategy_name) | Per-stock backtested strategies |
| `backtest_cache` | (exchange, computed_at) | Weekly walk-forward results |

**RLS**: Enabled on all tables. Dashboard uses service role key (bypasses RLS).

### 11.4 Sync Call Points

| Function | Called After | Tables Written |
|----------|-------------|----------------|
| `sync_signals_to_supabase()` | `job_signal_scan`, `job_rescan_and_trade` | signals |
| `sync_regime_to_supabase()` | same | regime |
| `sync_strategy_assignments_to_supabase()` | `job_strategy_selection`, `job_rescan_and_trade` | strategy_assignments |
| `sync_watchlist_to_supabase()` | `job_place_orders`, `job_market_close` | watchlist |
| `sync_trades_to_supabase()` | `job_market_close`, `job_rescan_and_trade` | trades |
| `sync_backtest_to_supabase()` | `job_weekly_sunday` | backtest_cache |

---

## 12. Dashboard Data Layer

**File**: `dashboard/data.py`

### 12.1 Backend Routing

```python
def _use_supabase() -> bool:
    return bool(os.getenv("SUPABASE_URL", ""))

# If SUPABASE_URL is set → use Supabase REST API (Streamlit Cloud)
# Else → use local PostgreSQL via SQLAlchemy (local development)

def _sb_config(db: str = "primary"):
    if db == "new":
        url = os.getenv("SUPABASE_URL_B", "")
        key = os.getenv("SUPABASE_KEY_B", "")
        if url and key: return url, key
    return os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
```

**Dashboard DB Switcher** (sidebar radio): Default = "new" (AITrading-V2). All data functions accept `db: str = "primary"` parameter propagated from `active_db` session state.

### 12.2 Key Data Functions

```python
get_signals(exchange, signal_date, n, db) 
    → 3-day lookback fallback (handles weekends/holidays)

get_portfolio(exchange, live, db)
    → watchlist + live yfinance prices + prev-close day P&L
    → total_invested, unrealised_pnl, realised_all_time, total_pnl

get_trades(exchange, days, db)
    → _normalise_trade() ensures net_pnl recomputed if 0/NULL
    → Returns newest-first, last N days

get_regime(exchange, db)
    → {regime_ok, index, index_name, ema200, pct_above}

get_cumulative_pnl(exchange, days, db)
    → daily + cumulative net P&L from closed trades

get_strategy_radar(exchange, db)
    → joins strategy_assignments + today's signals
    → fields: ticker, validated, firing, near_miss, bt_profit_factor,
              fw_profit_factor, fw_win_rate, composite_score, direction

get_score_history(ticker, days, db)
    → 30-day composite + component scores for sparklines

get_backtest_results(exchange, db)
    → parses backtest_cache.results_json from last Sunday run

market_status(exchange) → {open: bool, local_time: str}
```

### 12.3 Live Price Overlay

```python
# Inside get_portfolio() when live=True and market is open:
live_prices = get_live_prices(tickers)  # yfinance 1-min quotes

# Override watchlist's stored current_price with real-time quote
# Recompute unrealised_pnl and unrealised_pnl_pct
# Mark position with is_live=True for dashboard indicator
```

---

## 13. Alerts & Reporting

### 13.1 Telegram Alerts (`alerts/telegram_bot.py`)

| Trigger | Alert Type | Content |
|---------|-----------|---------|
| Signal above threshold | `send_signal_alert()` | Ticker, score breakdown, entry/stop/target, strategy |
| Volume spike ≥ 2× avg | `send_volume_spike_alert()` | Ticker, ratio, score |
| Stop loss hit | `send_exit_alert()` | Ticker, entry/exit, P&L, reason |
| Target hit | `send_exit_alert()` | Same |
| Position decay < 45 | warning alert | Ticker, current score |
| Negative news < 20 | `send_news_alert()` | Ticker, headline, sentiment |
| Weekly summary | `send_weekly_summary()` | Top 5 positions, P&L, backtest metrics |

### 13.2 Daily Report (`reports/daily_report.py`)

Runs at `job_daily_report` (ph+1:30):
- Top 10 signals by composite score
- Regime status
- Held positions summary
- Sent via Telegram

---

## 14. End-to-End Data Flow

### 14.1 Daily Trading Cycle

```
PRE-MARKET (ASX 09:00 / NSE 08:00)
═══════════════════════════════════
 ph:00   fetch_prices()
           → yfinance batch download
           → prices table (upsert)
           → macro_fetcher (RBA/INR/etc) → macro table

 ph:20   fetch_announcements()
           → ASX/NSE exchange APIs → news table

 ph:40   fetch_insider_trades()
           → ASX Form 604 / NSE SAST → director_trades table

 ph+1:00 job_ai_sentiment_fundamental()
           FOR EACH TICKER (parallel, 3 workers):
             1. get_recent_headlines(72h) → 5-15 headlines
             2. Ollama llama3.1 prompt → {score, label, theme}
             3. normalize -1.0→+1.0 to 0-100
             4. cache sentiment in Redis (1h TTL)
           FOR EACH TICKER:
             1. yfinance.info → P/E, ROE, EPS, debt, margin, etc
             2. 8 metrics × weights → fundamental composite (0-100)
             3. cache fundamental in Redis (6h TTL)

 ph+1:15 job_technical_regime()
           FOR EACH TICKER:
             1. price_series (last 120 days)
             2. RSI14, MACD(12/26/9), BB(20), EMA(20/50), Volume, StochRSI
             3. ADX modulation → technical composite (0-100)
             4. ATR14 → stop/target prices
             5. cache technical in Redis (4h TTL)
           REGIME:
             1. ^AXJO or ^NSEI index (last 220 days)
             2. EMA200
             3. regime_ok = index > EMA200
             4. cache 4h

 ph+1:20 job_signal_scan()
           FOR EACH TICKER:
             1. s = sentiment_score (from Redis)
             2. f = fundamental_score (from Redis)
             3. t = technical_score (from Redis)
             4. i = insider_score (director trade recency/size)
             5. composite = s×0.375 + f×0.3125 + t×0.3125 + i×0
             6. quality_check(s≥30, f≥35, t≥28)
             7. liquidity_check(avg_turnover ≥ $500k)
             8. get_strategy_signal() → fires? validated?
             9. actionable = quality_ok AND liquid_ok AND strategy_ok
                             AND composite ≥ 65
             10. IF actionable: compute_position_size(entry, stop, f, regime)
             11. UPSERT → signals table
           sync_signals_to_supabase()    → both Supabase DBs
           sync_regime_to_supabase()     → both Supabase DBs
           job_signal_decay_check()

 ph+1:30 job_daily_report()
           → top 10 signals → Telegram


MARKET OPEN (ASX 10:00 / NSE 09:15)
═════════════════════════════════════
 +45min  job_rescan_and_trade()
           1. run_strategy_selection(tickers)  ← RE-VALIDATE strategies
           2. run_full_scan(tickers)           ← RE-SCORE with fresh flags
           3. sync_signals + regime + assignments + trades → Supabase
           4. job_place_orders():
              get_top_signals(n=20, min_score=65)
              FOR each signal WHERE position_size_aud > 0 AND ticker not held:
                execute_buy(signal)
                  → yfinance latest price
                  → fill = price × 1.001  (slippage)
                  → WatchlistItem → DB
                  → Trade (entry) → DB
              sync_watchlist_to_supabase()


DURING MARKET (every 30 min)
══════════════════════════════
 job_intraday_check():
   live_prices = yfinance 1-min quotes (all held tickers)
   intraday_evaluate_exits(live_prices):
     LONG: if current ≤ stop_loss → execute_sell("intraday_stop")
           if current ≥ target   → execute_sell("intraday_target")
     SHORT: reversed
   → Telegram intraday alerts

 job_news_refresh() [every 2h]:
   fetch_news() → Google News RSS → news table (dedup)
   _check_held_position_news() → Telegram if sentiment < 20


MARKET CLOSE (ASX 16:00 / NSE 15:30)
══════════════════════════════════════
 job_market_close():
   evaluate_exits():
     FOR each WatchlistItem:
       close_price = yfinance daily close
       UPDATE current_price, unrealised_pnl, days_held
       LONG:  if close ≤ stop → sell("stop_loss")
              if close ≥ target → sell("target")
              check trailing stop (peak × trail_distance)
       SHORT: reversed logic
   check_stale_positions():
     if days_held > stale_days AND abs(pnl_pct) < 2% → sell("stale")
   sync_watchlist_to_supabase()   ← positions (filtered by epoch for new DB)
   sync_trades_to_supabase()      ← closed trades (filtered by epoch for new DB)


WEEKLY (Sunday)
════════════════
 07:00  job_strategy_selection():
   FOR each ticker:
     price_history = yfinance 2yr (760 bars)
     FOR each strategy in ALL_STRATEGIES:
       backtest on 70%: trades, win_rate, profit_factor, drawdown
       forward_test on 30%: same metrics
       validated = BT gate AND FW gate (see Section 7.2)
     rank_score = weighted composite of FW metrics
     assign best validated → StrategyAssignment (upsert)
   sync_strategy_assignments_to_supabase()

 08:00  job_weekly_sunday():
   run_walk_forward() (50-ticker sample, 6 months)
   claude_summarizer.generate_summaries() (top 10 positions)
   send_weekly_summary() → Telegram
   sync_backtest_to_supabase(results)
```

---

## 15. Key Thresholds & Parameters Reference

| Parameter | Value | File | Purpose |
|-----------|-------|------|---------|
| `SIGNAL_THRESHOLD` | 65.0 | settings.py | Min composite score to place order |
| `MAX_POSITION_PCT` | 20% | settings.py | Max % of capital per position |
| `STOP_LOSS_PCT` | 7% | settings.py | Hard stop fallback |
| `PAPER_BROKERAGE` | $9.95 | settings.py | Commission per leg (ASX flat) |
| `PAPER_SLIPPAGE` | 0.1% | settings.py | Simulated market impact |
| `PORTFOLIO_CAPITAL` | $20,000 | settings.py | Base trading capital |
| `DOLLAR_RISK_PCT` | 1.5% | risk_params.py | Per-trade risk budget |
| `ATR_STOP_MULT` | 2.0 | risk_params.py | Stop = entry - (2 × ATR) |
| `ATR_TARGET_MULT` | 3.5 | risk_params.py | Target = entry + (3.5 × ATR) |
| `TRAIL_ACTIVATE_MULT` | 1.0 | stop_loss.py | Start trailing at 1× ATR gain |
| `TRAIL_DISTANCE_MULT` | 1.5 | stop_loss.py | Trail 1.5× ATR below peak |
| `STALE_DAYS_DEFAULT` | 45 | risk_params.py | Exit if stuck > 45 days |
| `STALE_MIN_MOVE` | 2% | stop_loss.py | Only stale if move < 2% |
| `DECAY_THRESHOLD` | 45.0 | aggregator.py | Warn if held position drops below |
| `MIN_SENTIMENT` | 30.0 | aggregator.py | Quality gate — blocks v. negative |
| `MIN_FUNDAMENTAL` | 35.0 | aggregator.py | Quality gate — financial health |
| `MIN_TECHNICAL` | 28.0 | aggregator.py | Quality gate — chart floor |
| `MIN_LIQUIDITY` | $500k/day | aggregator.py | Avg daily turnover minimum |
| `BT_MIN_TRADES` | 8 | backtest.py | Backtest statistical minimum |
| `BT_MIN_WIN_RATE` | 45% | backtest.py | Backtest validation gate |
| `BT_MIN_PF` | 1.5 | backtest.py | Backtest profit factor |
| `BT_MAX_DD` | 25% | backtest.py | Backtest max drawdown |
| `FW_MIN_TRADES` | 4 | backtest.py | Forward test minimum |
| `FW_MIN_WIN_RATE` | 35% | backtest.py | Forward test gate |
| `FW_MIN_PF` | 1.3 | backtest.py | Forward test profit factor |
| `ASSIGNMENT_MAX_AGE` | 21 days | selector.py | Stale assignment threshold |
| `NEWS_FETCH_TIMEOUT` | 8 sec | news_fetcher.py | Per-ticker Google News timeout |
| `SENTIMENT_CACHE_TTL` | 1 hr | sentiment.py | Redis cache duration |
| `FUNDAMENTAL_CACHE_TTL` | 6 hrs | fundamental_scorer.py | Redis cache duration |
| `REGIME_CACHE_TTL` | 4 hrs | regime_filter.py | Redis cache duration |
| `NEW_DB_EPOCH` | 2026-06-19 | supabase_sync.py | Fresh account start date |

---

## 16. Phase Progression (Paper → Live)

```
PHASE 1 (current): Internal Paper Trader
  TRADING_PHASE=1
  IBKR_PAPER_ENABLED=False
  LIVE_TRADING_ENABLED=False
  
  Order path:
    process_new_signals(signals)
    → execute_buy(signal)
    → WatchlistItem + Trade(entry) → local PostgreSQL
    → sync_watchlist_to_supabase()
  
  Fill price: yfinance daily close + 0.1% slippage

PHASE 2: IBKR Paper Trading
  TRADING_PHASE=2
  IBKR_PAPER_ENABLED=True
  TWS paper account running on port 7497
  
  Order path:
    ibkr_process_new_signals(signals)
    → place_paper_order(ticker, shares, order_type="MKT")
    → TWS fills at real intraday market price
    → ibkr_paper_trader.py records fill

PHASE 3: IBKR Live Trading
  TRADING_PHASE=3
  LIVE_TRADING_ENABLED=True
  TWS live account running on port 7496
  
  Order path:
    place_market_buy(ticker, shares)
    → place_stop_loss_order(ticker, shares, stop_price)
    → Real money execution via IBKR
  
  ⚠ NEVER execute via Claude — user must approve all live trades
```

---

## 17. Project Directory Structure

```
AITrading/
├── config/
│   ├── __init__.py               # get_active_exchange()
│   ├── settings.py               # all constants, thresholds, env vars
│   ├── exchange_registry.py      # Exchange dataclass + registry
│   ├── exchanges/
│   │   ├── asx.py                # ASX 200 registration
│   │   └── nse.py                # NSE NIFTY 100 registration
│   ├── asx200_tickers.py         # 200 ASX tickers
│   └── nifty100_tickers.py       # 100 NSE tickers
│
├── storage/
│   ├── models.py                 # SQLAlchemy ORM (all 8 tables)
│   ├── database.py               # session factory, connection pooling
│   ├── cache.py                  # Redis wrapper (score + peak cache)
│   └── supabase_sync.py          # Supabase cloud sync (dual-write)
│
├── ai_engine/
│   ├── sentiment.py              # Ollama NLP sentiment scoring
│   ├── fundamental_scorer.py     # yfinance financial health scoring
│   ├── technical_engine.py       # RSI/MACD/BB/EMA/Volume indicators
│   ├── regime_filter.py          # 200-day EMA regime detection
│   ├── insider_pattern.py        # director trade scoring
│   ├── backtester.py             # walk-forward backtest engine
│   └── claude_summarizer.py      # Claude LLM weekly summaries
│
├── signals/
│   ├── aggregator.py             # multi-factor scoring + gates
│   ├── risk_params.py            # ATR stop/target, position sizing
│   ├── kelly_sizer.py            # Kelly criterion position sizing
│   └── watchlist.py              # active position management
│
├── strategies/
│   ├── base.py                   # Strategy abstract base class
│   ├── library.py                # ALL_STRATEGIES registry
│   ├── selector.py               # per-stock walk-forward assignment
│   ├── backtest.py               # backtest + forward test engine
│   ├── indicators.py             # precompute() indicator cache
│   ├── patterns.py               # candlestick pattern detection
│   └── *.py                      # individual strategy implementations
│
├── execution/
│   ├── paper_trader.py           # Phase 1 internal paper trading
│   ├── stop_loss.py              # exit management (stop/target/stale)
│   ├── ibkr_paper_trader.py      # Phase 2 IBKR paper
│   └── ibkr_trader.py            # Phase 3 IBKR live
│
├── data_ingestion/
│   ├── price_fetcher.py          # yfinance OHLCV + macro
│   ├── news_fetcher.py           # Google News RSS (8s timeout)
│   ├── macro_fetcher.py          # economic indicator fetcher
│   ├── nse_announcements.py      # NSE corporate action parser
│   └── nse_insider_scraper.py    # NSE SAST filing scraper
│
├── scheduler/
│   └── main_scheduler.py         # APScheduler: all jobs + cron times
│
├── dashboard/
│   ├── app_v2.py                 # Streamlit UI (multi-tab)
│   └── data.py                   # dual-backend data access layer
│
├── alerts/
│   └── telegram_bot.py           # signal/exit/decay Telegram alerts
│
├── reports/
│   └── daily_report.py           # top-10 daily Telegram report
│
├── scripts/
│   └── regression_test.py        # 4-scenario parameter sweep
│
├── logs/
│   ├── asx_trading.log           # ASX scheduler output
│   ├── nse_scheduler.log         # NSE scheduler output
│   ├── launchd_asx.log           # launchd stdout
│   └── launchd_nse.log           # launchd stdout
│
├── main.py                       # entry point → build_scheduler().start()
├── .env                          # secrets (gitignored)
├── .streamlit/config.toml        # Streamlit config
├── requirements.txt
└── docs/
    └── SYSTEM_ARCHITECTURE.md    # ← this document
```

---

*End of Document. Generated June 2026.*
