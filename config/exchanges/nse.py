"""NSE India — NIFTY 100 exchange configuration."""
from config.exchange_registry import Exchange, register
from config.nifty100_tickers import NIFTY100_TICKERS, NIFTY100_CODES

# NIFTY 100 index on yfinance is ^CNX100; NIFTY 50 is ^NSEI
_MACRO_SYMBOLS = {
    "nifty100_index": "^CNX100",
    "inr_usd":        "INRUSD=X",
    "gold_inr":       "GC=F",
    "oil_brent":      "BZ=F",
    "sp500":          "^GSPC",
    "vix":            "^VIX",
    "sensex":         "^BSESN",
    "copper":         "HG=F",
}


def _nse_news_query(ticker: str) -> str:
    code = ticker.replace(".NS", "")
    return f"{code} NSE India stock"


def _nse_announcement_fetcher():
    from data_ingestion.nse_announcements import fetch_nse_announcements
    return fetch_nse_announcements()


def _nse_insider_fetcher():
    from data_ingestion.nse_insider_scraper import fetch_nse_insider_trades
    return fetch_nse_insider_trades()


NSE = Exchange(
    id="nse",
    name="NSE NIFTY 100",
    flag="🇮🇳",
    tickers=NIFTY100_TICKERS,
    ticker_codes=NIFTY100_CODES,
    index_ticker="^CNX100",
    index_name="NIFTY 100",
    index_macro_key="nifty100_index",
    macro_symbols=_MACRO_SYMBOLS,
    timezone="Asia/Kolkata",
    currency_code="INR",
    currency_symbol="₹",
    market_open=(9, 15),
    market_close=(15, 30),
    pre_market_hour=9,
    gnews_hl="en-IN",
    gnews_gl="IN",
    gnews_ceid="IN:en",
    news_query_fn=_nse_news_query,
    announcement_fetcher=_nse_announcement_fetcher,
    insider_fetcher=_nse_insider_fetcher,
)

register(NSE)
