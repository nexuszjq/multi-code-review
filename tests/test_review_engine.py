import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from scripts.review_engine import collect_diff, build_prompt, get_adapters, INLINE_MAX_BYTES
from scripts.adapters.codex import CodexAdapter
from scripts.adapters.opencode import OpencodeAdapter


def test_collect_diff_staged():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="diff --git a/foo.py b/foo.py\n+hello")
        diff = collect_diff("staged", repo_path="/fake/repo")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "git" in cmd
        assert "diff" in cmd
        assert "--cached" in cmd
        assert "--no-ext-diff" in cmd
        assert diff == "diff --git a/foo.py b/foo.py\n+hello"


def test_collect_diff_working():
    with patch("subprocess.run") as mock_run:
        # Default: no untracked files included (only git diff HEAD)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="diff working changes"),
        ]
        diff = collect_diff("working", repo_path="/fake/repo")
        first_cmd = mock_run.call_args_list[0][0][0]
        assert "HEAD" in first_cmd
        assert diff == "diff working changes"
        # Should NOT call git ls-files when include_untracked=False
        assert mock_run.call_count == 1


def test_collect_diff_working_with_untracked(tmp_path):
    untracked_file = tmp_path / "new_file.py"
    untracked_file.write_text("print('new')")

    with patch("subprocess.run") as mock_run:
        # Calls: git diff HEAD, git rev-parse --show-toplevel, git ls-files --others
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="diff tracked changes"),
            MagicMock(returncode=0, stdout=str(tmp_path) + "\n"),
            MagicMock(returncode=0, stdout="new_file.py\n"),
        ]
        diff = collect_diff("working", repo_path=str(tmp_path), include_untracked=True)
        assert "diff tracked changes" in diff
        assert "new_file.py" in diff
        assert "print('new')" in diff


def test_collect_diff_range():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="diff range output")
        diff = collect_diff("range", repo_path="/fake/repo", range_spec="main...HEAD")
        cmd = mock_run.call_args[0][0]
        assert "main...HEAD" in cmd
        assert "--no-ext-diff" in cmd


def test_collect_diff_path(tmp_path):
    test_file = tmp_path / "hello.py"
    test_file.write_text("print('hello')")
    diff = collect_diff("path", repo_path=str(tmp_path), paths=[str(test_file)])
    assert "print('hello')" in diff


def test_build_prompt_inline(tmp_path):
    prompt_dir = tmp_path / "scripts" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "code_review.md").write_text(
        "## Repository\n$repo_path\n## Scope\n$scope_description\n"
        "## Code Changes\n$diff_content_or_file_reference\n"
        "## Host Context\n$host_context"
    )
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir)

    with patch("scripts.review_engine.SCRIPT_DIR", tmp_path / "scripts"):
        prompt, diff_file = build_prompt("code_review.md", "small diff", output_dir, repo_path="/repo")

    assert "small diff" in prompt
    assert "/repo" in prompt
    assert diff_file is None


def test_build_prompt_large_diff(tmp_path):
    prompt_dir = tmp_path / "scripts" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "code_review.md").write_text(
        "## Repository\n$repo_path\n## Scope\n$scope_description\n"
        "## Code Changes\n$diff_content_or_file_reference\n"
        "## Host Context\n$host_context"
    )
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir)

    large_diff = "x" * (INLINE_MAX_BYTES + 1)
    with patch("scripts.review_engine.SCRIPT_DIR", tmp_path / "scripts"):
        prompt, diff_file = build_prompt("code_review.md", large_diff, output_dir, repo_path="/repo")

    assert "Diff too large" in prompt
    assert diff_file is not None
    assert os.path.exists(diff_file)


def test_get_adapters_specified():
    with patch.object(CodexAdapter, "is_available", return_value=True):
        adapters = get_adapters("codex")
        assert len(adapters) == 1
        assert adapters[0].name == "codex"


def test_get_adapters_auto_detect():
    with patch.object(CodexAdapter, "is_available", return_value=False):
        with patch.object(OpencodeAdapter, "is_available", return_value=True):
            adapters = get_adapters(None)
            assert len(adapters) == 1
            assert adapters[0].name == "opencode"


def test_get_adapters_auto_detect_fallback_order():
    """When multiple reviewers are available, all are returned for fallback."""
    with patch.object(CodexAdapter, "is_available", return_value=True):
        with patch.object(OpencodeAdapter, "is_available", return_value=True):
            adapters = get_adapters(None)
            assert len(adapters) == 2


def test_get_adapters_none_available():
    with patch.object(CodexAdapter, "is_available", return_value=False):
        with patch.object(OpencodeAdapter, "is_available", return_value=False):
            adapters = get_adapters(None)
            assert adapters == []


def test_build_prompt_with_curly_braces(tmp_path):
    """Verify that diff content containing {} does not crash template substitution."""
    prompt_dir = tmp_path / "scripts" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "code_review.md").write_text(
        "## Repository\n$repo_path\n## Scope\n$scope_description\n"
        "## Code Changes\n$diff_content_or_file_reference\n"
        "## Host Context\n$host_context"
    )
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir)

    diff_with_braces = 'data = {"key": "value"}\nfor item in items:\n    print(f"{item}")'
    with patch("scripts.review_engine.SCRIPT_DIR", tmp_path / "scripts"):
        prompt, diff_file = build_prompt("code_review.md", diff_with_braces, output_dir, repo_path="/repo")

    assert '{"key": "value"}' in prompt
    assert 'f"{item}"' in prompt
    assert diff_file is None


def test_collect_diff_git_failure():
    """Verify that a failed git command raises RuntimeError."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal: bad revision 'nonexistent...HEAD'")
        with pytest.raises(RuntimeError, match="git command failed"):
            collect_diff("range", repo_path="/fake/repo", range_spec="nonexistent...HEAD")
