"""Scanner registry for managing available scanners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.security.scanners.base import BaseScanner, ScanContext
from src.agents.security.scanners.pattern_scanner import PatternScanner
from src.agents.security.scanners.llm_scanner import LLMScanner
from src.agents.security.scanners.spec_compliance import SpecComplianceScanner

if TYPE_CHECKING:
    from src.agents.security.findings import Finding
    from src.llm.client import LLMClient


class ScannerRegistry:
    """Registry for security scanners."""

    def __init__(self):
        """Initialize with default scanners."""
        self._scanners: dict[str, BaseScanner] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in scanners."""
        self.register(PatternScanner())
        # LLM and compliance scanners need external dependencies
        # They're registered separately

    def register(self, scanner: BaseScanner) -> None:
        """Register a scanner."""
        self._scanners[scanner.name] = scanner

    def register_llm_scanner(self, llm_client: LLMClient) -> None:
        """Register LLM scanner with client."""
        self.register(LLMScanner(llm_client))

    def register_compliance_scanner(self) -> None:
        """Register spec compliance scanner."""
        self.register(SpecComplianceScanner())

    def get(self, name: str) -> BaseScanner | None:
        """Get a scanner by name."""
        return self._scanners.get(name)

    def list_scanners(self) -> list[str]:
        """List all registered scanner names."""
        return list(self._scanners.keys())

    def get_lightweight_scanners(self) -> list[BaseScanner]:
        """Get scanners that run in lightweight mode."""
        return [s for s in self._scanners.values() if not s.is_heavyweight]

    def get_heavyweight_scanners(self) -> list[BaseScanner]:
        """Get all scanners (including heavyweight)."""
        return list(self._scanners.values())

    def scan(
        self,
        context: ScanContext,
        heavyweight: bool = False,
    ) -> list[Finding]:
        """Run all appropriate scanners.

        Args:
            context: Scan context with files.
            heavyweight: Whether to include heavyweight scanners.

        Returns:
            Combined findings from all scanners.
        """
        findings = []

        if heavyweight:
            scanners = self.get_heavyweight_scanners()
        else:
            scanners = self.get_lightweight_scanners()

        for scanner in scanners:
            try:
                scanner_findings = scanner.scan(context)
                findings.extend(scanner_findings)
            except Exception as e:
                # Don't let one scanner failure stop the others
                pass

        # Deduplicate similar findings
        findings = self._deduplicate(findings)

        # Sort by severity
        findings.sort(key=lambda f: f.severity.score, reverse=True)

        return findings

    def _deduplicate(self, findings: list[Finding]) -> list[Finding]:
        """Remove duplicate findings (same location + category)."""
        seen = set()
        unique = []

        for finding in findings:
            key = (finding.file_path, finding.line_number, finding.category)
            if key not in seen:
                seen.add(key)
                unique.append(finding)

        return unique
