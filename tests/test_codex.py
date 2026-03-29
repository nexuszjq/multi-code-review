import subprocess
from unittest.mock import patch, MagicMock
from scripts.adapters.codex import CodexAdapter


def test_codex_name():
    adapter = CodexAdapter()
    assert adapter.name == "codex"


@patch("shutil.which", return_value="/usr/local/bin/codex")
def test_is_available_true(mock_which):
    adapter = CodexAdapter()
    assert adapter.is_available() is True
    mock_which.assert_called_once_with("codex")


@patch("shutil.which", return_value=None)
def test_is_available_false(mock_which):
    adapter = CodexAdapter()
    assert adapter.is_available() is False


@patch("subprocess.run")
def test_invoke_success(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    adapter = CodexAdapter()
    prompt = "Review this code"
    output_dir = str(tmp_path / "review")

    import os
    os.makedirs(output_dir, exist_ok=True)
    # Pre-create the assessment file that codex would write
    assessment_file = os.path.join(output_dir, "assessment.md")
    with open(assessment_file, "w") as f:
        f.write("VERDICT: APPROVED")

    result = adapter.invoke(prompt, {"timeout": 120, "output_dir": output_dir})

    assert result.verdict == "APPROVED"
    assert result.reviewer == "codex"
    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert "codex" in cmd
    assert "-" in cmd  # stdin mode
    # Verify prompt is passed via stdin (input kwarg)
    assert mock_run.call_args[1]["input"] == prompt


@patch("subprocess.run")
def test_invoke_nonzero_exit(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error: authentication failed")
    adapter = CodexAdapter()
    result = adapter.invoke("prompt", {"timeout": 120, "output_dir": str(tmp_path)})
    assert result.verdict == "ERROR"
    assert "authentication failed" in result.raw_output


@patch("subprocess.run")
def test_invoke_timeout(mock_run, tmp_path):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=500)
    adapter = CodexAdapter()
    result = adapter.invoke("prompt", {"timeout": 500, "output_dir": str(tmp_path)})
    assert result.verdict == "ERROR"
    assert "timeout" in result.raw_output.lower()


@patch("subprocess.run")
def test_invoke_with_diff_file(mock_run, tmp_path):
    """Verify Codex adapter inlines diff_file content into the prompt."""
    output_dir = str(tmp_path / "review")
    import os
    os.makedirs(output_dir, exist_ok=True)

    # Create a diff file
    diff_file = os.path.join(output_dir, "diff.patch")
    with open(diff_file, "w") as f:
        f.write("diff --git a/foo.py\n+new code here")

    # Pre-create the assessment file
    assessment_file = os.path.join(output_dir, "assessment.md")
    with open(assessment_file, "w") as f:
        f.write("VERDICT: APPROVED")

    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    adapter = CodexAdapter()
    result = adapter.invoke("Review this", {"timeout": 500, "output_dir": output_dir, "diff_file": diff_file})

    assert result.verdict == "APPROVED"
    # Verify the diff content IS inlined into stdin for Codex
    call_kwargs = mock_run.call_args[1]
    assert "--- Begin Diff Content ---" in call_kwargs["input"]
    assert "+new code here" in call_kwargs["input"]


@patch("subprocess.run")
def test_cd_before_stdin_marker(mock_run, tmp_path):
    """Verify --cd comes before - in the command."""
    output_dir = str(tmp_path / "review")
    import os
    os.makedirs(output_dir, exist_ok=True)
    assessment_file = os.path.join(output_dir, "assessment.md")
    with open(assessment_file, "w") as f:
        f.write("VERDICT: APPROVED")

    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    adapter = CodexAdapter()
    adapter.invoke("prompt", {"timeout": 500, "output_dir": output_dir, "repo_path": "/my/repo"})

    cmd = mock_run.call_args[0][0]
    cd_index = cmd.index("--cd")
    stdin_index = cmd.index("-")
    assert cd_index < stdin_index, f"--cd at {cd_index} should come before - at {stdin_index}"
