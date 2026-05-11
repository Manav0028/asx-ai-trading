#!/usr/bin/env python3
"""Backfill price history for specific tickers or all ASX200."""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_ingestion.price_fetcher import fetch_prices
from config.asx200_tickers import ASX200_TICKERS

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365, help="Days to backfill")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (default: all ASX200)")
    args = parser.parse_args()

    tickers = args.tickers or ASX200_TICKERS
    print(f"Backfilling {args.days} days for {len(tickers)} tickers...")
    n = fetch_prices(tickers=tickers, days_back=args.days)
    print(f"Done: {n} rows stored")
