"""Cross-block validation for interface compatibility."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CrossBlockIssueType(Enum):
    """Type of cross-block validation issue."""
    MISSING_DEPENDENCY = "missing_dependency"
    OUTPUT_INPUT_MISMATCH = "output_input_mismatch"
    API_CONTRACT_CONFLICT = "api_contract_conflict"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    ORPHANED_BLOCK = "orphaned_block"
    VERSION_MISMATCH = "version_mismatch"


class CrossBlockSeverity(Enum):
    """Severity of cross-block issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class CrossBlockIssue:
    """A cross-block validation issue."""

    issue_type: CrossBlockIssueType
    severity: CrossBlockSeverity
    message: str
    source_block: str
    target_block: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "source_block": self.source_block,
            "target_block": self.target_block,
            "details": self.details,
        }


@dataclass
class BlockInterface:
    """Interface definition extracted from a block spec."""

    block_name: str
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    api_endpoints: list[dict[str, Any]] = field(default_factory=list)
    events_emitted: list[str] = field(default_factory=list)
    events_consumed: list[str] = field(default_factory=list)


@dataclass
class CrossBlockValidationResult:
    """Result of cross-block validation."""

    issues: list[CrossBlockIssue] = field(default_factory=list)
    blocks_analyzed: list[str] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return any(i.severity == CrossBlockSeverity.ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        """Count of errors."""
        return sum(1 for i in self.issues if i.severity == CrossBlockSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return sum(1 for i in self.issues if i.severity == CrossBlockSeverity.WARNING)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "has_errors": self.has_errors,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "blocks_analyzed": self.blocks_analyzed,
            "dependency_graph": self.dependency_graph,
            "issues": [i.to_dict() for i in self.issues],
        }


class CrossBlockValidator:
    """Validates interfaces between blocks."""

    def __init__(self, specs_dir: Path):
        """Initialize validator.

        Args:
            specs_dir: Directory containing specs.
        """
        self.specs_dir = specs_dir
        self.interfaces: dict[str, BlockInterface] = {}

    def extract_interface(self, block_name: str, content: str) -> BlockInterface:
        """Extract interface from block spec content.

        Args:
            block_name: Name of the block.
            content: Spec markdown content.

        Returns:
            BlockInterface with extracted information.
        """
        interface = BlockInterface(block_name=block_name)

        # Extract inputs
        interface.inputs = self._extract_table_rows(content, "### User Inputs")
        interface.inputs.extend(self._extract_table_rows(content, "### System Inputs"))

        # Extract outputs
        interface.outputs = self._extract_table_rows(content, "### Return Values")

        # Extract dependencies
        interface.dependencies = self._extract_dependencies(content)

        # Extract API endpoints
        interface.api_endpoints = self._extract_table_rows(content, "### Endpoints")

        # Extract events
        interface.events_emitted = self._extract_events(content, "### Events")

        return interface

    def _extract_table_rows(self, content: str, section_header: str) -> list[dict[str, Any]]:
        """Extract rows from a markdown table section."""
        rows = []

        if section_header not in content:
            return rows

        # Find section content
        section_start = content.find(section_header)
        section_end = content.find("###", section_start + 1)
        if section_end == -1:
            section_end = content.find("## ", section_start + 1)
        if section_end == -1:
            section_end = len(content)

        section_content = content[section_start:section_end]

        # Find table rows
        lines = section_content.split("\n")
        header_found = False
        headers = []

        for line in lines:
            line = line.strip()
            if not line.startswith("|"):
                continue

            # Parse table row
            cells = [c.strip() for c in line.split("|")[1:-1]]

            if not header_found:
                headers = cells
                header_found = True
            elif re.match(r"^[-\s|]+$", line):
                continue  # Skip separator
            else:
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))

        return rows

    def _extract_dependencies(self, content: str) -> list[str]:
        """Extract internal dependencies."""
        deps = []

        if "### Internal" not in content:
            return deps

        section_start = content.find("### Internal")
        section_end = content.find("###", section_start + 1)
        if section_end == -1:
            section_end = content.find("## ", section_start + 1)

        section_content = content[section_start:section_end] if section_end != -1 else content[section_start:]

        # Find module names in table
        for row in self._extract_table_rows(content, "### Internal"):
            if "Module" in row:
                deps.append(row["Module"])

        return deps

    def _extract_events(self, content: str, section_header: str) -> list[str]:
        """Extract event names."""
        events = []

        rows = self._extract_table_rows(content, section_header)
        for row in rows:
            if "Event" in row:
                events.append(row["Event"])

        return events

    def load_all_interfaces(self) -> dict[str, BlockInterface]:
        """Load interfaces from all block specs.

        Returns:
            Dict mapping block names to interfaces.
        """
        self.interfaces = {}

        # Find all block.md files
        for block_file in self.specs_dir.rglob("block.md"):
            # Get block name from path
            rel_path = block_file.parent.relative_to(self.specs_dir)
            block_name = str(rel_path).replace("/", "/")

            content = block_file.read_text()
            self.interfaces[block_name] = self.extract_interface(block_name, content)

        return self.interfaces

    def validate(self) -> CrossBlockValidationResult:
        """Validate all cross-block interfaces.

        Returns:
            CrossBlockValidationResult with all issues found.
        """
        result = CrossBlockValidationResult()

        # Load all interfaces
        self.load_all_interfaces()
        result.blocks_analyzed = list(self.interfaces.keys())

        # Build dependency graph
        for name, interface in self.interfaces.items():
            result.dependency_graph[name] = interface.dependencies

        # Run validations
        result.issues.extend(self._check_missing_dependencies())
        result.issues.extend(self._check_circular_dependencies())
        result.issues.extend(self._check_output_input_compatibility())
        result.issues.extend(self._check_api_conflicts())
        result.issues.extend(self._check_orphaned_blocks())

        return result

    def _check_missing_dependencies(self) -> list[CrossBlockIssue]:
        """Check for references to non-existent blocks."""
        issues = []

        for name, interface in self.interfaces.items():
            for dep in interface.dependencies:
                if dep not in self.interfaces:
                    issues.append(CrossBlockIssue(
                        issue_type=CrossBlockIssueType.MISSING_DEPENDENCY,
                        severity=CrossBlockSeverity.ERROR,
                        message=f"Block '{name}' depends on '{dep}' which does not exist",
                        source_block=name,
                        target_block=dep,
                    ))

        return issues

    def _check_circular_dependencies(self) -> list[CrossBlockIssue]:
        """Check for circular dependencies."""
        issues = []
        visited = set()
        rec_stack = set()

        def has_cycle(node: str, path: list[str]) -> list[str] | None:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in self.interfaces.get(node, BlockInterface(node)).dependencies:
                if neighbor not in visited:
                    result = has_cycle(neighbor, path + [neighbor])
                    if result:
                        return result
                elif neighbor in rec_stack:
                    return path + [neighbor]

            rec_stack.remove(node)
            return None

        for name in self.interfaces:
            if name not in visited:
                cycle = has_cycle(name, [name])
                if cycle:
                    issues.append(CrossBlockIssue(
                        issue_type=CrossBlockIssueType.CIRCULAR_DEPENDENCY,
                        severity=CrossBlockSeverity.ERROR,
                        message=f"Circular dependency detected: {' -> '.join(cycle)}",
                        source_block=cycle[0],
                        target_block=cycle[-1],
                        details={"cycle": cycle},
                    ))

        return issues

    def _check_output_input_compatibility(self) -> list[CrossBlockIssue]:
        """Check that outputs match expected inputs."""
        issues = []

        for name, interface in self.interfaces.items():
            for dep in interface.dependencies:
                if dep not in self.interfaces:
                    continue

                dep_interface = self.interfaces[dep]

                # Check if any required system inputs from this block
                # are provided as outputs from dependencies
                for input_def in interface.inputs:
                    if input_def.get("Required") == "yes":
                        input_name = input_def.get("Name", "")
                        input_type = input_def.get("Type", "")

                        # Look for matching output in dependency
                        matching_output = None
                        for output_def in dep_interface.outputs:
                            if output_def.get("Name") == input_name:
                                matching_output = output_def
                                break

                        if matching_output:
                            # Check type compatibility
                            output_type = matching_output.get("Type", "")
                            if output_type and input_type and output_type != input_type:
                                issues.append(CrossBlockIssue(
                                    issue_type=CrossBlockIssueType.OUTPUT_INPUT_MISMATCH,
                                    severity=CrossBlockSeverity.WARNING,
                                    message=f"Type mismatch: '{dep}' outputs '{input_name}' as {output_type}, but '{name}' expects {input_type}",
                                    source_block=name,
                                    target_block=dep,
                                    details={
                                        "field": input_name,
                                        "expected_type": input_type,
                                        "actual_type": output_type,
                                    },
                                ))

        return issues

    def _check_api_conflicts(self) -> list[CrossBlockIssue]:
        """Check for conflicting API endpoints."""
        issues = []
        endpoint_owners: dict[str, str] = {}

        for name, interface in self.interfaces.items():
            for endpoint in interface.api_endpoints:
                method = endpoint.get("Method", "")
                path = endpoint.get("Path", "")
                key = f"{method} {path}"

                if key in endpoint_owners:
                    issues.append(CrossBlockIssue(
                        issue_type=CrossBlockIssueType.API_CONTRACT_CONFLICT,
                        severity=CrossBlockSeverity.ERROR,
                        message=f"Duplicate endpoint '{key}' defined in '{endpoint_owners[key]}' and '{name}'",
                        source_block=name,
                        target_block=endpoint_owners[key],
                        details={"endpoint": key},
                    ))
                else:
                    endpoint_owners[key] = name

        return issues

    def _check_orphaned_blocks(self) -> list[CrossBlockIssue]:
        """Check for blocks with no dependents (except root)."""
        issues = []

        # Find all blocks that are depended on
        depended_on = set()
        for interface in self.interfaces.values():
            depended_on.update(interface.dependencies)

        # Check for orphans (excluding root blocks)
        for name, interface in self.interfaces.items():
            # Skip root blocks and blocks with dependencies
            if not interface.dependencies and name not in depended_on:
                # Check if it's a root block
                if "/" not in name:
                    continue  # Root blocks are OK to be orphans

                issues.append(CrossBlockIssue(
                    issue_type=CrossBlockIssueType.ORPHANED_BLOCK,
                    severity=CrossBlockSeverity.INFO,
                    message=f"Block '{name}' has no dependencies and no dependents",
                    source_block=name,
                ))

        return issues


def visualize_dependency_graph(result: CrossBlockValidationResult) -> str:
    """Generate Mermaid diagram of dependency graph.

    Args:
        result: Validation result with dependency graph.

    Returns:
        Mermaid diagram string.
    """
    lines = ["graph TD"]

    for block, deps in result.dependency_graph.items():
        safe_block = block.replace("/", "_").replace("-", "_")

        if not deps:
            lines.append(f"    {safe_block}[{block}]")
        else:
            for dep in deps:
                safe_dep = dep.replace("/", "_").replace("-", "_")
                lines.append(f"    {safe_block}[{block}] --> {safe_dep}[{dep}]")

    return "\n".join(lines)
