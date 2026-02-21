"""Ruff linter checker for Python code review."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.agents.review.checkers.base import BaseChecker, ReviewContext
from src.agents.review.findings import (
    ReviewComment,
    ReviewSeverity,
    ReviewCategory,
)


# Ruff rule code prefixes to severity mapping
RUFF_SEVERITY_MAP = {
    # Errors (blocking)
    "E9": ReviewSeverity.ERROR,   # Runtime errors
    "F4": ReviewSeverity.ERROR,   # Import errors
    "F5": ReviewSeverity.ERROR,   # Syntax errors
    "F6": ReviewSeverity.ERROR,   # Undefined names
    "F7": ReviewSeverity.ERROR,   # Statement issues
    "F8": ReviewSeverity.ERROR,   # Name errors
    "S": ReviewSeverity.ERROR,    # Security issues (bandit)
    # Warnings
    "F": ReviewSeverity.WARNING,  # Pyflakes (general)
    "W": ReviewSeverity.WARNING,  # pycodestyle warnings
    "C": ReviewSeverity.WARNING,  # Complexity
    "B": ReviewSeverity.WARNING,  # Bugbear (likely bugs)
    "N": ReviewSeverity.WARNING,  # Naming conventions
    # Suggestions
    "E": ReviewSeverity.SUGGESTION,  # pycodestyle errors (style)
    "I": ReviewSeverity.SUGGESTION,  # isort
    "D": ReviewSeverity.SUGGESTION,  # pydocstyle
    "UP": ReviewSeverity.SUGGESTION,  # pyupgrade
    "PL": ReviewSeverity.SUGGESTION,  # pylint
    "RUF": ReviewSeverity.SUGGESTION,  # ruff-specific
}

# Ruff rule code prefixes to category mapping
RUFF_CATEGORY_MAP = {
    "E": ReviewCategory.STYLE,
    "W": ReviewCategory.STYLE,
    "F": ReviewCategory.LOGIC,
    "I": ReviewCategory.STYLE,
    "N": ReviewCategory.STYLE,
    "D": ReviewCategory.DOCUMENTATION,
    "UP": ReviewCategory.MAINTAINABILITY,
    "B": ReviewCategory.LOGIC,
    "C": ReviewCategory.MAINTAINABILITY,
    "S": ReviewCategory.SECURITY,
    "PL": ReviewCategory.BEST_PRACTICE,
    "RUF": ReviewCategory.STYLE,
}


class RuffChecker(BaseChecker):
    """Ruff linter checker for Python files.

    Runs ruff on Python files and converts findings to review comments.
    Ruff is a fast Python linter written in Rust that implements many
    rules from flake8, isort, pyupgrade, and more.

    Features:
    - Auto-detects ruff installation
    - Falls back gracefully if ruff not available
    - Maps ruff rule codes to appropriate severity/category
    - Extracts suggestions from ruff output
    """

    name = "ruff_checker"
    description = "Python linter using ruff"
    is_heavyweight = False  # ruff is very fast

    def __init__(
        self,
        ruff_path: str | None = None,
        select_rules: list[str] | None = None,
        ignore_rules: list[str] | None = None,
        max_issues_per_file: int = 20,
    ):
        """Initialize ruff checker.

        Args:
            ruff_path: Path to ruff binary (auto-detected if None).
            select_rules: Rules to enable (e.g., ["E", "F", "W"]).
            ignore_rules: Rules to ignore (e.g., ["E501"]).
            max_issues_per_file: Max issues to report per file.
        """
        self.ruff_path = ruff_path or self._find_ruff()
        self.select_rules = select_rules
        self.ignore_rules = ignore_rules
        self.max_issues_per_file = max_issues_per_file

    def _find_ruff(self) -> str | None:
        """Find ruff binary in PATH or current Python environment."""
        import sys

        # First check PATH
        ruff_path = shutil.which("ruff")
        if ruff_path:
            return ruff_path

        # Check in current Python environment's bin/Scripts directory
        venv_bin = Path(sys.executable).parent
        ruff_in_venv = venv_bin / "ruff"
        if ruff_in_venv.exists():
            return str(ruff_in_venv)

        # Windows variant
        ruff_in_venv_exe = venv_bin / "ruff.exe"
        if ruff_in_venv_exe.exists():
            return str(ruff_in_venv_exe)

        return None

    def get_file_extensions(self) -> list[str]:
        """Ruff only handles Python files."""
        return [".py"]

    def supports_language(self, language: str) -> bool:
        """Only supports Python."""
        return language.lower() == "python"

    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Check Python files using ruff."""
        if not self.ruff_path:
            # Ruff not available, skip silently
            return []

        # Get Python files only
        python_files = context.get_python_files()
        if not python_files:
            return []

        comments = []

        # Write files to temp directory for ruff to analyze
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write files
            for file_path, content in python_files.items():
                # Preserve directory structure
                full_path = tmpdir_path / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # Run ruff
            ruff_results = self._run_ruff(tmpdir_path)

            # Convert results to comments
            for result in ruff_results:
                file_path = result.get("filename", "")
                # Remove temp dir prefix
                if file_path.startswith(str(tmpdir_path)):
                    file_path = file_path[len(str(tmpdir_path)) + 1:]

                comment = self._result_to_comment(result, file_path, python_files)
                if comment:
                    comments.append(comment)

        # Group by file and limit
        file_comments: dict[str, list[ReviewComment]] = {}
        for comment in comments:
            if comment.file_path not in file_comments:
                file_comments[comment.file_path] = []
            file_comments[comment.file_path].append(comment)

        # Apply per-file limit
        limited_comments = []
        for file_path, file_cmts in file_comments.items():
            limited_comments.extend(file_cmts[:self.max_issues_per_file])

        return limited_comments

    def _run_ruff(self, target_dir: Path) -> list[dict]:
        """Run ruff and return results as list of dicts."""
        cmd = [
            self.ruff_path,
            "check",
            "--output-format=json",
            "--no-cache",
            str(target_dir),
        ]

        # Add rule selection
        if self.select_rules:
            cmd.extend(["--select", ",".join(self.select_rules)])
        if self.ignore_rules:
            cmd.extend(["--ignore", ",".join(self.ignore_rules)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 1 minute timeout
            )
            # ruff returns non-zero if it finds issues, but output is still valid
            if result.stdout:
                return json.loads(result.stdout)
            return []
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            return []

    def _result_to_comment(
        self,
        result: dict,
        file_path: str,
        files: dict[str, str],
    ) -> ReviewComment | None:
        """Convert a ruff result to a ReviewComment."""
        code = result.get("code", "")
        message = result.get("message", "")
        line = result.get("location", {}).get("row")
        column = result.get("location", {}).get("column")

        if not code or not message:
            return None

        # Determine severity
        severity = self._get_severity(code)

        # Determine category
        category = self._get_category(code)

        # Extract code snippet if we have the file content
        snippet = ""
        if file_path in files and line:
            lines = files[file_path].splitlines()
            if 0 < line <= len(lines):
                snippet = lines[line - 1].strip()

        # Check for fix suggestion
        suggestion = ""
        if result.get("fix"):
            fix = result["fix"]
            suggestion = fix.get("message", "")
            if fix.get("applicability") == "safe":
                suggestion = f"[Auto-fixable] {suggestion}" if suggestion else "[Auto-fixable with --fix]"

        return ReviewComment(
            id=self._generate_id(f"RUFF-{code}", file_path, line),
            file_path=file_path,
            line_number=line,
            column=column,
            message=f"[{code}] {message}",
            severity=severity,
            category=category,
            suggestion=suggestion or f"Run 'ruff check --fix' to auto-fix if available",
            code_snippet=snippet,
            checker=self.name,
            confidence=1.0,  # ruff is deterministic
        )

    def _get_severity(self, code: str) -> ReviewSeverity:
        """Get severity based on ruff rule code."""
        # Check specific prefixes first (longer prefixes = more specific)
        for prefix in sorted(RUFF_SEVERITY_MAP.keys(), key=len, reverse=True):
            if code.startswith(prefix):
                return RUFF_SEVERITY_MAP[prefix]
        return ReviewSeverity.SUGGESTION

    def _get_category(self, code: str) -> ReviewCategory:
        """Get category based on ruff rule code."""
        for prefix in sorted(RUFF_CATEGORY_MAP.keys(), key=len, reverse=True):
            if code.startswith(prefix):
                return RUFF_CATEGORY_MAP[prefix]
        return ReviewCategory.STYLE
