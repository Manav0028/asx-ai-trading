# AI Trading System — System Manual

**Version:** Phase 1 (Paper Trading)
**Exchanges:** ASX 200 🇦🇺 · NSE NIFTY 100 🇮🇳
**Last updated:** May 2026

---

## 1. What the System Does

An automated stock scanning and paper trading engine that:
- **Pulls data** from 5 free sources every day before market open
- **Scores every stock** across 4 AI/ML dimensions (0–100 each)
- **Aggregates** into one composite score and shortlists candidates
- **Places simulated trades** on qualifying stocks at market open
- **Monitors positions** for stop-loss, trailing stop, and profit targets
- **Alerts** you via Telegram with plain-English explanations

No real money is used in Phase 1. All orders are simulated at real market prices.

---

## 2. Daily Schedule

### ASX 200 (AEST)
| Time | Job |
|------|-----|
| 5:50 AM | Scheduler starts (cron) |
| 6:00 AM | yFinance prices + macro indicators fetched |
| 6:30 AM | ASX announcements + Form 604 director trades |
| 7:00 AM | Ollama sentiment scoring (3 parallel workers) + fundamentals |
| 7:15 AM | Technical indicators + market regime check |
| 7:20 AM | Signal aggregation — all 153 stocks scored |
| 7:30 AM | 📱 Daily report → Telegram + email |
| 10:00 AM | Paper orders placed (score ≥ 65, regime checked) |
| 4:00 PM | Stop-loss / target / trailing-stop evaluation |
| Every 2h | Google News refresh |
| Sunday 8AM | Walk-forward backtest + weekly Telegram summary |

### NSE NIFTY 100 (IST — via EXCHANGE=nse)
Same pipeline, offset for IST timezone. Runs as a separate process.

---

## 3. Data Sources

| Source | What | Frequency |
|--------|------|-----------|
| **yFinance** | OHLCV prices for all tickers | Daily |
| **Google News RSS** | Headlines per stock | Every 2 hrs |
| **ASX Announcements** | Company filings + updates | Every 30 min |
| **Form 604 Scraper** | Director buy/sell disclosures | Daily |
| **yFinance Macro** | AUD/USD, gold, oil, VIX, S&P500, XJO/NIFTY | Daily |

---

## 4. Scoring Engines (Layer 3)

### 4.1 Sentiment Score — 30% weight

**Tool:** Ollama llama3.1 (local, free)
**Input:** Last 72 hours of news headlines per ticker
**Output:** 0–100 (50 = neutral)

**Calculation:**
```
Ollama reads up to 15 headlines and returns JSON:
  {"score": -1.0 to 1.0, "label": "positive/neutral/negative",
   "key_theme": "5-word summary", "reasoning": "one sentence"}

score_0_100 = (raw_score + 1.0) / 2.0 × 100
```

**Scoring guide Ollama uses:**
- `+1.0` = Very bullish (earnings beat, major contract, buyout)
- `+0.5` = Mildly positive (upgrade, guidance raised)
- ` 0.0` = Neutral (routine update)
- `-0.5` = Mildly negative (cost pressures, downgrade)
- `-1.0` = Very bearish (profit warning, scandal, regulatory action)

---

### 4.2 Fundamental Score — 25% weight

**Tool:** yFinance `.info` dict (P/E, ROE, EPS, etc.)
**Output:** 0–100

**8 metrics and their weights:**

| Metric | Weight | Scores High When |
|--------|--------|-----------------|
| Trailing P/E | 22% | P/E 8–20 (fair value) |
| Forward P/E | 13% | Forward P/E ≤ 18 |
| ROE | 20% | Return on equity ≥ 20% |
| EPS Growth | 18% | Forward EPS growing ≥ 12% vs trailing |
| Debt/Equity | 12% | D/E ratio below 0.5 |
| Net Profit Margin | 8% | Margin ≥ 12% |
| Revenue Growth | 5% | Revenue growing ≥ 8% |
| Dividend Yield | 2% | Yield ≥ 3% |

**Formula:**
```
fundamental = (PE×0.22) + (FPE×0.13) + (ROE×0.20) + (EPS×0.18)
            + (Debt×0.12) + (Margin×0.08) + (RevGrowth×0.05) + (Div×0.02)
```

