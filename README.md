# Multi Code Review

A Claude Code skill that invokes external AI CLIs (Codex, opencode) to independently review your code changes and plans.

## Features

- **Cross-AI Review** — Get a second opinion from Codex or opencode on your Claude Code work
- **Pluggable Architecture** — Easy to add new AI reviewers
- **Code & Plan Review** — Review git diffs or plan/design documents
- **Single-Round Review** — Quick one-shot review (multi-round coming soon)
- **Hook Support** — Auto-trigger reviews on git commit

## Prerequisites

Install at least one reviewer CLI:

```bash
# Codex (OpenAI)
npm install -g @openai/codex

# opencode
go install github.com/opencode-ai/opencode@latest
```

## Installation

```bash
npx skills add <your-github-username>/multi-code-review
```

## Usage

In Claude Code, use any of these triggers:

- `review code with codex`
- `review code with opencode`
- `multi code review`
- `/multi-code-review`

### CLI Usage

```bash
# Review staged changes with Codex
python3 scripts/review_engine.py --reviewer codex --staged

# Review working directory with opencode
python3 scripts/review_engine.py --reviewer opencode --working

# Review a git range
python3 scripts/review_engine.py --reviewer codex --range "main...HEAD"

# Review specific files
python3 scripts/review_engine.py --reviewer opencode --path src/main.py src/utils.py

# Review a plan document
python3 scripts/review_engine.py --reviewer codex --plan docs/design.md
```

### Hook Configuration

Add to your Claude Code `settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "pattern": "git commit",
        "command": "bash <skill-path>/hooks/post-commit-review.sh"
      }
    ]
  }
}
```

## Output

Review artifacts are saved to `$TMPDIR/multi-code-review/<timestamp>/` (or a custom path via `--output-dir`):

| File | Content |
|---|---|
| `prompt.md` | Full prompt sent to the reviewer |
| `assessment.md` | Reviewer's assessment |
| `result.json` | Structured result (verdict, findings, metadata) |

## License

MIT