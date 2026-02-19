"""Best practices checker - identifies anti-patterns and suggests improvements."""

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
class BestPracticeRule:
    """A best practice rule to check."""

    id: str
    name: str
    category: ReviewCategory
    pattern: str | None = None  # Regex pattern
    message: str = ""
    suggestion: str = ""
    severity: ReviewSeverity = ReviewSeverity.WARNING
    file_extensions: list[str] | None = None
    multiline: bool = False
    check_fn: Callable[[str, str], list[tuple[int, str]]] | None = None


# Python best practices
PYTHON_BEST_PRACTICES = [
    BestPracticeRule(
        id="PBP001",
        name="God class",
        category=ReviewCategory.MAINTAINABILITY,
        message="Class has too many methods (>20) - consider breaking it up",
        suggestion="Split into smaller, focused classes following Single Responsibility Principle",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
        check_fn=lambda path, content: _check_class_size(content, 20),
    ),
    BestPracticeRule(
        id="PBP002",
        name="Long function",
        category=ReviewCategory.MAINTAINABILITY,
        message="Function is too long (>50 lines) - consider refactoring",
        suggestion="Extract smaller helper functions for better readability",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
        check_fn=lambda path, content: _check_function_length(content, 50),
    ),
    BestPracticeRule(
        id="PBP003",
        name="Deep nesting",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r"^(\s{16,})\S",  # 4+ levels of indentation
        message="Code has deep nesting (>4 levels) - hard to read and maintain",
        suggestion="Use early returns, extract methods, or restructure logic",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP004",
        name="Magic number",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r"(?<!['\"])\b(?<!\.)\d{2,}(?!\d)(?!['\"])\b(?![\.\d])",
        message="Magic number detected - use a named constant",
        suggestion="Define a constant: MAX_RETRIES = 3",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP005",
        name="Catching broad exception",
        category=ReviewCategory.ERROR_HANDLING,
        pattern=r"except\s+Exception\s*:",
        message="Catching broad Exception - may hide bugs",
        suggestion="Catch specific exceptions: 'except ValueError, TypeError:'",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP006",
        name="Empty except block",
        category=ReviewCategory.ERROR_HANDLING,
        pattern=r"except[^:]*:\s*\n\s*pass\s*\n",
        message="Empty except block - silently ignoring errors",
        suggestion="Log the error or re-raise: 'except E as e: logger.warning(e)'",
        severity=ReviewSeverity.ERROR,
        file_extensions=[".py"],
        multiline=True,
    ),
    BestPracticeRule(
        id="PBP007",
        name="Hardcoded path",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r'["\'][/\\](?:home|Users|var|tmp|etc)[/\\][^"\']+["\']',
        message="Hardcoded file path - not portable",
        suggestion="Use pathlib or os.path with environment variables",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP008",
        name="Global variable modification",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r"^\s*global\s+\w+",
        message="Using global variables - can lead to hard-to-track bugs",
        suggestion="Pass values as parameters or use dependency injection",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP009",
        name="String concatenation in loop",
        category=ReviewCategory.PERFORMANCE,
        pattern=r"for\s+\w+\s+in\s+[^:]+:\s*\n[^}]*\+=\s*['\"]",
        message="String concatenation in loop is inefficient",
        suggestion="Use ''.join(items) or list append",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".py"],
        multiline=True,
    ),
    BestPracticeRule(
        id="PBP010",
        name="Unused variable",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r"^\s*(\w+)\s*=\s*[^=].*(?:\n(?!.*\1))*$",
        message="Variable appears to be unused - verify or remove",
        suggestion="Remove unused variables or prefix with underscore if intentional: _unused",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP011",
        name="No return type hint",
        category=ReviewCategory.DOCUMENTATION,
        pattern=r"def\s+\w+\([^)]*\)\s*:",
        message="Function is missing return type hint",
        suggestion="Add return type: 'def func() -> ReturnType:'",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="PBP012",
        name="Synchronous I/O in async",
        category=ReviewCategory.PERFORMANCE,
        pattern=r"async\s+def[^}]+\n[^}]*(open\(|requests\.|urllib\.)",
        message="Synchronous I/O in async function blocks event loop",
        suggestion="Use aiofiles for file I/O, httpx/aiohttp for HTTP",
        severity=ReviewSeverity.ERROR,
        file_extensions=[".py"],
        multiline=True,
    ),
]