---

### 4.3 Technical Score — 25% weight

**Tool:** Pure numpy from DB price history
**Output:** 0–100

#### RSI — Relative Strength Index (14-day) · 28% of tech score
```
Gains = price increases over last 14 days
Losses = price decreases over last 14 days
RS = avg(Gains) / avg(Losses)
RSI = 100 - (100 / (1 + RS))

Score: RSI < 25 → 90  (heavily oversold = bounce likely)
       RSI < 35 → 78  (oversold)
       RSI < 45 → 65  (mildly oversold)
       RSI 45-55 → 55 (neutral)
       RSI 55-65 → 45 (mildly overbought)
       RSI 65-75 → 32 (overbought)
       RSI > 75  → 18 (very overbought)
```

#### MACD — Moving Average Convergence Divergence · 22% of tech score
```
EMA12 = 12-day exponential moving average
EMA26 = 26-day exponential moving average
MACD_line = EMA12 - EMA26
Signal_line = 9-day EMA of MACD_line
Histogram = MACD_line - Signal_line

Score: Histogram just turned positive → 85 (momentum building — best signal)
       Histogram just turned negative → 15 (momentum fading)
       Histogram positive             → 65 (bullish)
       Histogram negative             → 35 (bearish)
```

#### Bollinger Bands (20-day, 2σ) · 22% of tech score
```
Middle = 20-day SMA of close
Upper = Middle + 2 × StdDev(20d)
Lower = Middle - 2 × StdDev(20d)
BB% = (Price - Lower) / (Upper - Lower)

Score: BB% < 10% → 88  (near lower band = bounce zone)
       BB% 10-25% → 72 (lower quarter = buy zone)
       BB% 25-45% → 58 (below midpoint)
       BB% 45-60% → 52 (midpoint)
       BB% 60-75% → 42 (above midpoint)
       BB% 75-90% → 28 (upper quarter = caution)
       BB% > 90%  → 15 (near upper band = stretched)
```

#### EMA Crossover (20-day / 50-day) · 18% of tech score
```
EMA20 = 20-day exponential moving average
EMA50 = 50-day exponential moving average

Score: EMA20 crosses above EMA50 → 90 (golden cross = strong bullish)
       EMA20 crosses below EMA50 → 10 (death cross = strong bearish)
       EMA20 already above EMA50 → 65 (uptrend confirmed)
       EMA20 already below EMA50 → 35 (downtrend confirmed)
```

#### Volume Spike · 10% of tech score
```
AvgVolume = average daily volume over last 20 days
Ratio = TodayVolume / AvgVolume

Score: Ratio ≥ 3.0× → 90 (strong institutional interest)
       Ratio ≥ 2.0× → 75 (elevated — worth noting)
       Ratio ≥ 1.3× → 60 (slightly elevated)
       Ratio < 0.5× → 35 (low activity = avoid)
       Otherwise    → 50 (normal)
```

#### ADX — Trend Strength Multiplier (not scored separately)
```
ADX measures how strong the current trend is (0–100)
ADX ≥ 30 → technical composite boosted × 1.10 (strong trend = more reliable signals)
ADX < 20 → technical composite reduced × 0.95 (choppy/sideways = less reliable)
```

#### Dynamic Stop/Target via ATR
```
ATR (14-day) = average of: max(High-Low, |High-PrevClose|, |Low-PrevClose|)
Stop-loss  = Entry price - (2 × ATR)   ← adapts to each stock's volatility
Target     = Entry price + (3 × ATR)   ← 1:1.5 risk/reward ratio
```

**Final technical score:**
```
technical = (RSI×0.28) + (MACD×0.22) + (BB×0.22) + (EMA×0.18) + (Vol×0.10)
          × ADX_multiplier
```

---

### 4.4 Insider Score — 20% weight

**Tool:** Rule-based (ML model trains once 6+ months of data accumulates)
**Source:** ASX Form 604 director trade disclosures
**Output:** 0–100 (base 50 = no data)

