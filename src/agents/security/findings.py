"""Security findings and report structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FindingSeverity(Enum):
    """Severity levels for security findings."""

    CRITICAL = "critical"  # Block deployment, immediate fix required
    HIGH = "high"          # Block PR, fix before merge
    MEDIUM = "medium"      # Warning, should fix soon
    LOW = "low"            # Informational, best practice
    INFO = "info"          # Suggestion for improvement

    @property
    def blocks_pr(self) -> bool:
        """Whether this severity should block a PR."""
        return self in (FindingSeverity.CRITICAL, FindingSeverity.HIGH)

    @property
    def blocks_deploy(self) -> bool:
        """Whether this severity should block deployment."""
        return self == FindingSeverity.CRITICAL

    @property
    def score(self) -> int:
        """Numeric score for sorting (higher = more severe)."""
        scores = {
            FindingSeverity.CRITICAL: 100,
            FindingSeverity.HIGH: 80,
            FindingSeverity.MEDIUM: 50,
            FindingSeverity.LOW: 20,
            FindingSeverity.INFO: 10,
        }
        return scores.get(self, 0)


class FindingCategory(Enum):
    """Categories of security findings."""

    SECRETS = "secrets"
    INJECTION = "injection"
    XSS = "xss"
    CRYPTO = "crypto"
    AUTH = "authentication"
    AUTHZ = "authorization"
    INPUT_VALIDATION = "input_validation"
    DATA_EXPOSURE = "data_exposure"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    COMPLIANCE = "compliance"
    OTHER = "other"


@dataclass
class Finding:
    """A security finding/vulnerability."""

    id: str
    title: str
    description: str
    severity: FindingSeverity
    category: FindingCategory
    file_path: str
    line_number: int | None = None
    column: int | None = None
    code_snippet: str = ""
    recommendation: str = ""
    cwe_id: str | None = None  # Common Weakness Enumeration ID
    owasp_category: str | None = None  # OWASP Top 10 category
    scanner: str = ""  # Which scanner found this
    confidence: float = 1.0  # 0.0 to 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line_number:
            return f"{self.file_path}:{self.line_number}"
        return self.file_path

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "category": self.category.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "code_snippet": self.code_snippet,
            "recommendation": self.recommendation,
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
            "scanner": self.scanner,
            "confidence": self.confidence,
        }


@dataclass
class SpecComplianceResult:
    """Result of checking a security spec requirement."""

    requirement: str
    status: str  # "pass", "fail", "partial", "not_found"
    details: str = ""
    related_findings: list[str] = field(default_factory=list)


@dataclass
class SecurityReport:
    """Complete security scan report."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    scan_duration_ms: int = 0
    mode: str = "lightweight"
    compliance_results: list[SpecComplianceResult] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        """Count of critical findings."""
        return sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Count of high findings."""
        return sum(1 for f in self.findings if f.severity == FindingSeverity.HIGH)

    @property
    def medium_count(self) -> int:
        """Count of medium findings."""
        return sum(1 for f in self.findings if f.severity == FindingSeverity.MEDIUM)

    @property
    def low_count(self) -> int:
        """Count of low findings."""
        return sum(1 for f in self.findings if f.severity == FindingSeverity.LOW)

    @property
    def has_blocking_issues(self) -> bool:
        """Check if there are any PR-blocking issues."""
        return any(f.severity.blocks_pr for f in self.findings)

    @property
    def has_deployment_blockers(self) -> bool:
        """Check if there are any deployment-blocking issues."""
        return any(f.severity.blocks_deploy for f in self.findings)

    @property
    def blocking_findings(self) -> list[Finding]:
        """Get all PR-blocking findings."""
        return [f for f in self.findings if f.severity.blocks_pr]

    @property
    def compliance_score(self) -> float:
        """Calculate compliance score (0.0 to 1.0)."""
        if not self.compliance_results:
            return 1.0
        passed = sum(1 for r in self.compliance_results if r.status == "pass")
        return passed / len(self.compliance_results)

    def get_findings_by_severity(self, severity: FindingSeverity) -> list[Finding]:
        """Get findings filtered by severity."""
        return [f for f in self.findings if f.severity == severity]

    def get_findings_by_category(self, category: FindingCategory) -> list[Finding]:
        """Get findings filtered by category."""
        return [f for f in self.findings if f.category == category]

    def to_summary(self) -> str:
        """Generate a short summary string."""
        status = "PASSED" if not self.has_blocking_issues else "FAILED"
        blocking = len(self.blocking_findings)
        return (
            f"Security Scan: {status} "
            f"({self.critical_count} critical, {self.high_count} high, "
            f"{self.medium_count} medium, {self.low_count} low)"
            + (f" - {blocking} blocking issues" if blocking else "")
        )

    def to_markdown(self) -> str:
        """Generate full markdown report."""
        lines = ["# Security Scan Report\n"]

        # Summary
        lines.append("## Summary")
        lines.append(f"- **Status:** {'FAILED' if self.has_blocking_issues else 'PASSED'}")
        lines.append(f"- **Files scanned:** {self.files_scanned}")
        lines.append(f"- **Issues found:** {len(self.findings)} "
                    f"({self.critical_count} critical, {self.high_count} high, "
                    f"{self.medium_count} medium, {self.low_count} low)")
        if self.compliance_results:
            lines.append(f"- **Spec compliance:** {self.compliance_score:.0%}")
        lines.append("")

        # Critical issues
        critical = self.get_findings_by_severity(FindingSeverity.CRITICAL)
        if critical:
            lines.append("## Critical Issues\n")
            for i, finding in enumerate(critical, 1):
                lines.append(f"### {i}. {finding.title}")
                lines.append(f"**Location:** `{finding.location}`")
                lines.append(f"**Description:** {finding.description}")
                if finding.code_snippet:
                    lines.append(f"**Code:**\n```\n{finding.code_snippet}\n```")
                if finding.recommendation:
                    lines.append(f"**Recommendation:** {finding.recommendation}")
                lines.append("")

        # High issues
        high = self.get_findings_by_severity(FindingSeverity.HIGH)
        if high:
            lines.append("## High Issues\n")
            for i, finding in enumerate(high, 1):
                lines.append(f"### {i}. {finding.title}")
                lines.append(f"**Location:** `{finding.location}`")
                lines.append(f"**Description:** {finding.description}")
                if finding.recommendation:
                    lines.append(f"**Recommendation:** {finding.recommendation}")
                lines.append("")

        # Medium/Low issues (condensed)
        medium_low = (
            self.get_findings_by_severity(FindingSeverity.MEDIUM) +
            self.get_findings_by_severity(FindingSeverity.LOW)
        )
        if medium_low:
            lines.append("## Other Issues\n")
            lines.append("| Severity | Location | Issue |")
            lines.append("|----------|----------|-------|")
            for finding in medium_low:
                lines.append(f"| {finding.severity.value} | `{finding.location}` | {finding.title} |")
            lines.append("")

        # Compliance results
        if self.compliance_results:
            lines.append("## Spec Compliance\n")
            lines.append("| Requirement | Status | Notes |")
            lines.append("|-------------|--------|-------|")
            for result in self.compliance_results:
                status_icon = {
                    "pass": "✅",
                    "fail": "❌",
                    "partial": "⚠️",
                    "not_found": "❓",
                }.get(result.status, "❓")
                lines.append(f"| {result.requirement} | {status_icon} {result.status.title()} | {result.details} |")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "summary": self.to_summary(),
            "files_scanned": self.files_scanned,
            "scan_duration_ms": self.scan_duration_ms,
            "mode": self.mode,
            "has_blocking_issues": self.has_blocking_issues,
            "findings": [f.to_dict() for f in self.findings],
            "counts": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
                "total": len(self.findings),
            },
            "compliance_score": self.compliance_score,
        }
