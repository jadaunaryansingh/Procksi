"""
Token Usage API endpoints.
Track and report AI model token usage and costs.
"""

import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional
from datetime import datetime, timedelta

from ..middleware.auth import get_current_user
from ..database import get_supabase
from ..utils.report_storage import ReportStorageManager

router = APIRouter(prefix="/api/token-usage", tags=["token-usage"])


DEFAULT_MODEL_PRICING_USD_PER_1M = {
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-5.4-nano": {"input": 0.050, "output": 0.400},
    "gpt-5-mini": {"input": 0.250, "output": 2.000},
}


def _normalize_model_name(model_name: Any) -> str:
    return str(model_name or "").strip().lower()


def _get_runtime_default_model() -> str:
    """Best-effort default model for rows without detailed token_usage metadata."""
    model_name = os.getenv("OPENAI_PRODUCT_EVALUATION_MODEL", "gpt-4o-mini")
    normalized = _normalize_model_name(model_name)
    return normalized or "gpt-4o-mini"


def _model_env_key(model_name: str) -> str:
    sanitized = re.sub(r"[^a-z0-9]+", "_", model_name.lower()).strip("_")
    return sanitized.upper()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _get_env_float(var_name: str) -> float | None:
    raw = os.getenv(var_name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _get_env_model_pricing(model_name: str) -> tuple[float, float] | None:
    model_key = _model_env_key(model_name)
    input_rate = _get_env_float(f"OPENAI_MODEL_{model_key}_INPUT_PRICE_PER_1M")
    output_rate = _get_env_float(f"OPENAI_MODEL_{model_key}_OUTPUT_PRICE_PER_1M")
    if input_rate is None or output_rate is None:
        return None
    return input_rate, output_rate


def _get_env_default_pricing() -> tuple[float, float] | None:
    eval_input = _get_env_float("OPENAI_PRODUCT_EVALUATION_INPUT_PRICE_PER_1M")
    eval_output = _get_env_float("OPENAI_PRODUCT_EVALUATION_OUTPUT_PRICE_PER_1M")
    if eval_input is not None and eval_output is not None:
        return eval_input, eval_output

    default_input = _get_env_float("OPENAI_DEFAULT_INPUT_PRICE_PER_1M")
    default_output = _get_env_float("OPENAI_DEFAULT_OUTPUT_PRICE_PER_1M")
    if default_input is not None and default_output is not None:
        return default_input, default_output

    return None


def _load_model_pricing_overrides() -> dict[str, dict[str, float]]:
    raw = os.getenv("OPENAI_MODEL_PRICING_JSON")
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}

        normalized: dict[str, dict[str, float]] = {}
        for model_name, rates in parsed.items():
            if not isinstance(rates, dict):
                continue
            input_rate = rates.get("input")
            output_rate = rates.get("output")
            if input_rate is None or output_rate is None:
                continue
            normalized[_normalize_model_name(model_name)] = {
                "input": float(input_rate),
                "output": float(output_rate),
            }
        return normalized
    except Exception:
        return {}


def _get_model_pricing(model_name: Any) -> tuple[str, float, float, str]:
    normalized_model = _normalize_model_name(model_name)
    if not normalized_model:
        normalized_model = "gpt-4o-mini"

    overrides = _load_model_pricing_overrides()
    if normalized_model in overrides:
        rates = overrides[normalized_model]
        return normalized_model, rates["input"], rates["output"], "env-override"

    model_pricing = _get_env_model_pricing(normalized_model)
    if model_pricing is not None:
        input_rate, output_rate = model_pricing
        return normalized_model, input_rate, output_rate, "env-model-key"

    for key, rates in DEFAULT_MODEL_PRICING_USD_PER_1M.items():
        if normalized_model == key or normalized_model.startswith(f"{key}-"):
            return key, rates["input"], rates["output"], "default-catalog"

    default_env_pricing = _get_env_default_pricing()
    if default_env_pricing is not None:
        input_rate, output_rate = default_env_pricing
        return normalized_model, input_rate, output_rate, "env-default"

    fallback = DEFAULT_MODEL_PRICING_USD_PER_1M["gpt-4o-mini"]
    return "gpt-4o-mini", fallback["input"], fallback["output"], "legacy-fallback"


