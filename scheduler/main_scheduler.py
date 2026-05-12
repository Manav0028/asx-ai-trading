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
    # ASX also scrapes Form 604 insider trades
    if exchange.id == "asx":
        from data_ingestion.form604_scraper import fetch_form604
        fetch_form604()


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


def job_daily_report():
    logger.info("Generating daily report")
    from reports.daily_report import generate_and_send
    generate_and_send()


def job_place_orders():
    logger.info("Placing paper/live orders")
    from signals.aggregator import get_top_signals
    from execution.paper_trader import process_new_signals
    from config.settings import LIVE_TRADING_ENABLED

    signals = get_top_signals(n=20)

    if LIVE_TRADING_ENABLED:
        from execution.ibkr_trader import place_market_buy, place_stop_loss_order
        from signals.kelly_sizer import compute_shares
        for sig in signals:
            shares = compute_shares(sig.get("position_size_aud", 0), sig.get("entry_price", 1))
            if shares > 0:
                fill = place_market_buy(sig["ticker"], shares)
                if fill and sig.get("stop_loss_price"):
                    place_stop_loss_order(sig["ticker"], shares, sig["stop_loss_price"])
    else:
        fills = process_new_signals(signals)
        logger.info("Paper orders placed: %d", len(fills))

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


def job_market_close():
    logger.info("Market close — evaluating exits + updating P&L")
    from execution.stop_loss import evaluate_exits, check_stale_positions
    evaluate_exits()
    stale = check_stale_positions()
    if stale:
        logger.info("Exited %d stale positions", len(stale))


def job_news_refresh():
    logger.info("Refreshing Google News RSS")
    from data_ingestion.news_fetcher import fetch_news
    fetch_news()


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

    # Orders ~45 min after market open
    orders_h = mo_h
    orders_m = mo_m + 45
    if orders_m >= 60:
        orders_h += 1
        orders_m -= 60

    scheduler.add_job(job_fetch_prices,            CronTrigger(hour=ph,      minute=0,       day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_fetch_announcements,      CronTrigger(hour=ph,      minute=30,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_ai_sentiment_fundamental, CronTrigger(hour=ph + 1,  minute=0,       day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_technical_regime,         CronTrigger(hour=ph + 1,  minute=15,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_signal_scan,              CronTrigger(hour=ph + 1,  minute=20,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_daily_report,             CronTrigger(hour=ph + 1,  minute=30,      day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_place_orders,             CronTrigger(hour=orders_h, minute=orders_m, day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_market_close,             CronTrigger(hour=mc_h,    minute=mc_m,    day_of_week="mon-fri", timezone=tz))
    scheduler.add_job(job_news_refresh,             CronTrigger(minute=0,     hour="*/2",                            timezone=tz))
    scheduler.add_job(job_weekly_sunday,            CronTrigger(day_of_week="sun", hour=8, minute=0,                 timezone=tz))

    logger.info(
        "Scheduler built for %s (%s) — pipeline starts %02d:00, market %02d:%02d–%02d:%02d",
        exchange.name, tz, ph, mo_h, mo_m, mc_h, mc_m,
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
