"""Spec linting and style checking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class LintSeverity(Enum):
    """Severity of lint issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class LintCategory(Enum):
    """Category of lint issues."""
    COMPLETENESS = "completeness"
    FORMATTING = "formatting"
    NAMING = "naming"
    CONSISTENCY = "consistency"
    BEST_PRACTICES = "best_practices"


@dataclass
class LintIssue:
    """A single lint issue."""

    rule_id: str
    severity: LintSeverity
    category: LintCategory
    message: str
    line: int | None = None
    section: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "line": self.line,
            "section": self.section,
            "suggestion": self.suggestion,
        }


@dataclass
class LintResult:
    """Result of linting a spec."""

    spec_path: str
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Count of errors."""
        return sum(1 for i in self.issues if i.severity == LintSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return sum(1 for i in self.issues if i.severity == LintSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of info issues."""
        return sum(1 for i in self.issues if i.severity == LintSeverity.INFO)

    @property
    def passed(self) -> bool:
        """Check if linting passed (no errors)."""
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spec_path": self.spec_path,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class LintRule:
    """A lint rule definition."""

    rule_id: str
    name: str
    severity: LintSeverity
    category: LintCategory
    description: str
    check_fn: Callable[[str, dict[str, Any]], list[LintIssue]]
    enabled: bool = True


