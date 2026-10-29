import hashlib
from typing import List, Tuple, Set

def _kgrams(tokens: List[str], k: int):
    for i in range(len(tokens) - k + 1):
        yield " ".join(tokens[i:i+k])

def tokens_from_code(code: str):
    # simple whitespace + punctuation tokenizer, language-agnostic baseline
    import re
    toks = re.findall(r"[A-Za-z_]\w+|\d+|==|!=|<=|>=|[{}()\[\];,.<>+\-*/%=]", code)
    return toks

def kgram_hashes(tokens: List[str], k: int) -> List[Tuple[int,int]]:
    """
    Return list of (hash, position) for each k-gram.
    """
    out = []
    for i, kg in enumerate(_kgrams(tokens, k)):
        h = int(hashlib.sha1(kg.encode("utf-8")).hexdigest()[:16], 16)
        out.append((h, i))
    return out

def winnow_hashes(tokens: List[str], k: int = 5, w: int = 4):
    """
    Winnowing algorithm. Returns set of chosen hashes (fingerprint).
    """
    khashes = kgram_hashes(tokens, k)
    if not khashes:
        return set()
    selected = set()
    # sliding window over khashes
    for i in range(len(khashes) - w + 1):
        window = khashes[i:i+w]
        minhash = min(window, key=lambda x: (x[0], -x[1]))  # prefer rightmost min
        selected.add(minhash[0])
    return selected

def jaccard_fingerprint(f1: Set[int], f2: Set[int]) -> float:
    if not f1 and not f2:
        return 0.0
    inter = len(f1 & f2)
    uni = len(f1 | f2)
    return inter / uni if uni else 0.0
