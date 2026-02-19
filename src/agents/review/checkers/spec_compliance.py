"""Spec compliance checker - verifies code matches spec requirements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.agents.review.checkers.base import BaseChecker, ReviewContext
from src.agents.review.findings import (
    ReviewComment,
    ReviewSeverity,
    ReviewCategory,
    SpecComplianceStatus,
)

if TYPE_CHECKING:
    from src.spec.schemas import Spec


@dataclass
class ComplianceRequirement:
    """A requirement to check for compliance."""

    id: str
    name: str
    check_type: str  # "pattern", "endpoint", "input", "output", "error_handling"
    patterns: list[str] = None  # Patterns to look for
    required: bool = True
    severity: ReviewSeverity = ReviewSeverity.ERROR

    def __post_init__(self):
        if self.patterns is None:
            self.patterns = []


class SpecComplianceChecker(BaseChecker):
    """Verifies code matches spec requirements.

    Checks that:
    - API endpoints defined in spec are implemented
    - Input validations match spec requirements
    - Output formats match spec definitions
    - Error handling covers spec-defined error cases
    - Security requirements are implemented
    """

    name = "spec_compliance_checker"
    description = "Spec requirement compliance checker"
    is_heavyweight = False  # Basic checks are lightweight

    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Check files for spec compliance issues."""
        comments = []

        if not context.spec and not context.spec_context:
            return comments

        # Extract requirements from spec
        requirements = self._extract_requirements(context)

        # Check each requirement
        for req in requirements:
            req_comments = self._check_requirement(req, context)
            comments.extend(req_comments)

        return comments

    def get_compliance_status(
        self,
        context: ReviewContext,
    ) -> list[SpecComplianceStatus]:
        """Get detailed compliance status for each requirement."""
        statuses = []

        if not context.spec and not context.spec_context:
            return statuses

        requirements = self._extract_requirements(context)

        for req in requirements:
            status = self._evaluate_requirement(req, context)
            statuses.append(status)

        return statuses

    def _extract_requirements(
        self,
        context: ReviewContext,
    ) -> list[ComplianceRequirement]:
        """Extract requirements from spec or spec context."""
        requirements = []

        # From full spec object
        if context.spec:
            requirements.extend(self._extract_from_spec(context.spec))

        # From routed spec context (text)
        if context.spec_context:
            requirements.extend(self._extract_from_text(context.spec_context))

        return requirements

    def _extract_from_spec(self, spec: Spec) -> list[ComplianceRequirement]:
        """Extract requirements from Spec object."""
        requirements = []

        # API endpoints
        if hasattr(spec, "api_contract") and spec.api_contract:
            for endpoint in spec.api_contract.endpoints:
                req = ComplianceRequirement(
                    id=f"API-{endpoint.method}-{endpoint.path}",
                    name=f"Endpoint {endpoint.method} {endpoint.path}",
                    check_type="endpoint",
                    patterns=self._endpoint_to_patterns(endpoint),
                    required=True,
                    severity=ReviewSeverity.ERROR,
                )
                requirements.append(req)

        # Input validation
        if hasattr(spec, "inputs") and spec.inputs:
            for user_input in spec.inputs.user_inputs:
                req = ComplianceRequirement(
                    id=f"INPUT-{user_input.name}",
                    name=f"Input validation for {user_input.name}",
                    check_type="input",
                    patterns=self._input_to_patterns(user_input),
                    required=user_input.required,
                    severity=ReviewSeverity.WARNING if not user_input.required else ReviewSeverity.ERROR,
                )
                requirements.append(req)

        # Error handling
        if hasattr(spec, "error_handling") and spec.error_handling:
            error_handling = spec.error_handling
            if hasattr(error_handling, "error_cases"):
                for error_case in error_handling.error_cases:
                    req = ComplianceRequirement(
                        id=f"ERR-{error_case.code}",
                        name=f"Error handling for {error_case.code}",
                        check_type="error_handling",
                        patterns=self._error_to_patterns(error_case),
                        required=True,
                        severity=ReviewSeverity.WARNING,
                    )
                    requirements.append(req)

        return requirements

    def _extract_from_text(self, spec_context: str) -> list[ComplianceRequirement]:
        """Extract requirements from spec context text."""
        requirements = []

        # Extract API endpoints from text
        # Pattern: GET /path, POST /path, etc.
        endpoint_pattern = r"(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s\n]+)"
        for match in re.finditer(endpoint_pattern, spec_context, re.IGNORECASE):
            method, path = match.groups()
            req = ComplianceRequirement(
                id=f"API-{method.upper()}-{path}",
                name=f"Endpoint {method.upper()} {path}",
                check_type="endpoint",
                patterns=[
                    rf"@(app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]" + re.escape(path),
                    rf"route\s*=\s*['\"]" + re.escape(path),
                    rf"path\s*=\s*['\"]" + re.escape(path),
                ],
                required=True,
                severity=ReviewSeverity.ERROR,
            )
            requirements.append(req)

        # Extract required inputs
        input_pattern = r"(?:required|mandatory)\s+(?:input|parameter|field)[:\s]+(\w+)"
        for match in re.finditer(input_pattern, spec_context, re.IGNORECASE):
            input_name = match.group(1)
            req = ComplianceRequirement(
                id=f"INPUT-{input_name}",
                name=f"Required input: {input_name}",
                check_type="input",
                patterns=[
                    rf"\b{input_name}\b",
                    rf'"{input_name}"',
                    rf"'{input_name}'",
                ],
                required=True,
                severity=ReviewSeverity.WARNING,
            )
            requirements.append(req)

        # Extract error codes
        error_pattern = r"error\s+(?:code|status)[:\s]+(\d{3})"
        for match in re.finditer(error_pattern, spec_context, re.IGNORECASE):
            error_code = match.group(1)
            req = ComplianceRequirement(
                id=f"ERR-{error_code}",
                name=f"Error code {error_code}",
                check_type="error_handling",
                patterns=[
                    rf"status[_\s]*(?:code)?\s*=?\s*{error_code}",
                    rf"HTTPStatus\.\w+",  # Generic HTTP status
                    rf"return\s+.*{error_code}",
                ],
                required=True,
                severity=ReviewSeverity.WARNING,
            )
            requirements.append(req)

        return requirements

    def _endpoint_to_patterns(self, endpoint) -> list[str]:
        """Convert endpoint definition to search patterns."""
        path = endpoint.path if hasattr(endpoint, "path") else ""
        method = endpoint.method.lower() if hasattr(endpoint, "method") else ""

        # Escape special regex characters but keep basic path structure
        escaped_path = re.escape(path).replace(r"\{", r"[^/]+").replace(r"\}", "")

        return [
            rf"@(app|router)\.{method}\s*\(\s*['\"]" + escaped_path,
            rf"\.{method}\s*\(\s*['\"]" + escaped_path,
            rf"route\s*\(\s*['\"]" + escaped_path,
            rf"path\s*=\s*['\"]" + escaped_path,
        ]

    def _input_to_patterns(self, user_input) -> list[str]:
        """Convert input definition to search patterns."""
        name = user_input.name if hasattr(user_input, "name") else ""
        input_type = user_input.type if hasattr(user_input, "type") else ""

        patterns = [
            rf"\b{name}\b\s*:",  # Type annotation
            rf'"{name}"',
            rf"'{name}'",
        ]

        # Add type-specific validation patterns
        if input_type.lower() in ("email", "str", "string"):
            patterns.append(rf"validate.*{name}")
        elif input_type.lower() in ("int", "integer", "number"):
            patterns.append(rf"int\s*\(\s*{name}")

        return patterns

    def _error_to_patterns(self, error_case) -> list[str]:
        """Convert error case to search patterns."""
        code = error_case.code if hasattr(error_case, "code") else ""
        message = error_case.message if hasattr(error_case, "message") else ""

        patterns = [
            rf"status[_\s]*(?:code)?\s*=?\s*{code}",
            rf"{code}",
        ]

        if message:
            # Look for similar error messages
            words = message.split()[:3]  # First 3 words
            if words:
                patterns.append(rf"{'.*'.join(words[:2])}")

        return patterns

    def _check_requirement(
        self,
        req: ComplianceRequirement,
        context: ReviewContext,
    ) -> list[ReviewComment]:
        """Check if a requirement is met in the code."""
        comments = []

        # Search for patterns in all files
        found = False
        found_in_files = []

        for file_path, content in context.files.items():
            for pattern in req.patterns:
                try:
                    if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                        found = True
                        found_in_files.append(file_path)
                        break
                except re.error:
                    continue

        if not found and req.required:
            comments.append(ReviewComment(
                id=self._generate_id(req.id, "(spec)"),
                file_path="(spec requirement)",
                message=f"Missing implementation: {req.name}",
                severity=req.severity,
                category=ReviewCategory.SPEC_COMPLIANCE,
                suggestion=f"Implement the requirement: {req.name}",
                checker=self.name,
                metadata={"requirement_id": req.id, "check_type": req.check_type},
            ))

        return comments

    def _evaluate_requirement(
        self,
        req: ComplianceRequirement,
        context: ReviewContext,
    ) -> SpecComplianceStatus:
        """Evaluate a requirement and return status."""
        found = False
        found_files = []

        for file_path, content in context.files.items():
            for pattern in req.patterns:
                try:
                    if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                        found = True
                        found_files.append(file_path)
                        break
                except re.error:
                    continue

        if found:
            return SpecComplianceStatus(
                requirement=req.name,
                status="pass",
                details=f"Found in: {', '.join(found_files[:3])}",
                file_path=found_files[0] if found_files else "",
            )
        elif req.required:
            return SpecComplianceStatus(
                requirement=req.name,
                status="fail",
                details="Not found in code",
            )
        else:
            return SpecComplianceStatus(
                requirement=req.name,
                status="not_implemented",
                details="Optional requirement not implemented",
            )
