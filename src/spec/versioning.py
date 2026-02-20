"""Spec versioning and migration system."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class SchemaVersion(Enum):
    """Supported schema versions."""
    V1_0 = "1.0"
    V1_1 = "1.1"
    V2_0 = "2.0"

    @classmethod
    def latest(cls) -> "SchemaVersion":
        """Get the latest schema version."""
        return cls.V2_0

    @classmethod
    def from_string(cls, version: str) -> "SchemaVersion":
        """Parse version string."""
        version = version.strip()
        for v in cls:
            if v.value == version:
                return v
        raise ValueError(f"Unknown schema version: {version}")


@dataclass
class VersionInfo:
    """Version information for a spec."""

    spec_version: str  # User-defined spec version (e.g., "1.0.0")
    schema_version: SchemaVersion  # Schema version used
    created_at: datetime
    updated_at: datetime
    content_hash: str
    previous_versions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spec_version": self.spec_version,
            "schema_version": self.schema_version.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "content_hash": self.content_hash,
            "previous_versions": self.previous_versions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VersionInfo":
        """Create from dictionary."""
        return cls(
            spec_version=data["spec_version"],
            schema_version=SchemaVersion.from_string(data["schema_version"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            content_hash=data["content_hash"],
            previous_versions=data.get("previous_versions", []),
        )


@dataclass
class MigrationStep:
    """A single migration step between versions."""

    from_version: SchemaVersion
    to_version: SchemaVersion
    description: str
    migrate_fn: Callable[[dict[str, Any]], dict[str, Any]]

    def apply(self, spec_data: dict[str, Any]) -> dict[str, Any]:
        """Apply this migration step."""
        return self.migrate_fn(spec_data)


class SpecVersionManager:
    """Manages spec versions and migrations."""

    def __init__(self, specs_dir: Path):
        """Initialize version manager.

        Args:
            specs_dir: Directory containing specs.
        """
        self.specs_dir = specs_dir
        self.versions_dir = specs_dir / ".versions"
        self.migrations: list[MigrationStep] = []
        self._register_migrations()

    def _register_migrations(self) -> None:
        """Register all migration steps."""
        # V1.0 -> V1.1: Add performance section defaults
        self.migrations.append(MigrationStep(
            from_version=SchemaVersion.V1_0,
            to_version=SchemaVersion.V1_1,
            description="Add performance section with defaults",
            migrate_fn=self._migrate_v1_0_to_v1_1,
        ))

        # V1.1 -> V2.0: Restructure inputs/outputs
        self.migrations.append(MigrationStep(
            from_version=SchemaVersion.V1_1,
            to_version=SchemaVersion.V2_0,
            description="Restructure inputs/outputs sections",
            migrate_fn=self._migrate_v1_1_to_v2_0,
        ))

    def _migrate_v1_0_to_v1_1(self, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate from V1.0 to V1.1."""
        if "performance" not in data:
            data["performance"] = {
                "p50": 100,
                "p95": 500,
                "p99": 1000,
                "target_rps": 100,
                "memory_limit": 512,
            }
        return data

    def _migrate_v1_1_to_v2_0(self, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate from V1.1 to V2.0."""
        # Restructure inputs section
        if "inputs" in data and isinstance(data["inputs"], list):
            old_inputs = data["inputs"]
            data["inputs"] = {
                "user_inputs": old_inputs,
                "system_inputs": [],
                "environment_variables": [],
            }

        # Restructure outputs section
        if "outputs" in data and isinstance(data["outputs"], list):
            old_outputs = data["outputs"]
            data["outputs"] = {
                "return_values": old_outputs,
                "side_effects": [],
                "events": [],
            }

        return data

    def compute_content_hash(self, content: str) -> str:
        """Compute hash of spec content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def detect_schema_version(self, spec_content: str) -> SchemaVersion:
        """Detect schema version from spec content."""
        # Check for V2.0 indicators
        if "### User Inputs" in spec_content and "### System Inputs" in spec_content:
            return SchemaVersion.V2_0

        # Check for V1.1 indicators
        if "## 10. Performance" in spec_content:
            return SchemaVersion.V1_1

        # Default to V1.0
        return SchemaVersion.V1_0

    def get_migration_path(
        self,
        from_version: SchemaVersion,
        to_version: SchemaVersion
    ) -> list[MigrationStep]:
        """Get ordered list of migrations to apply."""
        if from_version == to_version:
            return []

        path = []
        current = from_version

        while current != to_version:
            # Find migration from current version
            migration = next(
                (m for m in self.migrations if m.from_version == current),
                None
            )
            if migration is None:
                raise ValueError(
                    f"No migration path from {current.value} to {to_version.value}"
                )
            path.append(migration)
            current = migration.to_version

        return path

    def migrate(
        self,
        spec_data: dict[str, Any],
        from_version: SchemaVersion,
        to_version: SchemaVersion | None = None
    ) -> tuple[dict[str, Any], list[str]]:
        """Migrate spec data to target version.

        Args:
            spec_data: Spec data dictionary.
            from_version: Current schema version.
            to_version: Target version (defaults to latest).

        Returns:
            Tuple of (migrated data, list of applied migration descriptions).
        """
        if to_version is None:
            to_version = SchemaVersion.latest()

        migrations = self.get_migration_path(from_version, to_version)
        applied = []

        for migration in migrations:
            spec_data = migration.apply(spec_data)
            applied.append(migration.description)

        return spec_data, applied

    def save_version(
        self,
        spec_name: str,
        content: str,
        version: str,
        message: str = ""
    ) -> VersionInfo:
        """Save a new version of a spec.

        Args:
            spec_name: Name of the spec.
            content: Spec content.
            version: Version string (e.g., "1.0.0").
            message: Optional version message.

        Returns:
            VersionInfo for the saved version.
        """
        spec_versions_dir = self.versions_dir / spec_name
        spec_versions_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        content_hash = self.compute_content_hash(content)
        schema_version = self.detect_schema_version(content)

        # Load existing version info
        version_file = spec_versions_dir / "versions.json"
        if version_file.exists():
            with open(version_file) as f:
                versions_data = json.load(f)
            previous_versions = [v["spec_version"] for v in versions_data.get("versions", [])]
        else:
            versions_data = {"versions": []}
            previous_versions = []

        # Create version info
        version_info = VersionInfo(
            spec_version=version,
            schema_version=schema_version,
            created_at=now,
            updated_at=now,
            content_hash=content_hash,
            previous_versions=previous_versions,
        )

        # Save version content
        version_content_file = spec_versions_dir / f"{version}.md"
        with open(version_content_file, "w") as f:
            f.write(content)

        # Update versions.json
        versions_data["versions"].append({
            **version_info.to_dict(),
            "message": message,
        })
        versions_data["current"] = version

        with open(version_file, "w") as f:
            json.dump(versions_data, f, indent=2)

        return version_info

    def get_version(self, spec_name: str, version: str) -> str | None:
        """Get content of a specific version.

        Args:
            spec_name: Name of the spec.
            version: Version string.

        Returns:
            Spec content or None if not found.
        """
        version_file = self.versions_dir / spec_name / f"{version}.md"
        if version_file.exists():
            return version_file.read_text()
        return None

    def list_versions(self, spec_name: str) -> list[dict[str, Any]]:
        """List all versions of a spec.

        Args:
            spec_name: Name of the spec.

        Returns:
            List of version info dictionaries.
        """
        version_file = self.versions_dir / spec_name / "versions.json"
        if not version_file.exists():
            return []

        with open(version_file) as f:
            data = json.load(f)

        return data.get("versions", [])

    def get_current_version(self, spec_name: str) -> str | None:
        """Get current version of a spec.

        Args:
            spec_name: Name of the spec.

        Returns:
            Current version string or None.
        """
        version_file = self.versions_dir / spec_name / "versions.json"
        if not version_file.exists():
            return None

        with open(version_file) as f:
            data = json.load(f)

        return data.get("current")


def bump_version(version: str, bump_type: str = "patch") -> str:
    """Bump a semantic version.

    Args:
        version: Current version (e.g., "1.2.3").
        bump_type: Type of bump ("major", "minor", "patch").

    Returns:
        New version string.
    """
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Invalid version format: {version}")

    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"
