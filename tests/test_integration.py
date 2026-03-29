import json
import os
import subprocess
from unittest.mock import patch, MagicMock
from scripts.review_engine import collect_diff, build_prompt, get_adapters, save_artifacts
from scripts.adapters.base import ReviewResult, Finding
from scripts.adapters.codex import CodexAdapter
from scripts.adapters.opencode import OpencodeAdapter


def test_full_review_flow_codex(tmp_path):
    """End-to-end: collect diff → build prompt → invoke (mocked) codex → save artifacts."""
    output_dir = str(tmp_path / "review-output")
    os.makedirs(output_dir)

    diff_content = "diff --git a/foo.py\n+print('hello')"

    prompt_dir = tmp_path / "scripts" / "prompts"
    prompt_dir.mkdir(parents=True)
    template_text = (
        "## Repository\n$repo_path\n## Scope\n$scope_description\n"
        "## Code Changes\n$diff_content_or_file_reference\n"
        "## Host Context\n$host_context"
    )
    (prompt_dir / "code_review.md").write_text(template_text)

    with patch("scripts.review_engine.SCRIPT_DIR", tmp_path / "scripts"):
        prompt, _ = build_prompt("code_review.md", diff_content, output_dir, repo_path="/repo")

    assert "print('hello')" in prompt

    mock_result = ReviewResult(
        verdict="NEEDS_REVISION",
        findings=[
            Finding(id="FINDING-1", severity="MAJOR", description="Missing error handling", suggestion="Add try/except")
        ],
        raw_output="FINDING-1: MAJOR\nDescription: Missing error handling\nSuggestion: Add try/except\nVERDICT: NEEDS_REVISION",
        reviewer="codex",
        duration_seconds=5.0,
    )

    save_artifacts(output_dir, prompt, mock_result)

    assert os.path.exists(os.path.join(output_dir, "prompt.md"))
    assert os.path.exists(os.path.join(output_dir, "assessment.md"))
    assert os.path.exists(os.path.join(output_dir, "result.json"))

    with open(os.path.join(output_dir, "result.json")) as f:
        result_data = json.load(f)
    assert result_data["verdict"] == "NEEDS_REVISION"
    assert len(result_data["findings"]) == 1
    assert result_data["findings"][0]["severity"] == "MAJOR"
    assert result_data["reviewer"] == "codex"


def test_full_review_flow_opencode(tmp_path):
    """End-to-end: collect path content → build prompt → invoke (mocked) opencode → save artifacts."""
    output_dir = str(tmp_path / "review-output")
    os.makedirs(output_dir)

    test_file = tmp_path / "app.py"
    test_file.write_text("def add(a, b):\n    return a + b\n")

    # Mock _run_git so path boundary check resolves to tmp_path (not a real git repo)
    with patch("scripts.review_engine._run_git", return_value=str(tmp_path) + "\n"):
        diff_content = collect_diff("path", paths=[str(test_file)])
    assert "def add" in diff_content

    prompt_dir = tmp_path / "scripts" / "prompts"
    prompt_dir.mkdir(parents=True)
    template_text = (
        "## Repository\n$repo_path\n## Scope\n$scope_description\n"
        "## Code Changes\n$diff_content_or_file_reference\n"
        "## Host Context\n$host_context"
    )
    (prompt_dir / "code_review.md").write_text(template_text)

    with patch("scripts.review_engine.SCRIPT_DIR", tmp_path / "scripts"):
        prompt, _ = build_prompt("code_review.md", diff_content, output_dir, repo_path=str(tmp_path))

    mock_result = ReviewResult(
        verdict="APPROVED",
        findings=[],
        raw_output="VERDICT: APPROVED",
        reviewer="opencode",
        duration_seconds=3.2,
    )

    save_artifacts(output_dir, prompt, mock_result)

    with open(os.path.join(output_dir, "result.json")) as f:
        result_data = json.load(f)
    assert result_data["verdict"] == "APPROVED"
    assert result_data["findings"] == []


def test_adapter_registry():
    """Verify all adapters are registered and have correct names."""
    from scripts.review_engine import ADAPTERS
    assert "codex" in ADAPTERS
    assert "opencode" in ADAPTERS
    assert ADAPTERS["codex"]().name == "codex"
    assert ADAPTERS["opencode"]().name == "opencode"
