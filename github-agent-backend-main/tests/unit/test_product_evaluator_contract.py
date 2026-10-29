"""Contract tests for product evaluator argument compatibility and prompt context."""

from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

from src.detectors import product_evaluator as pe


class _FakeCompletions:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kwargs):
        self._sink.setdefault("requests", []).append(kwargs)
        self._sink["request"] = kwargs
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"project_name": "Demo", "implementation_score": 72}'
                    )
                )
            ],
        )


class _FakeOpenAIClient:
    def __init__(self, sink):
        self.chat = SimpleNamespace(completions=_FakeCompletions(sink))


class _TempRejectingCompletions:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kwargs):
        self._sink.setdefault("requests", []).append(kwargs)
        if len(self._sink["requests"]) == 1 and "temperature" in kwargs:
            raise ValueError(
                "Unsupported value: 'temperature' does not support 0.7 with this model. "
                "Only the default (1) value is supported."
            )
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=6, total_tokens=17),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"project_name": "Demo", "implementation_score": 73}'
                    )
                )
            ],
        )


class _TempRejectingOpenAIClient:
    def __init__(self, sink):
        self.chat = SimpleNamespace(completions=_TempRejectingCompletions(sink))


class _ContextLengthRejectingCompletions:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kwargs):
        self._sink.setdefault("requests", []).append(kwargs)
        # Simulate primary model context overflow and fallback model success.
        if kwargs.get("model") == "gpt-5.4-nano-2026-03-17":
            raise ValueError(
                "Error code: 400 - {'error': {'message': 'Input tokens exceed the configured limit of 272000 tokens. "
                "Your messages resulted in 314604 tokens. Please reduce the length of the messages.', "
                "'type': 'invalid_request_error', 'param': 'messages', 'code': 'context_length_exceeded'}}"
            )
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7, total_tokens=19),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"project_name": "Demo", "implementation_score": 74}'
                    )
                )
            ],
            model=kwargs.get("model"),
        )


class _ContextLengthRejectingOpenAIClient:
    def __init__(self, sink):
        self.chat = SimpleNamespace(completions=_ContextLengthRejectingCompletions(sink))


def test_evaluator_accepts_project_statement_and_future_kwargs(tmp_path, monkeypatch):
    """Evaluator should not crash when callers pass extra/renamed context kwargs."""
    captured = {}

    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    result = pe.evaluate_product_logic(
        repo_path=str(tmp_path),
        api_key="sk-test",
        project_statement="Build a smart attendance tracker",
        request_id="req-123",
        worker_name="celery-2",
    )

    assert result["project_name"] == "Demo"
    assert result["token_usage"]["total_tokens"] == 45
    assert len(captured["requests"]) == 3

    prompts = [req["messages"][1]["content"] for req in captured["requests"]]
    assert any("Build a smart attendance tracker" in prompt for prompt in prompts)


def test_evaluator_accepts_problem_statement_alias(tmp_path, monkeypatch):
    """Alias argument names should map to project context in the generated prompt."""
    captured = {}

    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    pe.evaluate_product_logic(
        repo_path=str(tmp_path),
        api_key="sk-test",
        problem_statement="Detect plagiarism in code submissions",
    )

    prompts = [req["messages"][1]["content"] for req in captured["requests"]]
    assert any("Detect plagiarism in code submissions" in prompt for prompt in prompts)


def test_infer_project_profile_detects_extension_from_statement_and_context():
    profile = pe.infer_project_profile(
        "Build a Chrome extension for tab productivity",
        "manifest_version, chrome.runtime, content_scripts, background.js",
    )
    assert profile["archetype"] == "chrome_extension"
    assert profile["confidence"] in {"medium", "high"}
    assert profile["source"] == "statement_and_repo_summary"


def test_infer_project_profile_detects_backend_api():
    profile = pe.infer_project_profile(
        "Backend API for student grading",
        "FastAPI router controller openapi swagger endpoint",
    )
    assert profile["archetype"] == "backend_api"


def test_infer_project_profile_detects_cli_tool():
    profile = pe.infer_project_profile(
        "Build a command line CLI tool for local file search",
        "import argparse, sys, click",
    )
    assert profile["archetype"] == "cli_tool"


