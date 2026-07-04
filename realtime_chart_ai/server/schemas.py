"""Pydantic payload shapes for the WebSocket/REST surface — documentation of
the wire contract between server and frontend, one type per message kind."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CandleUpdate(BaseModel):
    type: str = "candle_update"
    ticker: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


class PatternSignalMessage(BaseModel):
    type: str = "pattern_signal"
    ticker: str
    pattern_name: str
    pattern_type: str
    direction: str
    confidence: float
    composite_score: float
    rule_reason: str
    mtf_confluence: bool
    mtf_summary: str
    smc_zone: str
    claude_rationale: Optional[str] = None
    claude_model: Optional[str] = None
    price_at_signal: float
    interpretation_id: int


class JournalEntry(BaseModel):
    id: int
    ticker: str
    bar_ts: str
    pattern_name: str
    pattern_type: Optional[str] = None
    direction: Optional[str] = None
    confidence: Optional[float] = None
    composite_score: Optional[float] = None
    rule_reason: Optional[str] = None
    smc_zone: Optional[str] = None
    claude_rationale: Optional[str] = None
