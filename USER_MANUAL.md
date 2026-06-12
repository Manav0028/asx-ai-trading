# AI Trading System — User Manual

*A plain-English guide to what this system does, how it decides, and how you operate it.*

---

## 1. What this system is

An automated swing-trading system that scans the **ASX 200** (Australia) and **NSE NIFTY 100** (India) every trading day, scores every stock on four dimensions, and trades only the stocks where a **statistically validated strategy** fires that day — long or short. It paper-trades by default, alerts you on Telegram for every action, and shows everything live on a web dashboard.

**What it is NOT:** a get-rich-quick machine. No system wins every trade. This one is built around a harder, more honest idea: *only trade where you can prove an edge existed in the past AND held up on data the test never saw.* Most days it does nothing. That is by design.

---

## 2. The core idea in one paragraph

Every stock behaves differently — BHP trends, banks mean-revert, small caps breakout. So instead of forcing one strategy on all 250 stocks, the system backtests **15 different strategies on each stock's own 2-year history** and asks: *which strategy actually made money on THIS stock?* The test is split 70/30 — a strategy must be profitable on the first 70% (backtest) **and** the last 30% it has never seen (forward test). Only then is the strategy "validated" and allowed to trade that stock. Unvalidated stocks are never auto-traded, no matter how good their news looks.

---

## 3. The four scores (what makes a "signal")

Every day, every stock gets a composite score out of 100:

| Component | Weight | What it measures | Source |
|---|---|---|---|
| Sentiment | 30% | News tone over recent headlines | Local LLM (Ollama) reads the news |
| Fundamental | 25% | Business quality — P/E, growth, debt, margins | yFinance financials |
| Technical | 25% | RSI, MACD, Bollinger, EMA cross, StochRSI, volume, ADX | 300 days of price history |
| Insider | 20% | Director/promoter buying vs selling | ASX Form 604 / NSE disclosures |

A stock becomes a **candidate** when the composite ≥ 65 (longs) — or ≤ 35 for shorts, since a weak score is exactly what a short wants. But a candidate still cannot trade unless it passes the gates below.

## 4. The gates (why most signals never become trades)

A trade only executes when **ALL** of these pass:

1. **Quality gate** — blocked if news is very negative or technicals are broken (longs only; shorts skip this since bad news helps them)
2. **Liquidity gate** — enough daily turnover to enter/exit without moving the price
3. **Strategy gate** — the stock's *validated* strategy must fire on today's bar (the heart of the system; see §5)
4. **Score threshold** — composite ≥ 65 (long) or bearish composite ≥ 65 (short)
5. **Regime filter** — if the index (ASX 200 / NIFTY) is below its 200-day average, position sizes are halved

If any gate fails, the signal is recorded with **position size $0** — visible on the dashboard, never traded.

---

## 5. The Strategy Engine — 15 strategies, one per stock

### The library

**Classic practitioner strategies (long):**
| Strategy | Fires when | Holds up to |
|---|---|---|
| trend_follow | EMA20>EMA50 uptrend + ADX≥25 + fresh MACD bullish turn | 45 days |
| mean_reversion | Range-bound stock, RSI<32 at lower Bollinger band | 15 days |
| breakout | Close above 20-day high on 1.5x volume | 30 days |
| momentum_pullback | Uptrend, dip to EMA20, StochRSI reset | 25 days |
| oversold_bounce | RSI recovers through 30 with volume | 15 days |

**Academic anomalies (long) — the most replicated edges in finance:**
| Strategy | Fires when | Evidence |
|---|---|---|
| tsmom | 12-month momentum >10%, above 200-day MA, reclaims EMA20 | Moskowitz 2012 — works across 200 years |
| high_52w | Price pushes within 2% of its 52-week high on volume | George & Hwang 2004 |
| rsi2_dip | RSI(2) panic dip below 10 in a long-term uptrend | Connors & Alvarez |
| turtle_55 | 55-day Donchian breakout with trend confirmation | The Turtles / $350B CTA industry |

**Chart-reading patterns (long + SHORT) — Bulkowski's top-ranked candle patterns:**
| Strategy | Direction | Fires when |
|---|---|---|
| bull_engulf | LONG | Bullish engulfing candle after a 3-day fall, RSI<45 |
| hammer | LONG | Hammer (long lower wick) at the 20-day low |
| inside_break | LONG | Inside-bar squeeze breaks upward on volume |
| bear_engulf | SHORT | Bearish engulfing after a rally, RSI>60 |
| shooting_star | SHORT | Shooting star (long upper wick) at the 20-day high |
| breakdown | SHORT | Close below the 20-day low on 1.5x volume in a downtrend |

