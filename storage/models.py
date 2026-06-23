from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, Text, Date, Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Price(Base):
    __tablename__ = "prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float, nullable=False)
    volume = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_price_ticker_date"),
        Index("ix_price_ticker_date", "ticker", "date"),
    )


class NewsItem(Base):
    __tablename__ = "news"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    source = Column(String(50))          # 'asx_rss' | 'google_news' | 'form604'
    headline = Column(Text, nullable=False)
    url = Column(Text)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    sentiment_score = Column(Float)      # -1.0 → +1.0 (Ollama)
    sentiment_label = Column(String(20)) # 'positive' | 'neutral' | 'negative'
    __table_args__ = (Index("ix_news_ticker_pub", "ticker", "published_at"),)


class DirectorTrade(Base):
    __tablename__ = "director_trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    director_name = Column(String(200))
    trade_date = Column(Date)
    trade_type = Column(String(10))      # 'buy' | 'sell'
    shares = Column(Float)
    price = Column(Float)
    value = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_director_ticker", "ticker", "trade_date"),)


class MacroIndicator(Base):
    __tablename__ = "macro"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    indicator = Column(String(50), nullable=False)  # 'rba_rate' | 'aud_usd' | 'iron_ore' etc.
    value = Column(Float, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("date", "indicator", name="uq_macro_date_indicator"),
    )


class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    sentiment_score = Column(Float)
    fundamental_score = Column(Float)
    technical_score = Column(Float)
    insider_score = Column(Float)
    composite_score = Column(Float)      # 0-100 weighted aggregate
    regime_ok = Column(Boolean, default=True)
    kelly_fraction = Column(Float)
    position_size_aud = Column(Float)
    entry_price = Column(Float)
    target_price = Column(Float)
    stop_loss_price = Column(Float)
    strategy_name = Column(String(40))   # per-stock strategy that gated this signal
    direction = Column(String(8), default="long")  # 'long' | 'short'
    strategy_fires = Column(Boolean, default=False)  # entry condition triggered today
    generated_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_signal_ticker_date"),
        Index("ix_signal_composite", "date", "composite_score"),
    )


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    trade_type = Column(String(10), nullable=False)  # 'buy' | 'sell'
    mode = Column(String(10), default="paper")       # 'paper' | 'live'
    entry_date = Column(Date)
    exit_date = Column(Date)
    entry_price = Column(Float)
    exit_price = Column(Float)
    shares = Column(Float)
    gross_pnl = Column(Float)
    net_pnl = Column(Float)
    brokerage = Column(Float)
    exit_reason = Column(String(50))     # 'stop_loss' | 'target' | 'manual' | 'regime'
    signal_score = Column(Float)
    source = Column(String(20), default="morning")  # 'morning' | 'intraday'
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_trade_ticker_date", "ticker", "entry_date"),)


class StrategyAssignment(Base):
    """Per-stock strategy chosen by walk-forward backtest + forward-test validation."""
    __tablename__ = "strategy_assignments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, unique=True)
    strategy_name = Column(String(40), nullable=False)
    direction = Column(String(8), default="long")  # 'long' | 'short'
    validated = Column(Boolean, default=False)   # passed both backtest AND forward gates
    bt_trades = Column(Integer)
    bt_win_rate = Column(Float)
    bt_profit_factor = Column(Float)
    bt_avg_return_pct = Column(Float)
    bt_max_drawdown_pct = Column(Float)
    fw_trades = Column(Integer)
    fw_win_rate = Column(Float)
    fw_profit_factor = Column(Float)
    fw_total_return_pct = Column(Float)
    rank_score = Column(Float)
    assigned_at = Column(DateTime, default=datetime.utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, unique=True)
    entry_date = Column(Date)
    entry_price = Column(Float)
    target_price = Column(Float)
    stop_loss_price = Column(Float)
    shares = Column(Float)
    position_size_aud = Column(Float)
    current_price = Column(Float)
    unrealised_pnl = Column(Float)
    unrealised_pnl_pct = Column(Float)
    days_held = Column(Integer, default=0)
    signal_score = Column(Float)
    is_active = Column(Boolean, default=True)
    trading_mode = Column(String(20), default="paper")  # 'paper' | 'ibkr_paper' | 'live'
    direction = Column(String(8), default="long")     # 'long' | 'short'
    source = Column(String(20), default="morning")    # 'morning' | 'intraday'
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
