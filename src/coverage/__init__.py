"""Spec coverage tracking - track which spec sections are implemented."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ImplementationStatus(Enum):
    """Status of implementation for a spec section."""
    NOT_STARTED = "not_started"
    PARTIAL = "partial"
    COMPLETE = "complete"
    VERIFIED = "verified"


class DefinitionType(Enum):
    """Type of code definition extracted from spec."""
    CLASS = "class"
    DATACLASS = "dataclass"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    CONSTANT = "constant"


@dataclass
class CodeDefinition:
    """A code definition extracted from the spec."""
    name: str
    definition_type: DefinitionType
    parent: str | None = None  # For methods, the class name
    signature: str = ""  # Full signature for matching
    source_section: str = ""  # Which spec section it came from

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.definition_type.value,
            "parent": self.parent,
            "signature": self.signature,
            "source_section": self.source_section,
        }


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
    # New: code definitions from spec
    spec_definitions: list[CodeDefinition] = field(default_factory=list)
    implemented_definitions: list[str] = field(default_factory=list)
    missing_definitions: list[str] = field(default_factory=list)

    @property
    def definition_coverage(self) -> float:
        """Calculate coverage based on spec definitions found in code."""
        if not self.spec_definitions:
            return 100.0  # No definitions to check
        return (len(self.implemented_definitions) / len(self.spec_definitions)) * 100

    @property
    def overall_percentage(self) -> float:
        """Calculate overall coverage percentage."""
        # Use definition coverage if we have definitions, else fallback to section-based
        if self.spec_definitions:
            return self.definition_coverage
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
            "definition_coverage": self.definition_coverage,
            "status": self.status.value,
            "sections": {k: v.to_dict() for k, v in self.sections.items()},
            "code_files": self.code_files,
            "test_files": self.test_files,
            "spec_definitions": [d.to_dict() for d in self.spec_definitions],
            "implemented_definitions": self.implemented_definitions,
            "missing_definitions": self.missing_definitions,
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

    def __init__(
        self,
        project_dir: Path,
        specs_dir: Path | None = None,
        code_dir: Path | None = None,
        test_dir: Path | None = None,
    ):
        """Initialize coverage tracker.

        Args:
            project_dir: Root directory of the project.
            specs_dir: Directory containing specs.
            code_dir: Directory containing implementation code.
            test_dir: Directory containing test files.
        """
        self.project_dir = project_dir
        self.specs_dir = specs_dir or project_dir / "specs"
        self.code_dir = code_dir  # If None, will search by name matching
        self.test_dir = test_dir  # If None, will search by name matching
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
            last_analyzed=datetime.now(timezone.utc),
        )

        # Extract code definitions from spec
        coverage.spec_definitions = self._extract_code_definitions(content)

        # Analyze each section (for backwards compatibility)
        for section_name in self.TRACKED_SECTIONS:
            section_cov = self._analyze_section(content, section_name)
            coverage.sections[section_name] = section_cov

        # Find related code files
        coverage.code_files = self._find_code_files(spec_name)
        coverage.test_files = self._find_test_files(spec_name)

        # Check implementation status based on code definitions
        self._check_code_definitions(coverage)

        # Check implementation status based on code files (legacy)
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

    def _extract_code_definitions(self, content: str) -> list[CodeDefinition]:
        """Extract code definitions from spec code blocks.

        Parses Python code blocks in the spec to find:
        - Class definitions (including dataclass, Enum)
        - Function definitions
        - Method definitions (within classes)
        - Constants (UPPER_CASE assignments)
        """
        definitions: list[CodeDefinition] = []
        seen: set[str] = set()  # Avoid duplicates

        # Find all Python code blocks
        code_blocks = re.findall(
            r"```(?:python|py)?\n(.*?)```",
            content,
            re.DOTALL | re.IGNORECASE
        )

        # Track current section for context
        sections = re.split(r"\n##+ ", content)
        section_map: dict[int, str] = {}
        pos = 0
        for i, section in enumerate(sections):
            section_map[pos] = section.split("\n")[0] if section else ""
            pos += len(section) + 4  # Account for "\n## "

        for code_block in code_blocks:
            # Find which section this code block is in
            block_pos = content.find(code_block)
            current_section = ""
            for start_pos, section_name in sorted(section_map.items()):
                if start_pos <= block_pos:
                    current_section = section_name

            # Extract class definitions
            class_matches = list(re.finditer(
                r"^(@\w+(?:\([^)]*\))?\n)*class\s+(\w+)(?:\([^)]*\))?:",
                code_block,
                re.MULTILINE
            ))

            for i, match in enumerate(class_matches):
                decorators = match.group(1) or ""
                class_name = match.group(2)
                full_match = match.group(0)

                if class_name in seen:
                    continue
                seen.add(class_name)

                # Determine type based on decorators
                if "@dataclass" in decorators:
                    def_type = DefinitionType.DATACLASS
                elif "Enum" in full_match:
                    def_type = DefinitionType.ENUM
                else:
                    def_type = DefinitionType.CLASS

                definitions.append(CodeDefinition(
                    name=class_name,
                    definition_type=def_type,
                    signature=full_match.strip(),
                    source_section=current_section,
                ))

                # Extract methods from this class only (until next class or end)
                class_start = match.end()
                if i + 1 < len(class_matches):
                    class_end = class_matches[i + 1].start()
                else:
                    class_end = len(code_block)

                class_body = code_block[class_start:class_end]

                # Only match methods that are indented (part of the class)
                method_matches = re.finditer(
                    r"^\s{4}(?:async\s+)?def\s+(\w+)\s*\([^)]*\)",
                    class_body,
                    re.MULTILINE
                )
                for method_match in method_matches:
                    method_name = method_match.group(1)
                    method_key = f"{class_name}.{method_name}"
                    if method_key in seen:
                        continue
                    seen.add(method_key)

                    definitions.append(CodeDefinition(
                        name=method_name,
                        definition_type=DefinitionType.METHOD,
                        parent=class_name,
                        signature=method_match.group(0).strip(),
                        source_section=current_section,
                    ))

            # Extract top-level function definitions
            func_matches = re.finditer(
                r"^(?:async\s+)?def\s+(\w+)\s*\([^)]*\)",
                code_block,
                re.MULTILINE
            )
            for match in func_matches:
                func_name = match.group(1)
                # Skip if it's indented (method, not function)
                line_start = code_block.rfind("\n", 0, match.start()) + 1
                if line_start < match.start() and code_block[line_start:match.start()].strip() == "":
                    # It's at the start of the line
                    if func_name in seen:
                        continue
                    seen.add(func_name)

                    definitions.append(CodeDefinition(
                        name=func_name,
                        definition_type=DefinitionType.FUNCTION,
                        signature=match.group(0).strip(),
                        source_section=current_section,
                    ))

            # Extract constants (UPPER_CASE = value at module level)
            const_matches = re.finditer(
                r"^([A-Z][A-Z0-9_]+)\s*[=:]",
                code_block,
                re.MULTILINE
            )
            for match in const_matches:
                const_name = match.group(1)
                if const_name in seen:
                    continue
                seen.add(const_name)

                definitions.append(CodeDefinition(
                    name=const_name,
                    definition_type=DefinitionType.CONSTANT,
                    signature=match.group(0).strip(),
                    source_section=current_section,
                ))

        return definitions

    def _check_code_definitions(self, coverage: SpecCoverage) -> None:
        """Check which spec definitions are implemented in code files."""
        if not coverage.spec_definitions:
            return

        # Read all code files into a single combined content for searching
        all_code = ""
        for code_file in coverage.code_files:
            file_path = self.project_dir / code_file
            if file_path.exists():
                try:
                    all_code += file_path.read_text() + "\n"
                except Exception:
                    pass

        # Also read test files for test class definitions
        for test_file in coverage.test_files:
            file_path = self.project_dir / test_file
            if file_path.exists():
                try:
                    all_code += file_path.read_text() + "\n"
                except Exception:
                    pass

        if not all_code:
            return

        # Check each definition
        for defn in coverage.spec_definitions:
            found = False

            if defn.definition_type == DefinitionType.CLASS:
                # Look for class definition
                pattern = rf"class\s+{re.escape(defn.name)}\s*[:\(]"
                if re.search(pattern, all_code):
                    found = True

            elif defn.definition_type == DefinitionType.DATACLASS:
                # Look for dataclass definition
                pattern = rf"@dataclass.*\nclass\s+{re.escape(defn.name)}\s*[:\(]"
                if re.search(pattern, all_code, re.DOTALL):
                    found = True
                # Also check for just class definition (might not use decorator)
                elif re.search(rf"class\s+{re.escape(defn.name)}\s*[:\(]", all_code):
                    found = True

            elif defn.definition_type == DefinitionType.ENUM:
                # Look for enum definition
                pattern = rf"class\s+{re.escape(defn.name)}\s*\([^)]*Enum[^)]*\)"
                if re.search(pattern, all_code):
                    found = True

            elif defn.definition_type == DefinitionType.FUNCTION:
                # Look for function definition
                pattern = rf"(?:async\s+)?def\s+{re.escape(defn.name)}\s*\("
                if re.search(pattern, all_code):
                    found = True

            elif defn.definition_type == DefinitionType.METHOD:
                # Look for method in the parent class
                if defn.parent:
                    # First find the class, then look for the method
                    class_pattern = rf"class\s+{re.escape(defn.parent)}\s*[:\(]"
                    class_match = re.search(class_pattern, all_code)
                    if class_match:
                        # Look for the method after the class definition
                        remaining = all_code[class_match.end():]
                        # Match method with optional decorators on preceding lines
                        method_pattern = rf"(?:async\s+)?def\s+{re.escape(defn.name)}\s*\("
                        if re.search(method_pattern, remaining[:50000]):  # Search up to ~500 lines
                            found = True

            elif defn.definition_type == DefinitionType.CONSTANT:
                # Look for constant definition
                pattern = rf"^{re.escape(defn.name)}\s*="
                if re.search(pattern, all_code, re.MULTILINE):
                    found = True

            if found:
                key = f"{defn.parent}.{defn.name}" if defn.parent else defn.name
                coverage.implemented_definitions.append(key)
            else:
                key = f"{defn.parent}.{defn.name}" if defn.parent else defn.name
                coverage.missing_definitions.append(key)

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

        # If code_dir is explicitly set, use all files in that directory
        if self.code_dir:
            search_dir = self.project_dir / self.code_dir
            if search_dir.exists():
                for py_file in search_dir.rglob("*.py"):
                    if not py_file.name.startswith("__"):
                        code_files.append(str(py_file.relative_to(self.project_dir)))
                for ts_file in search_dir.rglob("*.ts"):
                    code_files.append(str(ts_file.relative_to(self.project_dir)))
            return code_files

        # Otherwise, search by spec name matching
        spec_id = spec_name.replace("-", "_").lower()
        # Also try just the last part of the path (e.g., "connector-sdk" -> "connector_sdk")
        spec_short_id = spec_name.split("/")[-1].replace("-", "_").lower()

        # Search for matching Python files
        for py_file in self.project_dir.rglob("*.py"):
            stem_lower = py_file.stem.lower()
            if spec_id in stem_lower or spec_short_id in str(py_file).lower():
                code_files.append(str(py_file.relative_to(self.project_dir)))

        # Search for matching TypeScript files
        for ts_file in self.project_dir.rglob("*.ts"):
            stem_lower = ts_file.stem.lower()
            if spec_id in stem_lower or spec_short_id in str(ts_file).lower():
                code_files.append(str(ts_file.relative_to(self.project_dir)))

        return code_files

    def _find_test_files(self, spec_name: str) -> list[str]:
        """Find test files related to a spec."""
        test_files = []

        # If test_dir is explicitly set, use all test files in that directory
        if self.test_dir:
            search_dir = self.project_dir / self.test_dir
            if search_dir.exists():
                for test_file in search_dir.rglob("test_*.py"):
                    test_files.append(str(test_file.relative_to(self.project_dir)))
                for test_file in search_dir.rglob("*_test.py"):
                    test_files.append(str(test_file.relative_to(self.project_dir)))
                for test_file in search_dir.rglob("*.test.ts"):
                    test_files.append(str(test_file.relative_to(self.project_dir)))
            return test_files

        # Otherwise, search by spec name matching
        spec_id = spec_name.replace("-", "_").lower()
        spec_short_id = spec_name.split("/")[-1].replace("-", "_").lower()

        # Search for matching test files
        for test_file in self.project_dir.rglob("test_*.py"):
            stem_lower = test_file.stem.lower()
            if spec_id in stem_lower or spec_short_id in str(test_file).lower():
                test_files.append(str(test_file.relative_to(self.project_dir)))

        for test_file in self.project_dir.rglob("*.test.ts"):
            stem_lower = test_file.stem.lower()
            if spec_id in stem_lower or spec_short_id in str(test_file).lower():
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
