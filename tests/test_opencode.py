import os
import subprocess
from unittest.mock import patch, MagicMock
from scripts.adapters.opencode import OpencodeAdapter


def test_opencode_name():
    adapter = OpencodeAdapter()
    assert adapter.name == "opencode"


@patch("shutil.which", return_value="/usr/local/bin/opencode")
def test_is_available_true(mock_which):
    adapter = OpencodeAdapter()
    assert adapter.is_available() is True
    mock_which.assert_called_once_with("opencode")


@patch("shutil.which", return_value=None)
def test_is_available_false(mock_which):
    adapter = OpencodeAdapter()
    assert adapter.is_available() is False


@patch("subprocess.run")
def test_invoke_success(mock_run, tmp_path):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="VERDICT: APPROVED",
        stderr="",
    )
    adapter = OpencodeAdapter()
    output_dir = str(tmp_path / "review")
    result = adapter.invoke("Review this code", {"timeout": 120, "output_dir": output_dir})
    assert result.verdict == "APPROVED"
    assert result.reviewer == "opencode"
    cmd = mock_run.call_args[0][0]
    assert "opencode" in cmd
    assert "run" in cmd
    # Verify prompt written to file and attached via --file
    prompt_file = os.path.join(output_dir, "opencode-prompt.md")
    assert os.path.exists(prompt_file)
    with open(prompt_file) as f:
        assert f.read() == "Review this code"
    assert "--file" in cmd
    assert prompt_file in cmd


@patch("subprocess.run")
def test_invoke_with_diff_file(mock_run, tmp_path):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="VERDICT: NEEDS_REVISION\nFINDING-1: MAJOR\nDescription: Bug found\nSuggestion: Fix it",
        stderr="",
    )
    adapter = OpencodeAdapter()
    output_dir = str(tmp_path / "review")
    result = adapter.invoke("Review", {"timeout": 120, "output_dir": output_dir, "diff_file": "/tmp/diff.patch"})
    assert result.verdict == "NEEDS_REVISION"
    assert len(result.findings) == 1
    cmd = mock_run.call_args[0][0]
    # Should have both the prompt file and the diff file as --file args
    file_args = [cmd[i + 1] for i, v in enumerate(cmd) if v == "--file"]
    prompt_file = os.path.join(output_dir, "opencode-prompt.md")
    assert prompt_file in file_args
    assert "/tmp/diff.patch" in file_args


@patch("subprocess.run")
def test_invoke_nonzero_exit(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error: config not found")
    adapter = OpencodeAdapter()
    result = adapter.invoke("prompt", {"timeout": 120, "output_dir": str(tmp_path)})
    assert result.verdict == "ERROR"
    assert "config not found" in result.raw_output


@patch("subprocess.run")
def test_invoke_timeout(mock_run, tmp_path):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="opencode", timeout=500)
    adapter = OpencodeAdapter()
    result = adapter.invoke("prompt", {"timeout": 500, "output_dir": str(tmp_path)})
    assert result.verdict == "ERROR"
    assert "timeout" in result.raw_output.lower()


@patch("subprocess.run")
def test_invoke_captures_stderr(mock_run, tmp_path):
    """Verify stderr is appended to raw_output for debugging but does not affect verdict."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="VERDICT: APPROVED",
        stderr="Warning: critical config cache miss",
    )
    adapter = OpencodeAdapter()
    result = adapter.invoke("prompt", {"timeout": 500, "output_dir": str(tmp_path)})
    # Verdict must come from stdout only — stderr "critical" must not flip it
    assert result.verdict == "APPROVED"
    assert "critical config cache miss" in result.raw_output


@patch("subprocess.run")
def test_invoke_unstructured_output_infers_verdict(mock_run, tmp_path):
    """Verify that free-form output without VERDICT still gets a usable verdict."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="The code looks good overall. No major issues found. LGTM.",
        stderr="",
    )
    adapter = OpencodeAdapter()
    result = adapter.invoke("prompt", {"timeout": 500, "output_dir": str(tmp_path)})
    assert result.verdict == "APPROVED"
