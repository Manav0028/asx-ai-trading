#!/bin/bash
# Convenience wrapper — activates the conda env and runs run_server.py
CONDA_PYTHON="/Users/manavsharma/opt/anaconda3/envs/asx_trading/bin/python"
cd "$(dirname "$0")"
"$CONDA_PYTHON" run_server.py "$@"