class SpecLinter:
    """Lint specs for style and consistency."""

    def __init__(self):
        """Initialize linter with default rules."""
        self.rules: list[LintRule] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default lint rules."""
        # Completeness rules
        self.rules.append(LintRule(
            rule_id="COMP-001",
            name="Missing Required Sections",
            severity=LintSeverity.ERROR,
            category=LintCategory.COMPLETENESS,
            description="Check that all required sections are present",
            check_fn=self._check_required_sections,
        ))

        self.rules.append(LintRule(
            rule_id="COMP-002",
            name="Empty Sections",
            severity=LintSeverity.WARNING,
            category=LintCategory.COMPLETENESS,
            description="Check for empty sections that should have content",
            check_fn=self._check_empty_sections,
        ))

        self.rules.append(LintRule(
            rule_id="COMP-003",
            name="Missing Test Cases",
            severity=LintSeverity.WARNING,
            category=LintCategory.COMPLETENESS,
            description="Check that test cases are defined",
            check_fn=self._check_test_cases,
        ))

        # Formatting rules
        self.rules.append(LintRule(
            rule_id="FMT-001",
            name="Consistent Heading Levels",
            severity=LintSeverity.WARNING,
            category=LintCategory.FORMATTING,
            description="Check heading hierarchy is consistent",
            check_fn=self._check_heading_levels,
        ))

        self.rules.append(LintRule(
            rule_id="FMT-002",
            name="Table Formatting",
            severity=LintSeverity.INFO,
            category=LintCategory.FORMATTING,
            description="Check table formatting is consistent",
            check_fn=self._check_table_formatting,
        ))

        # Naming rules
        self.rules.append(LintRule(
            rule_id="NAME-001",
            name="Spec ID Format",
            severity=LintSeverity.ERROR,
            category=LintCategory.NAMING,
            description="Check spec_id uses kebab-case",
            check_fn=self._check_spec_id_format,
        ))

        self.rules.append(LintRule(
            rule_id="NAME-002",
            name="Endpoint Path Format",
            severity=LintSeverity.WARNING,
            category=LintCategory.NAMING,
            description="Check API endpoint paths use proper format",
            check_fn=self._check_endpoint_format,
        ))

        # Consistency rules
        self.rules.append(LintRule(
            rule_id="CONS-001",
            name="Version Format",
            severity=LintSeverity.WARNING,
            category=LintCategory.CONSISTENCY,
            description="Check version uses semantic versioning",
            check_fn=self._check_version_format,
        ))

        self.rules.append(LintRule(
            rule_id="CONS-002",
            name="Status Values",
            severity=LintSeverity.ERROR,
            category=LintCategory.CONSISTENCY,
            description="Check status is a valid value",
            check_fn=self._check_status_values,
        ))

        # Best practices
        self.rules.append(LintRule(
            rule_id="BP-001",
            name="Non-Goals Defined",
            severity=LintSeverity.INFO,
            category=LintCategory.BEST_PRACTICES,
            description="Check that non-goals are explicitly defined",
            check_fn=self._check_non_goals,
        ))

        self.rules.append(LintRule(
            rule_id="BP-002",
            name="Error Codes Defined",
            severity=LintSeverity.WARNING,
            category=LintCategory.BEST_PRACTICES,
            description="Check that error codes are defined for APIs",
            check_fn=self._check_error_codes,
        ))

        self.rules.append(LintRule(
            rule_id="BP-003",
            name="Security Section Complete",
            severity=LintSeverity.WARNING,
            category=LintCategory.BEST_PRACTICES,
            description="Check security section has required fields",
            check_fn=self._check_security_complete,
        ))

    def _check_required_sections(self, content: str, _: dict) -> list[LintIssue]:
        """Check required sections are present."""
        issues = []
        required_sections = [
            "1. Metadata",
            "2. Overview",
            "3. Inputs",
            "4. Outputs",
            "7. Test Cases",
        ]

        for section in required_sections:
            if f"## {section}" not in content:
                issues.append(LintIssue(
                    rule_id="COMP-001",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.COMPLETENESS,
                    message=f"Missing required section: {section}",
                    section=section,
                    suggestion=f"Add '## {section}' section to the spec",
                ))

        return issues

    def _check_empty_sections(self, content: str, _: dict) -> list[LintIssue]:
        """Check for empty sections."""
        issues = []

        # Find sections with minimal content
        section_pattern = re.compile(r"## (\d+\. .+?)\n(.*?)(?=\n## \d+\.|\Z)", re.DOTALL)

        for match in section_pattern.finditer(content):
            section_name = match.group(1)
            section_content = match.group(2).strip()

            # Check if section has meaningful content
            if len(section_content) < 20:
                issues.append(LintIssue(
                    rule_id="COMP-002",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.COMPLETENESS,
                    message=f"Section '{section_name}' appears to be empty or minimal",
                    section=section_name,
                    suggestion="Add content to this section or mark as N/A if not applicable",
                ))

        return issues

    def _check_test_cases(self, content: str, _: dict) -> list[LintIssue]:
        """Check test cases are defined."""
        issues = []

        if "## 7. Test Cases" in content:
            # Check for actual test case rows
            test_section = content.split("## 7. Test Cases")[1].split("## ")[0]

            # Count table rows (excluding header and separator)
            rows = [l for l in test_section.split("\n") if l.strip().startswith("|")]
            data_rows = [r for r in rows if not re.match(r"^\|[-\s|]+\|$", r.strip())]

            if len(data_rows) < 3:  # Header + at least 1 test
                issues.append(LintIssue(
                    rule_id="COMP-003",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.COMPLETENESS,
                    message="Test Cases section has fewer than expected test cases",
                    section="7. Test Cases",
                    suggestion="Add at least 3 unit tests and 1 integration test",
                ))

        return issues

    def _check_heading_levels(self, content: str, _: dict) -> list[LintIssue]:
        """Check heading hierarchy."""
        issues = []
        lines = content.split("\n")

        prev_level = 0
        for i, line in enumerate(lines, 1):
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))

                # Check for skipped levels
                if level > prev_level + 1 and prev_level > 0:
                    issues.append(LintIssue(
                        rule_id="FMT-001",
                        severity=LintSeverity.WARNING,
                        category=LintCategory.FORMATTING,
                        message=f"Skipped heading level (from H{prev_level} to H{level})",
                        line=i,
                        suggestion=f"Use H{prev_level + 1} instead of H{level}",
                    ))

                prev_level = level

        return issues

    def _check_table_formatting(self, content: str, _: dict) -> list[LintIssue]:
        """Check table formatting."""
        issues = []
        lines = content.split("\n")

        in_table = False
        table_start = 0

        for i, line in enumerate(lines, 1):
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if not in_table:
                    in_table = True
                    table_start = i
            elif in_table and not line.strip().startswith("|"):
                in_table = False

        return issues

    def _check_spec_id_format(self, content: str, _: dict) -> list[LintIssue]:
        """Check spec_id format."""
        issues = []

        match = re.search(r"spec_id:\s*(.+)", content)
        if match:
            spec_id = match.group(1).strip()

            # Should be kebab-case
            if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", spec_id):
                issues.append(LintIssue(
                    rule_id="NAME-001",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.NAMING,
                    message=f"spec_id '{spec_id}' should use kebab-case",
                    suggestion="Use lowercase letters, numbers, and hyphens (e.g., 'my-feature')",
                ))

        return issues

    def _check_endpoint_format(self, content: str, _: dict) -> list[LintIssue]:
        """Check API endpoint path format."""
        issues = []

        # Find endpoint paths in tables
        endpoint_pattern = re.compile(r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*(/[^\s|]+)")

        for match in endpoint_pattern.finditer(content):
            path = match.group(2)

            # Check for camelCase in path
            if re.search(r"[a-z][A-Z]", path):
                issues.append(LintIssue(
                    rule_id="NAME-002",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.NAMING,
                    message=f"Endpoint path '{path}' contains camelCase",
                    suggestion="Use kebab-case or snake_case for URL paths",
                ))

        return issues

    def _check_version_format(self, content: str, _: dict) -> list[LintIssue]:
        """Check version format."""
        issues = []

        match = re.search(r"version:\s*(.+)", content)
        if match:
            version = match.group(1).strip()

            if not re.match(r"^\d+\.\d+\.\d+(-[a-z0-9]+)?$", version):
                issues.append(LintIssue(
                    rule_id="CONS-001",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.CONSISTENCY,
                    message=f"Version '{version}' should use semantic versioning",
                    suggestion="Use format: MAJOR.MINOR.PATCH (e.g., '1.0.0')",
                ))

        return issues

    def _check_status_values(self, content: str, _: dict) -> list[LintIssue]:
        """Check status is valid."""
        issues = []
        valid_statuses = {"draft", "review", "approved", "implemented", "deprecated"}

        match = re.search(r"status:\s*(.+)", content)
        if match:
            status = match.group(1).strip().lower()

            if status not in valid_statuses:
                issues.append(LintIssue(
                    rule_id="CONS-002",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.CONSISTENCY,
                    message=f"Invalid status '{status}'",
                    suggestion=f"Use one of: {', '.join(sorted(valid_statuses))}",
                ))

        return issues

    def _check_non_goals(self, content: str, _: dict) -> list[LintIssue]:
        """Check non-goals are defined."""
        issues = []

        if "### Non-Goals" in content:
            # Find non-goals section
            non_goals_section = content.split("### Non-Goals")[1].split("###")[0]

            # Check for actual items
            items = [l for l in non_goals_section.split("\n") if l.strip().startswith("-")]

            if not items:
                issues.append(LintIssue(
                    rule_id="BP-001",
                    severity=LintSeverity.INFO,
                    category=LintCategory.BEST_PRACTICES,
                    message="Non-Goals section exists but has no items",
                    section="Non-Goals",
                    suggestion="Add explicit non-goals to clarify scope boundaries",
                ))
        else:
            issues.append(LintIssue(
                rule_id="BP-001",
                severity=LintSeverity.INFO,
                category=LintCategory.BEST_PRACTICES,
                message="No Non-Goals section defined",
                suggestion="Add a Non-Goals section to clarify what is out of scope",
            ))

        return issues

    def _check_error_codes(self, content: str, _: dict) -> list[LintIssue]:
        """Check error codes are defined."""
        issues = []

        # Check if API Contract section exists and has endpoints
        if "## 6. API Contract" in content or "### Endpoints" in content:
            if "### Error Codes" not in content:
                issues.append(LintIssue(
                    rule_id="BP-002",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.BEST_PRACTICES,
                    message="API endpoints defined but no Error Codes section",
                    suggestion="Add '### Error Codes' section with possible error responses",
                ))

        return issues

    def _check_security_complete(self, content: str, _: dict) -> list[LintIssue]:
        """Check security section completeness."""
        issues = []
        required_fields = ["requires_auth", "handles_pii", "encryption"]

        if "## 11. Security" in content:
            security_section = content.split("## 11. Security")[1].split("## ")[0]

            for field in required_fields:
                if field not in security_section.lower():
                    issues.append(LintIssue(
                        rule_id="BP-003",
                        severity=LintSeverity.WARNING,
                        category=LintCategory.BEST_PRACTICES,
                        message=f"Security section missing '{field}' field",
                        section="11. Security",
                        suggestion=f"Add '{field}' field to security section",
                    ))

        return issues

    def lint(self, content: str, spec_path: str = "") -> LintResult:
        """Lint a spec.

        Args:
            content: Spec content.
            spec_path: Path to spec file (for reporting).

        Returns:
            LintResult with all issues found.
        """
        result = LintResult(spec_path=spec_path)

        for rule in self.rules:
            if not rule.enabled:
                continue

            try:
                issues = rule.check_fn(content, {})
                result.issues.extend(issues)
            except Exception as e:
                result.issues.append(LintIssue(
                    rule_id=rule.rule_id,
                    severity=LintSeverity.ERROR,
                    category=rule.category,
                    message=f"Rule check failed: {e}",
                ))

        return result

    def lint_file(self, path: Path) -> LintResult:
        """Lint a spec file.

        Args:
            path: Path to spec file.

        Returns:
            LintResult with all issues found.
        """
        content = path.read_text()
        return self.lint(content, str(path))

    def enable_rule(self, rule_id: str) -> None:
        """Enable a rule by ID."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                rule.enabled = True
                return

    def disable_rule(self, rule_id: str) -> None:
        """Disable a rule by ID."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                rule.enabled = False
                return

    def list_rules(self) -> list[dict[str, Any]]:
        """List all rules."""
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "severity": r.severity.value,
                "category": r.category.value,
                "description": r.description,
                "enabled": r.enabled,
            }
            for r in self.rules
        ]
