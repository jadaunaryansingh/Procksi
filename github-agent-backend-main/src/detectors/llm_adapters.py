#  src/detectors/llm_adapters.py
import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

def _safe_get_env(key: str):
    return os.environ.get(key)

# Codequiry adapter (template) ------------------------------------------------
def call_codequiry(code_text: str) -> Dict[str, Any]:
    """
    Template function to call Codequiry API.
    Set environment variable CODEQUIRY_API_KEY with your key.
    Replace endpoint with real Codequiry endpoint & payload expected by their API.
    """
    api_key = _safe_get_env("CODEQUIRY_API_KEY")
    if not api_key:
        return {"provider": "codequiry", "score": None, "error": "missing API key"}

    url = "https://api.codequiry.com/v1/detect"  # Example endpoint — replace if different
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"content": code_text, "type": "code"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        # The actual response shape will vary. Here we try to extract a normalized score (0..1)
        score = None
        if "ai_likelihood" in body:
            score = float(body["ai_likelihood"])
        elif "score" in body:
            score = float(body["score"])
        return {"provider": "codequiry", "score": score, "raw": body}
    except Exception as e:
        return {"provider": "codequiry", "score": None, "error": str(e)}

# Copyleaks adapter (template) ------------------------------------------------
def call_copyleaks(code_text: str) -> Dict[str, Any]:
    """
    Template function to call Copyleaks detection API.
    Requires COPYLEAKS_EMAIL and COPYLEAKS_KEY (or token flow).
    See Copyleaks docs for exact auth flow — this is illustrative.
    """
    email = _safe_get_env("COPYLEAKS_EMAIL")
    key = _safe_get_env("COPYLEAKS_KEY")
    if not email or not key:
        return {"provider": "copyleaks", "score": None, "error": "missing credentials"}

    # Copyleaks requires first obtaining an access token. Example:
    try:
        auth = requests.post(
            "https://id.copyleaks.com/v3/account/login/api",
            json={"email": email, "key": key},
            timeout=20
        )
        auth.raise_for_status()
        token = auth.json().get("access_token")
        if not token:
            return {"provider": "copyleaks", "score": None, "error": "no token from auth"}

        # submit the content for AI detection (placeholder endpoint)
        url = "https://api.copyleaks.com/v3/education/ai/content"  # placeholder — replace with actual
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"content": code_text, "filename": "snippet.py"}
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        score = None
        if "ai_probability" in body:
            score = float(body["ai_probability"])
        return {"provider": "copyleaks", "score": score, "raw": body}
    except Exception as e:
        return {"provider": "copyleaks", "score": None, "error": str(e)}
