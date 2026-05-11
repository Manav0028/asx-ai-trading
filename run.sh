#!/bin/bash
# Convenience wrapper — activates the conda env and runs main.py
CONDA_PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"
cd "$(dirname "$0")"
PYTHONPATH=. "$CONDA_PYTHON" main.py "$@"
