import os
import shutil
import subprocess
import time

from scripts.adapters.base import ReviewerAdapter, ReviewResult


class OpencodeAdapter(ReviewerAdapter):
    name = "opencode"

    def is_available(self) -> bool:
        return shutil.which("opencode") is not None

    def invoke(self, prompt: str, options: dict) -> ReviewResult:
        timeout = options.get("timeout", 500)
        output_dir = options.get("output_dir", "/tmp/multi-code-review")
        os.makedirs(output_dir, exist_ok=True)

        # Write prompt to file for opencode to read via --file
        prompt_file = os.path.join(output_dir, "opencode-prompt.md")
        with open(prompt_file, "w") as f:
            f.write(prompt)

        cmd = [
            "opencode", "run",
            "Follow the review instructions in the attached file exactly. "
            "You MUST end your response with structured FINDING and VERDICT lines as specified.",
            "--file", prompt_file,
        ]

        diff_file = options.get("diff_file")
        if diff_file:
            cmd.extend(["--file", diff_file])

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
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
                raw_output=f"opencode CLI failed: {error_msg}",
                reviewer=self.name,
                duration_seconds=duration,
            )

        # Parse only stdout for verdict inference to avoid stderr noise
        # (e.g. "critical config cache miss") polluting heuristic matching
        result = self.parse_output(proc.stdout)
        result.duration_seconds = duration

        # Append stderr to raw_output for debugging, after parsing
        if proc.stderr.strip():
            result.raw_output += "\n\n--- stderr ---\n" + proc.stderr.strip()

        return result
