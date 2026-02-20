"""Spec coverage tracking - track which spec sections are implemented."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class ImplementationStatus(Enum):
    """Status of implementation for a spec section."""
    NOT_STARTED = "not_started"
    PARTIAL = "partial"
    COMPLETE = "complete"
    VERIFIED = "verified"


@dataclass
class SectionCoverage:
    """Coverage for a single spec section."""

    section_name: str
    status: ImplementationStatus
    implemented_items: list[str] = field(default_factory=list)
    total_items: int = 0
    notes: str = ""
    last_updated: datetime | None = None

    @property
    def percentage(self) -> float:
        """Calculate coverage percentage."""
        if self.total_items == 0:
            return 100.0 if self.status == ImplementationStatus.COMPLETE else 0.0
        return (len(self.implemented_items) / self.total_items) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "section_name": self.section_name,
            "status": self.status.value,
            "implemented_items": self.implemented_items,
            "total_items": self.total_items,
            "percentage": self.percentage,
            "notes": self.notes,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class SpecCoverage:
    """Coverage for an entire spec."""

    spec_name: str
    spec_path: str
    sections: dict[str, SectionCoverage] = field(default_factory=dict)
    code_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    last_analyzed: datetime | None = None

    @property
    def overall_percentage(self) -> float:
        """Calculate overall coverage percentage."""
        if not self.sections:
            return 0.0

        total = sum(s.percentage for s in self.sections.values())
        return total / len(self.sections)

    @property
    def status(self) -> ImplementationStatus:
        """Get overall implementation status."""
        if not self.sections:
            return ImplementationStatus.NOT_STARTED

        statuses = [s.status for s in self.sections.values()]

        if all(s == ImplementationStatus.VERIFIED for s in statuses):
            return ImplementationStatus.VERIFIED
        elif all(s in [ImplementationStatus.COMPLETE, ImplementationStatus.VERIFIED] for s in statuses):
            return ImplementationStatus.COMPLETE
        elif any(s != ImplementationStatus.NOT_STARTED for s in statuses):
            return ImplementationStatus.PARTIAL
        else:
            return ImplementationStatus.NOT_STARTED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spec_name": self.spec_name,
            "spec_path": self.spec_path,
            "overall_percentage": self.overall_percentage,
            "status": self.status.value,
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "code_files": self.code_files,
            "test_files": self.test_files,
            "last_analyzed": self.last_analyzed.isoformat() if self.last_analyzed else None,
        }


class CoverageTracker:
    """Track implementation coverage for specs."""

    # Sections to track
    TRACKED_SECTIONS = [
        "2. Overview",
        "3. Inputs",
        "4. Outputs",
        "5. Dependencies",
        "6. API Contract",
        "7. Test Cases",
        "9. Error Handling",
        "11. Security",
        "12. Implementation",
    ]

    def __init__(self, project_dir: Path, specs_dir: Path | None = None):
        """Initialize coverage tracker.

        Args:
            project_dir: Root directory of the project.
            specs_dir: Directory containing specs.
        """
        self.project_dir = project_dir
        self.specs_dir = specs_dir or project_dir / "specs"
        self.coverage_file = project_dir / ".spec-dev" / "coverage.json"

    def analyze_spec(self, spec_name: str) -> SpecCoverage:
        """Analyze coverage for a spec.

        Args:
            spec_name: Name of the spec.

        Returns:
            SpecCoverage with analysis results.
        """
        # Find spec file
        spec_path = self._find_spec_file(spec_name)
        if not spec_path:
            raise FileNotFoundError(f"Spec not found: {spec_name}")

        content = spec_path.read_text()

        coverage = SpecCoverage(
            spec_name=spec_name,
            spec_path=str(spec_path),
            last_analyzed=datetime.now(),
        )

        # Analyze each section
        for section_name in self.TRACKED_SECTIONS:
            section_cov = self._analyze_section(content, section_name)
            coverage.sections[section_name] = section_cov

        # Find related code files
        coverage.code_files = self._find_code_files(spec_name)
        coverage.test_files = self._find_test_files(spec_name)

        # Check implementation status based on code files
        self._check_implementation(coverage)

        return coverage

    def _find_spec_file(self, spec_name: str) -> Path | None:
        """Find spec file by name."""
        # Check for block spec
        block_path = self.specs_dir / spec_name / "block.md"
        if block_path.exists():
            return block_path

        # Check for regular spec
        spec_path = self.specs_dir / f"{spec_name}.md"
        if spec_path.exists():
            return spec_path

        return None

    def _analyze_section(self, content: str, section_name: str) -> SectionCoverage:
        """Analyze a single section."""
        section_cov = SectionCoverage(
            section_name=section_name,
            status=ImplementationStatus.NOT_STARTED,
        )

        # Find section content
        pattern = re.compile(rf"## {re.escape(section_name)}\n(.*?)(?=\n## |\Z)", re.DOTALL)
        match = pattern.search(content)

        if not match:
            return section_cov

        section_content = match.group(1)

        # Count items based on section type
        if "API Contract" in section_name:
            # Count endpoints
            endpoints = re.findall(r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|", section_content)
            section_cov.total_items = len(endpoints)

        elif "Test Cases" in section_name:
            # Count test case rows
            test_rows = re.findall(r"\|\s*[A-Z]+-\d+\s*\|", section_content)
            section_cov.total_items = len(test_rows)

        elif "Inputs" in section_name or "Outputs" in section_name:
            # Count table rows (excluding headers)
            rows = [l for l in section_content.split("\n") if l.strip().startswith("|")]
            data_rows = [r for r in rows if not re.match(r"^\|[-\s|]+\|$", r.strip())]
            section_cov.total_items = max(0, len(data_rows) - 1)  # Exclude header

        elif "Dependencies" in section_name:
            # Count dependency entries
            deps = re.findall(r"\|\s*\w+\s*\|", section_content)
            section_cov.total_items = len(deps) // 2  # Divide by columns

        else:
            # Count list items or table rows
            items = re.findall(r"^[-*]\s+", section_content, re.MULTILINE)
            section_cov.total_items = len(items)

        return section_cov

    def _find_code_files(self, spec_name: str) -> list[str]:
        """Find code files related to a spec."""
        code_files = []
        spec_id = spec_name.replace("-", "_").lower()

        # Search for matching Python files
        for py_file in self.project_dir.rglob("*.py"):
            if spec_id in py_file.stem.lower():
                code_files.append(str(py_file.relative_to(self.project_dir)))

        # Search for matching TypeScript files
        for ts_file in self.project_dir.rglob("*.ts"):
            if spec_id in ts_file.stem.lower():
                code_files.append(str(ts_file.relative_to(self.project_dir)))

        return code_files

    def _find_test_files(self, spec_name: str) -> list[str]:
        """Find test files related to a spec."""
        test_files = []
        spec_id = spec_name.replace("-", "_").lower()

        # Search for matching test files
        for test_file in self.project_dir.rglob("test_*.py"):
            if spec_id in test_file.stem.lower():
                test_files.append(str(test_file.relative_to(self.project_dir)))

        for test_file in self.project_dir.rglob("*.test.ts"):
            if spec_id in test_file.stem.lower():
                test_files.append(str(test_file.relative_to(self.project_dir)))

        return test_files

    def _check_implementation(self, coverage: SpecCoverage) -> None:
        """Check implementation status based on code analysis."""
        if not coverage.code_files:
            return

        # Read code files and check for implementation markers
        for code_file in coverage.code_files:
            file_path = self.project_dir / code_file
            if not file_path.exists():
                continue

            content = file_path.read_text()

            # Check for implemented endpoints
            if "6. API Contract" in coverage.sections:
                section = coverage.sections["6. API Contract"]
                # Look for route decorators
                routes = re.findall(r'@(app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', content, re.IGNORECASE)
                for _, method, path in routes:
                    section.implemented_items.append(f"{method.upper()} {path}")

                if section.implemented_items:
                    if len(section.implemented_items) >= section.total_items:
                        section.status = ImplementationStatus.COMPLETE
                    else:
                        section.status = ImplementationStatus.PARTIAL

        # Check test coverage
        if coverage.test_files and "7. Test Cases" in coverage.sections:
            section = coverage.sections["7. Test Cases"]
            for test_file in coverage.test_files:
                file_path = self.project_dir / test_file
                if not file_path.exists():
                    continue

                content = file_path.read_text()
                tests = re.findall(r"def (test_\w+)", content)
                section.implemented_items.extend(tests)

            if section.implemented_items:
                if len(section.implemented_items) >= section.total_items:
                    section.status = ImplementationStatus.COMPLETE
                else:
                    section.status = ImplementationStatus.PARTIAL

    def save_coverage(self, coverage: SpecCoverage) -> None:
        """Save coverage data to file.

        Args:
            coverage: Coverage data to save.
        """
        self.coverage_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data
        if self.coverage_file.exists():
            with open(self.coverage_file) as f:
                data = json.load(f)
        else:
            data = {"specs": {}}

        # Update with new coverage
        data["specs"][coverage.spec_name] = coverage.to_dict()
        data["last_updated"] = datetime.now().isoformat()

        with open(self.coverage_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_coverage(self, spec_name: str) -> SpecCoverage | None:
        """Load coverage data from file.

        Args:
            spec_name: Name of the spec.

        Returns:
            SpecCoverage or None if not found.
        """
        if not self.coverage_file.exists():
            return None

        with open(self.coverage_file) as f:
            data = json.load(f)

        spec_data = data.get("specs", {}).get(spec_name)
        if not spec_data:
            return None

        coverage = SpecCoverage(
            spec_name=spec_data["spec_name"],
            spec_path=spec_data["spec_path"],
            code_files=spec_data.get("code_files", []),
            test_files=spec_data.get("test_files", []),
        )

        if spec_data.get("last_analyzed"):
            coverage.last_analyzed = datetime.fromisoformat(spec_data["last_analyzed"])

        for name, section_data in spec_data.get("sections", {}).items():
            coverage.sections[name] = SectionCoverage(
                section_name=section_data["section_name"],
                status=ImplementationStatus(section_data["status"]),
                implemented_items=section_data.get("implemented_items", []),
                total_items=section_data.get("total_items", 0),
                notes=section_data.get("notes", ""),
            )

        return coverage

    def get_all_coverage(self) -> dict[str, SpecCoverage]:
        """Get coverage for all specs.

        Returns:
            Dict mapping spec names to coverage.
        """
        result = {}

        # Find all specs
        for spec_file in self.specs_dir.rglob("block.md"):
            rel_path = spec_file.parent.relative_to(self.specs_dir)
            spec_name = str(rel_path)

            try:
                coverage = self.analyze_spec(spec_name)
                result[spec_name] = coverage
            except Exception:
                pass

        return result

    def generate_report(self) -> str:
        """Generate coverage report.

        Returns:
            Markdown report string.
        """
        all_coverage = self.get_all_coverage()

        lines = [
            "# Spec Coverage Report",
            "",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Summary",
            "",
            "| Spec | Status | Coverage | Code Files | Test Files |",
            "|------|--------|----------|------------|------------|",
        ]

        for name, coverage in sorted(all_coverage.items()):
            status_emoji = {
                ImplementationStatus.NOT_STARTED: ":white_circle:",
                ImplementationStatus.PARTIAL: ":yellow_circle:",
                ImplementationStatus.COMPLETE: ":green_circle:",
                ImplementationStatus.VERIFIED: ":white_check_mark:",
            }.get(coverage.status, ":question:")

            lines.append(
                f"| {name} | {status_emoji} {coverage.status.value} | "
                f"{coverage.overall_percentage:.1f}% | "
                f"{len(coverage.code_files)} | {len(coverage.test_files)} |"
            )

        lines.extend([
            "",
            "## Details",
            "",
        ])

        for name, coverage in sorted(all_coverage.items()):
            lines.extend([
                f"### {name}",
                "",
                "| Section | Status | Items | Coverage |",
                "|---------|--------|-------|----------|",
            ])

            for section_name, section in coverage.sections.items():
                impl_count = len(section.implemented_items)
                lines.append(
                    f"| {section_name} | {section.status.value} | "
                    f"{impl_count}/{section.total_items} | {section.percentage:.1f}% |"
                )

            lines.append("")

        return "\n".join(lines)
