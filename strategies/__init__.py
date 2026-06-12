"""
Layer 04b · Strategy Engine
Per-stock dynamic strategy selection: each ticker is matched to the trading
strategy that historically performs best on it (validated by walk-forward
backtest + out-of-sample forward test) before any order is placed.
"""
