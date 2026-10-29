from src.core.config import CONF
from typing import Dict, Any

def aggregate_scores(seg_alg: float, seg_llm: float, seg_cross: float, seg_commit: float) -> float:
    w_a, w_l, w_c, w_m = CONF.w_alg, CONF.w_llm, CONF.w_cross, CONF.w_commit
    num = w_a*seg_alg + w_l*seg_llm + w_c*seg_cross + w_m*seg_commit
    denom = w_a + w_l + w_c + w_m
    return num / denom

def interpret_risk(r: float) -> str:
    if r >= 0.8:
        return "High"
    if r >= 0.5:
        return "Suspicious"
    return "Low"
