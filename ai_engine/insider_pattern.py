"""
Layer 03 · AI Engine — Insider Pattern AI (scikit-learn)
Scores director buy/sell patterns using a trained LogisticRegression model.
Features: net_buy_value_90d, buy_count, sell_count, avg_price_vs_current,
          days_since_last_buy, cluster_buy (multiple directors).
Returns 0-100 insider signal score.
"""
import logging
import pickle
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from data_ingestion.form604_scraper import get_recent_director_trades
from data_ingestion.price_fetcher import get_latest_price
from storage.cache import cache_score, get_cached_score

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "insider_model.pkl"


def _extract_features(ticker: str, days: int = 90) -> np.ndarray:
    trades = get_recent_director_trades(ticker, days=days)
    current_price = get_latest_price(ticker) or 1.0

    buy_trades = [t for t in trades if t.trade_type == "buy"]
    sell_trades = [t for t in trades if t.trade_type == "sell"]

    net_buy_value = sum(t.value for t in buy_trades) - sum(t.value for t in sell_trades)
    buy_count = len(buy_trades)
    sell_count = len(sell_trades)

    # Average buy price vs current price
    if buy_trades:
        avg_buy_price = np.mean([t.price for t in buy_trades if t.price])
        price_ratio = avg_buy_price / current_price if current_price else 1.0
    else:
        price_ratio = 1.0

    # Days since last buy
    if buy_trades:
        latest_buy = max(t.trade_date for t in buy_trades)
        days_since_buy = (date.today() - latest_buy).days
    else:
        days_since_buy = days  # max staleness

    # Cluster buy: >1 unique director bought in last 30 days
    recent_directors = {
        t.director_name for t in buy_trades
        if (date.today() - t.trade_date).days <= 30
    }
    cluster_buy = 1 if len(recent_directors) > 1 else 0

    return np.array([
        net_buy_value / 1_000_000,  # scale to millions
        buy_count,
        sell_count,
        price_ratio,
        days_since_buy,
        cluster_buy,
    ], dtype=float)


def _rule_based_score(features: np.ndarray) -> float:
    net_buy_m, buy_count, sell_count, price_ratio, days_since_buy, cluster = features

    score = 50.0  # neutral baseline

    # Net buy value bonus
    if net_buy_m > 5:
        score += 25
    elif net_buy_m > 1:
        score += 15
    elif net_buy_m > 0:
        score += 8
    elif net_buy_m < -1:
        score -= 15
    elif net_buy_m < 0:
        score -= 8

    # Buy freshness
    if days_since_buy < 7:
        score += 10
    elif days_since_buy < 30:
        score += 5
    elif days_since_buy > 60:
        score -= 5

    # Cluster buy
    if cluster:
        score += 10

    # Insider buying below current price is more bullish
    if buy_count > 0 and price_ratio < 0.95:
        score += 5

    # Heavy selling
    if sell_count > buy_count * 2:
        score -= 10

    return max(0.0, min(100.0, score))


def _load_model():
    if MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return None


def score_insider(ticker: str) -> float:
    """Returns insider signal score 0-100."""
    cached = get_cached_score(ticker, "insider")
    if cached is not None:
        return cached

    try:
        features = _extract_features(ticker)
        model = _load_model()

        if model is not None:
            prob = model.predict_proba(features.reshape(1, -1))[0][1]  # P(bullish)
            score = prob * 100
        else:
            score = _rule_based_score(features)

    except Exception as e:
        logger.warning("Insider scoring failed for %s: %s", ticker, e)
        score = 50.0

    score = round(max(0.0, min(100.0, score)), 2)
    cache_score(ticker, "insider", score, ttl=3600 * 4)
    return score


def train_insider_model(training_data: list) -> None:
    """
    Train and persist the insider pattern model.
    training_data: list of (features_array, label) where label=1 if stock
                   outperformed XJO by >5% in 3 months following trades.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    if len(training_data) < 20:
        logger.warning("Not enough training data (%d samples)", len(training_data))
        return

    X = np.array([d[0] for d in training_data])
    y = np.array([d[1] for d in training_data])

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    model.fit(X, y)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    logger.info("Insider model trained and saved to %s", MODEL_PATH)


def batch_score_insider(tickers: list) -> dict:
    return {t: score_insider(t) for t in tickers}
