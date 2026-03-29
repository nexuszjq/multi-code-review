#!/usr/bin/env bash
# Example: post-commit hook for multi-code-review
# Add this to your Claude Code settings.json hooks configuration.
#
# Usage in settings.json:
# {
#   "hooks": {
#     "PostToolUse": [
#       {
#         "matcher": "Bash",
#         "pattern": "git commit",
#         "command": "bash <skill-path>/hooks/post-commit-review.sh"
#       }
#     ]
#   }
# }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Require Python 3.10+ (review_engine.py uses X | None type syntax)
PYTHON=${MULTI_CODE_REVIEW_PYTHON:-python3}
if ! "$PYTHON" -c "import sys; assert sys.version_info >= (3, 10)" 2>/dev/null; then
  echo "multi-code-review: Python 3.10+ required (found: $("$PYTHON" --version 2>&1))" >&2
  echo "Set MULTI_CODE_REVIEW_PYTHON to a 3.10+ interpreter." >&2
  exit 0  # Don't break the hook, just skip
fi

# Detect initial commit (no parent) and adjust range accordingly
if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
  RANGE="HEAD~1..HEAD"
else
  # First commit — review everything in this commit
  EMPTY_TREE=$(git hash-object -t tree /dev/null)
  RANGE="${EMPTY_TREE}..HEAD"
fi

"$PYTHON" "$SCRIPT_DIR/scripts/review_engine.py" \
  --range "$RANGE" \
  --output-only
