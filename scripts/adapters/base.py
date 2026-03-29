from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Finding:
    id: str
    severity: str
    description: str
    suggestion: str


@dataclass
class ReviewResult:
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    raw_output: str = ""
    reviewer: str = ""
    duration_seconds: float = 0.0


class ReviewerAdapter(ABC):
    name: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the CLI is installed."""

    @abstractmethod
    def invoke(self, prompt: str, options: dict) -> ReviewResult:
        """Invoke the reviewer CLI, return structured result."""

    def parse_output(self, raw_output: str) -> ReviewResult:
        """Parse CLI output into unified format.

        Default implementation extracts FINDING-N and VERDICT patterns.
        Subclasses can override for custom parsing.
        """
        import re

        findings = []
        # Tolerant pattern: allows extra whitespace, blank lines, markdown formatting
        finding_pattern = re.compile(
            r"FINDING[- ]?(\d+)\s*[:：]\s*(CRITICAL|MAJOR|MINOR)\s*\n"
            r"\s*(?:\*{0,2})Description(?:\*{0,2})\s*[:：]\s*(.*?)\n"
            r"\s*(?:\*{0,2})Suggestion(?:\*{0,2})\s*[:：]\s*(.*?)(?=\n\s*FINDING[- ]?\d|\n\s*VERDICT\s*[:：]|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        for match in finding_pattern.finditer(raw_output):
            findings.append(
                Finding(
                    id=f"FINDING-{match.group(1)}",
                    severity=match.group(2).upper(),
                    description=match.group(3).strip(),
                    suggestion=match.group(4).strip(),
                )
            )

        verdict_match = re.search(r"VERDICT\s*[:：]\s*(APPROVED|NEEDS_REVISION)", raw_output, re.IGNORECASE)
        if verdict_match:
            verdict = verdict_match.group(1).upper()
        else:
            # Fallback: infer verdict from findings or common phrases
            verdict = self._infer_verdict(raw_output, findings)

        return ReviewResult(
            verdict=verdict,
            findings=findings,
            raw_output=raw_output,
            reviewer=self.name,
        )

    @staticmethod
    def _infer_verdict(raw_output: str, findings: list["Finding"]) -> str:
        """Infer a verdict when no explicit VERDICT line is found."""
        import re

        text_lower = raw_output.lower()

        # If there are CRITICAL or MAJOR findings, it needs revision
        if any(f.severity in ("CRITICAL", "MAJOR") for f in findings):
            return "NEEDS_REVISION"

        # Look for common approval/rejection phrases
        negated_approval = re.search(
            r"\b(?:not|cannot|can't|don't|do not|should not|shouldn't)\s+(?:be\s+)?approve",
            text_lower,
        )
        approval_phrases = [
            r"\blooks?\s+good\b", r"\bno\s+issues?\s+found\b",
            r"\bapproved?\b", r"\blgtm\b",
            r"\bno\s+(?:major\s+)?(?:problems?|concerns?|bugs?)\b",
        ]
        rejection_phrases = [
            r"\bneeds?\s+(?:revision|changes?|fix(?:es|ing)?)\b",
            r"(?<!\bno\s)(?<!\bno\s\s)(?<!\bwithout\s)\bcritical\b",
            r"(?<!\bno\s)(?<!\bno\s\s)(?<!\bwithout\s)\bmajor\s+(?:issue|bug|problem)\b",
            r"\bmust\s+(?:be\s+)?fix", r"\bsecurity\s+vulnerabilit",
        ]

        # Also detect negated rejection phrases as approval signals
        negated_rejection = re.search(
            r"\b(?:no|without|free\s+of)\s+(?:critical|major)\s+(?:issues?|problems?|bugs?|findings?)\b",
            text_lower,
        )

        approval_score = sum(1 for p in approval_phrases if re.search(p, text_lower))
        rejection_score = sum(1 for p in rejection_phrases if re.search(p, text_lower))

        # Negated rejection phrases count as approval
        if negated_rejection:
            approval_score += 1

        # Negated approval counts as rejection, not approval
        if negated_approval:
            approval_score = max(0, approval_score - 1)
            rejection_score += 1

        if rejection_score > 0 and rejection_score >= approval_score:
            return "NEEDS_REVISION"
        if approval_score > rejection_score:
            return "APPROVED"

        # If findings exist (all MINOR), still approve
        if findings:
            return "APPROVED"

        return "UNKNOWN"
