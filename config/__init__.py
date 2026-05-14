"""Config package — exposes get_active_exchange() for all modules."""
import os
import config.exchanges  # noqa: F401 — registers all exchanges as a side effect
from config.exchange_registry import Exchange, get_exchange


def get_active_exchange() -> Exchange:
    """Reads EXCHANGE env var at call-time so two processes can run different exchanges."""
    exchange_id = os.environ.get("EXCHANGE", "asx").lower()
    return get_exchange(exchange_id)
