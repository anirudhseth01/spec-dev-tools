"""Test coverage checker for code review."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.review.checkers.base import BaseChecker, ReviewContext
from src.agents.review.findings import ReviewComment, ReviewSeverity, ReviewCategory


@dataclass
class CoverageResult:
    """Result of coverage measurement."""

    line_coverage: float
    branch_coverage: float | None
    total_statements: int
    total_missing: int
    file_coverage: dict[str, dict[str, Any]]
    success: bool
    error: str | None = None


class TestCoverageChecker(BaseChecker):
    """Check test coverage meets minimum thresholds.

    Runs pytest-cov and validates:
    - Line coverage >= min_line_coverage (default 80%)
    - Branch coverage >= min_branch_coverage (default 70%)

    If coverage is below thresholds:
    - Generates ERROR comments for significant gaps
    - Sets metadata for orchestrator to trigger test generation feedback loop
    """

    name = "test_coverage_checker"
    description = "Validates test coverage meets minimum thresholds"
    is_heavyweight = False

    def __init__(
        self,
        min_line_coverage: float = 80.0,
        min_branch_coverage: float = 70.0,
        fail_on_low_coverage: bool = True,
    ):
        """Initialize coverage checker.

        Args:
            min_line_coverage: Minimum line coverage percentage (0-100).
            min_branch_coverage: Minimum branch coverage percentage (0-100).
            fail_on_low_coverage: Whether to generate ERROR comments for low coverage.
        """
        self.min_line_coverage = min_line_coverage
        self.min_branch_coverage = min_branch_coverage
        self.fail_on_low_coverage = fail_on_low_coverage

    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Check test coverage."""
        comments = []

        # Try to run coverage
        coverage_result = self._run_coverage(context)

        if not coverage_result.success:
            # Could not run coverage - add warning
            comments.append(ReviewComment(
                id=self._generate_id("COV", "project", 0),
                file_path="project",
                message=f"Could not measure test coverage: {coverage_result.error}",
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.TESTING,
                checker=self.name,
            ))
            return comments

        # Store coverage result in context metadata for orchestrator
        context.metadata["coverage_result"] = {
            "line_coverage": coverage_result.line_coverage,
            "branch_coverage": coverage_result.branch_coverage,
            "meets_threshold": self._meets_threshold(coverage_result),
            "needs_more_tests": not self._meets_threshold(coverage_result),
            "file_coverage": coverage_result.file_coverage,
        }

        # Check line coverage
        if coverage_result.line_coverage < self.min_line_coverage:
            severity = ReviewSeverity.ERROR if self.fail_on_low_coverage else ReviewSeverity.WARNING
            gap = self.min_line_coverage - coverage_result.line_coverage

            comments.append(ReviewComment(
                id=self._generate_id("COV", "line_coverage", 0),
                file_path="project",
                message=(
                    f"Line coverage is {coverage_result.line_coverage:.1f}%, "
                    f"below minimum threshold of {self.min_line_coverage}% "
                    f"(gap: {gap:.1f}%)"
                ),
                severity=severity,
                category=ReviewCategory.TESTING,
                suggestion=f"Add tests to improve coverage by at least {gap:.1f}%",
                checker=self.name,
                metadata={
                    "current_coverage": coverage_result.line_coverage,
                    "required_coverage": self.min_line_coverage,
                    "coverage_type": "line",
                },
            ))

        # Check branch coverage
        if coverage_result.branch_coverage is not None:
            if coverage_result.branch_coverage < self.min_branch_coverage:
                severity = ReviewSeverity.ERROR if self.fail_on_low_coverage else ReviewSeverity.WARNING
                gap = self.min_branch_coverage - coverage_result.branch_coverage

                comments.append(ReviewComment(
                    id=self._generate_id("COV", "branch_coverage", 0),
                    file_path="project",
                    message=(
                        f"Branch coverage is {coverage_result.branch_coverage:.1f}%, "
                        f"below minimum threshold of {self.min_branch_coverage}% "
                        f"(gap: {gap:.1f}%)"
                    ),
                    severity=severity,
                    category=ReviewCategory.TESTING,
                    suggestion=f"Add tests for conditional branches to improve by {gap:.1f}%",
                    checker=self.name,
                    metadata={
                        "current_coverage": coverage_result.branch_coverage,
                        "required_coverage": self.min_branch_coverage,
                        "coverage_type": "branch",
                    },
                ))

        # Add per-file coverage comments for files below threshold
        for file_path, file_data in coverage_result.file_coverage.items():
            file_coverage = file_data.get("percent_covered", 0)
            missing_lines = file_data.get("missing_lines", [])

            if file_coverage < self.min_line_coverage and missing_lines:
                # Only add comment if significantly below threshold
                if file_coverage < self.min_line_coverage - 10:
                    severity = ReviewSeverity.WARNING

                    # List first few missing lines
                    missing_str = ", ".join(str(l) for l in missing_lines[:5])
                    if len(missing_lines) > 5:
                        missing_str += f", ... (+{len(missing_lines) - 5} more)"

                    comments.append(ReviewComment(
                        id=self._generate_id("COV", file_path, 0),
                        file_path=file_path,
                        message=(
                            f"File coverage is {file_coverage:.1f}%, "
                            f"below threshold of {self.min_line_coverage}%"
                        ),
                        severity=severity,
                        category=ReviewCategory.TESTING,
                        suggestion=f"Add tests covering lines: {missing_str}",
                        checker=self.name,
                        metadata={
                            "file_coverage": file_coverage,
                            "missing_lines": missing_lines,
                        },
                    ))

        return comments

    def _meets_threshold(self, result: CoverageResult) -> bool:
        """Check if coverage meets minimum thresholds."""
        if result.line_coverage < self.min_line_coverage:
            return False
        if result.branch_coverage is not None:
            if result.branch_coverage < self.min_branch_coverage:
                return False
        return True

    def _run_coverage(self, context: ReviewContext) -> CoverageResult:
        """Run pytest-cov and return coverage data."""
        project_root = context.project_root

        # Find test directory
        test_dirs = ["tests", "test"]
        test_dir = None
        for td in test_dirs:
            if (project_root / td).exists():
                test_dir = td
                break

        if not test_dir:
            return CoverageResult(
                line_coverage=0,
                branch_coverage=None,
                total_statements=0,
                total_missing=0,
                file_coverage={},
                success=False,
                error="No test directory found",
            )

        # Find source directory
        source_dirs = ["src", "lib", project_root.name]
        source_dir = None
        for sd in source_dirs:
            if (project_root / sd).exists():
                source_dir = sd
                break

        # Build pytest command
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            json_report = f.name

        cmd = [
            sys.executable, "-m", "pytest",
            test_dir,
            "-v",
            "--tb=no",
            "--no-header",
            "-q",
            "--cov-branch",
            f"--cov-report=json:{json_report}",
            "--cov-report=",  # Suppress terminal output
        ]

        if source_dir:
            cmd.append(f"--cov={source_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
            )

            # Parse JSON report
            try:
                with open(json_report) as f:
                    cov_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return CoverageResult(
                    line_coverage=0,
                    branch_coverage=None,
                    total_statements=0,
                    total_missing=0,
                    file_coverage={},
                    success=False,
                    error="Could not parse coverage report",
                )
            finally:
                # Cleanup
                try:
                    Path(json_report).unlink()
                except Exception:
                    pass

            # Extract totals
            totals = cov_data.get("totals", {})
            line_coverage = totals.get("percent_covered", 0)
            branch_coverage = totals.get("percent_covered_branches")
            total_statements = totals.get("num_statements", 0)
            total_missing = totals.get("missing_lines", 0)

            # Extract per-file coverage
            file_coverage = {}
            for filepath, data in cov_data.get("files", {}).items():
                summary = data.get("summary", {})
                file_coverage[filepath] = {
                    "percent_covered": summary.get("percent_covered", 0),
                    "num_statements": summary.get("num_statements", 0),
                    "missing_lines": data.get("missing_lines", []),
                    "num_branches": summary.get("num_branches", 0),
                }

            return CoverageResult(
                line_coverage=line_coverage,
                branch_coverage=branch_coverage,
                total_statements=total_statements,
                total_missing=total_missing,
                file_coverage=file_coverage,
                success=True,
            )

        except subprocess.TimeoutExpired:
            return CoverageResult(
                line_coverage=0,
                branch_coverage=None,
                total_statements=0,
                total_missing=0,
                file_coverage={},
                success=False,
                error="Coverage measurement timed out",
            )
        except Exception as e:
            return CoverageResult(
                line_coverage=0,
                branch_coverage=None,
                total_statements=0,
                total_missing=0,
                file_coverage={},
                success=False,
                error=str(e),
            )

    def get_file_extensions(self) -> list[str]:
        """This checker works on the project level, not specific files."""
        return []
