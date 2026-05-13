"""ASX 200 exchange configuration."""
from config.exchange_registry import Exchange, register
from config.asx200_tickers import ASX200_TICKERS, ASX200_CODES

_MACRO_SYMBOLS = {
    "aud_usd":   "AUDUSD=X",
    "iron_ore":  "IRON.L",
    "gold_usd":  "GC=F",
    "oil_brent": "BZ=F",
    "xjo_index": "^AXJO",
    "sp500":     "^GSPC",
    "vix":       "^VIX",
    "copper":    "HG=F",
}


def _asx_news_query(ticker: str) -> str:
    code = ticker.replace(".AX", "")
    return f"{code} ASX stock"


def _asx_announcement_fetcher():
    from data_ingestion.asx_announcements import fetch_asx_announcements
    return fetch_asx_announcements()


def _asx_insider_fetcher():
    from data_ingestion.form604_scraper import fetch_director_trades
    return fetch_director_trades()


ASX = Exchange(
    id="asx",
    name="ASX 200",
    tickers=ASX200_TICKERS,
    ticker_codes=ASX200_CODES,
    index_ticker="^AXJO",
    index_name="ASX 200",
    index_macro_key="xjo_index",
    macro_symbols=_MACRO_SYMBOLS,
    timezone="Australia/Sydney",
    currency_code="AUD",
    currency_symbol="$",
    market_open=(10, 0),
    market_close=(16, 0),
    pre_market_hour=6,
    gnews_hl="en-AU",
    gnews_gl="AU",
    gnews_ceid="AU:en",
    news_query_fn=_asx_news_query,
    announcement_fetcher=_asx_announcement_fetcher,
    insider_fetcher=_asx_insider_fetcher,
)

register(ASX)
