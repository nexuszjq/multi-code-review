import os
import shutil
import subprocess
import time

from scripts.adapters.base import ReviewerAdapter, ReviewResult


class CodexAdapter(ReviewerAdapter):
    name = "codex"

    def is_available(self) -> bool:
        return shutil.which("codex") is not None

    def invoke(self, prompt: str, options: dict) -> ReviewResult:
        timeout = options.get("timeout", 500)
        output_dir = options.get("output_dir", "/tmp/multi-code-review")
        os.makedirs(output_dir, exist_ok=True)
        assessment_file = os.path.join(output_dir, "assessment.md")

        # If a spill file exists (diff too large to inline), read and append
        # its content to the prompt so Codex receives the full diff.
        diff_file = options.get("diff_file")
        if diff_file and os.path.isfile(diff_file):
            with open(diff_file, "r") as f:
                spill_content = f.read()
            prompt += f"\n\n--- Begin Diff Content ---\n{spill_content}\n--- End Diff Content ---\n"

        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "-o", assessment_file,
        ]

        repo_path = options.get("repo_path")
        if repo_path:
            cmd.extend(["--cd", repo_path])

        cmd.append("-")  # read prompt from stdin

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return ReviewResult(
                verdict="ERROR",
                raw_output=f"Timeout after {timeout}s",
                reviewer=self.name,
                duration_seconds=duration,
            )

        duration = time.time() - start_time

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
            return ReviewResult(
                verdict="ERROR",
                raw_output=f"Codex CLI failed: {error_msg}",
                reviewer=self.name,
                duration_seconds=duration,
            )

        try:
            with open(assessment_file, "r") as f:
                raw_output = f.read()
        except FileNotFoundError:
            return ReviewResult(
                verdict="ERROR",
                raw_output="Codex did not produce output file",
                reviewer=self.name,
                duration_seconds=duration,
            )

        result = self.parse_output(raw_output)
        result.duration_seconds = duration
        return result