def _extract_token_usage_payload(team_row: dict[str, Any], allow_storage: bool = True) -> dict[str, Any]:
    """
    Extract token usage payload for a team row.

    When `allow_storage` is False the function will not attempt to download
    the full report JSON from storage and will instead use the lightweight
    `report_json` column (if present). This avoids long-running storage
    downloads when summarizing large numbers of teams.
    """
    report_json = None

    # Prefer lightweight DB column when storage fetches are disabled
    if not allow_storage:
        report_json = team_row.get("report_json")
        if isinstance(report_json, str):
            try:
                import json as _json
                report_json = _json.loads(report_json)
            except Exception:
                report_json = None

    # When allowed, fall back to fetching the full report from storage
    if report_json is None and allow_storage:
        try:
            report_json = ReportStorageManager.get_report_for_team(team_row)
        except Exception:
            report_json = None

    if not isinstance(report_json, dict):
        return {}

    judge = report_json.get("judge") if isinstance(report_json.get("judge"), dict) else {}
    usage = judge.get("token_usage") if isinstance(judge.get("token_usage"), dict) else {}

    if not usage:
        report_usage = report_json.get("token_usage")
        if isinstance(report_usage, dict):
            usage = report_usage

    return usage if isinstance(usage, dict) else {}


def _extract_api_call_tracking_payload(team_row: dict[str, Any], allow_storage: bool = True) -> dict[str, Any]:
    """
    Extract API call tracking payload for a team row.

    When `allow_storage` is False the function avoids downloading the full
    report from storage and uses `report_json` when available.
    """
    report_json = None

    if not allow_storage:
        report_json = team_row.get("report_json")
        if isinstance(report_json, str):
            try:
                import json as _json
                report_json = _json.loads(report_json)
            except Exception:
                report_json = None

    if report_json is None and allow_storage:
        try:
            report_json = ReportStorageManager.get_report_for_team(team_row)
        except Exception:
            report_json = None

    if not isinstance(report_json, dict):
        return {}

    tracking = report_json.get("api_call_tracking")
    return tracking if isinstance(tracking, dict) else {}


def _build_non_token_call_summary(teams: list[dict[str, Any]], allow_storage: bool = True) -> dict[str, int]:
    preflight_calls = 0

    for team in teams:
        tracking = _extract_api_call_tracking_payload(team, allow_storage=allow_storage)
        preflight_calls += _safe_int(tracking.get("openai_models_list_preflight_calls"))

    return {
        "openai_models_list_preflight_calls": preflight_calls,
        "total_non_token_calls": preflight_calls,
    }


def _extract_models_used(token_usage: dict[str, Any]) -> list[str]:
    models: list[str] = []

    for key in ("model", "frontend_model", "backend_model"):
        model_name = token_usage.get(key)
        if isinstance(model_name, str) and model_name.strip():
            models.append(model_name.strip())

    call_breakdown = token_usage.get("call_breakdown")
    if isinstance(call_breakdown, list):
        for call in call_breakdown:
            if not isinstance(call, dict):
                continue
            model_name = call.get("model")
            if isinstance(model_name, str) and model_name.strip():
                models.append(model_name.strip())

    model_costs = token_usage.get("model_costs")
    if isinstance(model_costs, dict):
        for model_name in model_costs.keys():
            if isinstance(model_name, str) and model_name.strip():
                models.append(model_name.strip())

    seen = set()
    ordered_unique = []
    for model_name in models:
        if model_name in seen:
            continue
        seen.add(model_name)
        ordered_unique.append(model_name)
    return ordered_unique


