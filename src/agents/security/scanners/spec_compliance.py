"""Spec compliance scanner - verifies code matches security requirements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.agents.security.scanners.base import BaseScanner, ScanContext
from src.agents.security.findings import (
    Finding,
    FindingSeverity,
    FindingCategory,
    SpecComplianceResult,
)

if TYPE_CHECKING:
    from src.spec.schemas import Spec


@dataclass
class ComplianceCheck:
    """A compliance check to perform."""

    id: str
    name: str
    check_fn: str  # Name of the method to call
    severity: FindingSeverity = FindingSeverity.HIGH
    required: bool = True


# Built-in compliance checks
COMPLIANCE_CHECKS = [
    ComplianceCheck(
        id="COMP-001",
        name="Authentication Required",
        check_fn="_check_authentication",
        severity=FindingSeverity.CRITICAL,
    ),
    ComplianceCheck(
        id="COMP-002",
        name="Rate Limiting",
        check_fn="_check_rate_limiting",
        severity=FindingSeverity.MEDIUM,
    ),
    ComplianceCheck(
        id="COMP-003",
        name="Input Validation",
        check_fn="_check_input_validation",
        severity=FindingSeverity.HIGH,
    ),
    ComplianceCheck(
        id="COMP-004",
        name="HTTPS/TLS Required",
        check_fn="_check_tls",
        severity=FindingSeverity.HIGH,
    ),
    ComplianceCheck(
        id="COMP-005",
        name="Logging/Audit Trail",
        check_fn="_check_logging",
        severity=FindingSeverity.MEDIUM,
    ),
]


class SpecComplianceScanner(BaseScanner):
    """Verifies code matches security spec requirements.

    Runs in heavyweight mode. Checks that the security requirements
    specified in the spec are actually implemented in the code.
    """

    name = "spec_compliance"
    description = "Security spec compliance verification"
    is_heavyweight = True  # Only runs in heavyweight mode

    def __init__(self, checks: list[ComplianceCheck] | None = None):
        """Initialize compliance scanner.

        Args:
            checks: Custom checks (replaces defaults).
        """
        self.checks = checks or COMPLIANCE_CHECKS

    def scan(self, context: ScanContext) -> list[Finding]:
        """Scan for spec compliance issues."""
        findings = []

        if not context.spec:
            return findings

        # Get security requirements from spec
        security_reqs = self._extract_security_requirements(context.spec)

        if not security_reqs:
            return findings

        # Run each check
        for check in self.checks:
            if check.check_fn and hasattr(self, check.check_fn):
                check_method = getattr(self, check.check_fn)
                result = check_method(context, security_reqs)

                if result.status == "fail":
                    findings.append(self._result_to_finding(check, result))

        return findings

    def get_compliance_results(
        self,
        context: ScanContext,
    ) -> list[SpecComplianceResult]:
        """Get detailed compliance results (for reports)."""
        results = []

        if not context.spec:
            return results

        security_reqs = self._extract_security_requirements(context.spec)

        for check in self.checks:
            if check.check_fn and hasattr(self, check.check_fn):
                check_method = getattr(self, check.check_fn)
                result = check_method(context, security_reqs)
                result.requirement = check.name
                results.append(result)

        return results

    def _extract_security_requirements(self, spec: Spec) -> dict:
        """Extract security requirements from spec."""
        reqs = {}

        if hasattr(spec, "security") and spec.security:
            security = spec.security
            if hasattr(security, "authentication_required"):
                reqs["auth_required"] = security.authentication_required
            if hasattr(security, "authorization_model"):
                reqs["authz_model"] = security.authorization_model
            if hasattr(security, "rate_limiting"):
                reqs["rate_limiting"] = security.rate_limiting
            if hasattr(security, "encryption"):
                reqs["encryption"] = security.encryption
            if hasattr(security, "audit_logging"):
                reqs["audit_logging"] = security.audit_logging

        return reqs

    def _check_authentication(
        self,
        context: ScanContext,
        reqs: dict,
    ) -> SpecComplianceResult:
        """Check if authentication is properly implemented."""
        # Look for auth patterns in code
        auth_patterns = [
            r"@login_required",
            r"@authenticated",
            r"@require_auth",
            r"jwt\.verify",
            r"verify_token",
            r"authenticate\(",
            r"Bearer\s+",
            r"Authorization",
            r"session\.get\(['\"]user",
        ]

        found_auth = False
        for content in context.files.values():
            for pattern in auth_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    found_auth = True
                    break
            if found_auth:
                break

        if reqs.get("auth_required", False) and not found_auth:
            return SpecComplianceResult(
                requirement="Authentication Required",
                status="fail",
                details="Spec requires authentication but no auth code found",
            )

        return SpecComplianceResult(
            requirement="Authentication Required",
            status="pass" if found_auth else "not_found",
            details="Authentication implementation detected" if found_auth else "",
        )

    def _check_rate_limiting(
        self,
        context: ScanContext,
        reqs: dict,
    ) -> SpecComplianceResult:
        """Check if rate limiting is implemented."""
        rate_limit_patterns = [
            r"rate_limit",
            r"ratelimit",
            r"throttle",
            r"@limiter",
            r"RateLimiter",
            r"slowapi",
            r"flask_limiter",
        ]

        found = False
        for content in context.files.values():
            for pattern in rate_limit_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    found = True
                    break
            if found:
                break

        if reqs.get("rate_limiting") and not found:
            return SpecComplianceResult(
                requirement="Rate Limiting",
                status="fail",
                details="Spec requires rate limiting but none found",
            )

        return SpecComplianceResult(
            requirement="Rate Limiting",
            status="pass" if found else "not_found",
            details="Rate limiting implementation detected" if found else "",
        )

    def _check_input_validation(
        self,
        context: ScanContext,
        reqs: dict,
    ) -> SpecComplianceResult:
        """Check if input validation is implemented."""
        validation_patterns = [
            r"pydantic",
            r"@validator",
            r"@field_validator",
            r"marshmallow",
            r"wtforms",
            r"cerberus",
            r"jsonschema",
            r"validate\(",
            r"sanitize\(",
        ]

        found = False
        for content in context.files.values():
            for pattern in validation_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    found = True
                    break
            if found:
                break

        return SpecComplianceResult(
            requirement="Input Validation",
            status="pass" if found else "partial",
            details="Input validation framework detected" if found else "Consider adding input validation",
        )

    def _check_tls(
        self,
        context: ScanContext,
        reqs: dict,
    ) -> SpecComplianceResult:
        """Check for TLS/HTTPS usage."""
        # Look for http:// URLs (bad) or TLS config
        http_pattern = r"http://(?!localhost|127\.0\.0\.1)"
        tls_patterns = [
            r"https://",
            r"ssl_context",
            r"TLS",
            r"certfile",
            r"keyfile",
        ]

        has_insecure = False
        has_tls = False

        for content in context.files.values():
            if re.search(http_pattern, content):
                has_insecure = True
            for pattern in tls_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_tls = True

        if has_insecure and not has_tls:
            return SpecComplianceResult(
                requirement="HTTPS/TLS Required",
                status="fail",
                details="Found insecure HTTP URLs without TLS configuration",
            )

        return SpecComplianceResult(
            requirement="HTTPS/TLS Required",
            status="pass" if has_tls else "not_found",
            details="TLS configuration detected" if has_tls else "",
        )

    def _check_logging(
        self,
        context: ScanContext,
        reqs: dict,
    ) -> SpecComplianceResult:
        """Check if security logging is implemented."""
        logging_patterns = [
            r"logging\.getLogger",
            r"logger\.info",
            r"logger\.warning",
            r"audit_log",
            r"security_log",
            r"structlog",
        ]

        found = False
        for content in context.files.values():
            for pattern in logging_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    found = True
                    break
            if found:
                break

        return SpecComplianceResult(
            requirement="Logging/Audit Trail",
            status="pass" if found else "partial",
            details="Logging implementation detected" if found else "Consider adding security logging",
        )

    def _result_to_finding(
        self,
        check: ComplianceCheck,
        result: SpecComplianceResult,
    ) -> Finding:
        """Convert compliance result to finding."""
        return Finding(
            id=check.id,
            title=f"Spec Compliance: {check.name}",
            description=result.details,
            severity=check.severity,
            category=FindingCategory.COMPLIANCE,
            file_path="(spec compliance)",
            recommendation=f"Implement {check.name} as specified in security requirements",
            scanner=self.name,
        )
