import os
import re
import json
from typing import Any
from openai import OpenAI
from src.utils.repo_summary import generate_repo_summary


DEFAULT_MODEL_PRICING_USD_PER_1M = {
    # Legacy baseline (existing implementation)
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    # New integrated evaluator models (override via OPENAI_MODEL_PRICING_JSON when needed)
    "gpt-5.4-nano": {"input": 0.050, "output": 0.400},
    "gpt-5-mini": {"input": 0.250, "output": 2.000},
}


def _normalize_model_name(model_name: Any) -> str:
    return str(model_name or "").strip().lower()


def _model_env_key(model_name: str) -> str:
    sanitized = re.sub(r"[^a-z0-9]+", "_", model_name.lower()).strip("_")
    return sanitized.upper()


def _get_env_float(var_name: str) -> float | None:
    raw = os.getenv(var_name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        print(f"      ⚠️ Invalid pricing env value for {var_name}: {raw}")
        return None


def _get_env_model_pricing(model_name: str) -> tuple[float, float] | None:
    """Resolve per-model pricing from env vars without code changes.

    Supported env formats:
    - OPENAI_MODEL_<MODEL_KEY>_INPUT_PRICE_PER_1M
    - OPENAI_MODEL_<MODEL_KEY>_OUTPUT_PRICE_PER_1M
    where MODEL_KEY is model name uppercased with non-alnum replaced by underscores.
    """
    model_key = _model_env_key(model_name)
    input_rate = _get_env_float(f"OPENAI_MODEL_{model_key}_INPUT_PRICE_PER_1M")
    output_rate = _get_env_float(f"OPENAI_MODEL_{model_key}_OUTPUT_PRICE_PER_1M")
    if input_rate is None or output_rate is None:
        return None
    return input_rate, output_rate


def _get_env_default_pricing() -> tuple[float, float] | None:
    """Resolve global fallback pricing from env vars.

    Priority:
    1. OPENAI_PRODUCT_EVALUATION_INPUT_PRICE_PER_1M / OPENAI_PRODUCT_EVALUATION_OUTPUT_PRICE_PER_1M
    2. OPENAI_DEFAULT_INPUT_PRICE_PER_1M / OPENAI_DEFAULT_OUTPUT_PRICE_PER_1M
    """
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
    """Load optional model pricing overrides from JSON env var.

    Env format:
    OPENAI_MODEL_PRICING_JSON={"gpt-5-mini-2025-08-07":{"input":0.25,"output":2.0}}
    """
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
    except Exception as exc:
        print(
            "      ⚠️ Failed to parse OPENAI_MODEL_PRICING_JSON; "
            f"using default pricing catalog. Error: {exc}"
        )
        return {}


def _get_model_pricing(model_name: Any) -> tuple[str, float, float, str]:
    """Resolve pricing for a model.

    Returns (pricing_key, input_rate, output_rate, source).
    """
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


OPTIONAL_SECURITY_TERMS = {
    "rate limit",
    "rate limiting",
    "waf",
    "web application firewall",
    "ddos",
    "security headers",
    "owasp",
    "csrf",
    "xss",
    "sql injection",
    "advanced security",
}


def _contains_optional_security_topic(value: Any) -> bool:
    """Check whether a value text references optional advanced security controls."""
    text = str(value).lower()
    return any(term in text for term in OPTIONAL_SECURITY_TERMS)


def _filter_optional_security_list(items: Any) -> Any:
    """Filter out list entries that mention optional advanced security controls."""
    if not isinstance(items, list):
        return items
    return [item for item in items if not _contains_optional_security_topic(item)]


def _sanitize_optional_security_text(text: Any) -> Any:
    """Remove optional-security sentences from freeform text fields."""
    if not isinstance(text, str):
        return text

    segments = [segment.strip() for segment in text.replace("\n", ". ").split(".")]
    kept = [segment for segment in segments if segment and not _contains_optional_security_topic(segment)]
    return ". ".join(kept)


def _sanitize_optional_security_mentions(report: dict) -> dict:
    """Strip optional security controls from report content to avoid reflecting them."""
    report["features"] = _filter_optional_security_list(report.get("features"))

    completeness = report.get("completeness_analysis") or {}
    completeness["missing_critical_features"] = _filter_optional_security_list(
        completeness.get("missing_critical_features")
    )
    report["completeness_analysis"] = completeness

    suggested_features = report.get("suggested_features")
    if isinstance(suggested_features, list):
        report["suggested_features"] = [
            item for item in suggested_features
            if not _contains_optional_security_topic(json.dumps(item, ensure_ascii=True))
        ]

    feature_analysis = report.get("feature_analysis")
    if isinstance(feature_analysis, list):
        report["feature_analysis"] = [
            item for item in feature_analysis
            if not _contains_optional_security_topic(json.dumps(item, ensure_ascii=True))
        ]

    for key in ("positive_feedback", "constructive_feedback", "overall_recommendation", "verdict_reasoning"):
        if key in report:
            report[key] = _sanitize_optional_security_text(report.get(key))

    part_reports = report.get("part_reports")
    if isinstance(part_reports, dict):
        for part_name, part_data in part_reports.items():
            if not isinstance(part_data, dict):
                continue
            part_data["features"] = _filter_optional_security_list(part_data.get("features"))
            part_data["missing_critical_features"] = _filter_optional_security_list(
                part_data.get("missing_critical_features")
            )
            part_data["key_evidence"] = _filter_optional_security_list(part_data.get("key_evidence"))
            if "positive_feedback" in part_data:
                part_data["positive_feedback"] = _sanitize_optional_security_text(part_data.get("positive_feedback"))
            if "constructive_feedback" in part_data:
                part_data["constructive_feedback"] = _sanitize_optional_security_text(part_data.get("constructive_feedback"))
            part_reports[part_name] = part_data
        report["part_reports"] = part_reports

    return report


def _project_requires_strict_security(project_statement: str | None) -> bool:
    """Return True when the project statement explicitly centers security use-cases."""
    if not project_statement:
        return False
    text = project_statement.lower()
    security_intent_terms = [
        "security",
        "cyber",
        "vulnerability",
        "penetration",
        "compliance",
        "soc",
        "siem",
        "threat detection",
        "fraud detection",
    ]
    return any(term in text for term in security_intent_terms)


def _to_number(value: Any) -> float | None:
    """Convert score-like values to float when possible."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


PROJECT_ARCHETYPES = (
    "chrome_extension",
    "web_app",
    "mobile_app",
    "backend_api",
    "ml_ai_pipeline",
    "iot_embedded",
    "cli_tool",
    "desktop_app",
    "game",
    "unknown",
)


def _normalize_project_statement(value: Any) -> str | None:
    """Normalize freeform project statement text."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return re.sub(r"\s+", " ", text)


def _score_project_archetypes(project_statement: str | None, context: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Score likely project archetypes using project statement and repo summary evidence."""
    stmt = (project_statement or "").lower()
    ctx = (context or "").lower()
    combined = f"{stmt}\n{ctx}"

    scores = {name: 0 for name in PROJECT_ARCHETYPES if name != "unknown"}
    evidence: dict[str, list[str]] = {name: [] for name in scores.keys()}

    def hit(archetype: str, patterns: list[str], weight: int, label: str):
        matched = [pattern for pattern in patterns if pattern in combined]
        if not matched:
            return
        scores[archetype] += weight
        evidence[archetype].append(f"{label}: {', '.join(matched[:3])}")

    hit(
        "chrome_extension",
        [
            "chrome extension",
            "browser extension",
            "manifest_version",
            "chrome.runtime",
            "background.js",
            "content_scripts",
            "web_accessible_resources",
        ],
        4,
        "extension markers",
    )
    hit(
        "mobile_app",
        [
            "react native",
            "flutter",
            "androidmanifest.xml",
            "build.gradle",
            "ios/",
            ".xcodeproj",
            "swiftui",
            "kotlin",
        ],
        3,
        "mobile markers",
    )
    hit(
        "backend_api",
        [
            "fastapi",
            "flask",
            "django",
            "express",
            "nestjs",
            "spring",
            "api endpoint",
            "swagger",
            "openapi",
            "router",
            "controller",
        ],
        3,
        "backend markers",
    )
    hit(
        "ml_ai_pipeline",
        [
            "machine learning",
            "deep learning",
            "pytorch",
            "tensorflow",
            "scikit",
            "notebook",
            "inference",
            "model.pkl",
            "huggingface",
            "training pipeline",
        ],
        3,
        "ml markers",
    )
    hit(
        "iot_embedded",
        [
            "iot",
            "firmware",
            "esp32",
            "arduino",
            "raspberry pi",
            "mqtt",
            "sensor",
            "microcontroller",
            "embedded",
        ],
        3,
        "iot markers",
    )
    hit(
        "cli_tool",
        [
            "cli tool",
            "command line",
            "argparse",
            "click",
            "typer",
            "commander",
            "yargs",
            "cobra",
            "--help",
            "-h",
            "clap",
            "optparse",
            "readline",
            "stdin",
            "stdout",
            "stderr",
        ],
        3,
        "cli markers",
    )
    hit(
        "desktop_app",
        [
            "desktop app",
            "electron",
            "tkinter",
            "pyqt",
            "pyside",
            "wxpython",
            "javafx",
            "swing",
            "wpf",
            "winforms",
            "tauri",
        ],
        3,
        "desktop markers",
    )
    hit(
        "game",
        [
            "game",
            "pygame",
            "unity",
            "unreal engine",
            "godot",
            "phaser",
            "canvas game",
            "sprite",
            "raylib",
            "three.js",
        ],
        3,
        "game markers",
    )
    hit(
        "web_app",
        [
            "web app",
            "frontend",
            "next.js",
            "react",
            "vue",
            "angular",
            "svelte",
            "vite",
            "tailwind",
            "client/src",
            "index.html",
        ],
        2,
        "web markers",
    )

    # Bias archetype from explicit statement wording when present.
    if stmt:
        if "extension" in stmt:
            scores["chrome_extension"] += 3
            evidence["chrome_extension"].append("statement intent: extension")
        if "mobile" in stmt or "android" in stmt or "ios" in stmt:
            scores["mobile_app"] += 2
            evidence["mobile_app"].append("statement intent: mobile")
        if "api" in stmt or "backend" in stmt:
            scores["backend_api"] += 2
            evidence["backend_api"].append("statement intent: api/backend")
        if "iot" in stmt or "sensor" in stmt:
            scores["iot_embedded"] += 2
            evidence["iot_embedded"].append("statement intent: iot")
        if "ml" in stmt or "ai" in stmt or "model" in stmt:
            scores["ml_ai_pipeline"] += 2
            evidence["ml_ai_pipeline"].append("statement intent: ml/ai")
        if "cli" in stmt or "command line" in stmt:
            scores["cli_tool"] += 2
            evidence["cli_tool"].append("statement intent: cli")
        if "desktop" in stmt or "electron" in stmt:
            scores["desktop_app"] += 2
            evidence["desktop_app"].append("statement intent: desktop")
        if "game" in stmt or "pygame" in stmt or "unity" in stmt:
            scores["game"] += 2
            evidence["game"].append("statement intent: game")

    return scores, evidence


def infer_project_profile(project_statement: str | None, context: str, manual_archetype: str | None = None) -> dict[str, Any]:
    """Infer project archetype and context confidence from statement + repo evidence."""
    normalized_statement = _normalize_project_statement(project_statement)
    scores, evidence = _score_project_archetypes(normalized_statement, context)
    best_archetype = max(scores.items(), key=lambda item: item[1])[0] if scores else "unknown"
    best_score = scores.get(best_archetype, 0)

    # If no strong evidence exists, keep unknown to avoid misleading specialization.
    if best_score <= 1:
        best_archetype = "unknown"

    if best_score >= 8:
        confidence = "high"
    elif best_score >= 4:
        confidence = "medium"
    else:
        confidence = "low"

    if normalized_statement and context.strip():
        source = "statement_and_repo_summary"
    elif normalized_statement:
        source = "statement_only"
    elif context.strip():
        source = "repo_summary_only"
    else:
        source = "none"

    if manual_archetype and manual_archetype in PROJECT_ARCHETYPES:
        best_archetype = manual_archetype
        confidence = "high"
        source = "manual_override"
        if manual_archetype not in evidence:
            evidence[manual_archetype] = []
        evidence[manual_archetype].append("manual override by admin")

    context_quality = "strong" if normalized_statement else "weak"
    if source == "none":
        context_quality = "missing"

    warning = None
    if context_quality != "strong" and not manual_archetype:
        warning = (
            "Project statement is missing or weak; evaluator used repository signals to infer project type. "
            "Some feedback may still be partially generic."
        )

    return {
        "archetype": best_archetype,
        "confidence": confidence,
        "source": source,
        "context_quality": context_quality,
        "evidence": evidence.get(best_archetype, []),
        "warning": warning,
        "score_map": scores,
    }


def _project_archetype_applicability_rules(archetype: str) -> str:
    """Return archetype-specific applicability rules to reduce generic suggestions."""
    rules = {
        "chrome_extension": (
            "- Prioritize extension-specific behavior (manifest, background/service worker, content scripts, permissions).\n"
            "- Avoid mobile-app-only guidance unless repo evidence clearly shows mobile targets.\n"
            "- Do not require backend infrastructure unless extension features actually depend on it."
        ),
        "mobile_app": (
            "- Prioritize mobile UX flows, platform integration, offline/state handling, and device constraints.\n"
            "- Avoid browser-extension-only guidance unless explicit repo evidence exists.\n"
            "- Do not require web-only SEO/browser concerns for native-only mobile projects."
        ),
        "backend_api": (
            "- Prioritize API contract quality, business logic correctness, data model integrity, and observability.\n"
            "- Avoid frontend-polish suggestions unless a frontend exists in repo evidence.\n"
            "- Keep recommendations focused on backend runtime behavior and reliability."
        ),
        "ml_ai_pipeline": (
            "- Prioritize data pipeline quality, model lifecycle, evaluation metrics, inference robustness, and reproducibility.\n"
            "- Avoid generic CRUD/web-UI expectations unless clearly in scope.\n"
            "- Evaluate whether model integration supports stated problem outcomes."
        ),
        "iot_embedded": (
            "- Prioritize device/firmware integration, telemetry reliability, hardware interaction, and fail-safe handling.\n"
            "- Avoid web-only/mobile-only assumptions unless repo evidence confirms those surfaces.\n"
            "- Emphasize operational behavior in constrained or intermittent environments."
        ),
        "cli_tool": (
            "- Prioritize command line usability, option parsing correctness, standard input/output/error conventions, and performance.\n"
            "- Avoid frontend/browser suggestions or web-hosting/deployment comments unless explicitly requested.\n"
            "- Do not require a backend database or external HTTP API endpoints unless CLI options clearly show dependency on remote services."
        ),
        "desktop_app": (
            "- Prioritize desktop packaging, application lifecycle management, OS integration, local file access, and UI responsiveness.\n"
            "- Avoid web-only routing/SEO suggestions or mobile-specific telemetry suggestions.\n"
            "- Do not require global web hosting or full-stack cloud databases unless explicitly stated."
        ),
        "game": (
            "- Prioritize game loop performance, asset loading, user input/controls, sound/rendering efficiency, and core gameplay mechanics.\n"
            "- Avoid standard business enterprise patterns or typical CRUD/database suggestions.\n"
            "- Do not require responsive web UI layouts or form-based validation guidelines unless evaluating game menus/forms."
        ),
        "web_app": (
            "- Prioritize user journeys, frontend-backend integration, validation/error handling, and deployment readiness.\n"
            "- Avoid extension-only or firmware-only guidance unless explicitly evidenced.\n"
            "- Keep suggestions tied to observed web architecture and implemented flows."
        ),
        "unknown": (
            "- If project type is unclear, infer conservatively from concrete evidence.\n"
            "- Avoid assumptions; mark low-confidence recommendations explicitly.\n"
            "- Prioritize broadly applicable, evidence-backed improvements only."
        ),
    }
    return rules.get(archetype, rules["unknown"])


def _apply_optional_security_policy(report: dict, project_statement: str | None) -> dict:
    """Do not enforce advanced security as critical unless project is security-focused."""
    if _project_requires_strict_security(project_statement):
        return report

    # Reward bonus when advanced security is present.
    quality = report.get("quality_indicators") or {}
    has_security_measures = quality.get("has_security_measures") is True
    if has_security_measures:
        base_score = _to_number(report.get("implementation_score"))
        if base_score is not None:
            report["implementation_score"] = max(0, min(100, round(base_score + 3)))

    # Do not reflect optional security controls in non-security project reports.
    report = _sanitize_optional_security_mentions(report)
    quality["has_security_measures"] = False
    report["quality_indicators"] = quality
    report.pop("security_bonus_applied", None)

    return report


def _apply_project_statement_alignment_policy(report: dict, project_statement: str | None) -> dict:
    """Blend implementation score with PS alignment when a project statement exists."""
    if not project_statement:
        return report

    ps_alignment = report.get("ps_alignment") or {}
    if not isinstance(ps_alignment, dict):
        return report

    implementation_score = _to_number(report.get("implementation_score"))
    alignment_score = _to_number(ps_alignment.get("alignment_score"))
    if implementation_score is None or alignment_score is None:
        return report

    # Give repo evidence primacy while forcing explicit PS alignment impact.
    blended_score = max(0, min(100, round((implementation_score * 0.7) + (alignment_score * 0.3))))
    report["implementation_score"] = blended_score

    report["ps_alignment_applied"] = {
        "model_implementation_score": implementation_score,
        "project_statement_alignment_score": alignment_score,
        "blended_implementation_score": blended_score,
        "weights": {
            "implementation_score": 0.7,
            "project_statement_alignment_score": 0.3,
        },
    }

    return report


def _get_evaluator_model() -> str:
    """Return configured model for product evaluation with a larger-context default."""
    return os.getenv("OPENAI_PRODUCT_EVALUATION_MODEL", "gpt-4o-mini")


def _get_evaluator_fallback_model() -> str:
    """Return fallback model used when primary model exceeds context length."""
    return os.getenv("OPENAI_PRODUCT_EVALUATION_FALLBACK_MODEL", "gpt-5-mini-2025-08-07")


def _get_evaluator_temperature() -> float | None:
    """Return temperature for evaluator model calls.

    Defaults to 0.0 for deterministic scoring unless explicitly overridden.
    """
    raw_temperature = os.getenv("OPENAI_PRODUCT_EVALUATION_TEMPERATURE")
    if raw_temperature is None or raw_temperature.strip() == "":
        return 0.0

    try:
        parsed = float(raw_temperature)
        if parsed < 0.0 or parsed > 2.0:
            raise ValueError("out of supported range")
        return parsed
    except ValueError:
        print(
            "      ⚠️ Invalid OPENAI_PRODUCT_EVALUATION_TEMPERATURE "
            f"'{raw_temperature}', using deterministic default 0.0."
        )
        return 0.0


def _stabilize_implementation_score(report: dict) -> dict:
    """Reduce one-run implementation score spikes/drops from synthesis variance.

    The synthesis call can occasionally return a score far from both part-level
    evaluators. When that happens, use a blended value biased toward part evidence.
    """
    if not isinstance(report, dict):
        return report

    part_reports = report.get("part_reports")
    if not isinstance(part_reports, dict):
        return report

    frontend = part_reports.get("frontend") if isinstance(part_reports.get("frontend"), dict) else {}
    backend = part_reports.get("backend") if isinstance(part_reports.get("backend"), dict) else {}

    synth_score = _to_number(report.get("implementation_score"))
    frontend_score = _to_number(frontend.get("implementation_score"))
    backend_score = _to_number(backend.get("implementation_score"))

    part_scores = [score for score in (frontend_score, backend_score) if score is not None]
    if synth_score is None or not part_scores:
        return report

    part_average = sum(part_scores) / len(part_scores)
    delta = abs(synth_score - part_average)

    # Guardrail: dampen only significant outliers to preserve genuine shifts.
    if delta > 25.0:
        stabilized = round((part_average * 0.6) + (synth_score * 0.4))
        report["implementation_score"] = max(0, min(100, stabilized))
        report["implementation_score_stability"] = {
            "synthesis_score": round(synth_score, 2),
            "frontend_score": frontend_score,
            "backend_score": backend_score,
            "parts_average": round(part_average, 2),
            "stabilized_score": report["implementation_score"],
            "reason": "large_synthesis_outlier",
        }

    return report


def _is_temperature_unsupported_error(exc: Exception) -> bool:
    """Detect temperature incompatibility errors returned by model endpoints."""
    msg = str(exc).lower()
    if "temperature" not in msg:
        return False
    return (
        "unsupported value" in msg
        or "does not support" in msg
        or "only the default" in msg
    )


def _is_context_length_exceeded_error(exc: Exception) -> bool:
    """Detect context-length overflow errors returned by model endpoints."""
    msg = str(exc).lower()
    return "context_length_exceeded" in msg or "input tokens exceed" in msg


def _get_evaluator_max_context_chars() -> int:
    """Return max characters allowed for codebase context in evaluator prompt."""
    default_max_chars = 200000
    raw = os.getenv("OPENAI_PRODUCT_EVALUATION_MAX_CONTEXT_CHARS")
    if raw is None or raw.strip() == "":
        return default_max_chars

    try:
        value = int(raw)
        if value < 10000:
            raise ValueError("too small")
        return value
    except Exception:
        print(
            "      ⚠️ Invalid OPENAI_PRODUCT_EVALUATION_MAX_CONTEXT_CHARS "
            f"'{raw}', using default {default_max_chars}."
        )
        return default_max_chars


def _truncate_context(context: str, max_chars: int) -> str:
    """Trim very large context while preserving evidence from across the text."""
    if len(context) <= max_chars:
        return context

    marker = "\n\n[... CODEBASE CONTEXT TRUNCATED DUE TO SIZE ...]\n\n"
    if max_chars <= len(marker) + 200:
        return context[:max_chars]

    segment_count = 5
    segment_budget = max_chars - (segment_count - 1) * len(marker)
    segment_len = max(50, segment_budget // segment_count)
    max_start = max(0, len(context) - segment_len)

    segments = []
    for i in range(segment_count):
        if segment_count == 1:
            start = 0
        else:
            start = int((max_start * i) / (segment_count - 1))
        segments.append(context[start:start + segment_len])

    truncated = marker.join(segments)
    if len(truncated) > max_chars:
        truncated = truncated[:max_chars]
    return truncated


def _split_summary_sections(summary: str) -> dict[str, str]:
    """Split generated summary text into named sections."""
    sections: dict[str, list[str]] = {}
    current = "GENERAL"
    sections[current] = []

    for line in summary.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)

    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _compose_part_context(sections: dict[str, str], part: str, max_chars: int) -> str:
    """Build a focused context slice for frontend/backend analysis."""
    if part not in {"frontend", "backend"}:
        raise ValueError(f"Unsupported part: {part}")

    selected_names = ["DIRECTORY STRUCTURE", "CONFIGURATION FILES"]
    if part == "frontend":
        selected_names.extend(["FRONTEND IMPLEMENTATION", "CORE BUSINESS LOGIC"])
    else:
        selected_names.extend(["DATABASE SCHEMAS", "BACKEND/API IMPLEMENTATION", "CORE BUSINESS LOGIC"])

    blocks = []
    for name in selected_names:
        section = sections.get(name)
        if section:
            blocks.append(f"=== {name} ===\n{section}")

    context = "\n\n".join(blocks).strip()
    if not context:
        context = sections.get("GENERAL", "")

    return _truncate_context(context, max_chars)


def _build_part_prompt(
    part: str,
    part_context: str,
    project_statement: str | None,
    project_profile: dict[str, Any],
) -> str:
    """Build per-part evaluator prompt with compact schema."""
    part_title = "Frontend" if part == "frontend" else "Backend"
    archetype = project_profile.get("archetype", "unknown")
    confidence = project_profile.get("confidence", "low")
    evidence = project_profile.get("evidence", [])
    applicability_rules = _project_archetype_applicability_rules(archetype)
    profile_block = (
        "Project profile guidance:\n"
        f"- Project archetype: {archetype}\n"
        f"- Inference confidence: {confidence}\n"
        f"- Evidence signals: {', '.join(evidence[:3]) if evidence else 'none'}\n"
        f"{applicability_rules}\n"
    )

    return f"""You are a Senior {part_title} Reviewer evaluating only the {part_title.upper()} side of a hackathon codebase.

{'' if not project_statement else f'Project statement: "{project_statement}"\nEvaluate against this goal.\n'}
{profile_block}
Return VALID JSON only (no markdown) using this schema:
{{
  "part": "{part}",
  "project_name": "inferred project name",
  "summary": "2-4 sentence summary of this part",
  "tech_stack_observed": ["list"],
  "features": ["list"],
  "implementation_score": 0,
        "project_statement_coverage": {{
            "aligned_requirements": ["requirements from PS that are implemented in this part"],
            "missing_requirements": ["requirements from PS that are missing in this part"],
            "alignment_score": 0
        }},
  "status": "Working | Partial | Broken",
  "key_evidence": ["specific file/function evidence"],
  "missing_critical_features": ["list"],
  "positive_feedback": "2-4 sentences",
  "constructive_feedback": "2-4 sentences"
}}

Guidelines:
- Be evidence-driven and strict.
- Focus on functionality over style.
- Mention concrete evidence in key_evidence.
    - Treat the project statement as the primary rubric. Features outside PS should be mentioned but must not dominate scoring.
    - For every aligned/missing requirement, reference concrete repo evidence where possible.
- If the project statement indicates this codebase is part of a multi-repository system or specialized, do not penalize it for missing components that belong in other repositories (e.g., missing frontend in a backend repo). Evaluate only what is present.
- If the project is classified under a specialized archetype like 'cli_tool', 'backend_api', 'ml_ai_pipeline', 'iot_embedded', 'desktop_app', or 'game', DO NOT penalize it for lacking standard full-stack web elements (e.g., do not penalize a CLI tool or backend-only API for lacking a browser-based frontend UI, web styling, HTML/CSS, or browser/mobile client features). Evaluate only elements relevant to the stack of the inferred archetype.
- Do NOT treat advanced security controls (rate limiting, WAF, DDoS hardening, OWASP hardening) as critical missing features unless the project statement explicitly demands security/compliance outcomes.
- For non-security projects, do not include optional security controls in missing_critical_features, suggested_features, or narrative feedback.

CODEBASE CONTEXT ({part_title.upper()}):
{part_context}"""


def _build_synthesis_prompt(
    frontend_report: dict,
    backend_report: dict,
    project_statement: str | None,
    project_profile: dict[str, Any],
) -> str:
    """Build synthesis prompt that returns legacy final product schema."""
    archetype = project_profile.get("archetype", "unknown")
    confidence = project_profile.get("confidence", "low")
    evidence = project_profile.get("evidence", [])
    applicability_rules = _project_archetype_applicability_rules(archetype)

    return f"""You are a Senior CTO synthesizing frontend and backend evaluations into ONE final product judgment.

{'' if not project_statement else f'Project statement: "{project_statement}"\n'}
Project profile guidance:
- Project archetype: {archetype}
- Inference confidence: {confidence}
- Evidence signals: {', '.join(evidence[:3]) if evidence else 'none'}
{applicability_rules}

Return VALID JSON only using this exact schema:
{{
    "project_name": "inferred name from codebase",
    "description": "2-3 sentence summary of what this product does and its core purpose",
    "features": ["list", "of", "all", "features", "you", "can", "identify"],
    "tech_stack_observed": ["all", "frameworks", "libraries", "tools", "detected"],
    "implementation_score": 0,
        "ps_alignment": {{
            "aligned_requirements": ["specific PS requirements that are implemented"],
            "missing_requirements": ["specific PS requirements not implemented"],
            "scope_deviations": ["major implemented items that are outside PS scope"],
            "alignment_score": 0,
            "alignment_reasoning": "2-4 sentence explanation grounded in repo evidence"
        }},

    "functionality_check": {{
        "has_working_backend": true,
        "has_working_frontend": true,
        "has_database_integration": false,
        "has_api_endpoints": false,
        "has_authentication": false,
        "has_business_logic": false,
        "has_error_handling": false,
        "has_input_validation": false,
        "deployment_ready": false,
        "can_run_locally": false
    }},

    "completeness_analysis": {{
        "core_features_complete": "percentage estimate (0-100)",
        "ui_polish_level": "None / Basic / Good / Professional",
        "code_organization": "Poor / Fair / Good / Excellent",
        "documentation_quality": "None / Minimal / Basic / Good / Comprehensive",
        "test_coverage": "None / Minimal / Moderate / Good / Extensive",
        "missing_critical_features": ["list"],
        "technical_debt": "Low / Moderate / High / Critical"
    }},

    "feature_analysis": [
        {{
            "feature_name": "Specific feature name",
            "status": "Fully Implemented / Partially Implemented / Stub Only / Missing",
            "whats_working": "Detailed description of what actually works",
            "improvements_needed": "Specific improvements that would help",
            "implementation_quality": "Excellent / Good / Average / Poor",
            "code_evidence": "Brief mention of files/functions that implement this"
        }}
    ],

    "product_analysis": {{
        "core_value_proposition": "What specific problem does this solve",
        "target_users": "Who would actually use this",
        "competitive_advantage": "What makes this unique or valuable",
        "market_readiness": "Production Ready / Beta Ready / Alpha / Concept Only",
        "usability_assessment": "How easy would this be for end users",
        "scalability_concerns": "Any architectural limitations for growth"
    }},

    "quality_indicators": {{
        "follows_best_practices": true,
        "has_proper_structure": true,
        "code_is_readable": true,
        "has_configuration_management": true,
        "has_logging": true,
        "has_security_measures": true,
        "readme_quality": "None / Poor / Basic / Good / Excellent"
    }},

    "suggested_features": [
        {{
            "feature_name": "Specific feature name",
            "priority": "Critical / High / Medium / Low",
            "reason": "Why this feature would add significant value",
            "implementation_hint": "Concrete suggestion on how to implement",
            "estimated_effort": "Low / Medium / High"
        }}
    ],

    "score_improvement_guide": {{
        "why_score_is_not_100": "Personalized, evidence-backed explanation of why the implementation score did not receive full marks, referencing specific missing parts or bugs.",
        "how_to_increase_score": [
            "Highly specific, actionable step tailored to this exact project to increase its score",
            "Another actionable, project-specific step"
        ]
    }},

    "positive_feedback": "Detailed, specific strengths (3-5 sentences)",
    "constructive_feedback": "Detailed, actionable improvements (3-5 sentences)",
    "verdict": "Production Ready / MVP / Prototype / Broken",
    "verdict_reasoning": "2-3 sentences explaining the verdict",
    "overall_recommendation": "2-3 sentences of final guidance"
}}

Synthesize from these part reports:
FRONTEND REPORT JSON:
{json.dumps(frontend_report, ensure_ascii=True)}

BACKEND REPORT JSON:
{json.dumps(backend_report, ensure_ascii=True)}

Policy notes:
- If the project statement indicates this codebase is part of a multi-repository system (Specialized part), DO NOT penalize it for missing frontend, missing backend, or lacking a full-stack deployment. Do NOT list the missing counterpart as a "missing_critical_feature". Evaluate it strictly on its own merits.
- CRITICAL: If one of the reports (FRONTEND or BACKEND) indicates that it found no code or functionality (e.g., implementation score 0, or missing), and the project is a multi-repo / specialized part, or classified under specialized archetypes like 'cli_tool', 'backend_api', 'ml_ai_pipeline', 'iot_embedded', 'desktop_app', or 'game', COMPLETELY IGNORE the empty report when calculating the final `implementation_score`, `ps_alignment.alignment_score`, and `completeness_analysis`. Do NOT average the scores. Base your entire final score and verdict solely on the report that actually examined the existing code.
- For specialized/non-web archetypes (like 'cli_tool', 'desktop_app', 'game', 'ml_ai_pipeline'), adjust the synthesis verdict and completeness metrics accordingly. For example, a CLI tool does not require web deployment readiness or a web UI polish level, so evaluate usability and code organization instead of UI polish.
- Do not enforce advanced security controls (rate limiting, WAF, DDoS protection, OWASP hardening) as mandatory for all projects.
- Mark them as critical only if project statement explicitly requires security/compliance goals.
- For non-security projects, avoid reflecting these controls in report text/feature lists.
- Project statement alignment is mandatory: score and verdict must primarily reflect fulfillment of the stated problem, not generic product quality.
- Recommendations and the score_improvement_guide must be highly personalized and applicable to the inferred project archetype. Avoid generic suggestions. Explain exactly what this specific project lacks and how to fix it."""


def _call_openai_json_with_retries(
    client: OpenAI,
    primary_model: str,
    fallback_model: str,
    system_msg: str,
    prompt: str,
    configured_temperature: float | None,
) -> tuple[dict, Any, str]:
    """Call OpenAI chat completion with temperature and model fallback resiliency."""
    request_payload: dict[str, Any] = {
        "model": primary_model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    if configured_temperature is not None:
        request_payload["temperature"] = configured_temperature

    candidate_models = [primary_model]
    if fallback_model and fallback_model != primary_model:
        candidate_models.append(fallback_model)

    response = None
    used_model = primary_model
    last_error = None

    for model_index, candidate_model in enumerate(candidate_models):
        attempt_payload = dict(request_payload)
        attempt_payload["model"] = candidate_model
        used_model = candidate_model

        while True:
            try:
                response = client.chat.completions.create(**attempt_payload)
                break
            except Exception as request_error:
                last_error = request_error
                if "temperature" in attempt_payload and _is_temperature_unsupported_error(request_error):
                    print(
                        f"      ⚠️ Model {candidate_model} rejected custom temperature; "
                        "retrying with endpoint default temperature."
                    )
                    attempt_payload.pop("temperature", None)
                    continue

                if _is_context_length_exceeded_error(request_error):
                    has_next_model = model_index < len(candidate_models) - 1
                    if has_next_model:
                        print(
                            f"      ⚠️ Context length exceeded on {candidate_model}; "
                            f"retrying with fallback model {candidate_models[model_index + 1]}."
                        )
                        break

                raise

        if response is not None:
            break

    if response is None and last_error is not None:
        raise last_error

    content = response.choices[0].message.content or "{}"
    return json.loads(content), response.usage, getattr(response, "model", used_model)

def evaluate_product_logic(
    repo_path: str,
    api_key: str = None,
    project_statement: str | None = None,
    **kwargs: Any,
) -> dict:
    # Backward/forward compatibility: tolerate renamed context keys from callers.
    if project_statement is None:
        project_statement = (
            kwargs.pop("problem_statement", None)
            or kwargs.pop("project_description", None)
            or kwargs.pop("project_context", None)
        )

    if project_statement is not None and not isinstance(project_statement, str):
        project_statement = str(project_statement)
    project_statement = _normalize_project_statement(project_statement)

    manual_archetype = kwargs.pop("manual_archetype", None)

    if kwargs:
        ignored_args = ", ".join(sorted(kwargs.keys()))
        print(f"      ⚠️ Ignoring unsupported evaluator args: {ignored_args}")

    # 1. Validation - fail hard if no API key
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not configured. "
            "Analysis cannot proceed without AI judge evaluation."
        )
    
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Product evaluation skipped: invalid repo_path ({repo_path})")
        return {
            "project_name": "Unknown",
            "description": "Repository path not available.",
            "features": [],
            "implementation_score": 50,
            "positive_feedback": "Unable to analyze - repository not cloned",
            "constructive_feedback": "Repository cloning failed",
            "verdict": "Analysis Incomplete"
        }

    model_name = _get_evaluator_model()
    fallback_model = _get_evaluator_fallback_model()
    max_context_chars = _get_evaluator_max_context_chars()
    print(f"      🧠 Generating Codebase Summary for OpenAI {model_name}...")
    context = generate_repo_summary(repo_path, max_chars=max_context_chars)
    # Strip lone surrogate characters that can't be UTF-8 encoded
    context = context.encode('utf-8', errors='replace').decode('utf-8')
    if len(context) > max_context_chars:
        print(
            "      ⚠️ Codebase summary is too large for reliable model context; "
            f"truncating from {len(context)} to {max_context_chars} chars."
        )
        context = _truncate_context(context, max_context_chars)

    sections = _split_summary_sections(context)
    part_budget = max(20000, max_context_chars // 2)
    frontend_context = _compose_part_context(sections, "frontend", part_budget)
    backend_context = _compose_part_context(sections, "backend", part_budget)
    project_profile = infer_project_profile(project_statement, context, manual_archetype=manual_archetype)
    
    # 2. Configure OpenAI API
    try:
        client = OpenAI(api_key=api_key)
        system_msg = (
            "You are a strict, evidence-driven codebase evaluator for hackathon repositories. "
            "Return valid JSON only with no markdown, code fences, or prose outside the JSON object."
        )
        
        configured_temperature = _get_evaluator_temperature()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0

        print(f"      🚀 Sending frontend and backend evaluators to OpenAI {model_name}...")
        frontend_prompt = _build_part_prompt("frontend", frontend_context, project_statement, project_profile)
        backend_prompt = _build_part_prompt("backend", backend_context, project_statement, project_profile)

        frontend_result, frontend_usage, frontend_model_used = _call_openai_json_with_retries(
            client=client,
            primary_model=model_name,
            fallback_model=fallback_model,
            system_msg=system_msg,
            prompt=frontend_prompt,
            configured_temperature=configured_temperature,
        )

        backend_result, backend_usage, backend_model_used = _call_openai_json_with_retries(
            client=client,
            primary_model=model_name,
            fallback_model=fallback_model,
            system_msg=system_msg,
            prompt=backend_prompt,
            configured_temperature=configured_temperature,
        )

        synth_prompt = _build_synthesis_prompt(frontend_result, backend_result, project_statement, project_profile)
        result, synth_usage, synth_model_used = _call_openai_json_with_retries(
            client=client,
            primary_model=model_name,
            fallback_model=fallback_model,
            system_msg=system_msg,
            prompt=synth_prompt,
            configured_temperature=configured_temperature,
        )

        call_usage_rows = [
            ("frontend", frontend_usage, frontend_model_used),
            ("backend", backend_usage, backend_model_used),
            ("synthesis", synth_usage, synth_model_used),
        ]

        call_breakdown = []
        model_costs: dict[str, dict[str, Any]] = {}

        for stage, usage, resolved_model in call_usage_rows:
            if not usage:
                continue

            prompt_tokens = int(usage.prompt_tokens or 0)
            completion_tokens = int(usage.completion_tokens or 0)
            usage_total_tokens = int(usage.total_tokens or (prompt_tokens + completion_tokens))

            pricing_model, input_rate, output_rate, pricing_source = _get_model_pricing(resolved_model)
            input_cost = (prompt_tokens / 1_000_000) * input_rate
            output_cost = (completion_tokens / 1_000_000) * output_rate
            usage_total_cost = input_cost + output_cost

            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            total_tokens += usage_total_tokens

            model_bucket = model_costs.setdefault(
                pricing_model,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "input_cost_usd": 0.0,
                    "output_cost_usd": 0.0,
                    "total_cost_usd": 0.0,
                    "input_price_per_1m": input_rate,
                    "output_price_per_1m": output_rate,
                    "pricing_source": pricing_source,
                },
            )

            model_bucket["prompt_tokens"] += prompt_tokens
            model_bucket["completion_tokens"] += completion_tokens
            model_bucket["total_tokens"] += usage_total_tokens
            model_bucket["input_cost_usd"] += input_cost
            model_bucket["output_cost_usd"] += output_cost
            model_bucket["total_cost_usd"] += usage_total_cost

            call_breakdown.append(
                {
                    "stage": stage,
                    "model": str(resolved_model or pricing_model),
                    "pricing_model": pricing_model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": usage_total_tokens,
                    "input_cost_usd": round(input_cost, 6),
                    "output_cost_usd": round(output_cost, 6),
                    "total_cost_usd": round(usage_total_cost, 6),
                    "input_price_per_1m": input_rate,
                    "output_price_per_1m": output_rate,
                    "pricing_source": pricing_source,
                }
            )

        # 4. Extract token usage totals
        prompt_tokens = total_prompt_tokens
        completion_tokens = total_completion_tokens

        input_cost = sum(item["input_cost_usd"] for item in call_breakdown)
        output_cost = sum(item["output_cost_usd"] for item in call_breakdown)
        total_cost = input_cost + output_cost

        for model_name, stats in model_costs.items():
            stats["input_cost_usd"] = round(stats["input_cost_usd"], 6)
            stats["output_cost_usd"] = round(stats["output_cost_usd"], 6)
            stats["total_cost_usd"] = round(stats["total_cost_usd"], 6)
            model_costs[model_name] = stats
        
        print(f"      💰 Tokens: {prompt_tokens} input + {completion_tokens} output = {total_tokens} total")
        print(f"      💵 Cost: ${total_cost:.6f} (${input_cost:.6f} input + ${output_cost:.6f} output)")
        
        # Add token usage and part-evaluator metadata to result
        result.setdefault("part_reports", {})
        result["part_reports"]["frontend"] = frontend_result
        result["part_reports"]["backend"] = backend_result
        result["project_profile"] = {
            "archetype": project_profile.get("archetype"),
            "confidence": project_profile.get("confidence"),
            "source": project_profile.get("source"),
            "evidence": project_profile.get("evidence", []),
            "manual_archetype": manual_archetype,
        }
        result["project_context"] = {
            "statement": project_statement,
            "context_quality": project_profile.get("context_quality"),
            "warning": project_profile.get("warning"),
        }

        # Make advanced security controls optional by default and apply bonus when present.
        result = _apply_optional_security_policy(result, project_statement)
        result = _apply_project_statement_alignment_policy(result, project_statement)
        result = _stabilize_implementation_score(result)

        result["token_usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "input_cost_usd": round(input_cost, 6),
            "output_cost_usd": round(output_cost, 6),
            "total_cost_usd": round(total_cost, 6),
            "model": synth_model_used,
            "frontend_model": frontend_model_used,
            "backend_model": backend_model_used,
            "pricing_currency": "USD",
            "model_costs": model_costs,
            "call_breakdown": call_breakdown,
        }
        
        return result

    except Exception as e:
        print(f"      ❌ OpenAI Error: {e}")
        # Fail hard - do not return fake default scores
        raise RuntimeError(
            f"OpenAI API call failed: {e}. "
            f"Analysis cannot proceed without AI judge evaluation. "
            f"Check your OPENAI_API_KEY and model configuration."
        ) from e
