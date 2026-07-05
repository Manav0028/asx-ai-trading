# Real-Time AI Chart/Candle Reading Feature (`realtime_chart_ai/`)

## Context

The current AITrading system (`dashboard/app_v2.py`, `strategies/patterns.py`, `execution/ibkr_trader.py`) is an end-of-day / daily-bar paper-trading system for ASX/NSE. It already has:
- Rule-based candlestick pattern detectors (`strategies/patterns.py`: bull_engulf, hammer, inside_break, bear_engulf, shooting_star, breakdown) that run against **daily** bars only, using full-array numpy indicator computation (`ind` dict of `closes/opens/highs/lows/rsi/...`).
- A read-only TradingView **iframe embed** (Advanced Chart widget) — sandboxed, cannot draw custom overlays.
- An IBKR TWS connection (`execution/ibkr_trader.py`, ib_insync, port 7497 paper) used only for order execution, not market data.
- No websocket/streaming infrastructure anywhere in the repo.

The user wants a new, parallel feature: an AI system that reads live candlestick charts in real time, draws on a self-hosted TradingView chart, and journals everything it sees and does — built and run fully independently of the EOD system.

## Research Findings That Shaped This Plan

**Data source decision — IBKR only (not Twelve Data), because the user asked for whichever is closest/accurate/fastest/cheapest:**
- IBKR is already integrated (existing connection pattern in `execution/ibkr_trader.py`) and delivers **direct exchange-sourced** real-time data once a market data subscription is active — no third-party vendor hop, which is the most accurate/lowest-latency path available.
- Twelve Data was investigated and **rejected as a real-time ASX source**: even its top "Ultra" tier ($149/mo) explicitly only provides **delayed** AU market data — it cannot satisfy "minimum real-time delay" for ASX at any price. Its Pro tier ($99/mo) does include India, but that's an extra paid third-party hop when IBKR already gives direct NSE access (IBKR India entity supports NSE stocks/futures/options with its own market data subscription, minimum ~USD 100 equivalent maintained).
- Conclusion: **IBKR is the single real-time data source** for both ASX and NSE — cheapest (small per-exchange market-data add-on on an account already paying for brokerage), fastest (broker-direct, no vendor relay), and most accurate (true exchange feed). The pluggable `CandleDataSource` interface is still built (for future extensibility, e.g. US tickers where Polygon/Twelve Data might make sense later), but only `ibkr_source.py` is implemented now.
- `yfinance` (already a dependency, free) is used as an **emergency delayed fallback** if IBKR disconnects — clearly tagged as delayed in the UI/journal, not a peer real-time source, so no paid secondary provider is needed at all.

**Available candle granularity (IBKR TWS API):**
- **Real-time streaming**: `reqRealTimeBars` gives true real-time **5-second bars** (the finest IBKR streams without a tick-by-tick data add-on) — these are aggregated into the engine's working timeframe (default 1-minute).
- **Historical backfill**: `reqHistoricalData` limits **1-minute bar requests to ~1 day of data per call** (chained/paginated backwards to build up e.g. 30-60 days of 1-min history); daily/weekly bars have no such restrictive windowing and can go back years. So the plan uses **chained historical requests** to bootstrap 1-min bars, plus direct daily-bar requests to seed higher-timeframe (5m/15m resampled, or daily-native) context on startup.

