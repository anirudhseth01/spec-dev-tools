"""Checker registry for managing available checkers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.review.checkers.base import BaseChecker, ReviewContext
from src.agents.review.checkers.style_checker import StyleChecker
from src.agents.review.checkers.spec_compliance import SpecComplianceChecker
from src.agents.review.checkers.best_practices import BestPracticesChecker
from src.agents.review.checkers.ruff_checker import RuffChecker
from src.agents.review.findings import ReviewComment, SpecComplianceStatus

if TYPE_CHECKING:
    from src.llm.client import LLMClient


class LLMReviewChecker(BaseChecker):
    """LLM-powered deep code review checker.

    Uses an LLM to perform sophisticated code analysis:
    - Logic correctness
    - Architecture concerns
    - Design pattern suggestions
    - Complex security issues
    - Spec interpretation nuances
    """

    name = "llm_review_checker"
    description = "LLM-powered deep code review"
    is_heavyweight = True

    def __init__(self, llm_client: LLMClient):
        """Initialize LLM review checker.

        Args:
            llm_client: LLM client for analysis.
        """
        self.llm = llm_client

    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Perform LLM-powered code review."""
        from src.agents.review.findings import (
            ReviewComment,
            ReviewSeverity,
            ReviewCategory,
        )

        comments = []

        # Build review prompt
        prompt = self._build_review_prompt(context)
        system_prompt = self._get_system_prompt()

        try:
            response = self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
                max_tokens=4096,
                temperature=0.2,
            )

            # Parse LLM response
            comments = self._parse_response(response.content, context)

        except Exception as e:
            # LLM failure shouldn't break the review
            pass

        return comments

    def _get_system_prompt(self) -> str:
        """Get system prompt for code review."""
        return """You are an expert code reviewer. Analyze the provided code and spec context.

Focus on:
1. Logic correctness - does the code do what the spec requires?
2. Edge cases - are all edge cases handled?
3. Error handling - is error handling comprehensive?
4. Security - are there security vulnerabilities?
5. Performance - are there obvious performance issues?
6. Maintainability - is the code clean and maintainable?

For each issue found, output in this format:
[ISSUE]
FILE: <file_path>
LINE: <line_number or "general">
SEVERITY: <error|warning|suggestion>
CATEGORY: <logic|security|performance|maintainability|error_handling|spec_compliance>
MESSAGE: <description of the issue>
SUGGESTION: <how to fix it>
[/ISSUE]

Be thorough but practical. Focus on significant issues, not style nitpicks."""

    def _build_review_prompt(self, context: ReviewContext) -> str:
        """Build the review prompt from context."""
        lines = []

        if context.spec_context:
            lines.append("## Specification Context")
            lines.append(context.spec_context)
            lines.append("")

        lines.append("## Code to Review")
        for file_path, content in context.files.items():
            lines.append(f"\n### {file_path}")
            lines.append("```")
            # Truncate very long files
            if len(content) > 10000:
                lines.append(content[:10000])
                lines.append("\n... (truncated)")
            else:
                lines.append(content)
            lines.append("```")

        lines.append("\n## Review Request")
        lines.append("Please review the code above against the specification.")
        lines.append("Identify any issues with logic, security, performance, or spec compliance.")

        return "\n".join(lines)

    def _parse_response(
        self,
        response: str,
        context: ReviewContext,
    ) -> list[ReviewComment]:
        """Parse LLM response into review comments."""
        import re
        from src.agents.review.findings import (
            ReviewComment,
            ReviewSeverity,
            ReviewCategory,
        )

        comments = []
        issue_pattern = r"\[ISSUE\](.*?)\[/ISSUE\]"

        for match in re.finditer(issue_pattern, response, re.DOTALL):
            issue_text = match.group(1)

            # Parse fields
            file_match = re.search(r"FILE:\s*(.+)", issue_text)
            line_match = re.search(r"LINE:\s*(\d+|general)", issue_text)
            severity_match = re.search(r"SEVERITY:\s*(\w+)", issue_text)
            category_match = re.search(r"CATEGORY:\s*(\w+)", issue_text)
            message_match = re.search(r"MESSAGE:\s*(.+?)(?=\n[A-Z]+:|$)", issue_text, re.DOTALL)
            suggestion_match = re.search(r"SUGGESTION:\s*(.+?)(?=\n[A-Z]+:|$)", issue_text, re.DOTALL)

            if not (file_match and message_match):
                continue

            file_path = file_match.group(1).strip()
            line_number = None
            if line_match and line_match.group(1) != "general":
                try:
                    line_number = int(line_match.group(1))
                except ValueError:
                    pass

            severity_str = severity_match.group(1).lower() if severity_match else "warning"
            severity_map = {
                "error": ReviewSeverity.ERROR,
                "warning": ReviewSeverity.WARNING,
                "suggestion": ReviewSeverity.SUGGESTION,
            }
            severity = severity_map.get(severity_str, ReviewSeverity.WARNING)

            category_str = category_match.group(1).lower() if category_match else "logic"
            category_map = {
                "logic": ReviewCategory.LOGIC,
                "security": ReviewCategory.SECURITY,
                "performance": ReviewCategory.PERFORMANCE,
                "maintainability": ReviewCategory.MAINTAINABILITY,
                "error_handling": ReviewCategory.ERROR_HANDLING,
                "spec_compliance": ReviewCategory.SPEC_COMPLIANCE,
                "style": ReviewCategory.STYLE,
                "documentation": ReviewCategory.DOCUMENTATION,
            }
            category = category_map.get(category_str, ReviewCategory.LOGIC)

            message = message_match.group(1).strip()
            suggestion = suggestion_match.group(1).strip() if suggestion_match else ""

            comments.append(ReviewComment(
                id=self._generate_id("LLM", file_path, line_number),
                file_path=file_path,
                line_number=line_number,
                message=message,
                severity=severity,
                category=category,
                suggestion=suggestion,
                checker=self.name,
                confidence=0.85,  # LLM reviews have some uncertainty
            ))

        return comments