def test_infer_project_profile_detects_desktop_app():
    profile = pe.infer_project_profile(
        "A desktop app built with PyQt",
        "electron tkinter pyqt5 tauri window widgets",
    )
    assert profile["archetype"] == "desktop_app"


def test_infer_project_profile_detects_game():
    profile = pe.infer_project_profile(
        "A 2D game in Pygame",
        "unity unreal engine godot pygame sprites assets",
    )
    assert profile["archetype"] == "game"


def test_evaluator_uses_repo_inference_when_project_statement_missing(tmp_path, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        pe,
        "generate_repo_summary",
        lambda *args, **kwargs: "manifest_version chrome.runtime content_scripts background.js",
    )
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    result = pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    assert result["project_profile"]["archetype"] == "chrome_extension"
    assert result["project_profile"]["source"] == "repo_summary_only"
    assert result["project_context"]["context_quality"] == "weak"
    assert result["project_context"]["warning"]

    prompts = [req["messages"][1]["content"] for req in captured["requests"]]
    assert any("Project archetype: chrome_extension" in prompt for prompt in prompts)


def test_evaluator_uses_deterministic_temperature_by_default(tmp_path, monkeypatch):
    """Without config, evaluator should use deterministic temperature for stable scoring."""
    captured = {}

    monkeypatch.delenv("OPENAI_PRODUCT_EVALUATION_TEMPERATURE", raising=False)
    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    assert captured["requests"]
    assert all(req.get("temperature") == 0.0 for req in captured["requests"])


def test_evaluator_retries_without_temperature_when_rejected(tmp_path, monkeypatch):
    """If model rejects custom temperature, evaluator should retry without it."""
    captured = {}

    monkeypatch.setenv("OPENAI_PRODUCT_EVALUATION_TEMPERATURE", "0.7")
    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _TempRejectingOpenAIClient(captured))

    result = pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    assert result["project_name"] == "Demo"
    assert len(captured["requests"]) == 4
    assert captured["requests"][0].get("temperature") == 0.7
    assert "temperature" not in captured["requests"][1]


def test_evaluator_falls_back_model_on_context_length_exceeded(tmp_path, monkeypatch):
    """When primary model exceeds context, evaluator should retry with fallback model."""
    captured = {}

    monkeypatch.delenv("OPENAI_PRODUCT_EVALUATION_TEMPERATURE", raising=False)
    monkeypatch.setenv("OPENAI_PRODUCT_EVALUATION_MODEL", "gpt-5.4-nano-2026-03-17")
    monkeypatch.setenv("OPENAI_PRODUCT_EVALUATION_FALLBACK_MODEL", "gpt-5-mini-2025-08-07")
    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _ContextLengthRejectingOpenAIClient(captured))

    result = pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    assert result["project_name"] == "Demo"
    assert len(captured["requests"]) == 6
    assert any(req["model"] == "gpt-5.4-nano-2026-03-17" for req in captured["requests"])
    assert any(req["model"] == "gpt-5-mini-2025-08-07" for req in captured["requests"])
    assert result["token_usage"]["model"] == "gpt-5-mini-2025-08-07"


def test_evaluator_truncates_oversized_context(tmp_path, monkeypatch):
    """Oversized repo summaries should be truncated before sending to model."""
    captured = {}

    monkeypatch.setenv("OPENAI_PRODUCT_EVALUATION_MAX_CONTEXT_CHARS", "10000")
    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "A" * 50000)
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    prompts = [req["messages"][1]["content"] for req in captured["requests"]]
    assert any("[... CODEBASE CONTEXT TRUNCATED DUE TO SIZE ...]" in prompt for prompt in prompts)


