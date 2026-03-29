# Code Review Request

You are an independent code reviewer. Review the following code changes
and provide a structured assessment.

## Repository
$repo_path

## Scope
$scope_description

## Code Changes
$diff_content_or_file_reference

## Host Context
$host_context

## Review Instructions
- Focus on: bugs, security issues, performance problems, logic errors
- Ignore: code style, formatting, naming preferences
- For each finding, provide severity (CRITICAL/MAJOR/MINOR) and a concrete suggestion

## Severity Guide
- CRITICAL: Security vulnerabilities, data loss/corruption risks, crashes in production paths
- MAJOR: Logic errors, missing error handling for likely failures, performance issues, race conditions
- MINOR: Missing edge case handling for unlikely scenarios, suboptimal but correct implementations

## Output Format
For each issue found:
FINDING-<N>: <SEVERITY>
Description: <what is wrong>
Suggestion: <how to fix>

End with:
VERDICT: APPROVED or VERDICT: NEEDS_REVISION