**Scoring rules:**
```
Net director buy value (90 days):
  > $5M  → +25 points
  $1-5M  → +15 points
  > $0   → +8 points
  < -$1M → -15 points (net selling)

Recency of last director buy:
  Within 7 days  → +10 points
  Within 30 days → +5 points
  Older than 60d → -5 points

Cluster buying (2+ directors in last 30 days):
  Yes → +10 points

Director buying below current price:
  Yes → +5 points

Heavy selling (sell count > 2× buy count):
  Yes → -10 points
```

---

## 5. Signal Aggregation (Layer 4)

### 5.1 Composite Score
```
composite = (sentiment × 0.30)
          + (fundamental × 0.25)
          + (technical × 0.25)
          + (insider × 0.20)
```
Result is 0–100. No regime dampening is applied to the score.

### 5.2 Market Regime Filter
```
XJO (or NIFTY) vs its 200-day EMA:

RISK-ON:  Index ABOVE EMA200 → normal position sizes
RISK-OFF: Index BELOW EMA200 → position sizes HALVED (scores unchanged)
```

### 5.3 Quality Gates (signal blocked if any fail)
```
Sentiment  ≥ 35   → not deeply negative news
Fundamental ≥ 40  → basic financial health present
Technical  ≥ 35   → not in free-fall
```

### 5.4 Liquidity Gate
```
Avg daily turnover = AvgVolume(20d) × Price
Minimum: $500,000/day   → avoids illiquid micro-caps
```

### 5.5 Trade Threshold
```
composite ≥ 65 (configurable in .env as SIGNAL_THRESHOLD)
AND quality gates pass
AND liquidity gate passes
AND no existing open position in that stock
```

---

## 6. Position Sizing — Kelly Formula

```
p = win probability   = 0.35 + (composite/100 × 0.40)
q = 1 - p             (loss probability)
b = reward/risk ratio = 1.0 + (composite/100 × 2.0)

Kelly fraction f* = (b×p - q) / b
Half-Kelly (safety) = f* / 2
Capped at MAX_POSITION_PCT (default 20% of portfolio)

Position AUD = Portfolio × min(half_kelly, 0.20)
Shares = floor(Position AUD / Entry Price)

In RISK-OFF regime: position AUD halved again
```

**Example at composite score = 70:**
```
p = 0.35 + (0.70 × 0.40) = 0.63
b = 1.0  + (0.70 × 2.0)  = 2.40
f* = (2.4×0.63 - 0.37) / 2.4 = 0.481
Half-Kelly = 0.241 → capped at 0.20 (20%)
Position = $100,000 × 0.20 = $20,000
```

---

## 7. Paper Trading Process (Layer 5)

### Entry (10:00 AM — market open)
```
1. Fetch top signals (score ≥ 65) from today's DB records
2. Skip any ticker already in active watchlist
3. Simulate fill:
   Buy fill price = latest price × 1.001 (0.1% slippage)
4. Add $9.95 brokerage
5. Record in trades table (mode='paper')
6. Add to watchlist with entry price, stop, target, shares
7. Send Telegram signal alert
```

### Position Monitoring (4:00 PM — market close)
Three exit conditions checked in order:

**1. Trailing Stop (activates after +5% gain)**
```
When gain ≥ 5%:
  Peak price = highest price seen since entry
  Trail stop = Peak × (1 - 0.05)  ← 5% below peak
  If current price ≤ trail stop → EXIT
  (Trail stop ratchets up as price rises — locks in gains)
```

**2. Hard Stop-Loss**
```
Effective stop = max(ATR-based stop, trail stop)
If current price ≤ stop → EXIT
```

**3. Profit Target**
```
Target = Entry + (3 × ATR)
If current price ≥ target → EXIT
```

**4. Time-Based Exit (stale position)**
```
If held ≥ 45 days AND price moved < 2% → EXIT
(Capital freed for better opportunities)
```

**On any exit:**
```
Sell fill price = latest price × 0.999 (0.1% slippage)
Net P&L = (sell - buy) × shares - $9.95×2 brokerage
Record in trades, remove from watchlist, send Telegram alert
```

---

## 8. Data Model

### 7 Tables in PostgreSQL (DB: asx_trading, port 5433)

