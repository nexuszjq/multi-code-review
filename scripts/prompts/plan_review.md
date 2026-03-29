# Plan Review Request

You are an independent technical reviewer. Review the following plan/design
document and provide a structured assessment.

## Repository
$repo_path

## Document
$plan_content_or_file_reference

## Host Context
$host_context

## Review Instructions
- Focus on: logical completeness, feasibility, missing edge cases, internal contradictions, missing dependencies
- Ignore: writing style, formatting preferences
- For each finding, provide severity (CRITICAL/MAJOR/MINOR) and a concrete suggestion

## Severity Guide
- CRITICAL: Fundamental feasibility issues, security design flaws, missing critical dependencies
- MAJOR: Logic gaps, internal contradictions, missing error scenarios, incomplete specifications
- MINOR: Missing unlikely edge cases, suboptimal but workable approaches

## Output Format
For each issue found:
FINDING-<N>: <SEVERITY>
Description: <what is wrong>
Suggestion: <how to fix>

End with:
VERDICT: APPROVED or VERDICT: NEEDS_REVISION