# TypeScript/JavaScript best practices
TS_BEST_PRACTICES = [
    BestPracticeRule(
        id="TBP001",
        name="Nested callbacks",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r"function\s*\([^)]*\)\s*\{[^}]*function\s*\([^)]*\)\s*\{[^}]*function",
        message="Nested callbacks (callback hell) - hard to read and maintain",
        suggestion="Use async/await or Promise chains",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
        multiline=True,
    ),
    BestPracticeRule(
        id="TBP002",
        name="Unhandled promise",
        category=ReviewCategory.ERROR_HANDLING,
        pattern=r"(?<!await\s)(?<!return\s)\w+\s*\([^)]*\)\s*\.then\(",
        message="Promise without error handling",
        suggestion="Add .catch() or use try/catch with await",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
    ),
    BestPracticeRule(
        id="TBP003",
        name="No error boundary",
        category=ReviewCategory.ERROR_HANDLING,
        pattern=r"<\w+Provider[^>]*>(?!.*ErrorBoundary)",
        message="React provider without error boundary",
        suggestion="Wrap providers with an ErrorBoundary component",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".tsx", ".jsx"],
        multiline=True,
    ),
    BestPracticeRule(
        id="TBP004",
        name="Inline styles",
        category=ReviewCategory.MAINTAINABILITY,
        pattern=r"style\s*=\s*\{\s*\{",
        message="Inline styles in React components",
        suggestion="Use CSS modules, styled-components, or Tailwind classes",
        severity=ReviewSeverity.SUGGESTION,
        file_extensions=[".tsx", ".jsx"],
    ),
    BestPracticeRule(
        id="TBP005",
        name="Array index as key",
        category=ReviewCategory.PERFORMANCE,
        pattern=r"key\s*=\s*\{?\s*(?:index|i|idx)\s*\}?",
        message="Using array index as React key can cause issues",
        suggestion="Use a stable unique identifier from your data",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".tsx", ".jsx"],
    ),
    BestPracticeRule(
        id="TBP006",
        name="Direct state mutation",
        category=ReviewCategory.LOGIC,
        pattern=r"this\.state\.\w+\s*=|state\.\w+\s*=(?!=)",
        message="Direct state mutation detected",
        suggestion="Use setState() or state updater functions",
        severity=ReviewSeverity.ERROR,
        file_extensions=[".tsx", ".jsx", ".ts", ".js"],
    ),
]

# Security-related best practices
SECURITY_BEST_PRACTICES = [
    BestPracticeRule(
        id="SBP001",
        name="Insecure random",
        category=ReviewCategory.SECURITY,
        pattern=r"random\(\)|Math\.random\(\)|randint\(",
        message="Using non-cryptographic random - insecure for sensitive operations",
        suggestion="Use secrets module (Python) or crypto.randomBytes (Node)",
        severity=ReviewSeverity.WARNING,
    ),
    BestPracticeRule(
        id="SBP002",
        name="SQL query building",
        category=ReviewCategory.SECURITY,
        pattern=r'f"[^"]*(?:SELECT|INSERT|UPDATE|DELETE)[^"]*\{',
        message="Building SQL query with f-string - potential SQL injection",
        suggestion="Use parameterized queries or an ORM",
        severity=ReviewSeverity.ERROR,
        file_extensions=[".py"],
    ),
    BestPracticeRule(
        id="SBP003",
        name="Disabled SSL verification",
        category=ReviewCategory.SECURITY,
        pattern=r"verify\s*=\s*False|ssl\s*=\s*False|NODE_TLS_REJECT_UNAUTHORIZED",
        message="SSL/TLS verification is disabled",
        suggestion="Enable SSL verification for production",
        severity=ReviewSeverity.ERROR,
    ),
    BestPracticeRule(
        id="SBP004",
        name="Dangerous innerHTML",
        category=ReviewCategory.SECURITY,
        pattern=r"innerHTML\s*=|dangerouslySetInnerHTML",
        message="Using innerHTML/dangerouslySetInnerHTML - XSS risk",
        suggestion="Sanitize input or use textContent/innerText",
        severity=ReviewSeverity.WARNING,
        file_extensions=[".ts", ".tsx", ".js", ".jsx"],
    ),
    BestPracticeRule(
        id="SBP005",
        name="Eval usage",
        category=ReviewCategory.SECURITY,
        pattern=r"\beval\s*\(|\bexec\s*\(",
        message="Using eval/exec - major security risk",
        suggestion="Find an alternative approach that doesn't require code execution",
        severity=ReviewSeverity.ERROR,
    ),
]


def _check_class_size(content: str, max_methods: int) -> list[tuple[int, str]]:
    """Check for classes with too many methods."""
    issues = []
    class_pattern = r"^class\s+(\w+)"
    method_pattern = r"^\s+def\s+\w+"

    lines = content.splitlines()
    current_class = None
    current_class_line = 0
    method_count = 0

    for i, line in enumerate(lines, 1):
        class_match = re.match(class_pattern, line)
        if class_match:
            # Check previous class
            if current_class and method_count > max_methods:
                issues.append((
                    current_class_line,
                    f"Class '{current_class}' has {method_count} methods"
                ))

            current_class = class_match.group(1)
            current_class_line = i
            method_count = 0
        elif current_class and re.match(method_pattern, line):
            method_count += 1

    # Check last class
    if current_class and method_count > max_methods:
        issues.append((
            current_class_line,
            f"Class '{current_class}' has {method_count} methods"
        ))

    return issues