```
┌─────────────────────────────────────────────────────────────┐
│  prices                                                      │
│  ticker | date | open | high | low | close | volume         │
│  PK: (ticker, date)                                          │
│  63,232 rows · 250 tickers · 365 days                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  news                                                        │
│  ticker | source | headline | url | published_at            │
│  sentiment_score | sentiment_label                           │
│  source: 'asx_rss' | 'google_news' | 'form604'              │
│  4,098 rows                                                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  signals                                                     │
│  ticker | date | sentiment_score | fundamental_score         │
│  technical_score | insider_score | composite_score           │
│  regime_ok | kelly_fraction | position_size_aud              │
│  entry_price | target_price | stop_loss_price                │
│  779 rows · 4 days of scans                                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  trades                                                      │
│  ticker | trade_type | mode | entry_date | exit_date         │
│  entry_price | exit_price | shares | gross_pnl | net_pnl     │
│  brokerage | exit_reason | signal_score                      │
│  exit_reason: 'stop_loss' | 'target' | 'stale' | 'manual'   │
│  23 rows (paper trades)                                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  watchlist                                                   │
│  ticker | entry_date | entry_price | target_price           │
│  stop_loss_price | shares | position_size_aud               │
│  current_price | unrealised_pnl | unrealised_pnl_pct        │
│  days_held | signal_score | is_active                        │
│  23 active positions                                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  director_trades                                             │
│  ticker | director_name | trade_date | trade_type           │
│  shares | price | value                                      │
│  trade_type: 'buy' | 'sell'                                  │
│  0 rows (ASX auth issue pending)                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  macro                                                       │
│  date | indicator | value                                    │
│  indicators: aud_usd, xjo_index, gold_usd, oil_brent,       │
│              vix, sp500, copper, iron_ore                    │
│  3,052 rows · 365 days                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Useful Queries

### Connect to Database
```bash
/opt/homebrew/opt/postgresql@14/bin/psql \
  -h /tmp -p 5433 -U manavsharma -d asx_trading
```

---

### Today's Top Signals
```sql
SELECT ticker, composite_score,
       sentiment_score, fundamental_score,
       technical_score, insider_score,
       entry_price, target_price, stop_loss_price,
       regime_ok
FROM signals
WHERE date = CURRENT_DATE
ORDER BY composite_score DESC
LIMIT 10;
```

### Signals Above Threshold (trade candidates)
```sql
SELECT ticker, composite_score,
       ROUND(entry_price::numeric, 2) AS entry,
       ROUND(target_price::numeric, 2) AS target,
       ROUND(stop_loss_price::numeric, 2) AS stop,
       ROUND(position_size_aud::numeric, 0) AS position_aud
FROM signals
WHERE date = CURRENT_DATE
  AND composite_score >= 65
ORDER BY composite_score DESC;
```

### All Active Positions (Watchlist)
```sql
SELECT ticker, entry_date, entry_price,
       current_price,
       ROUND(unrealised_pnl_pct::numeric, 2) AS pnl_pct,
       ROUND(unrealised_pnl::numeric, 2) AS pnl_aud,
       days_held,
       stop_loss_price, target_price
FROM watchlist
WHERE is_active = true
ORDER BY unrealised_pnl_pct DESC;
```

### Portfolio P&L Summary
```sql
SELECT
  COUNT(*) FILTER (WHERE is_active) AS open_positions,
  ROUND(SUM(unrealised_pnl) FILTER (WHERE is_active)::numeric, 2) AS total_unrealised_pnl,
  COUNT(*) FILTER (WHERE is_active AND unrealised_pnl > 0) AS winners,
  COUNT(*) FILTER (WHERE is_active AND unrealised_pnl <= 0) AS losers
FROM watchlist;
```

### All Closed Trades (History)
```sql
SELECT ticker, entry_date, exit_date,
       ROUND(entry_price::numeric, 3) AS bought_at,
       ROUND(exit_price::numeric, 3) AS sold_at,
       shares,
       ROUND(net_pnl::numeric, 2) AS net_pnl,
       exit_reason, signal_score