def _build_model_breakdown(teams: list[dict[str, Any]], allow_storage: bool = True) -> list[dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = {}

    for team in teams:
        team_id = str(team.get("id", ""))
        token_usage = _extract_token_usage_payload(team, allow_storage=allow_storage)
        token_usage_model_costs = token_usage.get("model_costs")

        if isinstance(token_usage_model_costs, dict) and token_usage_model_costs:
            for raw_model, model_stats in token_usage_model_costs.items():
                if not isinstance(model_stats, dict):
                    continue

                pricing_model, input_rate, output_rate, pricing_source = _get_model_pricing(raw_model)
                model_key = str(raw_model or pricing_model)
                bucket = by_model.setdefault(
                    model_key,
                    {
                        "model": model_key,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "input_cost_usd": 0.0,
                        "output_cost_usd": 0.0,
                        "total_cost_usd": 0.0,
                        "input_price_per_1m": input_rate,
                        "output_price_per_1m": output_rate,
                        "pricing_source": pricing_source,
                        "team_ids": set(),
                    },
                )

                bucket["prompt_tokens"] += _safe_int(model_stats.get("prompt_tokens"))
                bucket["completion_tokens"] += _safe_int(model_stats.get("completion_tokens"))
                bucket["total_tokens"] += _safe_int(model_stats.get("total_tokens"))
                bucket["input_cost_usd"] += _safe_float(model_stats.get("input_cost_usd"))
                bucket["output_cost_usd"] += _safe_float(model_stats.get("output_cost_usd"))
                bucket["total_cost_usd"] += _safe_float(model_stats.get("total_cost_usd"))
                bucket["team_ids"].add(team_id)
            continue

        fallback_model = (
            token_usage.get("model")
            if isinstance(token_usage.get("model"), str)
            else _get_runtime_default_model()
        )
        pricing_model, input_rate, output_rate, pricing_source = _get_model_pricing(fallback_model)
        model_key = str(fallback_model or pricing_model)

        prompt_tokens = _safe_int(team.get("openai_prompt_tokens"))
        completion_tokens = _safe_int(team.get("openai_completion_tokens"))
        total_tokens = _safe_int(team.get("openai_total_tokens"))
        total_cost_usd = _safe_float(team.get("openai_cost_usd"))

        bucket = by_model.setdefault(
            model_key,
            {
                "model": model_key,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "input_price_per_1m": input_rate,
                "output_price_per_1m": output_rate,
                "pricing_source": f"{pricing_source}-legacy-row",
                "team_ids": set(),
            },
        )

        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["total_tokens"] += total_tokens
        bucket["total_cost_usd"] += total_cost_usd
        bucket["input_cost_usd"] += (prompt_tokens / 1_000_000) * input_rate
        bucket["output_cost_usd"] += (completion_tokens / 1_000_000) * output_rate
        bucket["team_ids"].add(team_id)

    result = []
    for bucket in by_model.values():
        result.append(
            {
                "model": bucket["model"],
                "prompt_tokens": int(bucket["prompt_tokens"]),
                "completion_tokens": int(bucket["completion_tokens"]),
                "total_tokens": int(bucket["total_tokens"]),
                "input_cost_usd": round(float(bucket["input_cost_usd"]), 6),
                "output_cost_usd": round(float(bucket["output_cost_usd"]), 6),
                "total_cost_usd": round(float(bucket["total_cost_usd"]), 6),
                "teams_analyzed": len(bucket["team_ids"]),
                "input_price_per_1m": float(bucket["input_price_per_1m"]),
                "output_price_per_1m": float(bucket["output_price_per_1m"]),
                "pricing_source": bucket["pricing_source"],
            }
        )

    result.sort(key=lambda item: item["total_cost_usd"], reverse=True)
    return result


@router.get("/summary")
async def get_token_usage_summary(
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    days: Optional[int] = Query(30, description="Number of days to look back"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get token usage summary.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Build query
    query = supabase.table("teams").select(
        "id, team_name, batch_id, openai_prompt_tokens, openai_completion_tokens, "
        "openai_total_tokens, openai_cost_usd, last_analyzed_at, report_path, report_json"
    ).gte("last_analyzed_at", start_date.isoformat())
    
    if batch_id:
        query = query.eq("batch_id", batch_id)
    
    response = query.execute()
    teams = response.data or []
    
    # Calculate totals
    total_prompt_tokens = sum(t.get("openai_prompt_tokens", 0) or 0 for t in teams)
    total_completion_tokens = sum(t.get("openai_completion_tokens", 0) or 0 for t in teams)
    total_tokens = sum(t.get("openai_total_tokens", 0) or 0 for t in teams)
    total_cost = sum(float(t.get("openai_cost_usd", 0) or 0) for t in teams)
    
    # Calculate averages
    analyzed_count = len(teams)
    avg_tokens_per_analysis = total_tokens / analyzed_count if analyzed_count > 0 else 0
    avg_cost_per_analysis = total_cost / analyzed_count if analyzed_count > 0 else 0

    model_breakdown = _build_model_breakdown(teams, allow_storage=False)
    non_token_api_calls = _build_non_token_call_summary(teams, allow_storage=False)
    if len(model_breakdown) == 1:
        pricing = {
            "model": model_breakdown[0]["model"],
            "input_price_per_1m": model_breakdown[0]["input_price_per_1m"],
            "output_price_per_1m": model_breakdown[0]["output_price_per_1m"],
            "currency": "USD",
            "mode": "single-model",
        }
    else:
        pricing = {
            "model": "multiple",
            "input_price_per_1m": 0,
            "output_price_per_1m": 0,
            "currency": "USD",
            "mode": "multi-model",
        }
    
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": days
        },
        "totals": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "teams_analyzed": analyzed_count
        },
        "averages": {
            "tokens_per_analysis": round(avg_tokens_per_analysis, 2),
            "cost_per_analysis_usd": round(avg_cost_per_analysis, 6)
        },
        "pricing": pricing,
        "model_breakdown": model_breakdown,
        "active_models": [model["model"] for model in model_breakdown],
        "non_token_api_calls": non_token_api_calls,
        "teams": [
            {
                "team_id": t["id"],
                "team_name": t["team_name"],
                "batch_id": t["batch_id"],
                "tokens": t.get("openai_total_tokens", 0) or 0,
                "cost_usd": float(t.get("openai_cost_usd", 0) or 0),
                "analyzed_at": t.get("last_analyzed_at"),
                "models_used": _extract_models_used(_extract_token_usage_payload(t, allow_storage=False)) or [_get_runtime_default_model()],
                "non_token_api_calls": _extract_api_call_tracking_payload(t, allow_storage=False),
            }
            for t in teams
        ]
    }


