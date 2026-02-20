"""Spec diffing and comparison tools."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChangeType(Enum):
    """Type of change in diff."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class SectionChange:
    """Change in a spec section."""

    section_name: str
    change_type: ChangeType
    old_content: str | None = None
    new_content: str | None = None
    line_changes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Get a summary of the change."""
        if self.change_type == ChangeType.ADDED:
            return f"+ {self.section_name} (new section)"
        elif self.change_type == ChangeType.REMOVED:
            return f"- {self.section_name} (removed)"
        elif self.change_type == ChangeType.MODIFIED:
            additions = sum(1 for l in self.line_changes if l.startswith("+"))
            deletions = sum(1 for l in self.line_changes if l.startswith("-"))
            return f"~ {self.section_name} (+{additions}, -{deletions})"
        else:
            return f"  {self.section_name} (unchanged)"


@dataclass
class SpecDiff:
    """Diff between two spec versions."""

    old_version: str | None
    new_version: str | None
    old_path: str | None
    new_path: str | None
    section_changes: list[SectionChange] = field(default_factory=list)
    unified_diff: str = ""

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return any(
            c.change_type != ChangeType.UNCHANGED
            for c in self.section_changes
        )

    @property
    def summary(self) -> str:
        """Get a summary of all changes."""
        lines = []

        if self.old_version and self.new_version:
            lines.append(f"Comparing {self.old_version} -> {self.new_version}")
        elif self.old_path and self.new_path:
            lines.append(f"Comparing {self.old_path} -> {self.new_path}")

        lines.append("")

        added = sum(1 for c in self.section_changes if c.change_type == ChangeType.ADDED)
        removed = sum(1 for c in self.section_changes if c.change_type == ChangeType.REMOVED)
        modified = sum(1 for c in self.section_changes if c.change_type == ChangeType.MODIFIED)

        lines.append(f"Sections: +{added} added, -{removed} removed, ~{modified} modified")
        lines.append("")

        for change in self.section_changes:
            if change.change_type != ChangeType.UNCHANGED:
                lines.append(change.summary)

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "old_version": self.old_version,
            "new_version": self.new_version,
            "old_path": self.old_path,
            "new_path": self.new_path,
            "has_changes": self.has_changes,
            "section_changes": [
                {
                    "section": c.section_name,
                    "type": c.change_type.value,
                    "summary": c.summary,
                }
                for c in self.section_changes
            ],
        }


class SpecDiffer:
    """Compare specs and generate diffs."""

    # Section header pattern
    SECTION_PATTERN = re.compile(r"^##\s+(\d+)\.\s+(.+)$", re.MULTILINE)

    def __init__(self):
        """Initialize differ."""
        pass

    def parse_sections(self, content: str) -> dict[str, str]:
        """Parse spec content into sections.

        Args:
            content: Spec markdown content.

        Returns:
            Dict mapping section names to content.
        """
        sections = {}

        # Find all section headers
        matches = list(self.SECTION_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            section_num = match.group(1)
            section_name = match.group(2).strip()
            start = match.end()

            # End is either next section or end of content
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(content)

            section_content = content[start:end].strip()
            sections[f"{section_num}. {section_name}"] = section_content

        return sections

    def diff_sections(
        self,
        old_sections: dict[str, str],
        new_sections: dict[str, str]
    ) -> list[SectionChange]:
        """Compare two sets of sections.

        Args:
            old_sections: Sections from old spec.
            new_sections: Sections from new spec.

        Returns:
            List of section changes.
        """
        changes = []
        all_section_names = set(old_sections.keys()) | set(new_sections.keys())

        for section_name in sorted(all_section_names):
            old_content = old_sections.get(section_name)
            new_content = new_sections.get(section_name)

            if old_content is None:
                # New section added
                changes.append(SectionChange(
                    section_name=section_name,
                    change_type=ChangeType.ADDED,
                    new_content=new_content,
                ))
            elif new_content is None:
                # Section removed
                changes.append(SectionChange(
                    section_name=section_name,
                    change_type=ChangeType.REMOVED,
                    old_content=old_content,
                ))
            elif old_content != new_content:
                # Section modified
                line_diff = list(difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    lineterm="",
                ))
                changes.append(SectionChange(
                    section_name=section_name,
                    change_type=ChangeType.MODIFIED,
                    old_content=old_content,
                    new_content=new_content,
                    line_changes=line_diff,
                ))
            else:
                # Unchanged
                changes.append(SectionChange(
                    section_name=section_name,
                    change_type=ChangeType.UNCHANGED,
                    old_content=old_content,
                    new_content=new_content,
                ))

        return changes

    def diff_content(
        self,
        old_content: str,
        new_content: str,
        old_label: str = "old",
        new_label: str = "new"
    ) -> SpecDiff:
        """Diff two spec contents.

        Args:
            old_content: Old spec content.
            new_content: New spec content.
            old_label: Label for old version.
            new_label: Label for new version.

        Returns:
            SpecDiff with all changes.
        """
        old_sections = self.parse_sections(old_content)
        new_sections = self.parse_sections(new_content)

        section_changes = self.diff_sections(old_sections, new_sections)

        # Generate unified diff
        unified = "\n".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=old_label,
            tofile=new_label,
        ))

        return SpecDiff(
            old_version=old_label,
            new_version=new_label,
            old_path=None,
            new_path=None,
            section_changes=section_changes,
            unified_diff=unified,
        )

    def diff_files(self, old_path: Path, new_path: Path) -> SpecDiff:
        """Diff two spec files.

        Args:
            old_path: Path to old spec file.
            new_path: Path to new spec file.

        Returns:
            SpecDiff with all changes.
        """
        old_content = old_path.read_text()
        new_content = new_path.read_text()

        diff = self.diff_content(
            old_content,
            new_content,
            old_label=str(old_path),
            new_label=str(new_path),
        )
        diff.old_path = str(old_path)
        diff.new_path = str(new_path)

        return diff

    def diff_versions(
        self,
        specs_dir: Path,
        spec_name: str,
        old_version: str,
        new_version: str
    ) -> SpecDiff:
        """Diff two versions of a spec.

        Args:
            specs_dir: Directory containing specs.
            spec_name: Name of the spec.
            old_version: Old version string.
            new_version: New version string.

        Returns:
            SpecDiff with all changes.
        """
        from .versioning import SpecVersionManager

        manager = SpecVersionManager(specs_dir)

        old_content = manager.get_version(spec_name, old_version)
        new_content = manager.get_version(spec_name, new_version)

        if old_content is None:
            raise FileNotFoundError(f"Version {old_version} not found for {spec_name}")
        if new_content is None:
            raise FileNotFoundError(f"Version {new_version} not found for {spec_name}")

        diff = self.diff_content(
            old_content,
            new_content,
            old_label=f"{spec_name}@{old_version}",
            new_label=f"{spec_name}@{new_version}",
        )
        diff.old_version = old_version
        diff.new_version = new_version

        return diff


def format_diff_for_terminal(diff: SpecDiff, color: bool = True) -> str:
    """Format a diff for terminal output.

    Args:
        diff: The spec diff.
        color: Whether to use ANSI colors.

    Returns:
        Formatted string.
    """
    lines = []

    # Colors
    RED = "\033[91m" if color else ""
    GREEN = "\033[92m" if color else ""
    YELLOW = "\033[93m" if color else ""
    RESET = "\033[0m" if color else ""
    BOLD = "\033[1m" if color else ""

    # Header
    lines.append(f"{BOLD}Spec Diff{RESET}")
    lines.append("=" * 60)

    if diff.old_version and diff.new_version:
        lines.append(f"From: {diff.old_version}")
        lines.append(f"To:   {diff.new_version}")
    elif diff.old_path and diff.new_path:
        lines.append(f"From: {diff.old_path}")
        lines.append(f"To:   {diff.new_path}")

    lines.append("")

    # Summary
    added = sum(1 for c in diff.section_changes if c.change_type == ChangeType.ADDED)
    removed = sum(1 for c in diff.section_changes if c.change_type == ChangeType.REMOVED)
    modified = sum(1 for c in diff.section_changes if c.change_type == ChangeType.MODIFIED)

    lines.append(f"Changes: {GREEN}+{added} added{RESET}, {RED}-{removed} removed{RESET}, {YELLOW}~{modified} modified{RESET}")
    lines.append("")

    # Section changes
    for change in diff.section_changes:
        if change.change_type == ChangeType.ADDED:
            lines.append(f"{GREEN}+ {change.section_name}{RESET}")
        elif change.change_type == ChangeType.REMOVED:
            lines.append(f"{RED}- {change.section_name}{RESET}")
        elif change.change_type == ChangeType.MODIFIED:
            additions = sum(1 for l in change.line_changes if l.startswith("+") and not l.startswith("+++"))
            deletions = sum(1 for l in change.line_changes if l.startswith("-") and not l.startswith("---"))
            lines.append(f"{YELLOW}~ {change.section_name}{RESET} ({GREEN}+{additions}{RESET}, {RED}-{deletions}{RESET})")

    return "\n".join(lines)
