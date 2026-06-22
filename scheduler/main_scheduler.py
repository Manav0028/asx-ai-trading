"""
Master Scheduler — Daily Execution Schedule
Uses APScheduler for cron-style job execution in the active exchange's timezone.

Times below are relative to exchange local time (configured via EXCHANGE env var).

pre_market_hour+0:00  → yFinance OHLCV + macro fetch
pre_market_hour+0:30  → Exchange announcements
pre_market_hour+1:00  → Ollama sentiment + fundamental scores
pre_market_hour+1:15  → Technical engine + regime filter
pre_market_hour+1:20  → Signal aggregator (full scan)
pre_market_hour+1:30  → Daily report → Telegram + email
market_open+0:45      → Paper/live orders placed for score ≥ 75
market_close+0:00     → Stop-loss/target evaluation + watchlist P&L
Every 2h              → Google News RSS refresh
Sunday 07:00          → Per-stock strategy selection (backtest + forward validation)
Sunday 08:00          → Walk-forward backtest + Claude batch summaries
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import get_active_exchange

logger = logging.getLogger(__name__)


def _tickers():
    return get_active_exchange().tickers


# ── Individual job functions ──────────────────────────────────────────────────

def job_fetch_prices():
    logger.info("Fetching OHLCV prices + macro indicators")
    from data_ingestion.price_fetcher import fetch_prices
    from data_ingestion.macro_fetcher import fetch_macro
    fetch_prices()
    fetch_macro()


def job_fetch_announcements():
    exchange = get_active_exchange()
    logger.info("Fetching %s announcements", exchange.name)
    if exchange.announcement_fetcher:
        exchange.announcement_fetcher()


def job_fetch_insider_trades():
    exchange = get_active_exchange()
    logger.info("Fetching %s insider/director trades", exchange.name)
    if exchange.insider_fetcher:
        exchange.insider_fetcher()
    else:
        logger.info("No insider fetcher configured for %s", exchange.name)


def job_ai_sentiment_fundamental():
    logger.info("Running Ollama sentiment + fundamental scores")
    from ai_engine.sentiment import batch_score_sentiment
    from ai_engine.fundamental_scorer import batch_score_fundamental
    tickers = _tickers()
    batch_score_sentiment(tickers)
    batch_score_fundamental(tickers)


def job_technical_regime():
    logger.info("Running technical engine + regime filter")
    from ai_engine.technical_engine import batch_score_technical
    from ai_engine.regime_filter import is_regime_ok
    batch_score_technical(_tickers())
    ok = is_regime_ok()
    logger.info("Regime: %s", "RISK-ON" if ok else "RISK-OFF")


def job_signal_scan():
    logger.info("Running full signal scan")
    from signals.aggregator import run_full_scan
    from config.settings import SIGNAL_THRESHOLD
    results = run_full_scan(_tickers())
    above_threshold = [r for r in results if r["composite_score"] >= SIGNAL_THRESHOLD]
    logger.info(
        "Signal scan complete: %d tickers scored, %d above threshold (%.0f)",
        len(results), len(above_threshold), SIGNAL_THRESHOLD,
    )
    # ── Phase 2: Supabase cloud sync ─────────────────────────────────────────
    from storage.supabase_sync import sync_signals_to_supabase, sync_regime_to_supabase
    sync_signals_to_supabase()
    sync_regime_to_supabase()
    # ── Phase 3: Signal decay check on held positions ─────────────────────
    job_signal_decay_check()


def job_daily_report():
    logger.info("Generating daily report")
    from reports.daily_report import generate_and_send
    generate_and_send()


def job_place_orders():
    logger.info("Placing orders")
    from signals.aggregator import get_top_signals
    from config.settings import LIVE_TRADING_ENABLED, IBKR_PAPER_ENABLED

    signals = get_top_signals(n=20)

    if LIVE_TRADING_ENABLED:
        # ── Phase 3: IBKR live trading ────────────────────────────────────
        from execution.ibkr_trader import place_market_buy, place_stop_loss_order
        from signals.kelly_sizer import compute_shares
        for sig in signals:
            shares = compute_shares(sig.get("position_size_aud", 0), sig.get("entry_price", 1))
            if shares > 0:
                fill = place_market_buy(sig["ticker"], shares)
                if fill and sig.get("stop_loss_price"):
                    place_stop_loss_order(sig["ticker"], shares, sig["stop_loss_price"])

    elif IBKR_PAPER_ENABLED:
        # ── Phase 2: IBKR paper trading ───────────────────────────────────
        from execution.ibkr_paper_trader import ibkr_process_new_signals
        fills = ibkr_process_new_signals(signals)
        logger.info("IBKR paper orders placed: %d", len(fills))

    else:
        # ── Phase 1: Internal paper trader ────────────────────────────────
        from execution.paper_trader import process_new_signals
        fills = process_new_signals(signals)
        logger.info("Internal paper orders placed: %d", len(fills))

    # ── Telegram signal alerts for all non-live fills ─────────────────────
    if not LIVE_TRADING_ENABLED and 'fills' in dir():
        from alerts.telegram_bot import send_signal_alert
        from ai_engine.technical_engine import get_technical_meta
        from ai_engine.fundamental_scorer import get_fundamental_meta
        from ai_engine.sentiment import get_sentiment_meta
        for fill in fills:
            ticker = fill["ticker"]
            sig = next((s for s in signals if s["ticker"] == ticker), None)
            if sig:
                send_signal_alert(
                    sig,
                    tech_meta=get_technical_meta(ticker),
                    fund_meta=get_fundamental_meta(ticker),
                    sent_meta=get_sentiment_meta(ticker),
                )

        from alerts.telegram_bot import send_signal_alert
        from ai_engine.technical_engine import get_technical_meta
        from ai_engine.fundamental_scorer import get_fundamental_meta
        from ai_engine.sentiment import get_sentiment_meta
        from signals.watchlist import get_active_watchlist
        active_tickers = {p["ticker"] for p in get_active_watchlist()}
        for fill in fills:
            ticker = fill["ticker"]
            sig = next((s for s in signals if s["ticker"] == ticker), None)
            if sig:
                send_signal_alert(
                    sig,
                    tech_meta=get_technical_meta(ticker),
                    fund_meta=get_fundamental_meta(ticker),
                    sent_meta=get_sentiment_meta(ticker),
                )

        from alerts.telegram_bot import send_volume_spike_alert
        from ai_engine.technical_engine import get_technical_meta as gtm
        for sig in signals:
            if sig["composite_score"] >= 70:
                meta = gtm(sig["ticker"])
                vol_signals = [s for s in (meta.get("signals") or []) if "volume" in s.lower()]
                if vol_signals:
                    ratio_str = vol_signals[0].split("volume ")[1].split("x")[0] if "x" in vol_signals[0] else "2"
                    try:
                        ratio = float(ratio_str)
                    except Exception:
                        ratio = 2.0
                    if ratio >= 2.0:
                        send_volume_spike_alert(
                            sig["ticker"], sig.get("entry_price", 0),
                            ratio, sig["composite_score"]
                        )
    # ── Phase 2: Supabase cloud sync ─────────────────────────────────────────
    from storage.supabase_sync import sync_watchlist_to_supabase
    sync_watchlist_to_supabase()


def job_market_close():
    logger.info("Market close — evaluating exits + updating P&L")
    from execution.stop_loss import evaluate_exits, check_stale_positions
    evaluate_exits()
    stale = check_stale_positions()
    if stale:
        logger.info("Exited %d stale positions", len(stale))
    # ── Phase 2: Supabase cloud sync ─────────────────────────────────────────
    from storage.supabase_sync import sync_watchlist_to_supabase, sync_trades_to_supabase
    sync_watchlist_to_supabase()   # positions may have changed (stop/target exits)
    sync_trades_to_supabase()


def job_intraday_check():
    """
    Every 30 min during market hours — fetch live prices and check
    stop-loss / target exits without waiting for end-of-day close.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    exchange = get_active_exchange()
    tz       = exchange.timezone
    now      = datetime.now(ZoneInfo(tz))
    oh, om   = exchange.market_open
    ch, cm   = exchange.market_close

    # Guard: only run during market hours
    open_t  = now.replace(hour=oh,  minute=om, second=0, microsecond=0)
    close_t = now.replace(hour=ch,  minute=cm, second=0, microsecond=0)
    if not (open_t <= now <= close_t):
        logger.debug("Intraday check skipped — market closed (%s)", now.strftime("%H:%M"))
        return

    from signals.watchlist import get_active_watchlist
    positions = get_active_watchlist()
    if not positions:
        return

    # Fetch live prices from yfinance (1-minute bars, latest close)
    tickers = [p["ticker"] for p in positions]
    try:
        import yfinance as yf
        raw = yf.download(tickers, period="1d", interval="1m",
                          progress=False, auto_adjust=True)
        if raw.empty:
            logger.warning("Intraday: yfinance returned no data")
            return

        close = raw["Close"] if "Close" in raw.columns else raw
        live_prices = {}
        if len(tickers) == 1:
            live_prices[tickers[0]] = float(close.dropna().iloc[-1])
        else:
            for t in tickers:
                try:
                    live_prices[t] = float(close[t].dropna().iloc[-1])
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Intraday price fetch failed: %s", e)
        return

    from execution.stop_loss import intraday_evaluate_exits
    stops, targets = intraday_evaluate_exits(live_prices)
    logger.info(
        "Intraday check done — %d stop(s), %d target(s), prices checked: %d",
        len(stops), len(targets), len(live_prices),
    )