### How a stock earns the right to trade

Every Sunday 07:00 (and via `python main.py --select-strategies`):

1. Load each stock's last ~2 years of daily bars
2. Simulate **all 15 strategies** on it, with realistic slippage (0.1%) and brokerage ($9.95) per side
3. Split results 70/30: in-sample backtest / out-of-sample forward test
4. **Validation gates**: backtest needs ≥5 trades, profit factor ≥1.2, win rate ≥45%; forward test needs ≥2 trades and profit factor ≥1.0
5. The best validated strategy (ranked 40% backtest + 60% forward, to punish overfitting) is assigned to that stock
6. If nothing validates → the stock is watched but **never auto-traded**

Current state (as of 2026-06-12): **ASX 44/153 validated** (incl. 11 shorts), **NSE 22/97 validated** (incl. 3 shorts).

### Shorts

If a stock's best-proven edge is a *bearish* pattern (e.g. CSL's history validates bearish engulfing), the system will **short** it when that pattern prints: sell to open, stop ABOVE entry, target BELOW, cover to close. Short P&L = entry − exit.

---

## 6. Risk management (how positions are sized and protected)

| Mechanism | Rule |
|---|---|
| Position sizing | Risk **1.5% of capital** per trade: shares = dollar_risk ÷ distance-to-stop. Capped at 20% of capital per position |
| Stop-loss | ATR-based, per strategy (e.g. mean reversion 1.5×ATR tight, trend 2.5×ATR wide). Fallback −7% |
| Target | ATR-based per strategy (2.0–6.0×ATR). Minimum reward:risk enforced |
| Trailing stop | Activates after ~+5% gain, trails below the running peak (longs only) |
| Time exit | Positions going nowhere are closed after the strategy's max-hold days (ADX-adjusted) |
| Intraday checks | Every 30 minutes during market hours, live prices are checked against stops/targets |
| Regime filter | Index below 200-day MA → position sizes halved, targets tightened |
| Signal decay | Held positions are re-scored daily; deterioration triggers a review alert |

Slippage (0.1%) and brokerage ($9.95/side) are simulated on every paper fill so the results stay honest.

---

## 7. Trading phases (paper → real)

Set `TRADING_PHASE` in `.env`:

| Phase | Mode | What happens |
|---|---|---|
| 1 (current) | Internal paper | Fills simulated locally, logged to DB |
| 2 | IBKR paper | Orders sent to Interactive Brokers paper account |
| 3 | LIVE | Real money via IBKR. **Only enable after months of verified forward results** |

---

## 8. The daily schedule (automatic)

Each exchange runs its own scheduler in its own timezone. Relative to pre-market hour:

| Time | Job |
|---|---|
| +0:00 | Fetch prices (OHLCV) + macro data |
| +0:20 | Exchange announcements |
| +0:40 | Insider/director trade disclosures |
| +1:00 | AI sentiment + fundamental scoring |
| +1:15 | Technical engine + regime check |
| +1:20 | **Full signal scan** (all gates applied) |
| +1:30 | Daily report → Telegram + email |
| Market open | Place orders for actionable signals |
| Every 30 min | Intraday stop/target checks on open positions |
| Every 2 hrs | News refresh |
| Market close | Close-of-day processing |
| **Sunday 07:00** | **Strategy re-selection (all 15 strategies × all stocks)** |
| Sunday 08:00 | Weekly summary + backtest report |

The ASX scheduler starts via launchd (`com.asx.trading`, weekdays 05:50). The NSE one runs with `EXCHANGE=nse python main.py`.

---

## 9. The dashboard (http://localhost:8502)

| Tab | What you see |
|---|---|
| **Dashboard** | Total P&L, portfolio summary, win/loss, regime badge, 90-day P&L chart |
| **Holdings** | Open positions with live P&L, stops, targets, days held |
| **Signals** | Today's scored stocks, strategy chips, full signal table |
| **Radar** | ⭐ The strategy engine live: every assignment with LONG/SHORT chip, FIRING status when its validated strategy triggers today, entry/target/stop, forward-test stats. Click any ticker → TradingView chart |
| **Charts** | TradingView chart + custom technical-analysis card + company profile |
| **Scanner** | TradingView market screener |
| **Trade History** | Every closed trade with P&L and exit reason |
| **Backtest** | Walk-forward results + per-stock strategy assignment table |

Sidebar switches between ASX 200 and NSE NIFTY 100. Start it with:
```bash
streamlit run dashboard/app_v2.py --server.port 8502
```

---

## 10. Telegram alerts (what each message means)

