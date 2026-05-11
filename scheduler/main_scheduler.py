"""
Master Scheduler — Daily Execution Schedule
Uses APScheduler for cron-style job execution (all times AEST).

6:00 AM   → yFinance OHLCV + macro fetch
6:30 AM   → ASX announcements + Form 604
7:00 AM   → Ollama sentiment + fundamental scores
7:15 AM   → Technical engine + regime filter
7:20 AM   → Signal aggregator (full scan)
7:30 AM   → Daily report → Telegram + email
10:00 AM  → Paper/live orders placed for score ≥ 75
4:00 PM   → Stop-loss/target evaluation + watchlist P&L
Every 2h  → Google News RSS refresh
Sunday    → Walk-forward backtest + Claude batch summaries
"""
import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config.asx200_tickers import ASX200_TICKERS

logger = logging.getLogger(__name__)


# ── Individual job functions ──────────────────────────────────────────────────

def job_fetch_prices():
    logger.info("[6:00] Fetching OHLCV prices")
    from data_ingestion.price_fetcher import fetch_prices
    from data_ingestion.macro_fetcher import fetch_macro
    fetch_prices()
    fetch_macro()


def job_fetch_announcements():
    logger.info("[6:30] Fetching ASX announcements + Form 604")
    from data_ingestion.asx_announcements import fetch_asx_announcements
    from data_ingestion.form604_scraper import fetch_form604
    fetch_asx_announcements()
    fetch_form604()


def job_ai_sentiment_fundamental():
    logger.info("[7:00] Running Ollama sentiment + fundamental scores")
    from ai_engine.sentiment import batch_score_sentiment
    from ai_engine.fundamental_scorer import batch_score_fundamental
    batch_score_sentiment(ASX200_TICKERS)
    batch_score_fundamental(ASX200_TICKERS)


def job_technical_regime():
    logger.info("[7:15] Running technical engine + regime filter")
    from ai_engine.technical_engine import batch_score_technical
    from ai_engine.regime_filter import is_regime_ok
    batch_score_technical(ASX200_TICKERS)
    ok = is_regime_ok()
    logger.info("Regime: %s", "RISK-ON" if ok else "RISK-OFF")


def job_signal_scan():
    logger.info("[7:20] Running full signal scan")
    from signals.aggregator import run_full_scan
    results = run_full_scan(ASX200_TICKERS)
    above_threshold = [r for r in results if r["composite_score"] >= 75]
    logger.info(
        "Signal scan complete: %d tickers scored, %d above threshold",
        len(results), len(above_threshold),
    )


def job_daily_report():
    logger.info("[7:30] Generating daily report")
    from reports.daily_report import generate_and_send
    generate_and_send()


def job_place_orders():
    logger.info("[10:00] Placing paper/live orders")
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

        # Send Telegram alerts for new signals
        from alerts.telegram_bot import send_signal_alert
        for sig in signals[:5]:
            send_signal_alert(sig)


def job_market_close():
    logger.info("[4:00] Market close — evaluating exits + updating P&L")
    from execution.stop_loss import evaluate_exits, check_stale_positions
    from alerts.telegram_bot import send_stop_loss_alert, send_target_alert

    stops, targets = evaluate_exits()
    stale = check_stale_positions()

    for s in stops:
        send_stop_loss_alert(s["ticker"], s["fill_price"], s["pnl"])
    for t in targets:
        send_target_alert(t["ticker"], t["fill_price"], t["pnl"])

    if stale:
        logger.info("Exited %d stale positions", len(stale))


def job_news_refresh():
    logger.info("[2h] Refreshing Google News RSS")
    from data_ingestion.news_fetcher import fetch_news
    fetch_news()


def job_weekly_sunday():
    logger.info("[Sunday] Running walk-forward backtest + Claude batch")
    from ai_engine.backtester import run_walk_forward
    from ai_engine.claude_summarizer import generate_weekly_summaries
    from config.settings import BACKTESTER_LOOKBACK_MONTHS

    results = run_walk_forward(ASX200_TICKERS[:50], lookback_months=BACKTESTER_LOOKBACK_MONTHS)
    logger.info("Backtest complete for %d tickers", len(results))

    summaries = generate_weekly_summaries()
    logger.info("Claude summaries generated for %d tickers", len(summaries))


# ── Scheduler setup ───────────────────────────────────────────────────────────

def build_scheduler() -> BlockingScheduler:
    tz = os.getenv("TZ", "Australia/Sydney")
    scheduler = BlockingScheduler(timezone=tz)

    scheduler.add_job(job_fetch_prices,             CronTrigger(hour=6,  minute=0,  day_of_week="mon-fri"))
    scheduler.add_job(job_fetch_announcements,       CronTrigger(hour=6,  minute=30, day_of_week="mon-fri"))
    scheduler.add_job(job_ai_sentiment_fundamental,  CronTrigger(hour=7,  minute=0,  day_of_week="mon-fri"))
    scheduler.add_job(job_technical_regime,          CronTrigger(hour=7,  minute=15, day_of_week="mon-fri"))
    scheduler.add_job(job_signal_scan,               CronTrigger(hour=7,  minute=20, day_of_week="mon-fri"))
    scheduler.add_job(job_daily_report,              CronTrigger(hour=7,  minute=30, day_of_week="mon-fri"))
    scheduler.add_job(job_place_orders,              CronTrigger(hour=10, minute=0,  day_of_week="mon-fri"))
    scheduler.add_job(job_market_close,              CronTrigger(hour=16, minute=0,  day_of_week="mon-fri"))
    scheduler.add_job(job_news_refresh,              CronTrigger(minute=0, hour="*/2"))
    scheduler.add_job(job_weekly_sunday,             CronTrigger(day_of_week="sun", hour=8, minute=0))

    return scheduler


def start():
    logger.info("Starting ASX AI Trading scheduler")
    scheduler = build_scheduler()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