def job_signal_decay_check():
    """
    After daily signal scan — re-score held positions and warn via Telegram
    if any position's composite score has dropped below 45 (decay threshold).
    Does NOT auto-exit; sends an alert for manual review.
    """
    from datetime import date
    from signals.watchlist import get_active_watchlist
    from storage.database import get_session
    from storage.models import Signal

    DECAY_THRESHOLD = 45.0   # warn if today's score falls below this

    positions = get_active_watchlist()
    if not positions:
        return

    today    = date.today()
    tickers  = [p["ticker"] for p in positions]
    pos_map  = {p["ticker"]: p for p in positions}

    with get_session() as session:
        rows = (
            session.query(Signal)
            .filter(Signal.date == today, Signal.ticker.in_(tickers))
            .all()
        )
        scores_today = {r.ticker: r.composite_score for r in rows}

    from alerts.telegram_bot import send_signal_decay_alert
    warned = 0
    for ticker, score in scores_today.items():
        if score < DECAY_THRESHOLD:
            pos          = pos_map[ticker]
            entry_score  = pos.get("signal_score") or 65.0
            pnl_pct      = pos.get("unrealised_pnl_pct") or 0
            days_held    = pos.get("days_held") or 0
            logger.warning(
                "Signal decay: %s score %.1f → %.1f (held %dd, P&L %.1f%%)",
                ticker, entry_score, score, days_held, pnl_pct,
            )
            send_signal_decay_alert(ticker, score, entry_score, pnl_pct, days_held)
            warned += 1

    if warned:
        logger.info("Signal decay check: %d position(s) flagged", warned)
    else:
        logger.info("Signal decay check: all held positions scoring OK")


