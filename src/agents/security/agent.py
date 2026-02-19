"""SecurityScanAgent with lightweight and heavyweight modes."""

from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from src.agents.security.findings import SecurityReport, FindingSeverity
from src.agents.security.scanners import (
    ScanContext,
    ScannerRegistry,
    PatternScanner,
    LLMScanner,
    SpecComplianceScanner,
)

try:
    from src.llm.client import LLMClient
except ImportError:
    LLMClient = None


class ScanMode(Enum):
    """Execution mode for security scanning."""

    LIGHTWEIGHT = "lightweight"  # Fast, pattern-based (~30s)
    HEAVYWEIGHT = "heavyweight"  # Thorough, LLM + compliance (~5-10min)


class SecurityScanAgent(BaseAgent):
    """Security scanning agent with dual execution modes.

    Lightweight Mode (default, for PRs):
    - Pattern-based vulnerability detection
    - Hardcoded secrets, SQL injection, XSS, etc.
    - Fast execution (~30 seconds)
    - Returns blocking issues only

    Heavyweight Mode (nightly, on-demand):
    - All lightweight checks PLUS
    - LLM-powered deep analysis
    - Spec compliance verification
    - Full security report with recommendations
    """

    name = "security_agent"
    description = "Security vulnerability scanner"
    requires = ["coding_agent"]  # Runs after code is generated

    def __init__(
        self,
        mode: ScanMode | str = ScanMode.LIGHTWEIGHT,
        llm_client: Optional[Any] = None,
        scanner_registry: Optional[ScannerRegistry] = None,
        file_extensions: list[str] | None = None,
    ):
        """Initialize SecurityScanAgent.

        Args:
            mode: Scan mode (lightweight or heavyweight).
            llm_client: LLM client for heavyweight mode.
            scanner_registry: Custom scanner registry.
            file_extensions: File extensions to scan (default: common code files).
        """
        if isinstance(mode, str):
            mode = ScanMode(mode)
        self.mode = mode

        self.llm = llm_client
        self.registry = scanner_registry or ScannerRegistry()

        # Configure heavyweight scanners if needed
        if mode == ScanMode.HEAVYWEIGHT:
            if llm_client:
                self.registry.register_llm_scanner(llm_client)
            self.registry.register_compliance_scanner()

        self.file_extensions = file_extensions or [
            ".py", ".js", ".ts", ".jsx", ".tsx",
            ".go", ".java", ".rb", ".php", ".rs",
            ".yaml", ".yml", ".json", ".toml",
        ]

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute security scan."""
        start_time = time.time()

        try:
            # Collect files to scan
            files = self._collect_files(context)

            if not files:
                return AgentResult(
                    status=AgentStatus.SUCCESS,
                    message="No files to scan",
                    data={"report": SecurityReport().to_dict()},
                )

            # Create scan context
            scan_context = ScanContext(
                files=files,
                project_root=context.project_root,
                spec=context.spec,
            )

            # Run scanners
            findings = self.registry.scan(
                context=scan_context,
                heavyweight=(self.mode == ScanMode.HEAVYWEIGHT),
            )

            # Get compliance results if heavyweight
            compliance_results = []
            if self.mode == ScanMode.HEAVYWEIGHT:
                compliance_scanner = self.registry.get("spec_compliance")
                if compliance_scanner and isinstance(compliance_scanner, SpecComplianceScanner):
                    compliance_results = compliance_scanner.get_compliance_results(scan_context)

            # Build report
            duration_ms = int((time.time() - start_time) * 1000)
            report = SecurityReport(
                findings=findings,
                files_scanned=len(files),
                scan_duration_ms=duration_ms,
                mode=self.mode.value,
                compliance_results=compliance_results,
            )

            # Determine status
            if report.has_blocking_issues:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message=report.to_summary(),
                    data={
                        "report": report.to_dict(),
                        "markdown_report": report.to_markdown(),
                        "has_blocking_issues": True,
                        "blocking_count": len(report.blocking_findings),
                    },
                    errors=[
                        f"{f.location}: {f.title}"
                        for f in report.blocking_findings
                    ],
                )

            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=report.to_summary(),
                data={
                    "report": report.to_dict(),
                    "markdown_report": report.to_markdown(),
                    "has_blocking_issues": False,
                    "security_report": report,
                },
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Security scan failed: {str(e)}",
                errors=[str(e)],
            )

    def _collect_files(self, context: AgentContext) -> dict[str, str]:
        """Collect files to scan from project and artifacts."""
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

        # If no artifacts, scan project directory
        if not files:
            files = self._scan_directory(context.project_root)

        return files

    def _scan_directory(self, directory: Path) -> dict[str, str]:
        """Scan a directory for code files."""
        files = {}

        # Directories to skip
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".pytest_cache", ".mypy_cache", "dist", "build", ".tox",
        }

        for path in directory.rglob("*"):
            # Skip directories
            if path.is_dir():
                continue

            # Skip excluded directories
            if any(skip in path.parts for skip in skip_dirs):
                continue

            # Check extension
            if path.suffix not in self.file_extensions:
                continue

            # Read file
            try:
                relative_path = str(path.relative_to(directory))
                files[relative_path] = path.read_text()
            except Exception:
                pass

        return files

    def scan_files(
        self,
        files: dict[str, str],
        spec: Any = None,
    ) -> SecurityReport:
        """Scan specific files (for direct API usage).

        Args:
            files: Dict of file path -> content.
            spec: Optional spec for compliance checking.

        Returns:
            SecurityReport with findings.
        """
        start_time = time.time()

        scan_context = ScanContext(
            files=files,
            project_root=Path("."),
            spec=spec,
        )

        findings = self.registry.scan(
            context=scan_context,
            heavyweight=(self.mode == ScanMode.HEAVYWEIGHT),
        )

        compliance_results = []
        if self.mode == ScanMode.HEAVYWEIGHT and spec:
            compliance_scanner = self.registry.get("spec_compliance")
            if compliance_scanner and isinstance(compliance_scanner, SpecComplianceScanner):
                compliance_results = compliance_scanner.get_compliance_results(scan_context)

        duration_ms = int((time.time() - start_time) * 1000)

        return SecurityReport(
            findings=findings,
            files_scanned=len(files),
            scan_duration_ms=duration_ms,
            mode=self.mode.value,
            compliance_results=compliance_results,
        )