**Chart-reading techniques to implement (redoing the calculation approach, not just porting daily code):**
Research confirms professional/AI chart-reading systems combine several layers, and that multi-timeframe confluence alone measurably improves signal quality (cited 40-50% success-rate improvement vs single-timeframe):
1. **Candlestick patterns** (single/multi-bar): expand beyond the current 6 — add doji, morning/evening star, piercing line, dark cloud cover, three white soldiers/black crows, spinning top, marubozu.
2. **Swing-point-based chart patterns**: detect local swing highs/lows (fractal/pivot detection) to identify double top/bottom, head & shoulders, triangles, flags — none of this exists in the current daily engine and requires a genuinely new module, not a port.
3. **Support/resistance levels**: rolling pivot clusters + prior swing highs/lows + round-number levels.
4. **Trend/momentum indicators**: EMA20/50/200 alignment, RSI, MACD, ADX — computed **incrementally** (streaming formulas: recursive EMA, Wilder's smoothing for RSI) rather than recomputed from full arrays every bar, since this now runs continuously instead of once/day.
5. **Volume analysis**: VWAP (session-anchored), volume-vs-20-bar-average spikes, OBV.
6. **Fibonacci retracement** from the most recent significant swing, as confluence with support/resistance.
7. **Multi-timeframe confluence gate**: a pattern firing on the 1-minute execution timeframe only becomes a `PatternSignal` if the 5-minute/15-minute directional bias (EMA slope + trend) agrees — directly implementing the research finding above.
8. **Smart Money Concepts / ICT** (added after further research — see below): order blocks, fair value gaps, liquidity sweeps, break of structure / change of character, premium-discount zones. Purely OHLCV-derived (no extra data subscription needed), builds directly on the swing-point detector, and is the dominant modern price-action methodology for exactly this kind of real-time reactive system.
9. **Volume Profile** (POC / Value Area): session-anchored volume-at-price distribution, approximated from 1-min bar volume (no tick data required).
10. Elliott Wave noted as high-subjectivity/low-ROI for a rules engine — explicitly out of scope.
11. **Order flow / footprint / cumulative delta** — researched and explicitly deferred (not dropped): true footprint charts need bid/ask-classified trades, which on IBKR requires a `reqTickByTickData`/Level 2 market-depth subscription beyond the base real-time-bars subscription already planned. Given the "cheap" requirement, this is documented as an optional Phase 4 upgrade path, not built now.

**Why SMC/ICT and Volume Profile specifically (research findings):**
- **Order Blocks**: the last opposite-direction candle before a displacement move — marks where institutional positioning likely sits; price "rebalancing" back into an order block is a high-probability continuation/reversal zone. Purely geometric (needs only OHLC + the displacement move already computed for swing detection).
- **Fair Value Gaps (FVG)**: a 3-candle imbalance where candle 1's high/low doesn't overlap candle 3's low/high (gap left by a fast displacement move). Research cites price revisits FVGs roughly 70% of the time — a concrete, testable, purely-OHLC rule.
- **Liquidity sweeps**: price briefly pierces a prior swing high/low (where stop orders cluster) then reverses — detected as a swing-point break that fails to close beyond the level and snaps back within 1-3 bars.
- **Break of Structure (BOS) / Change of Character (CHoCH)**: BOS = two consecutive bar closes beyond the last confirmed swing (trend continuation confirmation, reduces fakeouts vs. a single-bar break); CHoCH = the first break of structure in the *opposite* direction of the prevailing trend (early reversal warning). Both are direct, deterministic consequences of the swing-point series already being tracked.
- **Premium/Discount zones**: split the current "dealing range" (most recent significant swing-low to swing-high) into thirds — bottom 25% = discount (favor longs), top 25% = premium (favor shorts), middle = equilibrium. Research is explicit that this is what "ties every other ICT concept together" — so rather than being one more pattern among many, it's used as an **entry-quality gate/weight** in the composite score (see below), the same architectural role multi-timeframe confluence already plays.
- **Volume Profile POC/Value Area**: point of control acts as a price magnet/mean-reversion target; value area high/low are natural pullback zones in a trend and range boundaries in a chop — adds a volume-weighted reference layer that plain S/R levels (price-only) don't capture.

This means `engine/` is a **new incremental multi-timeframe indicator + pattern engine**, not a straight port of `strategies/patterns.py`'s array-based approach — it reuses that file's *pattern logic and confidence/reason style* (`fires(ind, i) -> {"confidence", "reason"}`), not its calculation method.

**"Keep track of everything"**: the journal is expanded beyond trade interpretation into a full system event log (connection/failover/error events) and a persisted raw-bar log, so the entire chain — data received, indicators computed, patterns evaluated, confluence checked, AI asked, trade decided — is reconstructable after the fact.

**Claude integration from day one** (not deferred to a later phase): every fired signal gets a rationale call in Phase 1, and the frontend chart ships with the commentary panel from the start.

## Core Engine: Calculations & Decision Logic

This is the actual "brain" — everything else in this plan (data sources, journal, frontend) exists to feed or expose this. Mirrors the existing EOD system's weighted-composite-score philosophy (`signals/aggregator.py`: sentiment×30%+fundamental×25%+technical×25%+insider×20%, gated by `SIGNAL_THRESHOLD`), but since sentiment/fundamentals don't update intraday, this is a **pure price/volume composite**, recomputed continuously instead of once/day.

**1. Incremental streaming indicators** (`engine/indicators.py`) — O(1) update per bar, not a recompute over the full array like `ai_engine/technical_engine.py` does once/day:
- EMA: `ema[t] = price·k + ema[t-1]·(1-k)`, `k=2/(period+1)` — same formula as `technical_engine.py:_ema`, kept as running state (EMA20/50/200).
- RSI: **true Wilder smoothing** — `avg_gain[t] = (avg_gain[t-1]·13 + gain[t])/14` (same for loss), `RSI = 100 - 100/(1+avg_gain/avg_loss)`. Note: existing `technical_engine.py:_rsi` uses a flat mean of the last 14 deltas, not Wilder recursion — acceptable once/day but drifts under continuous recalculation, so this is a deliberate "redo," not a straight port.
- MACD: EMA12 − EMA26, signal = EMA9 of that line, histogram = MACD − signal.
- Bollinger Bands: mean/std over a 20-bar rolling deque (`maxlen=20`).
- ADX/+DI/−DI, ATR: Wilder-smoothed directional movement / true range (same recursive style as RSI).
- VWAP: session-anchored `Σ(price·vol)/Σ(vol)`, reset at each session open — cumulative sums.
- OBV: running total, ± volume vs prior close.
- Volume spike ratio: current bar volume ÷ rolling 20-bar average (same style as `technical_engine.py:_volume_spike`).

**2. Swing-point (fractal) detection** (`engine/swing_detector.py`): a bar is a confirmed swing high/low once 2 bars on each side confirm it (classic 5-bar William's fractal — unavoidable ~2-bar confirmation lag). Maintains a rolling list of the last ~50 confirmed swings per timeframe; feeds items 3 and 4b below.

**3. Support/resistance + Fibonacci** (`engine/levels.py`): cluster swing highs/lows within ~0.3×ATR of each other, weighted by touch count + recency, into a ranked S/R ladder. The most recent significant swing leg also generates Fibonacci retracement levels (23.6/38.2/50/61.8/78.6%) as additional confluence.

**4. Pattern detection** — all three families emit `{confidence: 0-1, reason: str, direction}`, same contract as the existing `Strategy.fires(ind, i)`:
- **4a. Candlestick** (`engine/candlestick_patterns.py`): the existing 6 (bull/bear engulfing, hammer, shooting star, inside bar) plus doji, morning/evening star, piercing line/dark cloud cover, three white soldiers/black crows, marubozu — concrete multi-bar rules (e.g. morning star = big down candle + small-bodied indecisive gap-down candle + big up candle closing above candle-1's midpoint).
- **4b. Chart patterns** (`engine/chart_patterns.py`, genuinely new — no daily-bar equivalent exists): double top/bottom (two similar-height swings + neckline break), head & shoulders (three swings, middle highest, neckline break), triangles (linear-regression trendline fit through recent swing highs/lows, breakout + volume), flags (impulse move + tight narrowing-range consolidation + breakout continuation).
- **4c. Smart Money Concepts / ICT** (`engine/smc.py`, new — added per further research): all purely OHLCV-derived, all consumers of the swing-point series from step 2.
  - **Order Block**: last opposite-color candle before a displacement move (a bar-to-bar range/body expansion ≥ ~1.5× the recent ATR); a retest of that candle's body range after the move is a `bullish_ob_retest`/`bearish_ob_retest` signal.
  - **Fair Value Gap (FVG)**: 3-candle imbalance where candle 1's high < candle 3's low (bullish FVG) or candle 1's low > candle 3's high (bearish FVG); fires `fvg_fill` when price re-enters that gap.
  - **Liquidity Sweep**: price pierces a prior confirmed swing high/low by a small margin then closes back inside within 1-3 bars — fires `liquidity_sweep_reversal` in the direction back toward the range.
  - **BOS / CHoCH**: `break_of_structure` = two consecutive closes beyond the last confirmed swing in the *prevailing* trend direction (continuation confirmation); `change_of_character` = the first opposite-direction structure break (early reversal warning) — both computed directly off the swing-point series, no new state needed.
- **Volume Profile** (`engine/volume_profile.py`, new, session-anchored, not itself a firing pattern but a context layer): approximates volume-at-price by distributing each 1-min bar's volume uniformly across its high-low range into price buckets, producing session POC (highest-volume price) and Value Area High/Low (bounds of the 70%-of-volume region). Feeds the composite score and Claude's context the same way S/R levels do.
- **Order flow / footprint / cumulative delta**: deliberately deferred (documented above) — would need a paid IBKR tick-by-tick/Level 2 subscription; noted as a Phase 4 candidate, not built now.

**5. Multi-timeframe confluence gate** (`engine/confluence.py`): on a 1-min pattern fire, compute 5-min bias (bullish if EMA20>EMA50 and price>EMA20; bearish if reversed; else neutral). Signal direction must agree with the 5-min bias to be "confirmed"; 15-min agreement adds a confidence bonus; disagreement doesn't delete the signal (still journaled per "track everything") but excludes it from auto-trading.

**6. Premium/Discount zone gate** (`engine/smc.py`): the dealing range = most recent significant swing-low to swing-high. Price in the bottom 25% of that range = discount (favors longs), top 25% = premium (favors shorts), middle 50% = equilibrium (neutral). This is computed alongside confluence and feeds the composite score below — research is explicit that premium/discount is what ties the other ICT concepts together, so it's treated as a first-class gate/weight, not just one more pattern.

**7. Composite Real-Time Score (0-100) — the actual trading-decision surface**, computed in `signal_engine.py`:
```
composite =
    35% × pattern_confidence      (firing pattern's own confidence × 100, whichever family fired — candlestick/chart/SMC)
  + 20% × trend_alignment         (EMA20/50/200 alignment + ADX strength — same style as technical_engine.py's _ema_crossover/_adx)
  + 15% × volume_confirmation     (volume spike ratio + proximity to Volume Profile POC/VAH/VAL — same style as _volume_spike)
  + 15% × mtf_confluence_bonus    (100 if 5m+15m agree, 50 neutral, 0 if 5m disagrees)
  + 15% × smc_zone_quality        (100 if long-in-discount or short-in-premium, 50 if equilibrium, 0 if trading against the zone)
```
A paper trade is only auto-actioned if `composite >= RTC_SIGNAL_THRESHOLD` (new config var, default 65, mirroring the `SIGNAL_THRESHOLD` philosophy). Below threshold: still journaled as "observed, not actioned" (never silently dropped). Stops/targets reuse the existing ATR-multiplier convention (`stop = entry ± ATR14 × stop_mult`, pattern-specific multipliers mirroring `strategies/patterns.py`'s `stop_mult`/`target_mult` fields) — SMC setups naturally supply their own stop reference too (e.g. beyond the order block / beyond the liquidity sweep wick).

**8. Claude's role**: explanatory, not decisional. The composite-score/threshold rule above is fully deterministic and auditable on its own; Claude is called after a signal is confirmed, given the pattern (including which SMC concepts were present — order block, FVG, sweep, BOS/CHoCH), the score breakdown, nearby S/R/Fib/Volume-Profile levels, premium/discount position, volume context, and MTF bias, and produces the plain-English rationale that gets journaled and shown in the commentary panel. "Why did it trade" is always answerable from the numbers alone; Claude adds narrative on top, it never gates the trade decision itself.

## Isolation Guarantees

- New sibling directory `realtime_chart_ai/`, own `requirements.txt`, own `.env`/settings module, own DB tables (separate SQLAlchemy `Base`), own entry point/port (8800).
- Zero edits to `dashboard/`, `strategies/`, `storage/`, `config/`, `execution/`, `main.py`. Existing files are read as patterns to replicate (connection/retry style, Claude client style), never imported/modified.
- Runs as its own process; coexists with the Streamlit dashboard (8501) and scheduler with no shared state beyond the same Postgres server (separate tables).

## Directory Layout

```
realtime_chart_ai/
├── requirements.txt          # ib_insync, fastapi, uvicorn[standard], anthropic, sqlalchemy,
│                              #   psycopg2-binary, python-dotenv, numpy, pandas, yfinance, websockets
├── .env.example
├── settings.py                 # own config module, own load_dotenv()
├── run_server.py                 # entry point: uvicorn.run(...), port 8800, --init-db flag
├── run.sh                          # conda-env wrapper, mirrors root run.sh
├── datasources/
│   ├── base.py                     # CandleDataSource ABC: connect(), subscribe(), fetch_historical(), is_healthy()
│   ├── ibkr_source.py                # ib_insync: reqRealTimeBars(5s) live + chained reqHistoricalData backfill;
│   │                                  #   separate IBKR_CLIENT_ID_REALTIME range (50-59), own retry/backoff
│   ├── yfinance_fallback.py           # emergency delayed-data source, activates only if IBKR unhealthy; tags candles delayed=True
│   └── manager.py                      # DataSourceManager: IBKR primary, yfinance fallback, normalizes to Candle{ts,o,h,l,c,v,source,delayed}
├── engine/
│   ├── timeframe_store.py               # multi-timeframe bar store: 1m execution bars + 5m/15m/daily resampled/native series per ticker
│   ├── indicators.py                      # INCREMENTAL streaming indicators: recursive EMA, Wilder RSI, MACD, ADX, VWAP, OBV, vol_avg_20
│   ├── swing_detector.py                   # fractal/pivot swing-high/low detection -> feeds pattern + S/R + Fibonacci + SMC modules
│   ├── levels.py                             # support/resistance clustering from swings + round numbers; Fibonacci retracement levels
│   ├── candlestick_patterns.py                # expanded single/multi-bar candle patterns (fires(ind, i) style, ported logic from strategies/patterns.py + new ones)
│   ├── chart_patterns.py                        # swing-point-based: double top/bottom, H&S, triangles, flags
│   ├── smc.py                                     # Smart Money Concepts/ICT: order blocks, fair value gaps, liquidity sweeps,
│   │                                               #   break of structure/change of character, premium-discount zone gate
│   ├── volume_profile.py                           # session POC / Value Area High-Low from bar-volume-at-price approximation
│   ├── confluence.py                                # multi-timeframe agreement gate (1m signal vs 5m/15m bias) before a signal is "confirmed"
│   ├── pattern_risk_defaults.py                       # stop_mult/target_mult/max_hold_bars lookup for SMC/chart-pattern signals
│   └── signal_engine.py                              # on_bar_closed(ticker) orchestrator: indicators -> swings -> patterns(candlestick/chart/SMC)
│                                                       #   -> confluence + zone gate -> composite score -> PatternSignal -> AI -> journal -> broadcast
├── ai/
│   └── rationale.py                       # generate_rationale(signal, mtf_context); mirrors ai_engine/claude_summarizer.py's
│                                           #   client + rule-based fallback; system prompt includes multi-timeframe + S/R + volume context; low max_tokens
├── journal/
│   ├── models.py                            # own Base; tables: rtc_bars, rtc_chart_interpretations, rtc_trade_actions,
│   │                                         #   rtc_trade_outcomes, rtc_open_positions, rtc_events
│   ├── db.py                                  # own engine/session, same Postgres host:5433, own init_db()
│   └── recorder.py                             # write_interpretation(), record_action(), record_outcome(), log_bar(), log_event(),
│                                                #   open_position_row(), update_open_position(), close_open_position(), get_open_positions(), query_history()
├── trading/
│   ├── state.py                                 # runtime auto-trade enable/disable toggle (live, not restart-only)
│   ├── sizing.py                                  # composite-score-driven dollar-risk position sizing (0.5x-1.5x)
│   ├── stops.py                                    # ATR-based stop/target/trailing-stop
│   ├── pnl.py                                       # simulated fill + P&L (slippage + brokerage)
│   ├── position_tracker.py                           # DB-backed open-position lifecycle (entry, per-bar exit check, restart recovery)
│   └── paper_or_live_bridge.py                        # thin dispatch facade; only "paper" mode implemented
├── server/
│   ├── app.py                                       # FastAPI: REST (journal/positions/auto-trade toggle, static files) + WS /ws/candles/{ticker}
│   ├── ws_hub.py                                      # connection registry + per-ticker broadcast
│   └── schemas.py                                       # pydantic payloads: candle_update, pattern_signal, trade_exit, journal_entry, auto-trade toggle
├── scripts/
│   └── verify_trading_phase.py                            # standalone verification harness for the automated trading capability
└── frontend/
    ├── index.html                                        # single page, FastAPI StaticFiles
    └── static/
        ├── lightweight-charts.standalone.production.js       # vendored (self-hosted)
        ├── tabler-icons.min.css + fonts/                       # vendored icon font (self-hosted, same reasoning)
        ├── app.js                                              # WS client, candlestick series + markers, Claude commentary panel,
        │                                                       #   journal/event history view, auto-trade toggle switch
        └── styles.css
```

## Data Flow

```
IBKR TWS reqRealTimeBars (5s) ──► DataSourceManager (IBKR primary, yfinance delayed fallback on disconnect)
        │
        ▼
TimeframeStore: aggregates 5s → 1m execution bars; maintains 5m/15m/daily resampled series per ticker
        │
        ▼
indicators.py: incremental EMA/RSI/MACD/ADX/VWAP/OBV updated on each bar close (all timeframes)
        │
        ▼
swing_detector.py: updates swing highs/lows -> levels.py (S/R + Fibonacci) and smc.py (order blocks/FVG/sweeps/BOS-CHoCH/zone) update
volume_profile.py: updates session POC/VAH/VAL from bar volume
        │
        ▼
signal_engine.on_bar_closed():
    position_tracker.check_exit() runs first (settles any open-position exit before new entries considered)
    candlestick_patterns.py + chart_patterns.py + smc.py all evaluate the 1m timeframe
        │ (on fire) ──► confluence.py checks 5m/15m bias agreement + smc.py premium/discount zone check
        │                     │ (confirmed) ──► composite score (§7 above) ──► PatternSignal{ticker, ts, pattern, confidence, reason, direction, mtf_context, smc_context}
        │
        ├─► ai/rationale.generate_rationale() ─► Claude call (S/R + Fib + Volume Profile + SMC context + MTF context in prompt) or rule fallback
        ├─► journal/recorder.write_interpretation()   [always, even if not trade-actioned]
        ├─► trading/paper_or_live_bridge (if state.is_enabled() and no open position on ticker) ─► position_tracker.open_position()
        └─► ws_hub.broadcast(ticker, {...})  ─► frontend: marker + Claude commentary panel

Every closed bar (any timeframe) → journal/recorder.log_bar() (rtc_bars) + broadcasts candle_update.
Every connect/disconnect/failover/error → journal/recorder.log_event() (rtc_events).
Every trailing-stop ratchet → journal/recorder.log_event("trailing_stop_updated") + rtc_open_positions row updated in place.
```

Transport: FastAPI + native WebSocket (starlette) via uvicorn — REST + WS + static frontend in one process/port.

## Journal Schema (first-class requirement — "keep track of everything")

Six tables under a dedicated `Base`, prefixed `rtc_`:

- **`rtc_bars`**: ticker, timeframe, bar_ts, open, high, low, close, volume, source, delayed (bool). Every closed bar on every tracked timeframe — full replay capability.
- **`rtc_chart_interpretations`**: ticker, bar_ts, timeframe, data_source, pattern_name, pattern_type (candlestick/chart/smc), direction, confidence, composite_score, rule_reason, mtf_confluence (bool + summary), smc_zone (premium/discount/equilibrium), smc_context, claude_rationale, claude_model, price_at_signal, created_at. Written for every confirmed signal, regardless of trade outcome.
- **`rtc_trade_actions`**: interpretation_id (FK), action_type (entry/exit/no_action), mode (paper/ibkr_paper/live), entry_price, shares, order_id, stop_price, target_price, composite_score_at_entry, dollar_risk, score_multiplier, atr_at_entry, executed_at.
- **`rtc_trade_outcomes`**: trade_action_id (FK, unique), exit_price, exit_ts, exit_reason, gross_pnl, net_pnl, bars_held.
- **`rtc_open_positions`**: the live, continuously-updated source of truth for "what's open right now" — ticker, trade_action_id (FK, unique), direction, entry_price, shares, stop_price (ratchets over time), target_price, peak_price, atr_at_entry, trail_activate_pct, trail_distance_pct, max_hold_bars, bars_held, status ('open'/'closed'), opened_at, updated_at. Backs `PositionTracker`'s restart recovery and `GET /api/positions`.
- **`rtc_events`**: ts, event_type (connect/disconnect/failover/error/backfill_complete/subscribe/auto_trade_toggled/entry_skipped_position_open/trailing_stop_updated), source, ticker (nullable), detail (text). System-level audit trail independent of trading logic — including every trailing-stop ratchet, so a position's full bar-by-bar lifecycle is backtrackable, not just its entry/exit.

## Config (`realtime_chart_ai/.env.example`, additive — root `.env` untouched)

```
DATABASE_URL=postgresql://manavsharma@localhost:5433/asx_trading
ANTHROPIC_API_KEY=
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID_REALTIME=50
PRIMARY_SOURCE=ibkr
FALLBACK_SOURCE=yfinance_delayed
EXECUTION_TIMEFRAME_SECONDS=60
CONTEXT_TIMEFRAMES=5m,15m,1d
RTC_HOST=0.0.0.0
RTC_PORT=8800
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=250
AUTO_TRADE_ENABLED_DEFAULT=false
RTC_TRADING_MODE=paper
RTC_SIGNAL_THRESHOLD=65
RTC_HIGH_ALERT_THRESHOLD=85
RTC_CAPITAL_POOL=20000
RTC_BASE_RISK_PCT=0.005
RTC_MAX_POSITION_PCT=0.40
RTC_SCORE_MULT_FLOOR=0.5
RTC_SCORE_MULT_CEIL=1.5
RTC_PAPER_SLIPPAGE=0.001
RTC_PAPER_BROKERAGE=9.95
RTC_MIN_STOP_PCT=0.02
RTC_MAX_STOP_PCT=0.08
RTC_MIN_RR_RATIO=1.5
RTC_TRAIL_ACTIVATE_MULT=1.0
RTC_TRAIL_DISTANCE_MULT=1.5
RTC_TRAIL_MIN_PCT=0.01
RTC_TRAIL_MAX_PCT=0.05
```

Note: `RTC_BASE_RISK_PCT`/`RTC_MAX_POSITION_PCT` were retuned from an initial 0.015/0.25 after verification revealed the position-value cap bound at every composite score for realistic intraday stop distances, silently erasing the score-driven sizing differentiation — 0.005/0.40 keeps the cap a genuine backstop instead of a constant constraint (see "Automated Trading Capability" below).

## Phased Build Order

**Phase 1 — IBKR live data + full indicator/pattern engine + Claude + journal + chart** ✅ Built.
1. `datasources/base.py` + `ibkr_source.py` (5s real-time bars + chained historical backfill for 1m, direct daily fetch for context).
2. `engine/timeframe_store.py` + `engine/indicators.py` + `engine/swing_detector.py` + `engine/levels.py`.
3. `engine/candlestick_patterns.py` + `engine/smc.py` + `engine/confluence.py`.
4. `signal_engine.py` composite score wired from the start.
5. `ai/rationale.py` wired in from the start.
6. `journal/models.py` + `db.py` + `recorder.py`.
7. `server/app.py` + `frontend/`.
8. Verified end-to-end via synthetic bars + real dev DB (no live IBKR TWS available in this environment).

**Phase 2 — chart-pattern module + volume profile + automated trading** ✅ Built.
1. `engine/chart_patterns.py` (double top/bottom, H&S, triangles from swing points).
2. `engine/volume_profile.py` (session POC/VAH/VAL), folded into the volume_confirmation term of the composite score.
3. Automated (simulated-fill) trading capability — see full section below. Replaces the original stub that just wrote a placeholder entry row with a hardcoded 100 shares and no exit logic.
4. `datasources/yfinance_fallback.py` wired into `manager.py` failover — **not yet built**.

## Automated Trading Capability (upgrades the original Phase 2 stub)

**Context:** The original stub only journaled a placeholder "entry" — it never sized a position, computed a stop/target, checked for an exit, or recorded P&L, so nothing ever actually "closed." The user wanted a real automated (but still fully simulated — no real broker orders) trading capability: dynamic position sizing driven by each signal's own composite score, ATR-based stops/targets/trailing-stops reused from the EOD system's conventions, and a **live on/off toggle** (API + frontend switch, not just a `.env` flag requiring a restart) — all still fully isolated in `realtime_chart_ai/` (own tables, own settings, no imports from the EOD system).

**Decisions confirmed with the user:**
1. **Simulated fill only** — no real IBKR paper/live order placement in this pass. `RTC_TRADING_MODE` stays conceptually open to `ibkr_paper`/`live` as future extension points, but only `"paper"` is implemented; any other mode raises `NotImplementedError` with a clear message.
2. **Sizing basis = the firing signal's own composite score** (not a per-ticker historical win-rate).
3. **Sizing range = 0.5x-1.5x base risk**: a bare-threshold signal risks half the base amount; a perfect signal risks 1.5x. Linear interpolation between.
4. **Enable/disable = a live runtime toggle**, not just a `.env` flag — a REST endpoint flips an in-process mutable flag immediately (no restart), exposed as a switch in the frontend header, with every flip logged to `rtc_events` for audit.
5. **Open-position state must be trackable and retrievable, not just in-memory** (feedback round 2) — upgraded to DB-backed via `rtc_open_positions`, with restart recovery and a `GET /api/positions` endpoint.

### Module layout in `trading/`

- **`trading/state.py`** — single source of truth for whether auto-trading is on. `is_enabled()`/`set_enabled(value, actor)`, seeded from `AUTO_TRADE_ENABLED_DEFAULT`. `signal_engine.py` calls `state.is_enabled()` live (not a cached import) so a runtime toggle takes effect on the very next signal.
- **`trading/sizing.py`** — pure `compute_position(entry_price, stop_price, composite_score) -> Dict`, the score-driven dollar-risk formula.
- **`trading/stops.py`** — pure `compute_stop_target(...)` and `update_trailing_stop(...)`, ATR-based, adapted from `signals/risk_params.py`.
- **`trading/pnl.py`** — `simulate_fill(price, side)` and `compute_pnl(direction, entry_price, exit_price, shares)`, identical formulas to `execution/paper_trader.py`.
- **`trading/position_tracker.py`** — the stateful core. In-memory `{ticker: OpenPosition}` dict as a **working-set cache**, backed by `rtc_open_positions` as the actual source of truth:
  - `has_open_position(ticker) -> bool`
  - `open_position(interpretation_id, ticker, direction, price, atr, composite_score, stop_mult, target_mult, max_hold_bars) -> Optional[Dict]`
  - `check_exit(ticker, ind, i) -> Optional[Dict]` — called on every closed 1m bar regardless of whether a new signal fired; advances `bars_held`, ratchets the trailing stop (logging every ratchet to `rtc_events`), checks stop/target/max-hold in order, simulates the fill and writes `RtcTradeOutcome` on exit.
  - `load_open_positions() -> None` — rebuilds the in-memory cache from `rtc_open_positions` at startup, so a restart doesn't lose track of what's open.
- **`trading/paper_or_live_bridge.py`** — thin dispatch façade; checks `RTC_TRADING_MODE`, delegates to `position_tracker` for `"paper"`, raises `NotImplementedError` otherwise.

### Formulas (adapted from `execution/paper_trader.py`, `signals/risk_params.py`, `execution/stop_loss.py` — cloned, not imported)

**Sizing:**
```
score_multiplier = RTC_SCORE_MULT_FLOOR + (RTC_SCORE_MULT_CEIL - RTC_SCORE_MULT_FLOOR)
                    * clamp((composite_score - RTC_SIGNAL_THRESHOLD) / (100 - RTC_SIGNAL_THRESHOLD), 0, 1)
dollar_risk      = RTC_CAPITAL_POOL * RTC_BASE_RISK_PCT * score_multiplier
stop_distance    = abs(entry_price - stop_price)
shares           = dollar_risk / stop_distance
position_value   = min(shares * entry_price, RTC_CAPITAL_POOL * RTC_MAX_POSITION_PCT)
shares           = position_value / entry_price   # re-derive if the cap clipped it
```

**Stop/target:**
```
stop_pct     = clamp((stop_mult * atr) / entry_price, RTC_MIN_STOP_PCT, RTC_MAX_STOP_PCT)
stop_price   = entry_price * (1 - stop_pct)   [long]   |   entry_price * (1 + stop_pct)   [short]
target_pct   = max((target_mult * atr) / entry_price, stop_pct * RTC_MIN_RR_RATIO)
target_price = entry_price * (1 + target_pct) [long]   |   entry_price * (1 - target_pct) [short]
```

**Trailing stop:**
```
activate_pct = clamp((RTC_TRAIL_ACTIVATE_MULT * atr) / entry_price, RTC_TRAIL_MIN_PCT, RTC_TRAIL_MAX_PCT)
distance_pct = clamp((RTC_TRAIL_DISTANCE_MULT * atr) / entry_price, RTC_TRAIL_MIN_PCT, RTC_TRAIL_MAX_PCT)
# long: once gain_pct >= activate_pct -> peak = max(peak, price); stop = max(stop, peak*(1-distance_pct))
# short mirrors with min()/trough — stop only ever ratchets favorably, never loosens
```

**Fill simulation:**
```
fill_price = price * (1 + RTC_PAPER_SLIPPAGE)   [buy]   |   price * (1 - RTC_PAPER_SLIPPAGE)   [sell]
gross_pnl  = (exit_fill - entry_fill) * shares  [long]  |   (entry_fill - exit_fill) * shares  [short]
net_pnl    = gross_pnl - RTC_PAPER_BROKERAGE * 2   # one brokerage leg each side
```

### Wiring into `engine/signal_engine.py`

In `_handle_bar_closed`, the exit check runs right after `volume_profile.update(ind, i)` and before pattern evaluation, so an exit on this bar settles before any new entry for the same ticker is considered on the same bar:
```python
exit_result = position_tracker.check_exit(self.ticker, ind, i)
if exit_result:
    for cb in self._signal_callbacks:
        cb(exit_result)
```

In `_process_signal`, the trade gate:
```python
trade_action = None
if composite >= RTC_SIGNAL_THRESHOLD and state.is_enabled():
    if position_tracker.has_open_position(self.ticker):
        log_event("entry_skipped_position_open", ticker=self.ticker, detail="...")
    else:
        trade_action = maybe_enter_trade(interpretation_id, self.ticker, direction, price, atr, composite,
                                          signal["stop_mult"], signal["target_mult"], signal["max_hold_bars"])
```
One open position per ticker at a time. The skip is logged to `rtc_events` (not `rtc_trade_actions`, since no fill happened); the interpretation row is still written unconditionally.

### `stop_mult`/`target_mult`/`max_hold_bars` for SMC and chart patterns

Candlestick patterns already carry these as class attributes; SMC and chart-pattern signal dicts didn't. `engine/pattern_risk_defaults.py` supplies a lookup table by `pattern_name`, applied once in `_evaluate_patterns`:

| pattern_name | stop_mult | target_mult | max_hold_bars |
|---|---|---|---|
| `bullish_ob_retest` / `bearish_ob_retest` | 1.5 | 3.0 | 60 |
| `fvg_fill_bullish` / `fvg_fill_bearish` | 1.3 | 2.5 | 30 |
| `liquidity_sweep_reversal` | 1.4 | 3.2 | 45 |
| `break_of_structure` | 1.8 | 3.5 | 60 |
| `change_of_character` | 1.6 | 3.5 | 50 |
| `double_top_breakdown` / `double_bottom_breakout` | 1.7 | 3.3 | 60 |
| `head_shoulders_breakdown` / `inv_head_shoulders_breakout` | 1.8 | 3.8 | 75 |
| `triangle_breakout` / `triangle_breakdown` | 1.5 | 3.0 | 60 |
| `flag_breakout` / `flag_breakdown` | 1.4 | 2.8 | 40 |

### Runtime toggle + position retrieval

```
GET  /api/auto-trade   -> {"enabled": state.is_enabled()}
POST /api/auto-trade   {"enabled": bool} -> flips it, logs rtc_events, returns new state
GET  /api/positions    -> current open positions, queried directly from rtc_open_positions (DB is the source of truth)
```
`server/app.py`'s lifespan calls `position_tracker.load_open_positions()` right after `init_db()`. Frontend: a switch in `#status-bar` next to the ticker/connection/source chips — confirm-to-enable (native `confirm()` dialog explaining what turning it on does), instant-to-disable.

### Journal schema additions

`RtcTradeAction` gained `stop_price`, `target_price`, `composite_score_at_entry`, `dollar_risk`, `score_multiplier`, `atr_at_entry`. `RtcTradeOutcome` gained `bars_held`. New table `RtcOpenPosition` (see Journal Schema section above) is the live, continuously-updated source of truth for open positions, backing both restart recovery and `GET /api/positions`. Every trailing-stop ratchet also gets an immutable `rtc_events` row so the full bar-by-bar lifecycle is backtrackable, not just the final entry/exit.

### Known limitations (documented, not blockers)

- **No real order routing** — 100% simulated fill only; `ibkr_paper`/`live` modes raise `NotImplementedError`.
- **`RTC_CAPITAL_POOL` is a static sizing reference, not a running balance** — matches how `PORTFOLIO_CAPITAL` works in the EOD system today.
- **Engine-side state** (`SwingDetector`, `LevelTracker`, `SMCEngine`'s active order-blocks/FVGs/structure-trend, `VolumeProfileTracker`) is still in-memory only — only the trade/position lifecycle was upgraded to DB-backed persistence, since that's the state where losing it on restart has real consequences.

### Verification

`realtime_chart_ai/scripts/verify_trading_phase.py` — a standalone harness (not a permanent test suite) run against the real dev DB, covering: sizing scales correctly with composite score across the realistic stop-distance range; stop/target formulas for both directions plus clamp-bound behavior; the full exit lifecycle (trailing-stop ratchet that never loosens, then a forced stop-loss exit); P&L math for both directions; the runtime toggle; restart recovery (a fresh `PositionTracker` reconstructing an open position exactly from the DB); and the journal/skip-path correctness (new columns populated, one-position-per-ticker gating logged). All checks pass; the script cleans up every row it creates regardless of pass/fail.

**Phase 3 — multi-ticker generalization (not yet built)**
1. `DataSourceManager.stream()` run concurrently per ticker (asyncio tasks), each with its own `TimeframeStore`/`SignalEngine`.
2. `/ws/scanner` endpoint for a cross-ticker grid view, reusing the single-ticker chart component.
3. **High-alert popup for trade-relevant events on background tickers** (per user feedback): once multiple tickers stream concurrently, a user watching one ticker's chart could easily miss something important happening on another.
   - **Alert criteria**: (a) a position exits on any tracked ticker, or (b) a new signal fires with `composite_score >= RTC_HIGH_ALERT_THRESHOLD` (default 85) on any tracked ticker.
   - **Transport**: a new `/ws/alerts` endpoint that every connected frontend client subscribes to regardless of which ticker's chart it currently has open. Every alert also written to `rtc_events` (`event_type="high_alert"`).
   - **Frontend**: a toast/banner notification with a "View" button that switches the dashboard's active ticker to the alerted one — the "popping charts and signals" behavior.

**Phase 4 (optional, future) — order flow / footprint**
Only if a paid IBKR tick-by-tick (`reqTickByTickData`) or Level 2 market-depth subscription is added later. Not built until that data subscription decision is made.

## Verification Plan

1. Confirm IBKR TWS/Gateway running in paper mode, port 7497, API enabled, and that the account's ASX/NSE market data subscription is active.
2. `python realtime_chart_ai/run_server.py --init-db` — creates the `rtc_*` tables; confirm via `psql` that existing tables are untouched.
3. Start server (`bash realtime_chart_ai/run.sh`); confirm log shows IBKR connect, historical backfill completion, live 5s-bar subscription.
4. Open `http://localhost:8800/`; confirm WS `101 Switching Protocols`, candles render/update, markers/commentary appear as signals fire.
5. Confirm `rtc_bars` accumulating every closed bar on every configured timeframe, and `rtc_events` capturing the startup connect/backfill sequence.
6. Confirm Claude rationale appears in both the DB and the commentary panel.
7. Toggle auto-trade on via the frontend switch; confirm a qualifying signal opens a position with `rtc_trade_actions`/`rtc_open_positions` populated, subsequent qualifying signals on the same ticker are skipped and logged, and the position eventually closes via one of the three exit paths with `rtc_trade_outcomes` populated.
8. Restart the server; confirm `GET /api/positions` still shows the position that was open before the restart, picked up exactly via `load_open_positions()`.
9. Confirm this server (8800) and the existing Streamlit dashboard (8501)/scheduler run simultaneously without conflict.
10. Run `realtime_chart_ai/scripts/verify_trading_phase.py` end-to-end against the real dev DB.

## Reference Files (patterns to replicate, not modify)

- `strategies/patterns.py`, `strategies/base.py` — candlestick pattern *style* (`fires(ind, i)` signature, confidence/reason dict) to reimplement against incremental multi-timeframe state.
- `execution/ibkr_trader.py` — IBKR connect/retry/backoff pattern to replicate in `datasources/ibkr_source.py` with a distinct client-ID range.
- `ai_engine/claude_summarizer.py` — Claude client construction + rule-based fallback pattern to replicate in `ai/rationale.py`.
- `storage/models.py`, `storage/database.py` — SQLAlchemy model/session conventions to mirror (own `Base`, own engine) in `journal/`.
- `execution/paper_trader.py` — simulated-fill slippage/brokerage formula to replicate in `trading/pnl.py`.
- `signals/risk_params.py` — dollar-risk position sizing and ATR-based stop/target/trailing-stop formulas to replicate (with new `RTC_`-prefixed config) in `trading/sizing.py` and `trading/stops.py`.
- `execution/stop_loss.py` — per-bar stop/target/trailing-stop exit-checking pattern to replicate in `trading/position_tracker.py` (the intraday `max_hold_bars` field replaces the EOD version's ADX-based stale-day threshold, since that's a daily-bar concept).
- `config/settings.py` — `python-dotenv` + `os.getenv(..., default)` convention to replicate in `realtime_chart_ai/settings.py`.
