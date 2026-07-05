"""
Runtime auto-trade toggle — the single source of truth for whether automated
paper trading is currently on. Seeded from AUTO_TRADE_ENABLED_DEFAULT at
import time, but the real control is the live toggle (POST /api/auto-trade),
not the env var — flipping it takes effect on the very next signal, no
restart needed, since signal_engine.py calls is_enabled() live rather than
caching a value at import time.
"""
import logging

from journal.recorder import log_event
from settings import AUTO_TRADE_ENABLED_DEFAULT

logger = logging.getLogger(__name__)

_auto_trade_enabled: bool = AUTO_TRADE_ENABLED_DEFAULT


def is_enabled() -> bool:
    return _auto_trade_enabled


def set_enabled(value: bool, actor: str = "api") -> bool:
    global _auto_trade_enabled
    _auto_trade_enabled = value
    logger.info("Auto-trade toggled: enabled=%s (actor=%s)", value, actor)
    log_event("auto_trade_toggled", source=actor, detail=f"enabled={value}")
    return _auto_trade_enabled
