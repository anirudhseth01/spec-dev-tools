"""CodeReviewAgent for reviewing code against specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus


class ReviewSeverity(Enum):
    """Severity levels for review comments."""

    BLOCKER = "blocker"      # Must fix before merge
    MAJOR = "major"          # Should fix before merge
    MINOR = "minor"          # Nice to fix
    SUGGESTION = "suggestion"  # Optional improvement
    PRAISE = "praise"        # Positive feedback


class ReviewCategory(Enum):
    """Categories for review comments."""

    SPEC_COMPLIANCE = "spec_compliance"
    CODE_QUALITY = "code_quality"
    SECURITY = "security"
    PERFORMANCE = "performance"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    STYLE = "style"
    ARCHITECTURE = "architecture"


@dataclass
class ReviewComment:
    """A single review comment."""

    id: str
    file_path: str
    line_number: Optional[int]
    severity: ReviewSeverity
    category: ReviewCategory
    title: str
    description: str
    suggestion: str = ""
    code_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
        }


@dataclass
class ReviewReport:
    """Complete code review report."""

    comments: list[ReviewComment] = field(default_factory=list)
    files_reviewed: int = 0
    spec_compliance_score: float = 1.0
    overall_rating: str = "approved"  # approved, changes_requested, needs_work

    @property
    def blocker_count(self) -> int:
        """Count of blocker comments."""
        return sum(1 for c in self.comments if c.severity == ReviewSeverity.BLOCKER)

    @property
    def major_count(self) -> int:
        """Count of major comments."""
        return sum(1 for c in self.comments if c.severity == ReviewSeverity.MAJOR)

    @property
    def minor_count(self) -> int:
        """Count of minor comments."""
        return sum(1 for c in self.comments if c.severity == ReviewSeverity.MINOR)

    @property
    def has_blockers(self) -> bool:
        """Check if there are any blockers."""
        return self.blocker_count > 0

    def to_summary(self) -> str:
        """Generate summary string."""
        status = "APPROVED" if self.overall_rating == "approved" else "CHANGES REQUESTED"
        return (
            f"Code Review: {status} "
            f"({self.blocker_count} blockers, {self.major_count} major, {self.minor_count} minor) "
            f"- Spec compliance: {self.spec_compliance_score:.0%}"
        )

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = ["# Code Review Report\n"]

        # Summary
        lines.append("## Summary")
        lines.append(f"- **Status:** {self.overall_rating.replace('_', ' ').title()}")
        lines.append(f"- **Files reviewed:** {self.files_reviewed}")
        lines.append(f"- **Spec compliance:** {self.spec_compliance_score:.0%}")
        lines.append(f"- **Issues:** {self.blocker_count} blockers, {self.major_count} major, {self.minor_count} minor")
        lines.append("")

        # Group comments by severity
        if self.blocker_count > 0:
            lines.append("## Blockers\n")
            for c in self.comments:
                if c.severity == ReviewSeverity.BLOCKER:
                    lines.append(self._format_comment(c))

        if self.major_count > 0:
            lines.append("## Major Issues\n")
            for c in self.comments:
                if c.severity == ReviewSeverity.MAJOR:
                    lines.append(self._format_comment(c))

        minor_and_suggestions = [
            c for c in self.comments
            if c.severity in (ReviewSeverity.MINOR, ReviewSeverity.SUGGESTION)
        ]
        if minor_and_suggestions:
            lines.append("## Minor Issues & Suggestions\n")
            for c in minor_and_suggestions:
                lines.append(self._format_comment(c))

        praise = [c for c in self.comments if c.severity == ReviewSeverity.PRAISE]
        if praise:
            lines.append("## Positive Feedback\n")
            for c in praise:
                lines.append(f"- **{c.file_path}**: {c.title}")
            lines.append("")

        return "\n".join(lines)

    def _format_comment(self, comment: ReviewComment) -> str:
        """Format a single comment for markdown."""
        lines = []
        location = f"{comment.file_path}"
        if comment.line_number:
            location += f":{comment.line_number}"

        lines.append(f"### [{comment.category.value}] {comment.title}")
        lines.append(f"**Location:** `{location}`\n")
        lines.append(comment.description)
        if comment.code_snippet:
            lines.append(f"\n```\n{comment.code_snippet}\n```")
        if comment.suggestion:
            lines.append(f"\n**Suggestion:** {comment.suggestion}")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "summary": self.to_summary(),
            "overall_rating": self.overall_rating,
            "files_reviewed": self.files_reviewed,
            "spec_compliance_score": self.spec_compliance_score,
            "has_blockers": self.has_blockers,
            "comments": [c.to_dict() for c in self.comments],
            "counts": {
                "blocker": self.blocker_count,
                "major": self.major_count,
                "minor": self.minor_count,
                "total": len(self.comments),
            },
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=2)


class CodeReviewAgent(BaseAgent):
    """Reviews code against specifications.

    Features:
    - Checks spec compliance (inputs, outputs, API contracts)
    - Validates error handling matches spec
    - Checks test coverage requirements
    - Reviews code quality and patterns
    - Provides actionable feedback
    """

    name = "code_review_agent"
    description = "Reviews code against specifications"
    requires = ["coding_agent"]  # Optionally also test_generator_agent

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        spec_path: Optional[Path] = None,
        strict_mode: bool = False,
    ):
        """Initialize CodeReviewAgent.

        Args:
            llm_client: LLM client for intelligent review.
            spec_path: Path to specification file.
            strict_mode: If True, be stricter about compliance.
        """
        self.llm = llm_client
        self.spec_path = spec_path
        self.strict_mode = strict_mode

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute code review."""
        try:
            # Get code to review
            code_files = self._get_code_files(context)
            if not code_files:
                return AgentResult(
                    status=AgentStatus.SKIPPED,
                    message="No code files to review",
                )

            # Get test files if available
            test_files = self._get_test_files(context)

            # Perform review
            report = self._review_code(
                code_files=code_files,
                test_files=test_files,
                context=context,
            )

            # Determine result status
            if report.has_blockers:
                status = AgentStatus.FAILED
                message = f"Review found {report.blocker_count} blocking issue(s)"
            else:
                status = AgentStatus.SUCCESS
                message = report.to_summary()

            return AgentResult(
                status=status,
                message=message,
                data={
                    "review": report.to_dict(),
                    "markdown_report": report.to_markdown(),
                    "overall_rating": report.overall_rating,
                    "spec_compliance_score": report.spec_compliance_score,
                },
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Code review failed: {str(e)}",
                errors=[str(e)],
            )

    def _get_code_files(self, context: AgentContext) -> dict[str, str]:
        """Get code files from context."""
        files = {}

        # From previous results
        coding_result = context.get_result("coding_agent")
        if coding_result and coding_result.data:
            if "code" in coding_result.data:
                files.update(coding_result.data["code"])

        # From parent context artifacts
        if "artifacts" in context.parent_context:
            artifacts = context.parent_context["artifacts"]
            if "code" in artifacts:
                code_artifact = artifacts["code"]
                if isinstance(code_artifact, dict) and "value" in code_artifact:
                    files.update(code_artifact["value"])

        return files

    def _get_test_files(self, context: AgentContext) -> dict[str, str]:
        """Get test files from context."""
        files = {}

        # From test generator results
        test_result = context.get_result("test_generator_agent")
        if test_result and test_result.data:
            if "tests" in test_result.data:
                files.update(test_result.data["tests"])

        # From parent context artifacts
        if "artifacts" in context.parent_context:
            artifacts = context.parent_context["artifacts"]
            if "tests" in artifacts:
                test_artifact = artifacts["tests"]
                if isinstance(test_artifact, dict) and "value" in test_artifact:
                    files.update(test_artifact["value"])

        return files

    def _review_code(
        self,
        code_files: dict[str, str],
        test_files: dict[str, str],
        context: AgentContext,
    ) -> ReviewReport:
        """Perform code review."""
        comments = []
        comment_id = 0

        # Check spec compliance
        compliance_comments, compliance_score = self._check_spec_compliance(
            code_files, context
        )
        comments.extend(compliance_comments)

        # Check code quality
        quality_comments = self._check_code_quality(code_files)
        comments.extend(quality_comments)

        # Check test coverage if tests available
        if test_files:
            test_comments = self._check_test_coverage(code_files, test_files, context)
            comments.extend(test_comments)

        # Use LLM for deeper review if available
        if self.llm:
            llm_comments = self._review_with_llm(code_files, test_files, context)
            comments.extend(llm_comments)

        # Assign IDs
        for i, comment in enumerate(comments):
            comment.id = f"REV-{i+1:03d}"

        # Determine overall rating
        if any(c.severity == ReviewSeverity.BLOCKER for c in comments):
            overall_rating = "changes_requested"
        elif any(c.severity == ReviewSeverity.MAJOR for c in comments):
            overall_rating = "changes_requested"
        else:
            overall_rating = "approved"

        return ReviewReport(
            comments=comments,
            files_reviewed=len(code_files),
            spec_compliance_score=compliance_score,
            overall_rating=overall_rating,
        )

    def _check_spec_compliance(
        self,
        code_files: dict[str, str],
        context: AgentContext,
    ) -> tuple[list[ReviewComment], float]:
        """Check code compliance with spec."""
        comments = []
        compliance_checks = 0
        passed_checks = 0

        if not context.spec:
            return comments, 1.0

        spec = context.spec

        # Check API contract compliance
        if spec.api_contract and spec.api_contract.endpoints:
            compliance_checks += 1
            endpoints_found = self._check_endpoints_implemented(code_files, spec.api_contract.endpoints)
            if endpoints_found:
                passed_checks += 1
            else:
                comments.append(ReviewComment(
                    id="",
                    file_path="*",
                    line_number=None,
                    severity=ReviewSeverity.MAJOR,
                    category=ReviewCategory.SPEC_COMPLIANCE,
                    title="Missing API endpoints",
                    description="Some endpoints defined in the spec are not implemented",
                    suggestion="Implement all endpoints defined in Section 6: API Contract",
                ))

        # Check error handling
        if spec.error_handling and spec.error_handling.error_types:
            compliance_checks += 1
            error_handling_ok = self._check_error_handling(code_files, spec.error_handling)
            if error_handling_ok:
                passed_checks += 1
            else:
                comments.append(ReviewComment(
                    id="",
                    file_path="*",
                    line_number=None,
                    severity=ReviewSeverity.MINOR,
                    category=ReviewCategory.SPEC_COMPLIANCE,
                    title="Incomplete error handling",
                    description="Not all error types from the spec are handled",
                    suggestion="Review Section 9: Error Handling and implement all specified error types",
                ))

        # Check inputs are validated
        if spec.inputs and (spec.inputs.user_inputs or spec.inputs.system_inputs):
            compliance_checks += 1
            inputs_validated = self._check_input_validation(code_files, spec.inputs)
            if inputs_validated:
                passed_checks += 1
            else:
                comments.append(ReviewComment(
                    id="",
                    file_path="*",
                    line_number=None,
                    severity=ReviewSeverity.MAJOR,
                    category=ReviewCategory.SPEC_COMPLIANCE,
                    title="Missing input validation",
                    description="Required inputs from the spec may not be properly validated",
                    suggestion="Ensure all required inputs from Section 3 are validated",
                ))

        compliance_score = passed_checks / compliance_checks if compliance_checks > 0 else 1.0
        return comments, compliance_score

    def _check_endpoints_implemented(self, code_files: dict[str, str], endpoints: list) -> bool:
        """Check if API endpoints are implemented."""
        all_code = "\n".join(code_files.values())

        for endpoint in endpoints:
            # Look for route decorators or handlers
            path = endpoint.path.replace("{", "").replace("}", "")
            method = endpoint.method.lower()

            # Check for common patterns
            patterns = [
                f"@{method}",
                f'@app.{method}',
                f'@router.{method}',
                f'.{method}(',
                f"method: '{method.upper()}'",
                f'method: "{method.upper()}"',
            ]

            found = any(pattern in all_code.lower() for pattern in patterns)
            if not found and path not in all_code:
                return False

        return True

    def _check_error_handling(self, code_files: dict[str, str], error_handling) -> bool:
        """Check if error handling is implemented."""
        all_code = "\n".join(code_files.values())

        # Look for try/except or try/catch
        has_exception_handling = "try" in all_code and ("except" in all_code or "catch" in all_code)

        # Look for custom error classes
        error_types = error_handling.error_types
        error_classes_found = sum(1 for et in error_types if et.lower() in all_code.lower())

        return has_exception_handling and error_classes_found > 0

    def _check_input_validation(self, code_files: dict[str, str], inputs) -> bool:
        """Check if input validation is present."""
        all_code = "\n".join(code_files.values())

        # Look for validation patterns
        validation_patterns = [
            "validate",
            "assert",
            "raise",
            "if not",
            "required",
            "Optional[",
            "pydantic",
            "schema",
            "joi",
            "yup",
            "zod",
        ]

        return any(pattern.lower() in all_code.lower() for pattern in validation_patterns)

    def _check_code_quality(self, code_files: dict[str, str]) -> list[ReviewComment]:
        """Check code quality issues."""
        comments = []

        for filepath, content in code_files.items():
            # Check for TODOs
            if "TODO" in content or "FIXME" in content:
                lines_with_todo = [
                    i + 1 for i, line in enumerate(content.split("\n"))
                    if "TODO" in line or "FIXME" in line
                ]
                comments.append(ReviewComment(
                    id="",
                    file_path=filepath,
                    line_number=lines_with_todo[0] if lines_with_todo else None,
                    severity=ReviewSeverity.MINOR,
                    category=ReviewCategory.CODE_QUALITY,
                    title="Unresolved TODO/FIXME comments",
                    description=f"Found {len(lines_with_todo)} TODO/FIXME comment(s)",
                    suggestion="Resolve or track these items before merging",
                ))

            # Check for hardcoded secrets patterns
            secret_patterns = ["password", "secret", "api_key", "apikey", "token"]
            for pattern in secret_patterns:
                if f'{pattern} = "' in content.lower() or f"{pattern} = '" in content.lower():
                    comments.append(ReviewComment(
                        id="",
                        file_path=filepath,
                        line_number=None,
                        severity=ReviewSeverity.BLOCKER,
                        category=ReviewCategory.SECURITY,
                        title="Potential hardcoded secret",
                        description=f"Found potential hardcoded {pattern}",
                        suggestion="Use environment variables or secret management",
                    ))

            # Check for print statements (Python) or console.log (JS)
            debug_patterns = ["print(", "console.log(", "console.debug("]
            for pattern in debug_patterns:
                if pattern in content:
                    comments.append(ReviewComment(
                        id="",
                        file_path=filepath,
                        line_number=None,
                        severity=ReviewSeverity.MINOR,
                        category=ReviewCategory.CODE_QUALITY,
                        title="Debug statements present",
                        description=f"Found {pattern.rstrip('(')} statements",
                        suggestion="Remove or replace with proper logging",
                    ))
                    break

            # Check file length
            lines = content.split("\n")
            if len(lines) > 500:
                comments.append(ReviewComment(
                    id="",
                    file_path=filepath,
                    line_number=None,
                    severity=ReviewSeverity.SUGGESTION,
                    category=ReviewCategory.ARCHITECTURE,
                    title="Large file",
                    description=f"File has {len(lines)} lines",
                    suggestion="Consider breaking into smaller modules",
                ))

        return comments

    def _check_test_coverage(
        self,
        code_files: dict[str, str],
        test_files: dict[str, str],
        context: AgentContext,
    ) -> list[ReviewComment]:
        """Check test coverage."""
        comments = []

        # Get coverage target from spec
        target = 80
        if context.spec and context.spec.test_cases:
            target = context.spec.test_cases.min_line_coverage or 80

        # Count functions/methods in code
        import re
        code_functions = set()
        for content in code_files.values():
            # Python functions
            code_functions.update(re.findall(r"def\s+(\w+)\s*\(", content))
            # JS/TS functions
            code_functions.update(re.findall(r"function\s+(\w+)\s*\(", content))
            code_functions.update(re.findall(r"(\w+)\s*=\s*(?:async\s*)?\(", content))

        # Count tests
        test_count = 0
        for content in test_files.values():
            test_count += len(re.findall(r"def\s+test_", content))
            test_count += len(re.findall(r"\bit\s*\(", content))
            test_count += len(re.findall(r"\btest\s*\(", content))

        # Simple heuristic: should have roughly as many tests as public functions
        public_functions = [f for f in code_functions if not f.startswith("_")]
        if len(public_functions) > 0 and test_count < len(public_functions) * 0.5:
            comments.append(ReviewComment(
                id="",
                file_path="tests/*",
                line_number=None,
                severity=ReviewSeverity.MAJOR,
                category=ReviewCategory.TESTING,
                title="Insufficient test coverage",
                description=f"Found {test_count} tests for {len(public_functions)} public functions",
                suggestion=f"Add more tests to meet {target}% coverage target",
            ))

        return comments

    def _review_with_llm(
        self,
        code_files: dict[str, str],
        test_files: dict[str, str],
        context: AgentContext,
    ) -> list[ReviewComment]:
        """Use LLM for deeper code review."""
        comments = []

        if not self.llm:
            return comments

        # Build prompt
        code_content = "\n\n".join([
            f"# File: {path}\n```\n{content}\n```"
            for path, content in code_files.items()
        ])

        spec_context = self._get_spec_context(context)

        system_prompt = """You are an expert code reviewer. Review the code for:
1. Spec compliance - Does the code implement what the spec requires?
2. Code quality - Is the code clean, readable, and maintainable?
3. Security - Are there any security issues?
4. Performance - Are there any performance concerns?
5. Best practices - Does the code follow best practices?

Return your review as a JSON array of comments with this structure:
[
  {
    "file_path": "path/to/file.py",
    "line_number": 42,
    "severity": "blocker|major|minor|suggestion|praise",
    "category": "spec_compliance|code_quality|security|performance|testing|documentation|style|architecture",
    "title": "Short title",
    "description": "Detailed description",
    "suggestion": "How to fix (optional)"
  }
]

Be constructive and specific. Only report actual issues, not style preferences unless they impact readability.
"""

        user_prompt = f"""Review this code against the specification.

## Specification Context
{spec_context}

## Code to Review
{code_content}

Return only the JSON array of comments.
"""

        try:
            response = self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            comments = self._parse_llm_review(response.content)
        except Exception:
            pass  # LLM review is optional

        return comments

    def _get_spec_context(self, context: AgentContext) -> str:
        """Get spec context for review."""
        lines = []

        if context.spec:
            spec = context.spec

            if spec.name:
                lines.append(f"# Spec: {spec.name}")

            if spec.overview and spec.overview.summary:
                lines.append(f"\n## Summary\n{spec.overview.summary}")

            if spec.overview and spec.overview.goals:
                lines.append("\n## Goals")
                for goal in spec.overview.goals:
                    lines.append(f"- {goal}")

            if spec.api_contract and spec.api_contract.endpoints:
                lines.append("\n## API Endpoints")
                for ep in spec.api_contract.endpoints:
                    lines.append(f"- {ep.method} {ep.path}")

            if spec.security:
                lines.append("\n## Security Requirements")
                if spec.security.requires_auth:
                    lines.append(f"- Requires auth: {spec.security.auth_method}")
                if spec.security.handles_pii:
                    lines.append("- Handles PII: Yes")

        return "\n".join(lines)

    def _parse_llm_review(self, content: str) -> list[ReviewComment]:
        """Parse LLM review response."""
        import json
        import re

        comments = []

        # Try to extract JSON array
        try:
            # Find JSON array in response
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                for item in data:
                    try:
                        severity = ReviewSeverity(item.get("severity", "minor"))
                    except ValueError:
                        severity = ReviewSeverity.MINOR

                    try:
                        category = ReviewCategory(item.get("category", "code_quality"))
                    except ValueError:
                        category = ReviewCategory.CODE_QUALITY

                    comments.append(ReviewComment(
                        id="",
                        file_path=item.get("file_path", "*"),
                        line_number=item.get("line_number"),
                        severity=severity,
                        category=category,
                        title=item.get("title", "Review comment"),
                        description=item.get("description", ""),
                        suggestion=item.get("suggestion", ""),
                    ))
        except (json.JSONDecodeError, KeyError):
            pass

        return comments

    def review_files(
        self,
        files: dict[str, str],
        spec: Any = None,
    ) -> ReviewReport:
        """Review specific files (for direct API usage).

        Args:
            files: Dict of file path -> content.
            spec: Optional spec for compliance checking.

        Returns:
            ReviewReport with review comments.
        """
        from src.spec.schemas import Spec

        context = AgentContext(
            spec=spec or Spec(name=""),
            project_root=Path("."),
        )

        return self._review_code(
            code_files=files,
            test_files={},
            context=context,
        )
