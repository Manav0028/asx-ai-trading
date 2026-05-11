import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import redis
    from config.settings import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_TTL_SECONDS

    _client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
        decode_responses=True, socket_connect_timeout=2,
    )
    _client.ping()
    REDIS_AVAILABLE = True
    logger.info("Redis connected at %s:%s", REDIS_HOST, REDIS_PORT)
except Exception as e:
    REDIS_AVAILABLE = False
    _client = None
    logger.warning("Redis unavailable (%s) — falling back to in-process dict cache", e)

_local: Dict[str, Any] = {}


def set_value(key: str, value: Any, ttl: int = None) -> None:
    if ttl is None:
        from config.settings import REDIS_TTL_SECONDS
        ttl = REDIS_TTL_SECONDS
    serialised = json.dumps(value)
    if REDIS_AVAILABLE and _client:
        _client.setex(key, ttl, serialised)
    else:
        _local[key] = serialised


def get_value(key: str) -> Optional[Any]:
    if REDIS_AVAILABLE and _client:
        raw = _client.get(key)
    else:
        raw = _local.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def delete_key(key: str) -> None:
    if REDIS_AVAILABLE and _client:
        _client.delete(key)
    else:
        _local.pop(key, None)


def cache_score(ticker: str, score_type: str, score: float, ttl: int = 3600) -> None:
    set_value(f"score:{ticker}:{score_type}", score, ttl)


def get_cached_score(ticker: str, score_type: str) -> Optional[float]:
    return get_value(f"score:{ticker}:{score_type}")