def job_news_refresh():
    logger.info("Refreshing Google News RSS")
    from data_ingestion.news_fetcher import fetch_news
    fetch_news()
    _check_held_position_news()


def _check_held_position_news():
    """
    After each news refresh — scan recent news for held tickers and send
    a Telegram warning if very negative sentiment is detected (score < 20).
    Called inside job_news_refresh(), not a standalone scheduled job.
    """
    from datetime import datetime, timedelta
    from signals.watchlist import get_active_watchlist
    from storage.database import get_session
    from storage.models import NewsItem

    NEGATIVE_THRESHOLD = 20.0   # 0–100 scale; below this is very negative
    LOOKBACK_HOURS     = 2

    positions = get_active_watchlist()
    if not positions:
        return

    cutoff  = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)
    pos_map = {p["ticker"]: p for p in positions}

    from alerts.telegram_bot import send_negative_news_alert
    alerted = set()

    with get_session() as session:
        for ticker in pos_map:
            recent_neg = (
                session.query(NewsItem)
                .filter(
                    NewsItem.ticker == ticker,
                    NewsItem.fetched_at >= cutoff,
                    NewsItem.sentiment_score != None,
                )
                .order_by(NewsItem.sentiment_score)   # worst first
                .limit(5)
                .all()
            )
            if not recent_neg:
                continue

            # sentiment_score in NewsItem is -1.0 → +1.0; normalise to 0-100
            worst = recent_neg[0]
            score_0_100 = (worst.sentiment_score + 1) / 2 * 100

            if score_0_100 < NEGATIVE_THRESHOLD and ticker not in alerted:
                headlines = [n.headline for n in recent_neg]
                pnl_pct   = pos_map[ticker].get("unrealised_pnl_pct") or 0
                logger.warning(
                    "Negative news on held position %s (sentiment %.0f/100)",
                    ticker, score_0_100,
                )
                send_negative_news_alert(ticker, headlines, score_0_100, pnl_pct)
                alerted.add(ticker)