@router.get("/batch/{batch_id}")
async def get_batch_token_usage(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get token usage for a specific batch.
    Admin only.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    supabase = get_supabase()
    
    # Get batch info
    batch_response = supabase.table("batches").select("*").eq("id", batch_id).execute()
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_response.data[0]
    
    # Get teams in batch with token usage
    teams_response = supabase.table("teams").select(
        "id, team_name, openai_prompt_tokens, openai_completion_tokens, "
        "openai_total_tokens, openai_cost_usd, last_analyzed_at"
    ).eq("batch_id", batch_id).execute()
    
    teams = teams_response.data or []
    
    # Calculate totals
    total_tokens = sum(t.get("openai_total_tokens", 0) or 0 for t in teams)
    total_cost = sum(float(t.get("openai_cost_usd", 0) or 0) for t in teams)
    analyzed_count = len(teams)
    model_breakdown = _build_model_breakdown(teams, allow_storage=False)
    non_token_api_calls = _build_non_token_call_summary(teams, allow_storage=False)
    
    return {
        "batch_id": batch_id,
        "batch_name": batch["name"],
        "total_teams": len(teams),
        "teams_analyzed": analyzed_count,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "avg_tokens_per_team": round(total_tokens / analyzed_count, 2) if analyzed_count > 0 else 0,
        "avg_cost_per_team_usd": round(total_cost / analyzed_count, 6) if analyzed_count > 0 else 0,
        "model_breakdown": model_breakdown,
        "active_models": [model["model"] for model in model_breakdown],
        "non_token_api_calls": non_token_api_calls,
        "teams": [
            {
                "team_id": t["id"],
                "team_name": t["team_name"],
                "tokens": t.get("openai_total_tokens", 0),
                "cost_usd": float(t.get("openai_cost_usd", 0) or 0),
                "analyzed_at": t.get("last_analyzed_at"),
                "models_used": _extract_models_used(_extract_token_usage_payload(t, allow_storage=False)) or [_get_runtime_default_model()],
                "non_token_api_calls": _extract_api_call_tracking_payload(t, allow_storage=False),
            }
            for t in teams
        ]
    }


@router.get("/team/{team_id}")
async def get_team_token_usage(
    team_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get token usage for a specific team.
    Admin or assigned mentor only.
    """
    supabase = get_supabase()
    
    # Get team data
    team_response = supabase.table("teams").select(
        "id, team_name, batch_id, mentor_id, openai_prompt_tokens, openai_completion_tokens, "
        "openai_total_tokens, openai_cost_usd, last_analyzed_at, report_json"
    ).eq("id", team_id).execute()
    
    if not team_response.data:
        raise HTTPException(status_code=404, detail="Team not found")
    
    team = team_response.data[0]
    
    # Check authorization
    role = current_user.role
    user_id = str(current_user.user_id)
    
    if role != "admin" and team.get("mentor_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied. You can only view token usage for teams assigned to you."
        )
    
    # Calculate cost breakdown
    prompt_tokens = team.get("openai_prompt_tokens", 0) or 0
    completion_tokens = team.get("openai_completion_tokens", 0) or 0

    token_usage = _extract_token_usage_payload(team)
    model_breakdown = _build_model_breakdown([team])
    has_model_breakdown = bool(model_breakdown)

    if has_model_breakdown and len(model_breakdown) == 1:
        pricing = {
            "model": model_breakdown[0]["model"],
            "input_price_per_1m": model_breakdown[0]["input_price_per_1m"],
            "output_price_per_1m": model_breakdown[0]["output_price_per_1m"],
            "currency": "USD",
            "mode": "single-model",
        }
    elif has_model_breakdown:
        pricing = {
            "model": "multiple",
            "input_price_per_1m": 0,
            "output_price_per_1m": 0,
            "currency": "USD",
            "mode": "multi-model",
        }
    else:
        fallback_model, input_rate, output_rate, _ = _get_model_pricing(token_usage.get("model"))
        pricing = {
            "model": fallback_model,
            "input_price_per_1m": input_rate,
            "output_price_per_1m": output_rate,
            "currency": "USD",
            "mode": "single-model",
        }

    input_cost = _safe_float(token_usage.get("input_cost_usd"))
    output_cost = _safe_float(token_usage.get("output_cost_usd"))
    if input_cost == 0 and output_cost == 0:
        input_rate = pricing.get("input_price_per_1m", 0)
        output_rate = pricing.get("output_price_per_1m", 0)
        input_cost = (prompt_tokens / 1_000_000) * input_rate
        output_cost = (completion_tokens / 1_000_000) * output_rate
    
    return {
        "team_id": team["id"],
        "team_name": team["team_name"],
        "batch_id": team["batch_id"],
        "analyzed_at": team.get("last_analyzed_at"),
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": team.get("openai_total_tokens", 0) or 0
        },
        "cost_breakdown": {
            "input_cost_usd": round(input_cost, 6),
            "output_cost_usd": round(output_cost, 6),
            "total_cost_usd": float(team.get("openai_cost_usd", 0) or 0)
        },
        "pricing": pricing,
        "model_breakdown": model_breakdown,
        "models_used": _extract_models_used(token_usage),
        "non_token_api_calls": _extract_api_call_tracking_payload(team),
    }
