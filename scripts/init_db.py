#!/usr/bin/env python3
"""One-time script to initialise the database and backfill historical data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.database import init_db, health_check
from data_ingestion.price_fetcher import fetch_prices
from data_ingestion.macro_fetcher import fetch_macro

if __name__ == "__main__":
    print("Checking DB connection...")
    if not health_check():
        print("ERROR: Cannot connect to database. Check your .env settings.")
        sys.exit(1)

    print("Creating tables...")
    init_db()

    print("Backfilling 365 days of price history (this may take a few minutes)...")
    n = fetch_prices(days_back=365)
    print(f"  → {n} price rows stored")

    print("Backfilling macro indicators...")
    m = fetch_macro(days_back=365)
    print(f"  → {m} macro rows stored")

    print("\nDatabase initialised successfully!")
    print("Next: run `python main.py --test-alerts` to verify Telegram/email.")
    print("Then: run `python main.py` to start the scheduler.")
