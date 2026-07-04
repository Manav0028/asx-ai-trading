"""
Journal schema — own declarative Base, isolated from storage/models.py.
Five `rtc_`-prefixed tables (see plan doc): every closed bar, every confirmed
signal interpretation (rule + Claude), every trade action/outcome, and a
system event log — "keep track of everything" is a first-class requirement,
not an afterthought.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RtcBar(Base):
    __tablename__ = "rtc_bars"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    bar_ts = Column(DateTime, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    source = Column(String(20))
    delayed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_rtc_bars_ticker_tf_ts", "ticker", "timeframe", "bar_ts"),)


class RtcChartInterpretation(Base):
    __tablename__ = "rtc_chart_interpretations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    bar_ts = Column(DateTime, nullable=False)
    timeframe = Column(String(10))
    data_source = Column(String(20))
    pattern_name = Column(String(40), nullable=False)
    pattern_type = Column(String(20))          # 'candlestick' | 'chart' | 'smc'
    direction = Column(String(8))              # 'long' | 'short'
    confidence = Column(Float)
    composite_score = Column(Float)
    rule_reason = Column(Text)
    mtf_confluence = Column(Boolean)
    mtf_summary = Column(Text)
    smc_zone = Column(String(20))              # 'premium' | 'discount' | 'equilibrium'
    smc_context = Column(Text)
    claude_rationale = Column(Text)
    claude_model = Column(String(40))
    price_at_signal = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_rtc_interp_ticker_ts", "ticker", "bar_ts"),)


class RtcTradeAction(Base):
    __tablename__ = "rtc_trade_actions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    interpretation_id = Column(Integer, ForeignKey("rtc_chart_interpretations.id"), nullable=False)
    action_type = Column(String(20))           # 'entry' | 'exit' | 'no_action'
    mode = Column(String(10), default="paper") # 'paper' | 'ibkr_paper' | 'live'
    entry_price = Column(Float)
    shares = Column(Float)
    order_id = Column(String(40))
    executed_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_rtc_action_interp", "interpretation_id"),)


class RtcTradeOutcome(Base):
    __tablename__ = "rtc_trade_outcomes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_action_id = Column(Integer, ForeignKey("rtc_trade_actions.id"), nullable=False, unique=True)
    exit_price = Column(Float)
    exit_ts = Column(DateTime)
    exit_reason = Column(String(50))           # 'stop_loss' | 'target' | 'manual' | 'session_close'
    gross_pnl = Column(Float)
    net_pnl = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RtcEvent(Base):
    __tablename__ = "rtc_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String(30))    # 'connect' | 'disconnect' | 'failover' | 'error' | 'backfill_complete' | 'subscribe'
    source = Column(String(20))
    ticker = Column(String(20), nullable=True)
    detail = Column(Text)
    __table_args__ = (Index("ix_rtc_events_ts", "ts"),)