class CheckerRegistry:
    """Registry for code review checkers."""

    def __init__(self):
        """Initialize with default checkers."""
        self._checkers: dict[str, BaseChecker] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in checkers."""
        self.register(StyleChecker())
        self.register(SpecComplianceChecker())
        self.register(BestPracticesChecker())
        self.register(RuffChecker())

    def register(self, checker: BaseChecker) -> None:
        """Register a checker."""
        self._checkers[checker.name] = checker

    def register_llm_checker(self, llm_client: LLMClient) -> None:
        """Register LLM checker with client."""
        self.register(LLMReviewChecker(llm_client))

    def get(self, name: str) -> BaseChecker | None:
        """Get a checker by name."""
        return self._checkers.get(name)

    def list_checkers(self) -> list[str]:
        """List all registered checker names."""
        return list(self._checkers.keys())

    def get_lightweight_checkers(self) -> list[BaseChecker]:
        """Get checkers that run in lightweight mode."""
        return [c for c in self._checkers.values() if not c.is_heavyweight]

    def get_all_checkers(self) -> list[BaseChecker]:
        """Get all checkers (including heavyweight)."""
        return list(self._checkers.values())

    def check(
        self,
        context: ReviewContext,
        deep_review: bool = False,
    ) -> list[ReviewComment]:
        """Run all appropriate checkers.

        Args:
            context: Review context with files.
            deep_review: Whether to include heavyweight (LLM) checkers.

        Returns:
            Combined comments from all checkers.
        """
        comments = []

        if deep_review:
            checkers = self.get_all_checkers()
        else:
            checkers = self.get_lightweight_checkers()

        for checker in checkers:
            try:
                checker_comments = checker.check(context)
                comments.extend(checker_comments)
            except Exception:
                # Don't let one checker failure stop the others
                pass

        # Deduplicate similar comments
        comments = self._deduplicate(comments)

        # Sort by severity then line number
        comments.sort(key=lambda c: (c.severity.score, c.line_number or 0), reverse=True)

        return comments

    def get_compliance_status(
        self,
        context: ReviewContext,
    ) -> list[SpecComplianceStatus]:
        """Get spec compliance status from compliance checker."""
        checker = self.get("spec_compliance_checker")
        if checker and isinstance(checker, SpecComplianceChecker):
            return checker.get_compliance_status(context)
        return []

    def _deduplicate(self, comments: list[ReviewComment]) -> list[ReviewComment]:
        """Remove duplicate comments (same location + category)."""
        seen = set()
        unique = []

        for comment in comments:
            key = (comment.file_path, comment.line_number, comment.category)
            if key not in seen:
                seen.add(key)
                unique.append(comment)

        return unique