def job_rescan_and_trade():
    """
    On-demand pipeline: validate strategies → rescore all tickers → place orders.
    Fixes stale position_size_aud=0 that occurs when signals were stored before
    strategy validation completed. Safe to run any time market is open.
    """
    logger.info("=== Rescan-and-trade: validate → rescore → place orders ===")

    # Step 1: validate strategies so position sizes are computed correctly
    from strategies.selector import run_strategy_selection
    sel = run_strategy_selection(_tickers())
    logger.info(
        "Strategy validation: %d total, %d validated, %d skipped",
        sel["total"], sel["validated"], sel["skipped"],
    )

    # Step 2: rescore all tickers — position_size_aud now reflects validated state
    from signals.aggregator import run_full_scan
    from config.settings import SIGNAL_THRESHOLD
    results = run_full_scan(_tickers())
    above = [r for r in results if r.get("position_size_aud", 0) > 0]
    logger.info(
        "Signal rescan: %d scored, %d with position size (actionable)",
        len(results), len(above),
    )

    # Step 3: sync fresh signals + regime to Supabase (both DBs)
    from storage.supabase_sync import (
        sync_signals_to_supabase, sync_regime_to_supabase,
        sync_strategy_assignments_to_supabase, sync_trades_to_supabase,
    )
    sync_signals_to_supabase()
    sync_regime_to_supabase()
    sync_strategy_assignments_to_supabase()
    sync_trades_to_supabase()   # keep closed-trade history current in both DBs

    # Step 4: place orders; job_place_orders also calls sync_watchlist_to_supabase
    job_place_orders()
    logger.info("=== Rescan-and-trade complete ===")


def job_strategy_selection():
    """
    Weekly per-stock strategy selection. Backtests all 5 strategies on each
    ticker's own history (70% in-sample / 30% out-of-sample forward test) and
    assigns the best validated strategy. Order placement only acts on signals
    whose assigned strategy passed both tests and fires on the day.
    """
    logger.info("Running per-stock strategy selection (backtest + forward validation)")
    from strategies.selector import run_strategy_selection
    summary = run_strategy_selection(_tickers())
    logger.info(
        "Strategy selection: %d assigned, %d validated, %d skipped",
        summary["total"], summary["validated"], summary["skipped"],
    )
    # ── Phase 2: Sync assignments to Supabase for the cloud Radar tab ─────────
    from storage.supabase_sync import sync_strategy_assignments_to_supabase
    sync_strategy_assignments_to_supabase()


def job_weekly_sunday():
    logger.info("Running walk-forward backtest + weekly summary")
    from ai_engine.backtester import run_walk_forward
    from ai_engine.claude_summarizer import generate_weekly_summaries
    from alerts.telegram_bot import send_weekly_summary, _send
    from signals.aggregator import get_top_signals
    from signals.watchlist import get_watchlist_summary
    from ai_engine.regime_filter import get_regime_summary
    from config.settings import BACKTESTER_LOOKBACK_MONTHS

    results = run_walk_forward(_tickers()[:50], lookback_months=BACKTESTER_LOOKBACK_MONTHS)
    logger.info("Backtest complete for %d tickers", len(results))
    # ── Phase 2: Cache backtest results to Supabase ───────────────────────────
    from storage.supabase_sync import sync_backtest_to_supabase
    sync_backtest_to_supabase(results)

    summaries = generate_weekly_summaries()
    logger.info("Summaries generated for %d tickers", len(summaries))

    top_signals  = get_top_signals(n=5, min_score=60)
    port_summary = get_watchlist_summary()
    regime       = get_regime_summary()
    send_weekly_summary(results, top_signals, port_summary, regime)

    if summaries:
        _send("📝 *Top Stock Summaries This Week:*")
        for ticker, summary in list(summaries.items())[:5]:
            _send(f"*{ticker}*\n{summary}")


