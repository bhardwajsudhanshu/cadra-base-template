"""Metrics: real per-request latency + inference cost (no LLM => 0.0)."""
from __future__ import annotations
import time

class Timer:
    def __init__(self):
        self.t0 = time.perf_counter()
    def ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

def inference_cost_usd() -> float:
    return 0.0
