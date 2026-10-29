import ast
from typing import List
from collections import deque

def canonical_ast_node_types(code: str) -> List[str]:
    """
    Parse Python code and return list of node type names (BFS traversal).
    """
    try:
        tree = ast.parse(code)
    except Exception:
        return []
    types = []
    q = deque([tree])
    while q:
        node = q.popleft()
        types.append(type(node).__name__)
        for child in ast.iter_child_nodes(node):
            q.append(child)
    return types

def lcs_length(a: List[str], b: List[str]) -> int:
    # classic DP LCS
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return 0
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n-1, -1, -1):
        for j in range(m-1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = 1 + dp[i+1][j+1]
            else:
                dp[i][j] = max(dp[i+1][j], dp[i][j+1])
    return dp[0][0]

def ast_similarity(code_a: str, code_b: str) -> float:
    ta = canonical_ast_node_types(code_a)
    tb = canonical_ast_node_types(code_b)
    if not ta or not tb:
        return 0.0
    lcs = lcs_length(ta, tb)
    # normalize by average length
    denom = (len(ta) + len(tb)) / 2
    if denom == 0:
        return 0.0
    return lcs / denom
