from typing import List, Dict, Any, Tuple
from src.utils.winnowing import jaccard_fingerprint
from src.utils.ast_utils import ast_similarity

def algorithmic_similarity(file_a: Dict[str, Any], file_b: Dict[str, Any]) -> Dict:
    """
    Combines fingerprint jaccard (token) and AST similarity (if available).
    Returns combined score and evidence.
    """
    fp_a = file_a.get("fingerprint", set())
    fp_b = file_b.get("fingerprint", set())
    token_sim = jaccard_fingerprint(fp_a, fp_b)

    ast_sim = 0.0
    if file_a.get("ast_types") is not None and file_b.get("ast_types") is not None:
        ast_sim = ast_similarity(file_a["content"], file_b["content"])

    # simple aggregation:
    if file_a.get("lang") == "python" and file_b.get("lang") == "python":
        combined = 0.6 * ast_sim + 0.4 * token_sim
    else:
        combined = token_sim

    evidence = {
        "token_similarity": token_sim,
        "ast_similarity": ast_sim,
    }
    return {"score": combined, "evidence": evidence}
