"""CodeReviewAgent for automated code quality review."""

from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from src.agents.review.findings import (
    ReviewReport,
    ReviewComment,
    ReviewSeverity,
    ReviewCategory,
    SpecComplianceStatus,
)
from src.agents.review.checkers import (
    ReviewContext,
    CheckerRegistry,
    StyleChecker,
    SpecComplianceChecker,
    BestPracticesChecker,
)

try:
    from src.llm.client import LLMClient
except ImportError:
    LLMClient = None


class ReviewMode(Enum):
    """Execution mode for code review."""

    QUICK = "quick"          # Fast, pattern-based (~5s)
    STANDARD = "standard"    # All lightweight checkers (~30s)
    DEEP = "deep"            # Includes LLM analysis (~2-5min)


class CodeReviewAgent(BaseAgent):
    """Code review agent with multiple review modes and coverage validation.

    Quick Mode (for rapid feedback):
    - Basic style checks
    - Obvious anti-patterns
    - Fast execution (~5 seconds)

    Standard Mode (default, for PRs):
    - All pattern-based checks
    - Style, best practices, spec compliance
    - Test coverage validation
    - Medium execution (~30 seconds)

    Deep Mode (thorough review):
    - All standard checks PLUS
    - LLM-powered logic analysis
    - Architecture concerns
    - Full review report (~2-5 minutes)

    Coverage Feedback Loop:
    - If test coverage < min_coverage (default 80%), sets needs_more_tests flag
    - Orchestrator can use this to trigger TestGeneratorAgent to add more tests
    - Supports iterative improvement up to max_coverage_iterations

    Design Decisions:
    - Spec-first: Primary focus is spec compliance
    - Modular: Uses pluggable checker system
    - Multi-severity: error/warning/suggestion levels
    - Actionable: Provides specific suggestions for improvements
    - Coverage-aware: Validates test coverage and triggers feedback loop
    """

    name = "code_review_agent"
    description = "Automated code quality reviewer with coverage validation"
    requires = ["coding_agent"]  # Reviews code after generation

    def __init__(
        self,
        mode: ReviewMode | str = ReviewMode.STANDARD,
        llm_client: Optional[Any] = None,
        checker_registry: Optional[CheckerRegistry] = None,
        file_extensions: list[str] | None = None,
        max_files: int = 50,
        fail_on_errors: bool = True,
        min_coverage: float = 80.0,
        enable_coverage_feedback: bool = True,
    ):
        """Initialize CodeReviewAgent.

        Args:
            mode: Review mode (quick, standard, or deep).
            llm_client: LLM client for deep mode.
            checker_registry: Custom checker registry.
            file_extensions: File extensions to review.
            max_files: Maximum number of files to review.
            fail_on_errors: Whether to fail the agent on error-level findings.
            min_coverage: Minimum test coverage percentage (0-100).
            enable_coverage_feedback: Whether to enable coverage feedback loop.
        """
        if isinstance(mode, str):
            mode = ReviewMode(mode)
        self.mode = mode

        self.llm = llm_client
        self.registry = checker_registry or CheckerRegistry()

        # Configure deep mode if needed
        if mode == ReviewMode.DEEP and llm_client:
            self.registry.register_llm_checker(llm_client)

        self.file_extensions = file_extensions or [
            ".py", ".js", ".ts", ".jsx", ".tsx",
            ".go", ".java", ".rb", ".rs",
        ]
        self.max_files = max_files
        self.fail_on_errors = fail_on_errors
        self.min_coverage = min_coverage
        self.enable_coverage_feedback = enable_coverage_feedback

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute code review with coverage validation."""
        start_time = time.time()

        try:
            # Collect files to review
            files = self._collect_files(context)

            if not files:
                return AgentResult(
                    status=AgentStatus.SUCCESS,
                    message="No files to review",
                    data={"report": ReviewReport().to_dict()},
                )

            # Build review context
            review_context = self._build_review_context(files, context)

            # Run checkers based on mode
            deep_review = (self.mode == ReviewMode.DEEP)
            comments = self.registry.check(
                context=review_context,
                deep_review=deep_review,
            )

            # Get spec compliance status
            compliance_status = []
            if self.mode != ReviewMode.QUICK:
                compliance_status = self.registry.get_compliance_status(review_context)

            # Extract coverage results from review context
            coverage_result = review_context.metadata.get("coverage_result", {})
            needs_more_tests = coverage_result.get("needs_more_tests", False)
            line_coverage = coverage_result.get("line_coverage", 0)

            # Build report
            duration_ms = int((time.time() - start_time) * 1000)
            report = ReviewReport(
                comments=comments,
                files_reviewed=len(files),
                review_duration_ms=duration_ms,
                spec_compliance=compliance_status,
                summary_notes=self._generate_summary_notes(comments, compliance_status),
            )

            # Add coverage to summary notes
            if coverage_result:
                report.summary_notes.append(
                    f"Test coverage: {line_coverage:.1f}% "
                    f"(threshold: {self.min_coverage}%)"
                )
                if needs_more_tests:
                    report.summary_notes.append(
                        "Coverage below threshold - more tests needed"
                    )

            # Determine status
            # If coverage feedback is enabled and coverage is low, we return success
            # but with needs_more_tests flag so orchestrator can trigger more tests
            if self.fail_on_errors and report.has_blocking_issues:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message=report.to_summary(),
                    data={
                        "report": report.to_dict(),
                        "markdown_report": report.to_markdown(),
                        "has_blocking_issues": True,
                        "blocking_count": len(report.blocking_comments),
                        "review_report": report,
                        "needs_more_tests": needs_more_tests,
                        "coverage_result": coverage_result,
                    },
                    errors=[
                        f"{c.location}: {c.message}"
                        for c in report.blocking_comments
                    ],
                )

            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=report.to_summary(),
                data={
                    "report": report.to_dict(),
                    "markdown_report": report.to_markdown(),
                    "has_blocking_issues": report.has_blocking_issues,
                    "review_report": report,
                    "needs_more_tests": needs_more_tests,
                    "coverage_result": coverage_result,
                    "low_coverage_files": self._get_low_coverage_files(coverage_result),
                },
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Code review failed: {str(e)}",
                errors=[str(e)],
            )

    def _get_low_coverage_files(self, coverage_result: dict) -> list[dict]:
        """Extract files with coverage below threshold."""
        low_files = []
        file_coverage = coverage_result.get("file_coverage", {})

        for file_path, data in file_coverage.items():
            pct = data.get("percent_covered", 0)
            if pct < self.min_coverage:
                low_files.append({
                    "file_path": file_path,
                    "coverage": pct,
                    "missing_lines": data.get("missing_lines", []),
                    "gap": self.min_coverage - pct,
                })

        # Sort by coverage gap (worst first)
        low_files.sort(key=lambda x: x["gap"], reverse=True)
        return low_files

    def _collect_files(self, context: AgentContext) -> dict[str, str]:
        """Collect files to review from context and artifacts."""
        files = {}

        # Get files from coding agent artifacts
        if "artifacts" in context.parent_context:
            artifacts = context.parent_context["artifacts"]

            # Code artifact (dict of file path -> content)
            if "code" in artifacts:
                code_artifact = artifacts["code"]
                if isinstance(code_artifact, dict) and "value" in code_artifact:
                    code_files = code_artifact["value"]
                    if isinstance(code_files, dict):
                        files.update(code_files)

            # Files created list
            if "files_created" in artifacts:
                files_artifact = artifacts["files_created"]
                if isinstance(files_artifact, dict) and "value" in files_artifact:
                    file_list = files_artifact["value"]
                    for file_path in file_list:
                        if file_path not in files:
                            full_path = context.project_root / file_path
                            if full_path.exists():
                                try:
                                    files[file_path] = full_path.read_text()
                                except Exception:
                                    pass

        # Get from previous results (coding_agent)
        coding_result = context.get_result("coding_agent")
        if coding_result and coding_result.is_success:
            if "code" in coding_result.data:
                code_data = coding_result.data["code"]
                if isinstance(code_data, dict):
                    files.update(code_data)

        # If no artifacts, scan project directory
        if not files:
            files = self._scan_directory(context.project_root)

        # Filter by extension and limit
        filtered = {}
        for path, content in files.items():
            ext = "." + path.split(".")[-1] if "." in path else ""
            if ext in self.file_extensions:
                filtered[path] = content
                if len(filtered) >= self.max_files:
                    break

        return filtered

    def _scan_directory(self, directory: Path) -> dict[str, str]:
        """Scan a directory for code files."""
        files = {}

        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".pytest_cache", ".mypy_cache", "dist", "build", ".tox",
        }

        for path in directory.rglob("*"):
            if path.is_dir():
                continue

            if any(skip in path.parts for skip in skip_dirs):
                continue

            if path.suffix not in self.file_extensions:
                continue

            try:
                relative_path = str(path.relative_to(directory))
                files[relative_path] = path.read_text()
            except Exception:
                pass

            if len(files) >= self.max_files:
                break

        return files

    def _build_review_context(
        self,
        files: dict[str, str],
        context: AgentContext,
    ) -> ReviewContext:
        """Build review context from agent context."""
        spec_context = ""

        # Get routed spec from parent context
        if "routed_spec" in context.parent_context:
            routed = context.parent_context["routed_spec"]
            if hasattr(routed, "to_prompt_context"):
                spec_context = routed.to_prompt_context()

        # Fallback to extracting from spec
        if not spec_context and context.spec:
            spec_context = self._spec_to_context(context.spec)

        return ReviewContext(
            files=files,
            project_root=context.project_root,
            spec=context.spec,
            spec_context=spec_context,
        )

    def _spec_to_context(self, spec: Any) -> str:
        """Convert spec to context string."""
        lines = []

        if hasattr(spec, "name") and spec.name:
            lines.append(f"# {spec.name}")

        if hasattr(spec, "overview") and spec.overview:
            lines.append("## Overview")
            if spec.overview.summary:
                lines.append(f"Summary: {spec.overview.summary}")
            if spec.overview.goals:
                lines.append("Goals:")
                for goal in spec.overview.goals:
                    lines.append(f"  - {goal}")
            lines.append("")

        if hasattr(spec, "api_contract") and spec.api_contract:
            lines.append("## API Contract")
            for endpoint in spec.api_contract.endpoints:
                lines.append(f"- {endpoint.method} {endpoint.path}")
            lines.append("")

        if hasattr(spec, "error_handling") and spec.error_handling:
            lines.append("## Error Handling")
            error_handling = spec.error_handling
            if hasattr(error_handling, "error_cases"):
                for error in error_handling.error_cases:
                    lines.append(f"- {error.code}: {error.message}")
            lines.append("")

        if hasattr(spec, "security") and spec.security:
            lines.append("## Security")
            security = spec.security
            if hasattr(security, "authentication_required"):
                lines.append(f"- Authentication required: {security.authentication_required}")
            lines.append("")

        return "\n".join(lines)

    def _generate_summary_notes(
        self,
        comments: list[ReviewComment],
        compliance: list[SpecComplianceStatus],
    ) -> list[str]:
        """Generate summary notes for the report."""
        notes = []

        # Count by category
        categories: dict[str, int] = {}
        for c in comments:
            cat = c.category.value
            categories[cat] = categories.get(cat, 0) + 1

        if categories:
            top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
            for cat, count in top_categories:
                notes.append(f"Most issues in: {cat.replace('_', ' ').title()} ({count})")

        # Compliance summary
        if compliance:
            failed = [c for c in compliance if c.status == "fail"]
            if failed:
                notes.append(f"Spec compliance issues: {len(failed)} requirements not met")
            else:
                notes.append("All spec requirements verified")

        return notes

    def review_files(
        self,
        files: dict[str, str],
        spec: Any = None,
        spec_context: str = "",
    ) -> ReviewReport:
        """Review specific files (for direct API usage).

        Args:
            files: Dict of file path -> content.
            spec: Optional spec for compliance checking.
            spec_context: Optional spec context string.

        Returns:
            ReviewReport with findings.
        """
        start_time = time.time()

        review_context = ReviewContext(
            files=files,
            project_root=Path("."),
            spec=spec,
            spec_context=spec_context,
        )

        deep_review = (self.mode == ReviewMode.DEEP)
        comments = self.registry.check(
            context=review_context,
            deep_review=deep_review,
        )

        compliance_status = []
        if self.mode != ReviewMode.QUICK:
            compliance_status = self.registry.get_compliance_status(review_context)

        duration_ms = int((time.time() - start_time) * 1000)

        return ReviewReport(
            comments=comments,
            files_reviewed=len(files),
            review_duration_ms=duration_ms,
            spec_compliance=compliance_status,
            summary_notes=self._generate_summary_notes(comments, compliance_status),
        )

    def add_checker(self, checker) -> None:
        """Add a custom checker to the registry.

        Args:
            checker: A checker instance implementing BaseChecker.
        """
        self.registry.register(checker)
