"""Incremental implementation - only regenerate changed sections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import re


@dataclass
class SectionHash:
    """Hash of a spec section."""

    section_name: str
    content_hash: str
    last_modified: datetime


@dataclass
class SpecSnapshot:
    """Snapshot of a spec's state."""

    spec_name: str
    spec_path: str
    overall_hash: str
    section_hashes: dict[str, SectionHash] = field(default_factory=dict)
    generated_files: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spec_name": self.spec_name,
            "spec_path": self.spec_path,
            "overall_hash": self.overall_hash,
            "section_hashes": {
                k: {
                    "section_name": v.section_name,
                    "content_hash": v.content_hash,
                    "last_modified": v.last_modified.isoformat(),
                }
                for k, v in self.section_hashes.items()
            },
            "generated_files": self.generated_files,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecSnapshot":
        """Create from dictionary."""
        snapshot = cls(
            spec_name=data["spec_name"],
            spec_path=data["spec_path"],
            overall_hash=data["overall_hash"],
            generated_files=data.get("generated_files", []),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )

        for name, section_data in data.get("section_hashes", {}).items():
            snapshot.section_hashes[name] = SectionHash(
                section_name=section_data["section_name"],
                content_hash=section_data["content_hash"],
                last_modified=datetime.fromisoformat(section_data["last_modified"]),
            )

        return snapshot


@dataclass
class ChangeSet:
    """Set of changes between snapshots."""

    added_sections: list[str] = field(default_factory=list)
    modified_sections: list[str] = field(default_factory=list)
    removed_sections: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.added_sections or self.modified_sections or self.removed_sections)

    @property
    def affected_sections(self) -> list[str]:
        """Get all affected sections."""
        return self.added_sections + self.modified_sections


