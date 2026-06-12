"""
Strategy Engine — Base Strategy Interface
Each strategy evaluates a single bar of precomputed indicators and decides
whether to enter, with its own stop/target geometry suited to its edge.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional

import numpy as np


class Strategy(ABC):
    """A self-contained entry rule with its own risk geometry."""

    name: str = "base"
    description: str = ""
    direction: str = "long"   # "long" or "short" — shorts profit from falls
    # ATR multipliers — each strategy holds for a different kind of move
    stop_mult: float = 2.0
    target_mult: float = 3.5
    max_hold_days: int = 30

    @abstractmethod
    def fires(self, ind: Dict[str, np.ndarray], i: int) -> Optional[Dict]:
        """
        Evaluate bar `i` of the precomputed indicator arrays.
        Returns None (no entry) or a dict:
          {"confidence": 0-1, "reason": str}
        """

    def evaluate_latest(self, ind: Dict[str, np.ndarray]) -> Optional[Dict]:
        return self.fires(ind, len(ind["closes"]) - 1)