# ── Scheduler setup ───────────────────────────────────────────────────────────

def build_scheduler() -> BlockingScheduler:
    exchange = get_active_exchange()
    tz = exchange.timezone
    scheduler = BlockingScheduler(timezone=tz)

    ph = exchange.pre_market_hour          # pre-market pipeline start hour
    mo_h, mo_m = exchange.market_open      # market open
    mc_h, mc_m = exchange.market_close     # market close

    # job_rescan_and_trade runs periodically throughout the session so the system
    # can pick up new entry signals as the day progresses.
    #
    # First run: the later of (pipeline done + 20 min buffer) and (market open + 45 min).
    # Subsequent runs: every RESCAN_INTERVAL_MIN minutes.
    # Last run: no later than market_close - RESCAN_CUTOFF_MIN (avoid late-day entries).
    RESCAN_INTERVAL_MIN = 90
    RESCAN_CUTOFF_MIN   = 60   # don't start a new rescan within 60 min of close

    pipeline_done_min  = (ph + 1) * 60 + 50   # ph+1:50 — 20 min after signal_scan
    market_open_min    = mo_h * 60 + mo_m + 45
    first_rescan_min   = max(pipeline_done_min, market_open_min)
    market_close_min   = mc_h * 60 + mc_m
    cutoff_min         = market_close_min - RESCAN_CUTOFF_MIN

    rescan_times = []
    t = first_rescan_min
    while t <= cutoff_min:
        rescan_times.append((t // 60, t % 60))
        t += RESCAN_INTERVAL_MIN

    scheduler.add_job(job_fetch_prices,            CronTrigger(hour=ph,      minute=0,       day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_fetch_announcements,      CronTrigger(hour=ph,      minute=20,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_fetch_insider_trades,     CronTrigger(hour=ph,      minute=40,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_ai_sentiment_fundamental, CronTrigger(hour=ph + 1,  minute=0,       day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_technical_regime,         CronTrigger(hour=ph + 1,  minute=15,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_signal_scan,              CronTrigger(hour=ph + 1,  minute=20,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_daily_report,             CronTrigger(hour=ph + 1,  minute=30,      day_of_week="mon-fri", timezone=tz))
    for rh, rm in rescan_times:
        scheduler.add_job(job_rescan_and_trade,     CronTrigger(hour=rh,      minute=rm,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_intraday_check,           CronTrigger(minute="*/30", day_of_week="mon-fri",                timezone=tz))
    scheduler.add_job(job_market_close,             CronTrigger(hour=mc_h,    minute=mc_m,    day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_news_refresh,             CronTrigger(minute=0,     hour="*/2",                            timezone=tz))
    scheduler.add_job(job_strategy_selection,       CronTrigger(day_of_week="sun", hour=7, minute=0,                 timezone=tz))
    scheduler.add_job(job_weekly_sunday,            CronTrigger(day_of_week="sun", hour=8, minute=0,                 timezone=tz))

    times_str = ", ".join(f"{h:02d}:{m:02d}" for h, m in rescan_times)
    logger.info(
        "Scheduler built for %s (%s) — pipeline starts %02d:00, market %02d:%02d–%02d:%02d, rescan+trade at: %s",
        exchange.name, tz, ph, mo_h, mo_m, mc_h, mc_m, times_str,
    )
    return scheduler


def start():
    exchange = get_active_exchange()
    logger.info("Starting AI Trading scheduler — %s", exchange.name)
    scheduler = build_scheduler()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