class IncrementalTracker:
    """Track spec changes for incremental implementation."""

    # Section header pattern
    SECTION_PATTERN = re.compile(r"^##\s+(\d+)\.\s+(.+)$", re.MULTILINE)

    def __init__(self, project_dir: Path):
        """Initialize tracker.

        Args:
            project_dir: Project root directory.
        """
        self.project_dir = project_dir
        self.snapshots_file = project_dir / ".spec-dev" / "snapshots.json"

    def compute_hash(self, content: str) -> str:
        """Compute hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def parse_sections(self, content: str) -> dict[str, str]:
        """Parse spec into sections.

        Args:
            content: Spec content.

        Returns:
            Dict mapping section names to content.
        """
        sections = {}
        matches = list(self.SECTION_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            section_num = match.group(1)
            section_name = match.group(2).strip()
            start = match.end()

            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(content)

            section_content = content[start:end].strip()
            sections[f"{section_num}. {section_name}"] = section_content

        return sections

    def create_snapshot(self, spec_name: str, content: str, spec_path: str = "") -> SpecSnapshot:
        """Create snapshot of current spec state.

        Args:
            spec_name: Name of the spec.
            content: Spec content.
            spec_path: Path to spec file.

        Returns:
            SpecSnapshot of current state.
        """
        snapshot = SpecSnapshot(
            spec_name=spec_name,
            spec_path=spec_path,
            overall_hash=self.compute_hash(content),
        )

        sections = self.parse_sections(content)
        now = datetime.now()

        for name, section_content in sections.items():
            snapshot.section_hashes[name] = SectionHash(
                section_name=name,
                content_hash=self.compute_hash(section_content),
                last_modified=now,
            )

        return snapshot

    def detect_changes(self, old_snapshot: SpecSnapshot, new_snapshot: SpecSnapshot) -> ChangeSet:
        """Detect changes between snapshots.

        Args:
            old_snapshot: Previous snapshot.
            new_snapshot: Current snapshot.

        Returns:
            ChangeSet with detected changes.
        """
        changes = ChangeSet()

        old_sections = set(old_snapshot.section_hashes.keys())
        new_sections = set(new_snapshot.section_hashes.keys())

        # Added sections
        changes.added_sections = list(new_sections - old_sections)

        # Removed sections
        changes.removed_sections = list(old_sections - new_sections)

        # Modified sections
        for section in old_sections & new_sections:
            old_hash = old_snapshot.section_hashes[section].content_hash
            new_hash = new_snapshot.section_hashes[section].content_hash
            if old_hash != new_hash:
                changes.modified_sections.append(section)

        return changes

    def save_snapshot(self, snapshot: SpecSnapshot) -> None:
        """Save snapshot to file.

        Args:
            snapshot: Snapshot to save.
        """
        self.snapshots_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing snapshots
        if self.snapshots_file.exists():
            with open(self.snapshots_file) as f:
                data = json.load(f)
        else:
            data = {"snapshots": {}}

        # Update with new snapshot
        data["snapshots"][snapshot.spec_name] = snapshot.to_dict()

        with open(self.snapshots_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_snapshot(self, spec_name: str) -> SpecSnapshot | None:
        """Load snapshot from file.

        Args:
            spec_name: Name of the spec.

        Returns:
            SpecSnapshot or None if not found.
        """
        if not self.snapshots_file.exists():
            return None

        with open(self.snapshots_file) as f:
            data = json.load(f)

        snapshot_data = data.get("snapshots", {}).get(spec_name)
        if snapshot_data:
            return SpecSnapshot.from_dict(snapshot_data)

        return None

    def get_incremental_context(self, spec_name: str, content: str, spec_path: str = "") -> dict[str, Any]:
        """Get context for incremental implementation.

        Args:
            spec_name: Name of the spec.
            content: Current spec content.
            spec_path: Path to spec file.

        Returns:
            Context dict with change information.
        """
        new_snapshot = self.create_snapshot(spec_name, content, spec_path)
        old_snapshot = self.load_snapshot(spec_name)

        context = {
            "spec_name": spec_name,
            "is_incremental": old_snapshot is not None,
            "new_snapshot": new_snapshot,
            "old_snapshot": old_snapshot,
            "changes": None,
            "affected_sections": [],
            "previously_generated": [],
        }

        if old_snapshot:
            changes = self.detect_changes(old_snapshot, new_snapshot)
            context["changes"] = changes
            context["affected_sections"] = changes.affected_sections
            context["previously_generated"] = old_snapshot.generated_files

            # If no changes, mark as up-to-date
            if not changes.has_changes:
                context["up_to_date"] = True

        return context

    def record_generation(self, spec_name: str, generated_files: list[str]) -> None:
        """Record generated files for a spec.

        Args:
            spec_name: Name of the spec.
            generated_files: List of generated file paths.
        """
        snapshot = self.load_snapshot(spec_name)
        if snapshot:
            snapshot.generated_files = generated_files
            snapshot.timestamp = datetime.now()
            self.save_snapshot(snapshot)


# Section to implementation mapping
SECTION_TO_IMPLEMENTATION = {
    "2. Overview": ["models", "interfaces"],
    "3. Inputs": ["models", "validators", "schemas"],
    "4. Outputs": ["models", "schemas"],
    "5. Dependencies": ["requirements", "imports"],
    "6. API Contract": ["routes", "handlers", "controllers"],
    "7. Test Cases": ["tests"],
    "8. Edge Cases": ["tests", "validators"],
    "9. Error Handling": ["exceptions", "handlers"],
    "10. Performance": ["caching", "optimization"],
    "11. Security": ["auth", "middleware", "validators"],
    "12. Implementation": ["services", "logic"],
}


def get_affected_implementations(changes: ChangeSet) -> list[str]:
    """Get list of implementation areas affected by changes.

    Args:
        changes: The change set.

    Returns:
        List of affected implementation areas.
    """
    affected = set()

    for section in changes.affected_sections:
        if section in SECTION_TO_IMPLEMENTATION:
            affected.update(SECTION_TO_IMPLEMENTATION[section])

    return sorted(affected)
