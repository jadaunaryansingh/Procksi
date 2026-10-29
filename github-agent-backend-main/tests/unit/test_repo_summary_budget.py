"""Tests for repository summary context-budget behavior."""

from src.utils.repo_summary import generate_repo_summary


def test_repo_summary_respects_budget_and_preserves_sections(tmp_path):
    """Summary should stay within budget while retaining cross-section visibility."""
    # Configuration/docs
    (tmp_path / "README.md").write_text("Project overview\n" * 400, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n" * 100, encoding="utf-8")

    # Backend
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "api_server.py").write_text("def route():\n    return 'ok'\n" * 800, encoding="utf-8")

    # Frontend
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "App.jsx").write_text("export default function App(){return <div>Hello</div>}\n" * 700, encoding="utf-8")

    # Schema / core
    (src_dir / "models.py").write_text("class User: pass\n" * 600, encoding="utf-8")
    (src_dir / "core_logic.py").write_text("def compute(x): return x * 2\n" * 800, encoding="utf-8")

    summary = generate_repo_summary(str(tmp_path), max_chars=3500)

    assert len(summary) <= 3500
    assert "=== DIRECTORY STRUCTURE ===" in summary
    assert "=== CONFIGURATION FILES ===" in summary
    assert "=== BACKEND/API IMPLEMENTATION ===" in summary
    assert "=== FRONTEND IMPLEMENTATION ===" in summary
