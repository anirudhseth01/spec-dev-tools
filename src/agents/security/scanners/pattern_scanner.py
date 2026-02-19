"""Pattern-based vulnerability scanner (fast, regex-based)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.agents.security.scanners.base import BaseScanner, ScanContext
from src.agents.security.findings import (
    Finding,
    FindingSeverity,
    FindingCategory,
)


@dataclass
class VulnerabilityPattern:
    """A vulnerability detection pattern."""

    id: str
    name: str
    pattern: str
    severity: FindingSeverity
    category: FindingCategory
    description: str
    recommendation: str
    cwe_id: str | None = None
    owasp_category: str | None = None
    languages: list[str] | None = None  # None = all languages
    confidence: float = 0.9


# Built-in vulnerability patterns
VULNERABILITY_PATTERNS = [
    # Hardcoded Secrets
    VulnerabilityPattern(
        id="SEC-001",
        name="Hardcoded Password",
        pattern=r"""(?i)(?:password|passwd|pwd)\s*=\s*['"]\w+['"]""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.SECRETS,
        description="Hardcoded password detected in source code",
        recommendation="Use environment variables or a secrets manager",
        cwe_id="CWE-798",
        owasp_category="A07:2021 - Identification and Authentication Failures",
    ),
    VulnerabilityPattern(
        id="SEC-002",
        name="Hardcoded API Key",
        pattern=r"""(?i)(?:api[_-]?key|apikey|api[_-]?secret)\s*=\s*['"][a-zA-Z0-9_\-]{16,}['"]""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.SECRETS,
        description="Hardcoded API key detected in source code",
        recommendation="Use environment variables or a secrets manager",
        cwe_id="CWE-798",
        owasp_category="A07:2021 - Identification and Authentication Failures",
    ),
    VulnerabilityPattern(
        id="SEC-003",
        name="AWS Secret Key",
        pattern=r"""(?i)(?:aws[_-]?secret[_-]?access[_-]?key)\s*=\s*['"][A-Za-z0-9/+=]{40}['"]""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.SECRETS,
        description="AWS secret access key detected in source code",
        recommendation="Use AWS IAM roles or environment variables",
        cwe_id="CWE-798",
    ),
    VulnerabilityPattern(
        id="SEC-004",
        name="Private Key",
        pattern=r"""-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.SECRETS,
        description="Private key detected in source code",
        recommendation="Store private keys securely outside source code",
        cwe_id="CWE-321",
    ),

    # SQL Injection
    VulnerabilityPattern(
        id="SEC-010",
        name="SQL Injection (f-string)",
        pattern=r"""f['"](?:SELECT|INSERT|UPDATE|DELETE|DROP).*\{[^}]+\}""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.INJECTION,
        description="Potential SQL injection via f-string formatting",
        recommendation="Use parameterized queries with placeholders",
        cwe_id="CWE-89",
        owasp_category="A03:2021 - Injection",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-011",
        name="SQL Injection (format)",
        pattern=r"""['"](?:SELECT|INSERT|UPDATE|DELETE).*['"]\.format\s*\(""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.INJECTION,
        description="Potential SQL injection via string format",
        recommendation="Use parameterized queries with placeholders",
        cwe_id="CWE-89",
        owasp_category="A03:2021 - Injection",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-012",
        name="SQL Injection (concatenation)",
        pattern=r"""(?:execute|query)\s*\(\s*['"].*\+\s*\w+""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.INJECTION,
        description="Potential SQL injection via string concatenation",
        recommendation="Use parameterized queries with placeholders",
        cwe_id="CWE-89",
        owasp_category="A03:2021 - Injection",
        confidence=0.7,
    ),

    # Command Injection
    VulnerabilityPattern(
        id="SEC-020",
        name="OS Command Injection (os.system)",
        pattern=r"""os\.system\s*\(\s*(?:f['"]|['"].*\+|.*\.format)""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.INJECTION,
        description="Potential command injection via os.system",
        recommendation="Use subprocess with shell=False and list arguments",
        cwe_id="CWE-78",
        owasp_category="A03:2021 - Injection",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-021",
        name="Shell Injection (subprocess shell=True)",
        pattern=r"""subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.INJECTION,
        description="Using shell=True with subprocess is dangerous",
        recommendation="Use shell=False with list of arguments",
        cwe_id="CWE-78",
        owasp_category="A03:2021 - Injection",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-022",
        name="Eval Usage",
        pattern=r"""(?<!#.*)\beval\s*\(""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.INJECTION,
        description="Use of eval() can lead to code injection",
        recommendation="Avoid eval(); use ast.literal_eval() for literals",
        cwe_id="CWE-95",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-023",
        name="Exec Usage",
        pattern=r"""(?<!#.*)\bexec\s*\(""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.INJECTION,
        description="Use of exec() can lead to code injection",
        recommendation="Avoid exec(); find a safer alternative",
        cwe_id="CWE-95",
        languages=["python"],
    ),

    # XSS
    VulnerabilityPattern(
        id="SEC-030",
        name="innerHTML Assignment",
        pattern=r"""\.innerHTML\s*=\s*[^;]+(?:var|let|const|\+)""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.XSS,
        description="Direct innerHTML assignment with variable data",
        recommendation="Use textContent or sanitize HTML before assignment",
        cwe_id="CWE-79",
        owasp_category="A03:2021 - Injection",
        languages=["javascript", "typescript"],
    ),
    VulnerabilityPattern(
        id="SEC-031",
        name="document.write",
        pattern=r"""document\.write\s*\(""",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.XSS,
        description="document.write can lead to XSS vulnerabilities",
        recommendation="Use DOM manipulation methods instead",
        cwe_id="CWE-79",
        languages=["javascript", "typescript"],
    ),
    VulnerabilityPattern(
        id="SEC-032",
        name="Unsafe Template Rendering",
        pattern=r"""\{\{\s*\w+\s*\|\s*safe\s*\}\}""",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.XSS,
        description="Template marked as 'safe' bypasses HTML escaping",
        recommendation="Ensure content is properly sanitized before marking safe",
        cwe_id="CWE-79",
        languages=["python"],  # Jinja2
        confidence=0.7,
    ),

    # Insecure Cryptography
    VulnerabilityPattern(
        id="SEC-040",
        name="Weak Hash (MD5)",
        pattern=r"""hashlib\.md5\s*\(""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.CRYPTO,
        description="MD5 is cryptographically broken",
        recommendation="Use SHA-256 or stronger (hashlib.sha256)",
        cwe_id="CWE-328",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-041",
        name="Weak Hash (SHA1)",
        pattern=r"""hashlib\.sha1\s*\(""",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.CRYPTO,
        description="SHA-1 is deprecated for security purposes",
        recommendation="Use SHA-256 or stronger (hashlib.sha256)",
        cwe_id="CWE-328",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-042",
        name="Insecure Random",
        pattern=r"""random\.(?:random|randint|choice)\s*\(""",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.CRYPTO,
        description="random module is not cryptographically secure",
        recommendation="Use secrets module for security-sensitive randomness",
        cwe_id="CWE-338",
        languages=["python"],
        confidence=0.6,  # May be fine for non-security uses
    ),

    # Authentication Issues
    VulnerabilityPattern(
        id="SEC-050",
        name="Disabled SSL Verification",
        pattern=r"""verify\s*=\s*False""",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.AUTH,
        description="SSL/TLS certificate verification disabled",
        recommendation="Enable SSL verification (verify=True)",
        cwe_id="CWE-295",
        languages=["python"],
    ),
    VulnerabilityPattern(
        id="SEC-051",
        name="JWT None Algorithm",
        pattern=r"""algorithm\s*=\s*['"]none['"]""",
        severity=FindingSeverity.CRITICAL,
        category=FindingCategory.AUTH,
        description="JWT with 'none' algorithm allows token forgery",
        recommendation="Use a secure algorithm like HS256 or RS256",
        cwe_id="CWE-347",
    ),

    # Miscellaneous
    VulnerabilityPattern(
        id="SEC-060",
        name="Debug Mode in Production",
        pattern=r"""(?:DEBUG|debug)\s*=\s*True""",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.CONFIGURATION,
        description="Debug mode appears to be enabled",
        recommendation="Disable debug mode in production environments",
        cwe_id="CWE-215",
        confidence=0.5,  # Might be in test/dev files
    ),
    VulnerabilityPattern(
        id="SEC-061",
        name="Binding to All Interfaces",
        pattern=r"""(?:host|bind)\s*=\s*['"]0\.0\.0\.0['"]""",
        severity=FindingSeverity.LOW,
        category=FindingCategory.CONFIGURATION,
        description="Server binding to all network interfaces",
        recommendation="Bind to specific interface or use reverse proxy",
        cwe_id="CWE-200",
        confidence=0.5,
    ),
]


class PatternScanner(BaseScanner):
    """Fast regex-based vulnerability scanner.

    Runs in both lightweight and heavyweight modes.
    Uses pattern matching for common vulnerability patterns.
    """

    name = "pattern_scanner"
    description = "Fast regex-based vulnerability detection"
    is_heavyweight = False  # Runs in both modes

    def __init__(
        self,
        patterns: list[VulnerabilityPattern] | None = None,
        extra_patterns: list[VulnerabilityPattern] | None = None,
    ):
        """Initialize pattern scanner.

        Args:
            patterns: Custom patterns (replaces defaults).
            extra_patterns: Additional patterns (added to defaults).
        """
        if patterns is not None:
            self.patterns = patterns
        else:
            self.patterns = VULNERABILITY_PATTERNS.copy()
            if extra_patterns:
                self.patterns.extend(extra_patterns)

        # Compile patterns for performance
        self._compiled: dict[str, re.Pattern] = {}
        for pattern in self.patterns:
            try:
                self._compiled[pattern.id] = re.compile(
                    pattern.pattern,
                    re.IGNORECASE | re.MULTILINE,
                )
            except re.error:
                pass  # Skip invalid patterns

    def scan(self, context: ScanContext) -> list[Finding]:
        """Scan files for pattern-based vulnerabilities."""
        findings = []

        for file_path, content in context.files.items():
            language = self._detect_language(file_path)
            file_findings = self._scan_file(file_path, content, language)
            findings.extend(file_findings)

        return findings

    def _scan_file(
        self,
        file_path: str,
        content: str,
        language: str,
    ) -> list[Finding]:
        """Scan a single file."""
        findings = []
        lines = content.split("\n")

        for pattern in self.patterns:
            # Check language filter
            if pattern.languages and language not in pattern.languages:
                continue

            # Get compiled pattern
            compiled = self._compiled.get(pattern.id)
            if not compiled:
                continue

            # Find matches
            for match in compiled.finditer(content):
                line_number = content[:match.start()].count("\n") + 1
                code_snippet = self._get_snippet(lines, line_number)

                findings.append(Finding(
                    id=f"{pattern.id}-{file_path}:{line_number}",
                    title=pattern.name,
                    description=pattern.description,
                    severity=pattern.severity,
                    category=pattern.category,
                    file_path=file_path,
                    line_number=line_number,
                    code_snippet=code_snippet,
                    recommendation=pattern.recommendation,
                    cwe_id=pattern.cwe_id,
                    owasp_category=pattern.owasp_category,
                    scanner=self.name,
                    confidence=pattern.confidence,
                ))

        return findings

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
        }
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        return "unknown"

    def _get_snippet(self, lines: list[str], line_number: int, context: int = 2) -> str:
        """Get code snippet around a line."""
        start = max(0, line_number - context - 1)
        end = min(len(lines), line_number + context)
        snippet_lines = lines[start:end]
        return "\n".join(snippet_lines)

    def get_file_extensions(self) -> list[str]:
        """Return supported file extensions."""
        return [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb", ".php"]