| Alert | Meaning | Action expected from you |
|---|---|---|
| 🟢 NEW BUY SIGNAL | A validated strategy fired; position opened with entry/target/stop and the "why" | None — informational |
| 🔴 STOP-LOSS HIT | Position closed at the safety exit | None — capital protected automatically |
| 🎯 TARGET REACHED | Profit taken automatically | None |
| ⏱ TIME-BASED EXIT | Stale position freed up | None |
| 🔴/🎯 INTRADAY | Stop/target hit mid-session on live prices | None |
| ⚠️ SIGNAL DETERIORATING | A held stock's score dropped sharply | **Review manually** |
| 📰 NEGATIVE NEWS | Bad news on a held position | **Review manually** |
| ✅/⚠️ MARKET TURNED | Regime flip (bullish/cautious) | Expect bigger/smaller positions |
| 📊 DAILY REPORT | Morning summary | Read with coffee |
| 📅 WEEKLY SUMMARY | Sunday wrap-up + top radar stocks | Read |

---

## 11. Commands you'll actually use

```bash
# All commands from the project root, using the asx_trading conda env.
# For NSE, prefix any command with EXCHANGE=nse

python main.py                       # start the scheduler (daemon)
python main.py --run-now             # run today's full pipeline once
python main.py --scan                # signal scan only
python main.py --select-strategies   # re-run per-stock strategy validation
python main.py --backtest            # walk-forward backtest
python main.py --report              # generate + send today's report
python main.py --backfill 730        # backfill 2 years of prices
python main.py --test-alerts         # test Telegram connectivity
python main.py --init-db             # create DB tables (first run)
```

Python path: `/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python`

---

## 12. Key configuration (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `SIGNAL_THRESHOLD` | 65 | Composite score needed to act |
| `PORTFOLIO_CAPITAL` | 100,000 | Notional capital for sizing |
| `MAX_POSITION_PCT` | 0.20 | Max 20% of capital in one stock |
| `STOP_LOSS_PCT` | 0.07 | Fallback stop when no ATR |
| `TRADING_PHASE` | 1 | 1=paper, 2=IBKR paper, 3=live |
| `EXCHANGE` | asx | `asx` or `nse` |
| `TELEGRAM_BOT_TOKEN` / `CHAT_ID` | — | Alert delivery |

Risk-per-trade (1.5%) and validation gates live in code: `signals/risk_params.py`, `strategies/backtest.py`.

---

## 13. How to read the Radar tab (your daily 30-second check)

1. **"X firing now"** badge — if 0, the engine found no proven setup today. Normal. Patience is a position.
2. **Firing cards (green border)** — a validated strategy triggered today. Check the direction chip (LONG green / SHORT red), entry/target/stop, and forward-test profit factor. The trade will be placed automatically at the order window.
3. **Validated — Watching** — stocks with a proven edge waiting for their setup. Fwd PF is the out-of-sample profit factor (>1 = made money on unseen data; 99 = no losing trades in that window, small sample — trust the trade count more).
4. Click any ticker to open its TradingView chart and see the setup yourself.

---

## 14. Honest limitations (read this twice)

- **Past edge ≠ future edge.** Validation reduces, but cannot eliminate, the risk that a pattern stops working. The weekly re-selection retires strategies that decay.
- **Small samples.** A forward test with 2–3 trades can validate on luck. Treat "Fwd PF 99 on 2 trades" with appropriate skepticism — the rank already discounts it.
- **No intraday entries.** The system works on daily bars; it enters at/near the next session's prices, not the exact pattern close.
- **Shorts carry unlimited theoretical risk** — stops are mandatory and the system always sets them, but gaps can jump past stops.
- **Paper fills are optimistic.** Real fills will be slightly worse than simulated, even with the slippage model.
- **The Mac must be on.** Schedulers run locally; if the machine sleeps, days are missed (cloud deployment is planned — see `docker-compose` files / Oracle Free Tier plan).
- **Nothing here is financial advice.** It is a research system trading simulated money until *you* decide otherwise — and that decision deserves months of forward evidence first.

---

## 15. Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard empty / stale | `pkill -f streamlit` then restart it (cached old code) |
| No Telegram messages | `python main.py --test-alerts`; check token/chat-id in `.env` |
| "insufficient price history" in selection | `python main.py --backfill 730` |
| Strategy never fires for tsmom/high_52w | These need 260+ bars of history — backfill first |
| Scores look wrong/stale | Clear Redis: keys `score:*` and `tech_meta:*` have a 4-hour TTL |
| Scheduler not running | `ps aux | grep main.py` — restart via the launchd wrapper (ASX) or `EXCHANGE=nse nohup python main.py &` (NSE) |
| DB connection refused | PostgreSQL on port 5433 must be up before the scheduler starts |
