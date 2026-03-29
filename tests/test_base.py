# tests/test_base.py
from scripts.adapters.base import Finding, ReviewResult


def test_finding_creation():
    f = Finding(id="FINDING-1", severity="CRITICAL", description="SQL injection", suggestion="Use parameterized queries")
    assert f.id == "FINDING-1"
    assert f.severity == "CRITICAL"
    assert f.description == "SQL injection"
    assert f.suggestion == "Use parameterized queries"


def test_review_result_approved():
    result = ReviewResult(
        verdict="APPROVED",
        findings=[],
        raw_output="VERDICT: APPROVED",
        reviewer="codex",
        duration_seconds=5.2,
    )
    assert result.verdict == "APPROVED"
    assert result.findings == []
    assert result.reviewer == "codex"


def test_review_result_needs_revision():
    f = Finding(id="FINDING-1", severity="MAJOR", description="Missing null check", suggestion="Add guard clause")
    result = ReviewResult(
        verdict="NEEDS_REVISION",
        findings=[f],
        raw_output="raw",
        reviewer="opencode",
        duration_seconds=10.0,
    )
    assert result.verdict == "NEEDS_REVISION"
    assert len(result.findings) == 1
    assert result.findings[0].severity == "MAJOR"


def test_review_result_error():
    result = ReviewResult(
        verdict="ERROR",
        findings=[],
        raw_output="timeout",
        reviewer="codex",
        duration_seconds=120.0,
    )
    assert result.verdict == "ERROR"


from scripts.adapters.base import ReviewerAdapter


class MockAdapter(ReviewerAdapter):
    name = "mock"

    def is_available(self) -> bool:
        return True

    def invoke(self, prompt: str, options: dict) -> ReviewResult:
        return ReviewResult(verdict="APPROVED", reviewer=self.name)


def test_parse_output_approved():
    adapter = MockAdapter()
    raw = "Everything looks good.\n\nVERDICT: APPROVED"
    result = adapter.parse_output(raw)
    assert result.verdict == "APPROVED"
    assert result.findings == []


def test_parse_output_with_findings():
    adapter = MockAdapter()
    raw = (
        "FINDING-1: CRITICAL\n"
        "Description: SQL injection in query builder\n"
        "Suggestion: Use parameterized queries\n"
        "FINDING-2: MINOR\n"
        "Description: Unused import\n"
        "Suggestion: Remove unused import\n"
        "VERDICT: NEEDS_REVISION"
    )
    result = adapter.parse_output(raw)
    assert result.verdict == "NEEDS_REVISION"
    assert len(result.findings) == 2
    assert result.findings[0].id == "FINDING-1"
    assert result.findings[0].severity == "CRITICAL"
    assert result.findings[1].id == "FINDING-2"
    assert result.findings[1].severity == "MINOR"


def test_parse_output_no_verdict_unknown():
    adapter = MockAdapter()
    raw = "Some unstructured review text without a verdict."
    result = adapter.parse_output(raw)
    assert result.verdict == "UNKNOWN"
    assert result.findings == []


def test_infer_verdict_from_approval_phrases():
    adapter = MockAdapter()
    raw = "The code looks good. No issues found. LGTM."
    result = adapter.parse_output(raw)
    assert result.verdict == "APPROVED"


def test_infer_verdict_from_rejection_phrases():
    adapter = MockAdapter()
    raw = "There is a critical security vulnerability that must be fixed immediately."
    result = adapter.parse_output(raw)
    assert result.verdict == "NEEDS_REVISION"


def test_infer_verdict_from_findings_severity():
    """If findings have MAJOR severity but no explicit VERDICT, infer NEEDS_REVISION."""
    adapter = MockAdapter()
    raw = (
        "FINDING-1: MAJOR\n"
        "Description: Missing null check\n"
        "Suggestion: Add guard clause\n"
    )
    result = adapter.parse_output(raw)
    assert result.verdict == "NEEDS_REVISION"


def test_infer_verdict_minor_findings_only():
    """Minor-only findings without explicit VERDICT should infer APPROVED."""
    adapter = MockAdapter()
    raw = (
        "FINDING-1: MINOR\n"
        "Description: Unused variable\n"
        "Suggestion: Remove it\n"
    )
    result = adapter.parse_output(raw)
    assert result.verdict == "APPROVED"


def test_infer_verdict_negation_not_approved():
    """'not approved' or 'should not be approved' must NOT infer APPROVED."""
    adapter = MockAdapter()
    raw = "This should not be approved until the security issue is resolved."
    result = adapter.parse_output(raw)
    assert result.verdict == "NEEDS_REVISION"


def test_infer_verdict_negation_cannot_approve():
    """'cannot approve' must NOT infer APPROVED."""
    adapter = MockAdapter()
    raw = "I cannot approve this code in its current state."
    result = adapter.parse_output(raw)
    assert result.verdict == "NEEDS_REVISION"


def test_parse_output_tolerant_formatting():
    """Verify parser handles extra whitespace, markdown bold, and case variations."""
    adapter = MockAdapter()
    raw = (
        "FINDING 1: critical\n"
        "  **Description**: Buffer overflow in parser\n"
        "  **Suggestion**: Bounds check the input\n"
        "\n"
        "FINDING-2:  MAJOR\n"
        "Description：Missing null check\n"
        "Suggestion：Add guard clause\n"
        "\n"
        "Verdict: needs_revision"
    )
    result = adapter.parse_output(raw)
    assert result.verdict == "NEEDS_REVISION"
    assert len(result.findings) == 2
    assert result.findings[0].severity == "CRITICAL"
    assert result.findings[0].description == "Buffer overflow in parser"
    assert result.findings[1].severity == "MAJOR"
