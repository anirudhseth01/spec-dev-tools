"""Review findings and report structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReviewSeverity(Enum):
    """Severity levels for review comments."""

    ERROR = "error"        # Must fix before merge
    WARNING = "warning"    # Should fix, but not blocking
    SUGGESTION = "suggestion"  # Nice to have improvements

    @property
    def blocks_merge(self) -> bool:
        """Whether this severity should block a merge."""
        return self == ReviewSeverity.ERROR

    @property
    def score(self) -> int:
        """Numeric score for sorting (higher = more severe)."""
        scores = {
            ReviewSeverity.ERROR: 100,
            ReviewSeverity.WARNING: 50,
            ReviewSeverity.SUGGESTION: 20,
        }
        return scores.get(self, 0)


class ReviewCategory(Enum):
    """Categories of review comments."""

    STYLE = "style"              # Code style and conventions
    LOGIC = "logic"              # Logic errors or issues
    PERFORMANCE = "performance"  # Performance concerns
    SECURITY = "security"        # Security issues
    SPEC_COMPLIANCE = "spec_compliance"  # Spec requirement compliance
    BEST_PRACTICE = "best_practice"  # Best practices and anti-patterns
    DOCUMENTATION = "documentation"  # Missing or incorrect docs
    MAINTAINABILITY = "maintainability"  # Code maintainability concerns
    ERROR_HANDLING = "error_handling"  # Error handling issues
    TESTING = "testing"          # Test coverage or quality


@dataclass
class ReviewComment:
    """A code review comment."""

    id: str
    file_path: str
    message: str
    severity: ReviewSeverity
    category: ReviewCategory
    line_number: int | None = None
    end_line: int | None = None
    column: int | None = None
    suggestion: str = ""  # Suggested fix or improvement
    code_snippet: str = ""
    checker: str = ""  # Which checker generated this
    confidence: float = 1.0  # 0.0 to 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line_number:
            if self.end_line and self.end_line != self.line_number:
                return f"{self.file_path}:{self.line_number}-{self.end_line}"
            return f"{self.file_path}:{self.line_number}"
        return self.file_path

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "column": self.column,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
            "checker": self.checker,
            "confidence": self.confidence,
        }


@dataclass
class SpecComplianceStatus:
    """Status of a spec requirement compliance check."""

    requirement: str
    status: str  # "pass", "fail", "partial", "not_implemented"
    details: str = ""
    file_path: str = ""
    related_comments: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    """Complete code review report."""

    comments: list[ReviewComment] = field(default_factory=list)
    files_reviewed: int = 0
    review_duration_ms: int = 0
    spec_compliance: list[SpecComplianceStatus] = field(default_factory=list)
    summary_notes: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Count of error comments."""
        return sum(1 for c in self.comments if c.severity == ReviewSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warning comments."""
        return sum(1 for c in self.comments if c.severity == ReviewSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        """Count of suggestion comments."""
        return sum(1 for c in self.comments if c.severity == ReviewSeverity.SUGGESTION)

    @property
    def has_blocking_issues(self) -> bool:
        """Check if there are any merge-blocking issues."""
        return any(c.severity.blocks_merge for c in self.comments)

    @property
    def blocking_comments(self) -> list[ReviewComment]:
        """Get all merge-blocking comments."""
        return [c for c in self.comments if c.severity.blocks_merge]

    @property
    def compliance_score(self) -> float:
        """Calculate spec compliance score (0.0 to 1.0)."""
        if not self.spec_compliance:
            return 1.0
        passed = sum(1 for s in self.spec_compliance if s.status == "pass")
        return passed / len(self.spec_compliance)

    def get_comments_by_severity(self, severity: ReviewSeverity) -> list[ReviewComment]:
        """Get comments filtered by severity."""
        return [c for c in self.comments if c.severity == severity]

    def get_comments_by_category(self, category: ReviewCategory) -> list[ReviewComment]:
        """Get comments filtered by category."""
        return [c for c in self.comments if c.category == category]

    def get_comments_by_file(self, file_path: str) -> list[ReviewComment]:
        """Get comments for a specific file."""
        return [c for c in self.comments if c.file_path == file_path]

    def to_summary(self) -> str:
        """Generate a short summary string."""
        status = "PASSED" if not self.has_blocking_issues else "NEEDS CHANGES"
        blocking = len(self.blocking_comments)
        return (
            f"Code Review: {status} "
            f"({self.error_count} errors, {self.warning_count} warnings, "
            f"{self.suggestion_count} suggestions)"
            + (f" - {blocking} blocking issues" if blocking else "")
        )

    def to_markdown(self) -> str:
        """Generate full markdown report."""
        lines = ["# Code Review Report\n"]

        # Summary
        lines.append("## Summary")
        lines.append(f"- **Status:** {'NEEDS CHANGES' if self.has_blocking_issues else 'APPROVED'}")
        lines.append(f"- **Files reviewed:** {self.files_reviewed}")
        lines.append(f"- **Total comments:** {len(self.comments)} "
                    f"({self.error_count} errors, {self.warning_count} warnings, "
                    f"{self.suggestion_count} suggestions)")
        if self.spec_compliance:
            lines.append(f"- **Spec compliance:** {self.compliance_score:.0%}")
        lines.append("")

        # Summary notes
        if self.summary_notes:
            lines.append("## Overall Notes")
            for note in self.summary_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Errors (blocking)
        errors = self.get_comments_by_severity(ReviewSeverity.ERROR)
        if errors:
            lines.append("## Errors (Must Fix)\n")
            for i, comment in enumerate(errors, 1):
                lines.append(f"### {i}. {comment.category.value.replace('_', ' ').title()}")
                lines.append(f"**Location:** `{comment.location}`")
                lines.append(f"**Issue:** {comment.message}")
                if comment.code_snippet:
                    lines.append(f"**Code:**\n```\n{comment.code_snippet}\n```")
                if comment.suggestion:
                    lines.append(f"**Suggestion:** {comment.suggestion}")
                lines.append("")

        # Warnings
        warnings = self.get_comments_by_severity(ReviewSeverity.WARNING)
        if warnings:
            lines.append("## Warnings\n")
            for i, comment in enumerate(warnings, 1):
                lines.append(f"### {i}. {comment.category.value.replace('_', ' ').title()}")
                lines.append(f"**Location:** `{comment.location}`")
                lines.append(f"**Issue:** {comment.message}")
                if comment.suggestion:
                    lines.append(f"**Suggestion:** {comment.suggestion}")
                lines.append("")

        # Suggestions (condensed)
        suggestions = self.get_comments_by_severity(ReviewSeverity.SUGGESTION)
        if suggestions:
            lines.append("## Suggestions\n")
            lines.append("| Location | Category | Suggestion |")
            lines.append("|----------|----------|------------|")
            for comment in suggestions:
                category = comment.category.value.replace('_', ' ').title()
                lines.append(f"| `{comment.location}` | {category} | {comment.message} |")
            lines.append("")

        # Spec compliance
        if self.spec_compliance:
            lines.append("## Spec Compliance\n")
            lines.append("| Requirement | Status | Details |")
            lines.append("|-------------|--------|---------|")
            for status in self.spec_compliance:
                status_icon = {
                    "pass": "PASS",
                    "fail": "FAIL",
                    "partial": "PARTIAL",
                    "not_implemented": "NOT IMPLEMENTED",
                }.get(status.status, "UNKNOWN")
                lines.append(f"| {status.requirement} | {status_icon} | {status.details} |")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "summary": self.to_summary(),
            "files_reviewed": self.files_reviewed,
            "review_duration_ms": self.review_duration_ms,
            "has_blocking_issues": self.has_blocking_issues,
            "comments": [c.to_dict() for c in self.comments],
            "counts": {
                "error": self.error_count,
                "warning": self.warning_count,
                "suggestion": self.suggestion_count,
                "total": len(self.comments),
            },
            "compliance_score": self.compliance_score,
            "spec_compliance": [
                {
                    "requirement": s.requirement,
                    "status": s.status,
                    "details": s.details,
                }
                for s in self.spec_compliance
            ],
            "summary_notes": self.summary_notes,
        }