FROM trades
WHERE exit_date IS NOT NULL
ORDER BY exit_date DESC;
```

### Trade Performance Summary
```sql
SELECT
  COUNT(*) AS total_trades,
  COUNT(*) FILTER (WHERE net_pnl > 0) AS winners,
  COUNT(*) FILTER (WHERE net_pnl <= 0) AS losers,
  ROUND(AVG(net_pnl)::numeric, 2) AS avg_pnl,
  ROUND(SUM(net_pnl)::numeric, 2) AS total_pnl,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE net_pnl > 0) / NULLIF(COUNT(*), 0),
    1
  ) AS win_rate_pct
FROM trades
WHERE exit_date IS NOT NULL;
```

### Exit Reason Breakdown
```sql
SELECT exit_reason,
       COUNT(*) AS count,
       ROUND(AVG(net_pnl)::numeric, 2) AS avg_pnl
FROM trades
WHERE exit_date IS NOT NULL
GROUP BY exit_reason
ORDER BY count DESC;
```

### Recent News for a Stock
```sql
SELECT published_at, source, headline,
       sentiment_score, sentiment_label
FROM news
WHERE ticker = 'ALL.AX'          -- change ticker here
  AND published_at > NOW() - INTERVAL '7 days'
ORDER BY published_at DESC
LIMIT 20;
```

### Signal History for a Stock (last 30 days)
```sql
SELECT date, composite_score,
       sentiment_score, fundamental_score,
       technical_score, insider_score,
       entry_price
FROM signals
WHERE ticker = 'ALL.AX'          -- change ticker here
ORDER BY date DESC
LIMIT 30;
```

### Price History for a Stock
```sql
SELECT date, open, high, low, close,
       ROUND(volume::numeric, 0) AS volume
FROM prices
WHERE ticker = 'BHP.AX'          -- change ticker here
ORDER BY date DESC
LIMIT 30;
```

### Macro Indicators (latest)
```sql
SELECT indicator, value, date
FROM macro
WHERE date = (SELECT MAX(date) FROM macro)
ORDER BY indicator;
```

### Stocks with Best Fundamentals
```sql
SELECT DISTINCT ON (ticker) ticker,
       fundamental_score, composite_score, date
FROM signals
WHERE date = CURRENT_DATE
ORDER BY ticker, fundamental_score DESC
LIMIT 20;
```

### Stocks Flagged as Illiquid (for reference)
```sql
SELECT p.ticker,
       ROUND(AVG(p.volume * p.close)::numeric, 0) AS avg_daily_turnover
FROM prices p
WHERE p.date >= CURRENT_DATE - INTERVAL '20 days'
GROUP BY p.ticker
HAVING AVG(p.volume * p.close) < 500000
ORDER BY avg_daily_turnover;
```

---

## 10. CLI Commands

```bash
# Run full pipeline right now (all 5 layers)
./run.sh --run-now

# Scan only (scores all stocks, no trades)
./run.sh --scan

# Send today's report to Telegram
./run.sh --report

# Run backtest (last 6 months)
./run.sh --backtest

# Backfill price history
./run.sh --backfill 365

# NSE equivalents (prefix with EXCHANGE=nse)
EXCHANGE=nse ./run.sh --run-now
EXCHANGE=nse ./run.sh --scan

# Check system status
ps aux | grep main.py | grep -v grep
tail -20 asx_trading.log
tail -20 nse_trading.log
```

---

## 11. Configuration (.env)

```bash
SIGNAL_THRESHOLD=65.0    # Minimum composite score to trade
MAX_POSITION_PCT=0.20    # Max 20% of portfolio per stock
STOP_LOSS_PCT=0.07       # Hard stop fallback (ATR-based preferred)
PORTFOLIO_CAPITAL=100000 # Simulated capital ($AUD)
TRADING_PHASE=1          # 1=paper only, 3=live (IBKR)
EXCHANGE=asx             # asx | nse
```

---

## 12. What Happens at Each Score Level

| Score | Meaning | Action |
|-------|---------|--------|
| 80–100 | Very high conviction — all 4 engines agree | Trade placed, full/half-Kelly position |
| 65–79 | Good conviction — most signals align | Trade placed if quality + liquidity pass |
| 50–64 | Mixed signals — one or two engines weak | Watchlist only, no trade |
| 35–49 | Weak — most engines negative | Skip |
| 0–34 | Blocked — quality gate fails | Explicitly excluded |

---

*Generated by ASX AI Trading System · Phase 1 Paper Trading*
