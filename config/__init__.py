"""Config package — exposes get_active_exchange() for all modules."""
import config.exchanges  # noqa: F401 — registers all exchanges as a side effect
from config.exchange_registry import Exchange, get_exchange
from config.settings import EXCHANGE


def get_active_exchange() -> Exchange:
    return get_exchange(EXCHANGE)