def test_evaluator_uses_env_model_key_pricing_for_future_models(tmp_path, monkeypatch):
    """Future model names should pick up pricing via OPENAI_MODEL_<MODEL_KEY> env vars."""
    captured = {}

    monkeypatch.setenv("OPENAI_PRODUCT_EVALUATION_MODEL", "gpt-future-1-2027-01-01")
    monkeypatch.setenv("OPENAI_MODEL_GPT_FUTURE_1_2027_01_01_INPUT_PRICE_PER_1M", "1.23")
    monkeypatch.setenv("OPENAI_MODEL_GPT_FUTURE_1_2027_01_01_OUTPUT_PRICE_PER_1M", "4.56")
    monkeypatch.delenv("OPENAI_MODEL_PRICING_JSON", raising=False)
    monkeypatch.delenv("OPENAI_DEFAULT_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_DEFAULT_OUTPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_PRODUCT_EVALUATION_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_PRODUCT_EVALUATION_OUTPUT_PRICE_PER_1M", raising=False)

    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    result = pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    assert result["token_usage"]["call_breakdown"]
    assert all(
        call["pricing_source"] == "env-model-key"
        for call in result["token_usage"]["call_breakdown"]
    )


def test_evaluator_uses_env_default_pricing_for_unknown_models(tmp_path, monkeypatch):
    """Unknown models should use global default pricing env vars when no specific rate exists."""
    captured = {}

    monkeypatch.setenv("OPENAI_PRODUCT_EVALUATION_MODEL", "gpt-unknown-next")
    monkeypatch.setenv("OPENAI_DEFAULT_INPUT_PRICE_PER_1M", "0.77")
    monkeypatch.setenv("OPENAI_DEFAULT_OUTPUT_PRICE_PER_1M", "1.99")
    monkeypatch.delenv("OPENAI_MODEL_PRICING_JSON", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_GPT_UNKNOWN_NEXT_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_GPT_UNKNOWN_NEXT_OUTPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_PRODUCT_EVALUATION_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_PRODUCT_EVALUATION_OUTPUT_PRICE_PER_1M", raising=False)

    monkeypatch.setattr(pe, "generate_repo_summary", lambda *args, **kwargs: "repo summary")
    monkeypatch.setattr(pe, "OpenAI", lambda api_key: _FakeOpenAIClient(captured))

    result = pe.evaluate_product_logic(repo_path=str(tmp_path), api_key="sk-test")

    assert result["token_usage"]["call_breakdown"]
    assert all(
        call["pricing_source"] == "env-default"
        for call in result["token_usage"]["call_breakdown"]
    )


def test_optional_security_not_enforced_for_general_projects():
    """General projects should not be penalized for missing advanced security controls."""
    report = {
        "implementation_score": 78,
        "completeness_analysis": {
            "missing_critical_features": [
                "rate limiting on APIs",
                "waf protection",
                "user onboarding flow",
            ]
        },
        "suggested_features": [
            {"feature_name": "Add rate limiting", "priority": "High"},
            {"feature_name": "Improve onboarding", "priority": "Medium"},
        ],
        "positive_feedback": "Great architecture. Strong rate limiting strategy.",
        "quality_indicators": {"has_security_measures": False},
    }

    updated = pe._apply_optional_security_policy(report, project_statement="Campus event app")
    assert updated["completeness_analysis"]["missing_critical_features"] == ["user onboarding flow"]
    assert updated["suggested_features"] == [{"feature_name": "Improve onboarding", "priority": "Medium"}]
    assert "rate limiting" not in updated["positive_feedback"].lower()
    assert updated["quality_indicators"]["has_security_measures"] is False
    assert updated["implementation_score"] == 78


def test_security_bonus_applied_when_present():
    """Security controls should award a small bonus when present on non-security projects."""
    report = {
        "implementation_score": 88,
        "completeness_analysis": {"missing_critical_features": ["missing analytics dashboard"]},
        "quality_indicators": {"has_security_measures": True},
    }

    updated = pe._apply_optional_security_policy(report, project_statement="Food delivery app")
    assert updated["implementation_score"] == 91
    assert "security_bonus_applied" not in updated
    assert updated["quality_indicators"]["has_security_measures"] is False


def test_security_projects_keep_security_requirements():
    """Security-focused projects should retain security requirements as critical."""
    report = {
        "implementation_score": 82,
        "completeness_analysis": {
            "missing_critical_features": [
                "rate limiting",
                "threat detection alerts",
            ]
        },
        "quality_indicators": {"has_security_measures": False},
    }

    updated = pe._apply_optional_security_policy(report, project_statement="Cybersecurity monitoring platform")
    assert "rate limiting" in updated["completeness_analysis"]["missing_critical_features"]
