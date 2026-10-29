# src/detectors/llm_detector.py
import math
from typing import Dict, Any, List
from .llm_adapters import call_codequiry, call_copyleaks

def token_entropy(tokens):
    from collections import Counter
    c = Counter(tokens)
    probs = [v/len(tokens) for v in c.values()] if tokens else [1.0]
    return -sum(p * math.log2(p) for p in probs if p>0)

def llm_heuristic_score(file_doc: Dict[str, Any]) -> float:
    tokens = file_doc.get("tokens", [])
    if not tokens:
        return 0.0
    ent = token_entropy(tokens)
    x = ent
    
    # Adjusted Heuristic:
    # Code Entropy usually falls between 3.5 (simple) and 6.0 (complex/human).
    # Minified code is > 8.0.
    # AI code tends to be more regular (lower entropy) than messy human code.
    # We shift pivot from 6.0 to 5.5 to allow more sensitivity.
    
    # If entropy is LOW (< 5.5), score goes HIGH (AI).
    # If entropy is HIGH (> 5.5), score goes LOW (Human/Minified).
    score = 1 / (1 + math.exp((x - 5.5) * 1.5)) 
    
    length_factor = min(1.0, len(tokens) / 100)
    return float(score * length_factor)

def llm_origin_ensemble(file_doc: Dict[str, Any], providers: List[str] = None) -> Dict:
    """
    providers: list like ["codequiry", "copyleaks"] to call adapters.
    Returns: {score: 0..1, traces: [...]}
    """
    providers = providers or []
    traces = []
    local_score = llm_heuristic_score(file_doc)
    traces.append({"provider": "local_heuristic", "score": local_score, "explain": "entropy-based heuristic"})
    content = file_doc.get("content", "")[:20000]  # limit size for API calls

    for p in providers:
        if p.lower() == "codequiry":
            res = call_codequiry(content)
            traces.append(res)
        elif p.lower() == "copyleaks":
            res = call_copyleaks(content)
            traces.append(res)
        else:
            traces.append({"provider": p, "score": None, "error": "unknown provider"})

    # compute numeric scores only from entries that have 'score' numeric
    numeric_scores = [float(t["score"]) for t in traces if t.get("score") is not None]
    if numeric_scores:
        ensemble = sum(numeric_scores) / len(numeric_scores)
    else:
        ensemble = local_score
    return {"score": ensemble, "traces": traces}