def _check_function_length(content: str, max_lines: int) -> list[tuple[int, str]]:
    """Check for functions that are too long."""
    issues = []
    func_pattern = r"^(\s*)def\s+(\w+)"

    lines = content.splitlines()
    current_func = None
    current_func_line = 0
    current_indent = 0
    func_lines = 0

    for i, line in enumerate(lines, 1):
        func_match = re.match(func_pattern, line)
        if func_match:
            # Check previous function
            if current_func and func_lines > max_lines:
                issues.append((
                    current_func_line,
                    f"Function '{current_func}' is {func_lines} lines long"
                ))

            current_indent = len(func_match.group(1))
            current_func = func_match.group(2)
            current_func_line = i
            func_lines = 0
        elif current_func:
            # Check if we're still in the function
            if line.strip() and not line.startswith(" " * (current_indent + 1)):
                if not line.startswith(" " * current_indent) or line.strip().startswith("def "):
                    # Function ended
                    if func_lines > max_lines:
                        issues.append((
                            current_func_line,
                            f"Function '{current_func}' is {func_lines} lines long"
                        ))
                    current_func = None
                    continue
            func_lines += 1

    # Check last function
    if current_func and func_lines > max_lines:
        issues.append((
            current_func_line,
            f"Function '{current_func}' is {func_lines} lines long"
        ))

    return issues


class BestPracticesChecker(BaseChecker):
    """Checks for anti-patterns and best practices violations.

    Detects:
    - God classes and long functions
    - Deep nesting
    - Error handling issues
    - Security anti-patterns
    - Performance issues
    - Maintainability concerns
    """

    name = "best_practices_checker"
    description = "Anti-patterns and best practices checker"
    is_heavyweight = False

    def __init__(
        self,
        python_rules: list[BestPracticeRule] | None = None,
        ts_rules: list[BestPracticeRule] | None = None,
        security_rules: list[BestPracticeRule] | None = None,
        max_issues_per_file: int = 15,
    ):
        """Initialize best practices checker.

        Args:
            python_rules: Custom Python rules (replaces defaults).
            ts_rules: Custom TypeScript/JS rules (replaces defaults).
            security_rules: Custom security rules (replaces defaults).
            max_issues_per_file: Max issues to report per file.
        """
        self.python_rules = python_rules or PYTHON_BEST_PRACTICES
        self.ts_rules = ts_rules or TS_BEST_PRACTICES
        self.security_rules = security_rules or SECURITY_BEST_PRACTICES
        self.max_issues_per_file = max_issues_per_file

    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Check files for best practice violations."""
        comments = []

        for file_path, content in context.files.items():
            file_comments = self._check_file(file_path, content)
            comments.extend(file_comments[:self.max_issues_per_file])

        return comments

    def _check_file(self, file_path: str, content: str) -> list[ReviewComment]:
        """Check a single file for best practice violations."""
        comments = []
        extension = "." + file_path.split(".")[-1] if "." in file_path else ""

        rules = self._get_rules_for_file(extension)

        for rule in rules:
            rule_comments = self._apply_rule(rule, file_path, content)
            comments.extend(rule_comments)

        comments.sort(key=lambda c: (c.severity.score, c.line_number or 0), reverse=True)
        return comments

    def _get_rules_for_file(self, extension: str) -> list[BestPracticeRule]:
        """Get rules applicable to a file extension."""
        rules = []

        # Security rules apply to all files
        rules.extend([r for r in self.security_rules
                     if r.file_extensions is None or extension in r.file_extensions])

        # Language-specific rules
        if extension == ".py":
            rules.extend(self.python_rules)
        elif extension in (".ts", ".tsx", ".js", ".jsx"):
            rules.extend([r for r in self.ts_rules
                         if r.file_extensions is None or extension in r.file_extensions])

        return rules

    def _apply_rule(
        self,
        rule: BestPracticeRule,
        file_path: str,
        content: str,
    ) -> list[ReviewComment]:
        """Apply a single rule to file content."""
        comments = []

        # Custom check function
        if rule.check_fn:
            issues = rule.check_fn(file_path, content)
            for line_num, detail in issues:
                comments.append(ReviewComment(
                    id=self._generate_id(rule.id, file_path, line_num),
                    file_path=file_path,
                    line_number=line_num,
                    message=f"{rule.message} - {detail}",
                    severity=rule.severity,
                    category=rule.category,
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
            for match in pattern.finditer(content):
                line_number = content[:match.start()].count('\n') + 1
                snippet = self._get_snippet(lines, line_number)
                comments.append(ReviewComment(
                    id=self._generate_id(rule.id, file_path, line_number),
                    file_path=file_path,
                    line_number=line_number,
                    message=rule.message,
                    severity=rule.severity,
                    category=rule.category,
                    suggestion=rule.suggestion,
                    code_snippet=snippet,
                    checker=self.name,
                ))
        else:
            for line_num, line in enumerate(lines, 1):
                if pattern.search(line):
                    comments.append(ReviewComment(
                        id=self._generate_id(rule.id, file_path, line_num),
                        file_path=file_path,
                        line_number=line_num,
                        message=rule.message,
                        severity=rule.severity,
                        category=rule.category,
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
