import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from string import Template

# Support both `python3 scripts/review_engine.py` and `python3 -m scripts.review_engine`
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.adapters.base import ReviewerAdapter, ReviewResult
from scripts.adapters.codex import CodexAdapter
from scripts.adapters.opencode import OpencodeAdapter

INLINE_MAX_BYTES = 20 * 1024  # 20KB
DIFF_WARN_BYTES = 100 * 1024  # 100KB
SCRIPT_DIR = Path(__file__).parent
ADAPTERS = {"codex": CodexAdapter, "opencode": OpencodeAdapter}


def _run_git(cmd: list[str], repo_path: str) -> str:
    """Run a git command and return stdout, raising on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"git command failed: {' '.join(cmd)}\n{stderr}")
    return result.stdout


def collect_diff(mode: str, repo_path: str = ".", range_spec: str = "", paths: list[str] | None = None, include_untracked: bool = False) -> str:
    """Collect diff content based on the specified mode."""
    if mode == "staged":
        return _run_git(["git", "diff", "--cached", "--no-ext-diff"], repo_path)
    elif mode == "working":
        # Use fallback for repos without a HEAD commit
        try:
            diff_output = _run_git(["git", "diff", "HEAD", "--no-ext-diff"], repo_path)
        except RuntimeError as e:
            if "does not have any commits" in str(e) or "unknown revision" in str(e):
                # No HEAD yet (new repo before first commit)
                # Combine staged changes + unstaged working tree changes
                diff_output = _run_git(["git", "diff", "--cached", "--no-ext-diff"], repo_path)
                diff_output += _run_git(["git", "diff", "--no-ext-diff"], repo_path)
            else:
                raise

        # Include untracked files only when explicitly opted in
        if include_untracked:
            repo_root = _run_git(["git", "rev-parse", "--show-toplevel"], repo_path).strip()
            untracked_out = _run_git(["git", "ls-files", "--others", "--exclude-standard"], repo_root)
            for filepath in untracked_out.strip().splitlines():
                if not filepath:
                    continue
                full_path = os.path.join(repo_root, filepath)
                # Safety: skip symlinks and non-regular files
                if os.path.islink(full_path) or not os.path.isfile(full_path):
                    continue
                # Safety: ensure resolved path stays under repo root
                resolved = os.path.realpath(full_path)
                if not resolved.startswith(os.path.realpath(repo_root) + os.sep):
                    continue
                try:
                    with open(full_path, "r") as f:
                        lines = f.readlines()
                    line_count = len(lines)
                    hunk = f"@@ -0,0 +1,{line_count} @@\n"
                    added_lines = "".join(f"+{line}" if line.endswith("\n") else f"+{line}\n\\ No newline at end of file\n" for line in lines)
                    diff_output += f"\n--- /dev/null\n+++ b/{filepath}\n{hunk}{added_lines}"
                except UnicodeDecodeError:
                    print(f"Warning: skipping binary file: {filepath}", file=sys.stderr)
                except FileNotFoundError:
                    print(f"Warning: skipping missing file: {filepath}", file=sys.stderr)
                except OSError as e:
                    print(f"Warning: skipping unreadable file: {filepath} ({e})", file=sys.stderr)

        return diff_output
    elif mode == "range":
        return _run_git(["git", "diff", range_spec, "--no-ext-diff"], repo_path)
    elif mode == "path":
        try:
            repo_root = os.path.realpath(_run_git(["git", "rev-parse", "--show-toplevel"], repo_path).strip())
        except RuntimeError:
            # Fall back to repo_path-based containment when git is unavailable
            repo_root = os.path.realpath(repo_path)
        contents = []
        for p in (paths or []):
            real_p = os.path.realpath(p)
            if not real_p.startswith(repo_root + os.sep) and real_p != repo_root:
                raise RuntimeError(f"Path is outside the repository: {p}")
            if not os.path.exists(p):
                raise RuntimeError(f"File not found: {p}")
            if not os.path.isfile(p):
                raise RuntimeError(f"Not a regular file: {p}")
            try:
                with open(p, "r") as f:
                    contents.append(f"--- {p} ---\n{f.read()}")
            except UnicodeDecodeError:
                raise RuntimeError(f"Cannot read binary file: {p}")
            except OSError as e:
                raise RuntimeError(f"Cannot read file {p}: {e}")
        return "\n\n".join(contents)
    else:
        raise ValueError(f"Unknown diff mode: {mode}")


def build_prompt(template_name: str, diff_content: str, output_dir: str, repo_path: str = ".", host_context: str = "") -> tuple[str, str | None]:
    """Build the review prompt from a template and diff content.

    Returns (prompt_text, diff_file_path_or_none).
    """
    template_path = SCRIPT_DIR / "prompts" / template_name
    template = template_path.read_text()

    diff_size = len(diff_content.encode("utf-8"))
    if diff_size > DIFF_WARN_BYTES:
        print(f"Warning: diff is {diff_size // 1024}KB (>{DIFF_WARN_BYTES // 1024}KB). Consider using --path to narrow scope.", file=sys.stderr)

    spill_file_path = None
    if diff_size <= INLINE_MAX_BYTES:
        content_ref = diff_content
    else:
        is_plan = template_name == "plan_review.md"
        spill_name = "document.md" if is_plan else "diff.patch"
        spill_label = "Document" if is_plan else "Diff"
        spill_file_path = os.path.join(output_dir, spill_name)
        _write_private(spill_file_path, diff_content)
        content_ref = f"[{spill_label} too large to inline ({diff_size // 1024}KB). See file: {spill_file_path}]"

    tmpl = Template(template)
    if template_name == "code_review.md":
        scope = f"Code changes ({len(diff_content.splitlines())} lines)"
        prompt = tmpl.safe_substitute(
            repo_path=os.path.abspath(repo_path),
            scope_description=scope,
            diff_content_or_file_reference=content_ref,
            host_context=host_context or "No additional context provided.",
        )
    else:
        prompt = tmpl.safe_substitute(
            repo_path=os.path.abspath(repo_path),
            plan_content_or_file_reference=content_ref,
            host_context=host_context or "No additional context provided.",
        )

    return prompt, spill_file_path


def get_adapters(reviewer_name: str | None = None) -> list[ReviewerAdapter]:
    """Get adapter(s), auto-detecting if not specified. Returns ordered list for fallback."""
    if reviewer_name:
        if reviewer_name not in ADAPTERS:
            print(f"Error: Unknown reviewer '{reviewer_name}'. Available: {', '.join(ADAPTERS.keys())}", file=sys.stderr)
            return []
        adapter = ADAPTERS[reviewer_name]()
        if not adapter.is_available():
            install_cmds = {"codex": "npm install -g @openai/codex", "opencode": "go install github.com/opencode-ai/opencode@latest"}
            print(f"Error: {reviewer_name} CLI not found. Install: {install_cmds.get(reviewer_name, 'unknown')}", file=sys.stderr)
            return []
        return [adapter]

    available = []
    for name, cls in ADAPTERS.items():
        adapter = cls()
        if adapter.is_available():
            available.append(adapter)

    if not available:
        print("Error: No reviewer CLI found. Install one of:", file=sys.stderr)
        print("  Codex:    npm install -g @openai/codex", file=sys.stderr)
        print("  opencode: go install github.com/opencode-ai/opencode@latest", file=sys.stderr)

    return available


def _write_private(path: str, content: str):
    """Write a file with owner-only permissions (0600)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)


