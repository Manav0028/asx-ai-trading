#!/usr/bin/env python3
"""
ASX AI Trading System — Main Entry Point

Usage:
  python main.py                    # Start the full scheduler
  python main.py --run-now          # Run today's full pipeline once immediately
  python main.py --report           # Generate and send today's report
  python main.py --scan             # Run signal scan only
  python main.py --backtest         # Run walk-forward backtest
  python main.py --init-db          # Initialise database tables
  python main.py --backfill 30      # Backfill 30 days of price history
  python main.py --test-alerts      # Send test Telegram + email alert
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
        logging.FileHandler("asx_trading.log"),
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
    """Execute the entire daily pipeline sequentially."""
    from scheduler.main_scheduler import (
        job_fetch_prices,
        job_fetch_announcements,
        job_ai_sentiment_fundamental,
        job_technical_regime,
        job_signal_scan,
        job_daily_report,
        job_place_orders,
    )
    logger.info("=== Running full pipeline ===")
    job_fetch_prices()
    job_fetch_announcements()
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
    parser = argparse.ArgumentParser(description="ASX AI Trading System")
    parser.add_argument("--run-now",  action="store_true", help="Run full pipeline once")
    parser.add_argument("--report",   action="store_true", help="Generate today's report")
    parser.add_argument("--scan",     action="store_true", help="Run signal scan")
    parser.add_argument("--backtest", action="store_true", help="Run walk-forward backtest")
    parser.add_argument("--init-db",  action="store_true", help="Initialise DB tables")
    parser.add_argument("--backfill", type=int, metavar="DAYS", help="Backfill N days of prices")
    parser.add_argument("--test-alerts", action="store_true", help="Send test alert")
    args = parser.parse_args()

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
        from config.asx200_tickers import ASX200_TICKERS
        from signals.aggregator import run_full_scan
        results = run_full_scan(ASX200_TICKERS)
        top = [r for r in results if r["composite_score"] >= 75]
        print(f"\nTop signals (score ≥ 75): {len(top)}")
        for s in top[:10]:
            print(
                f"  {s['ticker']:10s} score={s['composite_score']:.1f}  "
                f"entry=${s.get('entry_price', 0):.3f}"
            )

    elif args.backtest:
        from config.asx200_tickers import ASX200_TICKERS
        from ai_engine.backtester import run_walk_forward
        from config.settings import BACKTESTER_LOOKBACK_MONTHS
        results = run_walk_forward(ASX200_TICKERS[:50], lookback_months=BACKTESTER_LOOKBACK_MONTHS)
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
