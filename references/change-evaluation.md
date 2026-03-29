# Change Evaluation Guide

## Severity Levels

### CRITICAL
- Security vulnerabilities (injection, auth bypass, data exposure)
- Data loss or corruption risks
- Crashes or infinite loops in production paths

### MAJOR
- Logic errors that produce wrong results
- Missing error handling for likely failure cases
- Performance issues (O(n²) where O(n) is straightforward)
- Race conditions or concurrency bugs

### MINOR
- Missing edge case handling for unlikely scenarios
- Suboptimal but correct implementations
- Minor readability issues that affect correctness understanding

## What to Ignore
- Code style and formatting preferences
- Naming conventions (unless misleading)
- Comment presence or absence
- Import ordering
- Whitespace