def save_artifacts(output_dir: str, prompt: str, result: ReviewResult):
    """Save review artifacts to the output directory."""
    os.makedirs(output_dir, mode=0o700, exist_ok=True)

    _write_private(os.path.join(output_dir, "prompt.md"), prompt)
    _write_private(os.path.join(output_dir, "assessment.md"), result.raw_output)

    result_data = {
        "verdict": result.verdict,
        "findings": [
            {"id": f.id, "severity": f.severity, "description": f.description, "suggestion": f.suggestion}
            for f in result.findings
        ],
        "reviewer": result.reviewer,
        "duration_seconds": result.duration_seconds,
        "timestamp": datetime.now().isoformat(),
    }
    _write_private(os.path.join(output_dir, "result.json"), json.dumps(result_data, indent=2))


def _collect_content(args) -> tuple[str, str]:
    """Collect review content based on CLI args. Returns (content, template_name)."""
    if args.staged:
        return collect_diff("staged"), "code_review.md"
    elif args.working:
        return collect_diff("working", include_untracked=args.include_untracked), "code_review.md"
    elif args.range:
        return collect_diff("range", range_spec=args.range), "code_review.md"
    elif args.path:
        return collect_diff("path", paths=args.path), "code_review.md"
    elif args.plan:
        try:
            repo_root = os.path.realpath(_run_git(["git", "rev-parse", "--show-toplevel"], ".").strip())
        except RuntimeError:
            repo_root = None
        if repo_root is not None:
            real_plan = os.path.realpath(args.plan)
            if not real_plan.startswith(repo_root + os.sep) and real_plan != repo_root:
                raise RuntimeError(f"Plan path is outside the repository: {args.plan}")
        try:
            with open(args.plan, "r") as f:
                return f.read(), "plan_review.md"
        except OSError as e:
            raise RuntimeError(f"Cannot read plan file: {e}") from e
    else:
        print("Error: No review source specified.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Multi Code Review — cross-AI code review engine")
    parser.add_argument("--reviewer", choices=list(ADAPTERS.keys()), help="Reviewer to use (auto-detect if omitted)")
    parser.add_argument("--timeout", type=int, default=500, help="Timeout in seconds (default: 500)")
    parser.add_argument("--output-only", action="store_true", help="Only output result file path (for hook mode)")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory for review artifacts")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--staged", action="store_true", help="Review staged changes")
    source.add_argument("--working", action="store_true", help="Review working directory changes")
    source.add_argument("--range", type=str, help="Review a git range (e.g., main...HEAD)")
    source.add_argument("--path", nargs="+", help="Review specific file(s)")
    source.add_argument("--plan", type=str, help="Review a plan/document file")

    parser.add_argument("--include-untracked", action="store_true", help="Include untracked files in --working mode (off by default to avoid leaking secrets)")
    parser.add_argument("--context", type=str, default="", help="Additional context for the reviewer")

    args = parser.parse_args()

    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        default_output_base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "multi-code-review")
        output_dir = os.path.join(default_output_base, timestamp)
    os.makedirs(output_dir, mode=0o700, exist_ok=True)

    try:
        diff_content, template = _collect_content(args)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not diff_content.strip():
        if args.working and not args.include_untracked:
            # Check if there are untracked files the user might want to include
            try:
                repo_root = _run_git(["git", "rev-parse", "--show-toplevel"], ".").strip()
                untracked = _run_git(["git", "ls-files", "--others", "--exclude-standard"], repo_root).strip()
                if untracked:
                    print(
                        "No tracked changes to review, but untracked files exist.\n"
                        "Re-run with --include-untracked to include them.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            except RuntimeError:
                pass
        print("No changes to review.", file=sys.stderr)
        sys.exit(0)

    adapters = get_adapters(args.reviewer)
    if not adapters:
        error_result = ReviewResult(
            verdict="ERROR",
            raw_output="No reviewer CLI available",
            reviewer="none",
        )
        save_artifacts(output_dir, "", error_result)
        if args.output_only:
            print(os.path.join(output_dir, "result.json"))
            sys.exit(0)
        sys.exit(1)

    try:
        repo_path = _run_git(["git", "rev-parse", "--show-toplevel"], ".").strip()
    except RuntimeError:
        repo_path = os.getcwd()
    prompt, diff_file_path = build_prompt(template, diff_content, output_dir, repo_path=repo_path, host_context=args.context)

    options = {"timeout": args.timeout, "output_dir": output_dir, "repo_path": repo_path}
    if diff_file_path:
        options["diff_file"] = diff_file_path

    # Try each adapter in order; fall back to next on ERROR or UNKNOWN
    result = None
    for adapter in adapters:
        result = adapter.invoke(prompt, options)
        if result.verdict not in ("ERROR", "UNKNOWN"):
            break
        print(f"Warning: {adapter.name} returned {result.verdict}, trying next reviewer...", file=sys.stderr)

    save_artifacts(output_dir, prompt, result)

    # In --output-only mode, always exit 0 so hooks don't fail;
    # the caller reads result.json to check the verdict.
    if args.output_only:
        print(os.path.join(output_dir, "result.json"))
        sys.exit(0)

    print(f"\nReviewer: {result.reviewer}")
    print(f"Verdict: {result.verdict}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    if result.findings:
        print(f"\nFindings ({len(result.findings)}):")
        for f in result.findings:
            print(f"  [{f.severity}] {f.id}: {f.description}")
            print(f"    Suggestion: {f.suggestion}")
    print(f"\nFull results: {output_dir}")

    sys.exit(1 if result.verdict in ("ERROR", "UNKNOWN") else 0)


if __name__ == "__main__":
    main()
