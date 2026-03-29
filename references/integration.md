# Review Result Integration Guide

Instructions for Claude Code when processing external review results.

## Core Principle

Do NOT blindly adopt external review findings. You must independently verify
each finding before presenting it to the user.

## Process

1. Read the external assessment
2. For each finding:
   a. Inspect the actual code yourself
   b. Determine if the finding is valid based on your own analysis
   c. Keep only findings that survive your independent verification
3. Highlight where the external reviewer found something you missed
4. Discard findings that are:
   - Incorrect or based on misunderstanding the code
   - Style-only concerns
   - Duplicates of other findings
   - Generic advice not specific to the actual code

## Output Format

Present findings to the user as:

### Review Summary
- **Reviewer:** [codex/opencode]
- **Verdict:** [APPROVED/NEEDS_REVISION]
- **Duration:** [Xs]

### Verified Findings
[Only findings you independently confirmed]

### Disputed Findings
[Findings you disagree with, including your reasoning]

### Assessment
[Your synthesized recommendation]
