from dataclasses import dataclass

@dataclass
class Config:
    winnow_k: int = 5
    winnow_window: int = 4
    # Scoring weights
    w_alg = 0.4
    w_llm = 0.25
    w_cross = 0.2
    w_commit = 0.15
    # Thresholds
    plag_threshold = 0.8
    suspicious_threshold = 0.5

CONF = Config()
