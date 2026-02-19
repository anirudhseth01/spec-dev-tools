"""Style checker for code review - checks code style and conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from src.agents.review.checkers.base import BaseChecker, ReviewContext
from src.agents.review.findings import (
    ReviewComment,
    ReviewSeverity,
    ReviewCategory,
)


@dataclass
class StyleRule:
    """A code style rule to check."""

    id: str
    name: str
    pattern: str  # Regex pattern
    message: str
    suggestion: str = ""
    severity: ReviewSeverity = ReviewSeverity.WARNING
    file_extensions: list[str] | None = None  # None = all files
    multiline: bool = False
    check_fn: Callable[[str, str], bool] | None = None  # Custom check function


# Python style rules
PYTHON_STYLE_RULES = [
    StyleRule(
        id="PY001",
        name="Line too long",
        pattern=r"^.{120,}$",
        message="Line exceeds 120 characters",
        suggestion="Break the line into multiple lines for better readability",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY002",
        name="Missing docstring",
        pattern=r"^(def|class)\s+\w+[^:]*:\s*\n\s*(?!\"\"\"|\'\'\')(?=\S)",
        message="Function or class is missing a docstring",
        suggestion="Add a docstring describing the purpose, parameters, and return value",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
        multiline=True,
    ),
    StyleRule(
        id="PY003",
        name="Trailing whitespace",
        pattern=r"\s+$",
        message="Line has trailing whitespace",
        suggestion="Remove trailing whitespace",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY004",
        name="Import star",
        pattern=r"from\s+\S+\s+import\s+\*",
        message="Avoid 'from X import *' - it pollutes the namespace",
        suggestion="Import specific names: 'from module import name1, name2'",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY005",
        name="Bare except",
        pattern=r"except\s*:",
        message="Avoid bare 'except:' clauses - they catch all exceptions including system ones",
        suggestion="Use 'except Exception:' or catch specific exceptions",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY006",
        name="Mutable default argument",
        pattern=r"def\s+\w+\([^)]*=\s*(\[\]|\{\}|\w+\(\))[^)]*\)",
        message="Mutable default argument can lead to unexpected behavior",
        suggestion="Use None as default and initialize inside the function: 'def f(x=None): x = x or []'",
        severity=ReviewSeverity.ERROR,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY007",
        name="Print statement in production code",
        pattern=r"^\s*print\s*\(",
        message="Avoid print() in production code",
        suggestion="Use logging instead: 'logger.info(...)' or 'logger.debug(...)'",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY008",
        name="TODO comment",
        pattern=r"#\s*(TODO|FIXME|XXX|HACK):",
        message="Found TODO/FIXME comment that should be addressed",
        suggestion="Address the TODO or create a tracked issue",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY009",
        name="Unused import indicator",
        pattern=r"^import\s+\w+\s*$",
        message="Check if this import is actually used",
        suggestion="Remove unused imports or use 'from X import Y' for specific imports",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    StyleRule(
        id="PY010",
        name="Assert in production code",
        pattern=r"^\s*assert\s+",
        message="Assert statements can be disabled with -O flag",
        suggestion="Use explicit if/raise for production validation",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
]

# TypeScript/JavaScript style rules
TS_STYLE_RULES = [
    StyleRule(
        id="TS001",
        name="Console log",
        pattern=r"console\.(log|debug|info|warn)\s*\(",
        message="Avoid console.log in production code",
        suggestion="Use a proper logging library or remove debug statements",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
    ),
    StyleRule(
        id="TS002",
        name="Any type",
        pattern=r":\s*any\b",
        message="Avoid using 'any' type - it defeats TypeScript's type checking",
        suggestion="Use a specific type, unknown, or create a proper interface",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx"],
    ),
    StyleRule(
        id="TS003",
        name="Non-null assertion",
        pattern=r"\w+![\.\[]",
        message="Non-null assertion (!) can hide potential null errors",
        suggestion="Use optional chaining (?.) or proper null checks",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".ts", ".tsx"],
    ),
    StyleRule(
        id="TS004",
        name="Var declaration",
        pattern=r"\bvar\s+\w+",
        message="Use 'const' or 'let' instead of 'var'",
        suggestion="Use 'const' for values that don't change, 'let' for mutable variables",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
    ),
    StyleRule(
        id="TS005",
        name="Double equals",
        pattern=r"[^=!<>]==[^=]",
        message="Use strict equality (===) instead of loose equality (==)",
        suggestion="Replace == with === for type-safe comparisons",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
    ),
    StyleRule(
        id="TS006",
        name="TODO comment",
        pattern=r"//\s*(TODO|FIXME|XXX|HACK):",
        message="Found TODO/FIXME comment that should be addressed",
        suggestion="Address the TODO or create a tracked issue",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
    ),
]

# General style rules
GENERAL_STYLE_RULES = [
    StyleRule(
        id="GEN001",
        name="Very long file",
        pattern=r"",  # Custom check
        message="File is very long (>500 lines) - consider breaking it up",
        suggestion="Split into smaller, focused modules",
        severity=ReviewSeverity.SUGGESTION,
        check_fn=lambda path, content: len(content.splitlines()) > 500,
    ),
    StyleRule(
        id="GEN002",
        name="Mixed indentation",
        pattern=r"^\t+ +|\t +\t",
        message="Mixed tabs and spaces in indentation",
        suggestion="Use consistent indentation (spaces recommended)",
        severity=ReviewSeverity.WARNING,
        multiline=True,
    ),
]


class StyleChecker(BaseChecker):
    """Checks code style and conventions.

    Runs pattern-based style checks for various languages.
    Detects common style issues like:
    - Line length violations
    - Missing docstrings
    - Unused imports (hints)
    - Anti-patterns
    """

    name = "style_checker"
    description = "Code style and conventions checker"
    is_heavyweight = False

    def __init__(
        self,
        python_rules: list[StyleRule] | None = None,
        ts_rules: list[StyleRule] | None = None,
        general_rules: list[StyleRule] | None = None,
        max_issues_per_file: int = 10,
    ):
        """Initialize style checker.

        Args:
            python_rules: Custom Python rules (replaces defaults).
            ts_rules: Custom TypeScript/JS rules (replaces defaults).
            general_rules: Custom general rules (replaces defaults).
            max_issues_per_file: Max issues to report per file.
        """
        self.python_rules = python_rules or PYTHON_STYLE_RULES
        self.ts_rules = ts_rules or TS_STYLE_RULES
        self.general_rules = general_rules or GENERAL_STYLE_RULES
        self.max_issues_per_file = max_issues_per_file

    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Check files for style issues."""
        comments = []

        for file_path, content in context.files.items():
            file_comments = self._check_file(file_path, content)
            # Limit issues per file
            comments.extend(file_comments[:self.max_issues_per_file])

        return comments

    def _check_file(self, file_path: str, content: str) -> list[ReviewComment]:
        """Check a single file for style issues."""
        comments = []
        extension = "." + file_path.split(".")[-1] if "." in file_path else ""

        # Get applicable rules
        rules = self._get_rules_for_file(extension)

        for rule in rules:
            rule_comments = self._apply_rule(rule, file_path, content)
            comments.extend(rule_comments)

        # Sort by line number
        comments.sort(key=lambda c: c.line_number or 0)

        return comments

    def _get_rules_for_file(self, extension: str) -> list[StyleRule]:
        """Get rules applicable to a file extension."""
        rules = []

        # Add general rules
        rules.extend(self.general_rules)

        # Add language-specific rules
        if extension == ".py":
            rules.extend(self.python_rules)
        elif extension in (".ts", ".tsx"):
            rules.extend(self.ts_rules)
        elif extension in (".js", ".jsx"):
            rules.extend([r for r in self.ts_rules if extension in (r.file_extensions or [])])

        # Filter by extension
        filtered = []
        for rule in rules:
            if rule.file_extensions is None:
                filtered.append(rule)
            elif extension in rule.file_extensions:
                filtered.append(rule)

        return filtered

    def _apply_rule(
        self,
        rule: StyleRule,
        file_path: str,
        content: str,
    ) -> list[ReviewComment]:
        """Apply a single rule to file content."""
        comments = []

        # Custom check function
        if rule.check_fn:
            if rule.check_fn(file_path, content):
                comments.append(ReviewComment(
                    id=self._generate_id(rule.id, file_path),
                    file_path=file_path,
                    message=rule.message,
                    severity=rule.severity,
                    category=ReviewCategory.STYLE,
                    suggestion=rule.suggestion,
                    checker=self.name,
                ))
            return comments

        # Pattern-based check
        if not rule.pattern:
            return comments

        flags = re.MULTILINE
        if rule.multiline:
            flags |= re.DOTALL

        try:
            pattern = re.compile(rule.pattern, flags)
        except re.error:
            return comments

        lines = content.splitlines()

        if rule.multiline:
            # Search entire content
            for match in pattern.finditer(content):
                line_number = content[:match.start()].count('\n') + 1
                snippet = self._get_snippet(lines, line_number)
                comments.append(ReviewComment(
                    id=self._generate_id(rule.id, file_path, line_number),
                    file_path=file_path,
                    line_number=line_number,
                    message=rule.message,
                    severity=rule.severity,
                    category=ReviewCategory.STYLE,
                    suggestion=rule.suggestion,
                    code_snippet=snippet,
                    checker=self.name,
                ))
        else:
            # Search line by line
            for line_num, line in enumerate(lines, 1):
                if pattern.search(line):
                    comments.append(ReviewComment(
                        id=self._generate_id(rule.id, file_path, line_num),
                        file_path=file_path,
                        line_number=line_num,
                        message=rule.message,
                        severity=rule.severity,
                        category=ReviewCategory.STYLE,
                        suggestion=rule.suggestion,
                        code_snippet=line.strip(),
                        checker=self.name,
                    ))

        return comments

    def _get_snippet(self, lines: list[str], line_number: int, context: int = 2) -> str:
        """Get a code snippet around a line number."""
        start = max(0, line_number - context - 1)
        end = min(len(lines), line_number + context)
        return '\n'.join(lines[start:end])
