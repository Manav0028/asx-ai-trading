"""
Exchange Registry — defines the Exchange dataclass and registry of supported exchanges.

Set the active exchange with the EXCHANGE environment variable (default: "asx").
Supported values: "asx", "nse"
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class Exchange:
    id: str                             # e.g. "asx", "nse"
    name: str                           # e.g. "ASX 200", "NSE NIFTY 100"
    tickers: List[str]                  # yfinance ticker symbols
    index_ticker: str                   # benchmark index yfinance symbol
    index_name: str                     # display name, e.g. "ASX 200", "NIFTY 100"
    index_macro_key: str                # key stored in macro table, e.g. "xjo_index"
    macro_symbols: Dict[str, str]       # indicator_name -> yfinance symbol
    timezone: str                       # IANA tz, e.g. "Australia/Sydney"
    currency_code: str                  # e.g. "AUD", "INR"
    currency_symbol: str                # e.g. "$", "₹"
    market_open: tuple                  # (hour, minute) in exchange local time
    market_close: tuple                 # (hour, minute) in exchange local time
    pre_market_hour: int                # hour to start morning pipeline (local)
    gnews_hl: str                       # Google News hl param, e.g. "en-AU"
    gnews_gl: str                       # Google News gl param, e.g. "AU"
    gnews_ceid: str                     # Google News ceid, e.g. "AU:en"
    news_query_fn: Callable[[str], str] # builds search query string from ticker
    announcement_fetcher: Optional[Callable] = None   # exchange-specific filings fetcher
    ticker_codes: List[str] = field(default_factory=list)  # bare codes (no suffix)


_REGISTRY: Dict[str, "Exchange"] = {}


def register(exchange: Exchange) -> None:
    _REGISTRY[exchange.id] = exchange


def get_exchange(exchange_id: str) -> Exchange:
    if exchange_id not in _REGISTRY:
        raise ValueError(
            f"Unknown exchange '{exchange_id}'. Available: {list(_REGISTRY)}"
        )
    return _REGISTRY[exchange_id]


def list_exchanges() -> List[str]:
    return list(_REGISTRY.keys())
