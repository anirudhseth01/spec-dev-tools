"""LLM-powered security scanner for deep analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.agents.security.scanners.base import BaseScanner, ScanContext
from src.agents.security.findings import (
    Finding,
    FindingSeverity,
    FindingCategory,
)

if TYPE_CHECKING:
    from src.llm.client import LLMClient


SECURITY_REVIEW_PROMPT = """You are an expert security code reviewer. Analyze the following code for security vulnerabilities.

Focus on:
1. Authentication and authorization logic flaws
2. Data validation and sanitization issues
3. Cryptographic implementation problems
4. Business logic vulnerabilities
5. Race conditions and concurrency issues
6. Data exposure risks
7. Insecure defaults

For each issue found, provide:
- SEVERITY: CRITICAL, HIGH, MEDIUM, or LOW
- CATEGORY: one of [AUTH, AUTHZ, INJECTION, XSS, CRYPTO, DATA_EXPOSURE, CONFIG, OTHER]
- LOCATION: file path and line number if possible
- DESCRIPTION: clear explanation of the vulnerability
- RECOMMENDATION: how to fix it

Format your response as:
---FINDING---
SEVERITY: <severity>
CATEGORY: <category>
LOCATION: <file:line>
TITLE: <short title>
DESCRIPTION: <description>
RECOMMENDATION: <fix>
---END---

If no issues are found, respond with: NO_ISSUES_FOUND

Code to analyze:
"""


class LLMScanner(BaseScanner):
    """LLM-powered deep security analysis.

    Only runs in heavyweight mode. Uses Claude to analyze
    code for complex vulnerabilities that pattern matching misses.
    """

    name = "llm_scanner"
    description = "LLM-powered deep security analysis"
    is_heavyweight = True  # Only runs in heavyweight mode

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize LLM scanner.

        Args:
            llm_client: LLM client for analysis. If None, scanner is disabled.
        """
        self.llm = llm_client

    def scan(self, context: ScanContext) -> list[Finding]:
        """Scan files using LLM analysis."""
        if not self.llm:
            return []

        findings = []

        # Batch files to avoid too many LLM calls
        batched_content = self._batch_files(context.files)

        for batch_name, content in batched_content.items():
            batch_findings = self._analyze_batch(batch_name, content)
            findings.extend(batch_findings)

        return findings

    def _batch_files(
        self,
        files: dict[str, str],
        max_tokens: int = 30000,
    ) -> dict[str, str]:
        """Batch files to fit within context limits."""
        batches = {}
        current_batch = []
        current_tokens = 0
        batch_num = 1

        for path, content in files.items():
            # Rough token estimate
            tokens = len(content) // 4

            if current_tokens + tokens > max_tokens:
                # Start new batch
                if current_batch:
                    batches[f"batch_{batch_num}"] = "\n\n".join(current_batch)
                    batch_num += 1
                current_batch = []
                current_tokens = 0

            # Add file to current batch
            file_content = f"### File: {path}\n```\n{content}\n```"
            current_batch.append(file_content)
            current_tokens += tokens

        # Don't forget last batch
        if current_batch:
            batches[f"batch_{batch_num}"] = "\n\n".join(current_batch)

        return batches

    def _analyze_batch(self, batch_name: str, content: str) -> list[Finding]:
        """Analyze a batch of files with LLM."""
        prompt = SECURITY_REVIEW_PROMPT + content

        response = self.llm.generate(
            system_prompt="You are a security expert reviewing code for vulnerabilities.",
            user_prompt=prompt,
            temperature=0.0,
        )

        return self._parse_findings(response.content)

    def _parse_findings(self, response: str) -> list[Finding]:
        """Parse LLM response into findings."""
        findings = []

        if "NO_ISSUES_FOUND" in response:
            return findings

        # Split by finding markers
        parts = response.split("---FINDING---")

        for part in parts[1:]:  # Skip first empty part
            if "---END---" not in part:
                continue

            finding_text = part.split("---END---")[0].strip()
            finding = self._parse_single_finding(finding_text)
            if finding:
                findings.append(finding)

        return findings

    def _parse_single_finding(self, text: str) -> Finding | None:
        """Parse a single finding from text."""
        lines = text.strip().split("\n")
        data = {}

        for line in lines:
            if ":" in line:
                key, _, value = line.partition(":")
                data[key.strip().upper()] = value.strip()

        # Required fields
        if not all(k in data for k in ["SEVERITY", "CATEGORY", "TITLE", "DESCRIPTION"]):
            return None

        # Parse severity
        severity_map = {
            "CRITICAL": FindingSeverity.CRITICAL,
            "HIGH": FindingSeverity.HIGH,
            "MEDIUM": FindingSeverity.MEDIUM,
            "LOW": FindingSeverity.LOW,
        }
        severity = severity_map.get(data["SEVERITY"].upper(), FindingSeverity.MEDIUM)

        # Parse category
        category_map = {
            "AUTH": FindingCategory.AUTH,
            "AUTHZ": FindingCategory.AUTHZ,
            "INJECTION": FindingCategory.INJECTION,
            "XSS": FindingCategory.XSS,
            "CRYPTO": FindingCategory.CRYPTO,
            "DATA_EXPOSURE": FindingCategory.DATA_EXPOSURE,
            "CONFIG": FindingCategory.CONFIGURATION,
            "OTHER": FindingCategory.OTHER,
        }
        category = category_map.get(data["CATEGORY"].upper(), FindingCategory.OTHER)

        # Parse location
        location = data.get("LOCATION", "unknown")
        file_path = location
        line_number = None
        if ":" in location:
            parts = location.rsplit(":", 1)
            file_path = parts[0]
            try:
                line_number = int(parts[1])
            except ValueError:
                pass

        return Finding(
            id=f"LLM-{hash(text) % 10000:04d}",
            title=data["TITLE"],
            description=data["DESCRIPTION"],
            severity=severity,
            category=category,
            file_path=file_path,
            line_number=line_number,
            recommendation=data.get("RECOMMENDATION", ""),
            scanner=self.name,
            confidence=0.8,  # LLM findings have moderate confidence
        )
