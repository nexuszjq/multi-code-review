---
name: multi-code-review
description: Cross-AI code review — invoke Codex or opencode to review code changes and plans
triggers:
  - "review code with codex"
  - "review code with opencode"
  - "multi code review"
slash_command: /multi-code-review
---

# Multi Code Review

Invoke an external AI reviewer (Codex or opencode) to provide an independent
assessment of code changes or plan documents.

## When to Activate

This skill activates when the user says:
- "review code with codex" or "review code with opencode"
- "multi code review"
- `/multi-code-review`

Do NOT activate on generic phrases like "review code", "code review", or "check my code".

## Workflow

### Step 1: Determine Scope

Ask the user what to review if not specified:
- Staged changes (`--staged`)
- Working directory changes (`--working`)
- A git range (`--range main...HEAD`)
- Specific files (`--path file1.py file2.py`)
- A plan document (`--plan docs/plan.md`)

If the user just finished coding and says "review code with codex", default to `--working`.

### Step 2: Generate Host Context

Before invoking the external reviewer, document:
- What changed and why (from conversation context)
- Any constraints or assumptions
- Specific concerns the user mentioned

### Step 3: Invoke External Review

Run the review engine via a subagent (to keep main context clean):

```bash
python3 <skill-path>/scripts/review_engine.py \
  --reviewer <codex|opencode> \
  --<scope-flag> \
  --context "<host context summary>"
```

Where `<skill-path>` is the directory containing this SKILL.md.

### Step 4: Analyze Results

Read the output files from the result directory:
- `result.json` for structured findings
- `assessment.md` for the full review text

Follow the guidance in `references/integration.md`:
1. Independently verify each finding by inspecting the actual code
2. Keep only findings that survive your own verification
3. Present verified findings, disputed findings, and your synthesis

### Step 5: Present to User

Format the review as described in `references/integration.md`:
- Review summary (reviewer, verdict, duration)
- Verified findings with severity
- Any disputed findings with your reasoning
- Overall assessment and recommendation

## Hook Configuration

Users can configure automatic review via Claude Code hooks in `settings.json`.
See the `hooks/` directory for example configurations.

Example post-commit hook:
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

When triggered via hook (`--output-only`), read the result.json path from stdout
and present findings to the user.
