#!/usr/bin/env python3
"""
AI Trading System — Main Entry Point
Exchange is selected via the EXCHANGE env var (default: asx, options: asx, nse).

Usage:
  EXCHANGE=nse python main.py             # Start scheduler for NSE NIFTY 100
  python main.py                          # Start scheduler (default: ASX 200)
  python main.py --run-now                # Run today's full pipeline once immediately
  python main.py --report                 # Generate and send today's report
  python main.py --scan                   # Run signal scan only
  python main.py --backtest               # Run walk-forward backtest
  python main.py --init-db                # Initialise database tables
  python main.py --backfill 30            # Backfill 30 days of price history
  python main.py --test-alerts            # Send test Telegram + email alert
  python main.py --list-exchanges         # List all supported exchanges
"""
import argparse
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading.log"),
    ],
)
logger = logging.getLogger("main")


def _wait_for_db(retries: int = 10, delay: int = 5) -> bool:
    """Wait for PostgreSQL to be ready — important when started via launchd at login."""
    from storage.database import health_check
    for i in range(retries):
        if health_check():
            return True
        logger.info("Waiting for database... (%d/%d)", i + 1, retries)
        time.sleep(delay)
    return False


def run_full_pipeline():
    from scheduler.main_scheduler import (
        job_fetch_prices,
        job_fetch_announcements,
        job_news_refresh,
        job_ai_sentiment_fundamental,
        job_technical_regime,
        job_signal_scan,
        job_daily_report,
        job_place_orders,
    )
    logger.info("=== Running full pipeline ===")
    job_fetch_prices()
    job_fetch_announcements()
    job_news_refresh()           # fetch headlines before sentiment scoring
    job_ai_sentiment_fundamental()
    job_technical_regime()
    job_signal_scan()
    job_daily_report()
    job_place_orders()
    logger.info("=== Pipeline complete ===")


def init_database():
    from storage.database import init_db, health_check
    if not health_check():
        logger.error("Cannot connect to database — check DATABASE_URL in .env")
        sys.exit(1)
    init_db()
    logger.info("Database initialised successfully")


def backfill_prices(days: int):
    from data_ingestion.price_fetcher import fetch_prices
    from data_ingestion.macro_fetcher import fetch_macro
    logger.info("Backfilling %d days of price history...", days)
    n = fetch_prices(days_back=days)
    m = fetch_macro(days_back=days)
    logger.info("Backfill complete: %d price rows, %d macro rows", n, m)


def test_alerts():
    from alerts.telegram_bot import send_test_message
    ok = send_test_message()
    logger.info("Telegram test: %s", "OK" if ok else "FAILED / not configured")


def main():
    from config import get_active_exchange
    from config.exchange_registry import list_exchanges
    exchange = get_active_exchange()

    parser = argparse.ArgumentParser(
        description=f"AI Trading System ({exchange.name})"
    )
    parser.add_argument("--run-now",        action="store_true", help="Run full pipeline once")
    parser.add_argument("--report",         action="store_true", help="Generate today's report")
    parser.add_argument("--scan",           action="store_true", help="Run signal scan")
    parser.add_argument("--backtest",       action="store_true", help="Run walk-forward backtest")
    parser.add_argument("--init-db",        action="store_true", help="Initialise DB tables")
    parser.add_argument("--backfill",       type=int, metavar="DAYS", help="Backfill N days of prices")
    parser.add_argument("--test-alerts",    action="store_true", help="Send test alert")
    parser.add_argument("--list-exchanges", action="store_true", help="List supported exchanges")
    args = parser.parse_args()

    if args.list_exchanges:
        print("Supported exchanges (set with EXCHANGE env var):")
        for ex_id in list_exchanges():
            print(f"  {ex_id}")
        return

    logger.info("Active exchange: %s (%s)", exchange.name, exchange.timezone)

    if args.init_db:
        init_database()

    elif args.backfill:
        backfill_prices(args.backfill)

    elif args.run_now:
        run_full_pipeline()

    elif args.report:
        from reports.daily_report import generate_and_send
        generate_and_send()

    elif args.scan:
        from signals.aggregator import run_full_scan
        from config.settings import SIGNAL_THRESHOLD
        results = run_full_scan(exchange.tickers)
        top = [r for r in results if r["composite_score"] >= SIGNAL_THRESHOLD]
        print(f"\nTop signals (score ≥ {SIGNAL_THRESHOLD}): {len(top)}")
        for s in top[:10]:
            print(
                f"  {s['ticker']:15s} score={s['composite_score']:.1f}  "
                f"entry={exchange.currency_symbol}{s.get('entry_price', 0):.3f}"
            )

    elif args.backtest:
        from ai_engine.backtester import run_walk_forward
        from config.settings import BACKTESTER_LOOKBACK_MONTHS
        results = run_walk_forward(exchange.tickers[:50], lookback_months=BACKTESTER_LOOKBACK_MONTHS)
        print(f"Backtest complete: {len(results)} tickers")

    elif args.test_alerts:
        test_alerts()

    else:
        if not _wait_for_db():
            logger.error("Database unavailable after retries — exiting")
            sys.exit(1)
        from scheduler.main_scheduler import start
        start()


if __name__ == "__main__":
    main()
