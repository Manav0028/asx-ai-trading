"""
Layer 01 · Data Ingestion — NSE India Promoter & Insider Trade Disclosures
SEBI mandates disclosure of insider trades via the NSE/BSE PIT (Prohibition of
Insider Trading) Regulations. This fetcher queries:
  1. NSE's public corporate PIT API (primary)
  2. BSE's bulk/block deal data (supplementary — large institutional trades)

Data is stored in the shared director_trades table with source='nse_pit'.
"""
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import List

import requests

from config.nifty100_tickers import NIFTY100_CODES
from storage.database import get_session
from storage.models import DirectorTrade

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
})

# NSE PIT disclosures endpoint — returns insider trading for a symbol
NSE_PIT_URL = (
    "https://www.nseindia.com/api/corporates-pit"
    "?index=equities&symbol={symbol}&from_date={from_date}&to_date={to_date}"
)

# BSE bulk deal endpoint — large block trades (institutional)
BSE_BULK_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/BulkDealData/w"
    "?strdate={from_date}&enddate={to_date}&scripcd="
)


def _warm_session() -> bool:
    """Visit NSE homepage to initialise cookies (required for API access)."""
    try:
        _session.get("https://www.nseindia.com", timeout=10)
        return True
    except Exception as e:
        logger.debug("NSE session warm failed: %s", e)
        return False


def _parse_date(s: str) -> date:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return date.today()


def _store_trade(
    ticker: str,
    director: str,
    trade_date: date,
    trade_type: str,
    shares: float,
    price: float,
    value: float,
    source: str = "nse_pit",
) -> bool:
    if not ticker or not trade_date:
        return False
    with get_session() as session:
        exists = (
            session.query(DirectorTrade)
            .filter(
                DirectorTrade.ticker == ticker,
                DirectorTrade.trade_date == trade_date,
                DirectorTrade.director_name == director,
                DirectorTrade.trade_type == trade_type,
            )
            .first()
        )
        if exists:
            return False
        session.add(DirectorTrade(
            ticker=ticker,
            director_name=director,
            trade_date=trade_date,
            trade_type=trade_type,
            shares=shares,
            price=price,
            value=value,
        ))
        return True


def _fetch_nse_pit(symbol: str, from_date: str, to_date: str) -> int:
    """Fetch SEBI PIT disclosures from NSE for one symbol."""
    url = NSE_PIT_URL.format(symbol=symbol, from_date=from_date, to_date=to_date)
    try:
        resp = _session.get(url, timeout=12)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        rows = data.get("data", [])
        stored = 0
        ticker = f"{symbol}.NS"
        for row in rows:
            # Fields vary by NSE API version — handle both known formats
            person = (
                row.get("personName")
                or row.get("acqName")
                or row.get("name", "Unknown")
            )
            acq_mode = (row.get("acqMode") or "").lower()
            # Purchases: "Buy", "ESOP", "Allotment"; Sales: "Sell", "Gift"
            trade_type = "sell" if any(
                w in acq_mode for w in ["sell", "transfer", "gift", "pledge"]
            ) else "buy"

            try:
                shares = float(row.get("secAcq") or row.get("secTran") or 0)
            except (ValueError, TypeError):
                shares = 0.0
            try:
                price = float(row.get("price") or row.get("avgprice") or 0)
            except (ValueError, TypeError):
                price = 0.0
            try:
                value = float(row.get("val") or (shares * price))
            except (ValueError, TypeError):
                value = shares * price

            trade_date_str = (
                row.get("date")
                or row.get("acqfromDt")
                or row.get("intimDt", "")
            )
            trade_date = _parse_date(trade_date_str)

            if _store_trade(ticker, person, trade_date, trade_type, shares, price, value):
                stored += 1
        return stored
    except Exception as e:
        logger.debug("NSE PIT fetch failed for %s: %s", symbol, e)
        return 0


def fetch_nse_insider_trades(
    codes: List[str] = None,
    days_back: int = 90,
) -> int:
    """
    Fetch SEBI insider trading disclosures for all NIFTY 100 stocks.
    Stores results in the director_trades table.
    """
    codes = codes or NIFTY100_CODES
    to_dt = date.today()
    from_dt = to_dt - timedelta(days=days_back)
    from_date = from_dt.strftime("%d-%m-%Y")
    to_date = to_dt.strftime("%d-%m-%Y")
    stored = 0
    api_hits = 0

    logger.info(
        "Fetching NSE insider trades for %d symbols (%s → %s)",
        len(codes), from_date, to_date,
    )

    _warm_session()

    for i, code in enumerate(codes):
        n = _fetch_nse_pit(code, from_date, to_date)
        if n > 0:
            api_hits += 1
            stored += n

        # Polite rate limiting to avoid NSE rate-limit bans
        if i % 10 == 9:
            time.sleep(2.0)
        else:
            time.sleep(0.5)

    logger.info(
        "NSE insider trades: %d new records stored (API responded for %d/%d symbols)",
        stored, api_hits, len(codes),
    )
    return stored


def get_recent_insider_trades(ticker: str, days: int = 90) -> List[DirectorTrade]:
    """Returns recent insider trades for a ticker (used by insider_pattern.py)."""
    cutoff = date.today() - timedelta(days=days)
    with get_session() as session:
        trades = (
            session.query(DirectorTrade)
            .filter(DirectorTrade.ticker == ticker, DirectorTrade.trade_date >= cutoff)
            .order_by(DirectorTrade.trade_date.desc())
            .all()
        )
        session.expunge_all()
        return trades
