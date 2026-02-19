"""Rule system data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuleLevel(Enum):
    """Level at which a rule is applied."""

    GLOBAL = "global"  # Applies to all blocks
    SCOPED = "scoped"  # Applies to a block and its descendants
    LOCAL = "local"  # Applies only to a specific block


class RuleCategory(Enum):
    """Category of rule for organization."""

    SECURITY = "security"
    TESTING = "testing"
    API = "api"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    CODE_QUALITY = "code_quality"


class RuleSeverity(Enum):
    """Severity level of a rule violation."""

    ERROR = "error"  # Must be fixed before proceeding
    WARNING = "warning"  # Should be fixed but not blocking
    INFO = "info"  # Informational, best practice suggestion


@dataclass
class Rule:
    """A validation rule that can be applied to specifications.

    Rules define constraints that specifications must satisfy. They can be
    applied at different levels (global, scoped, local) and target specific
    sections of a specification.
    """

    id: str  # Unique identifier, e.g., "SEC-001"
    name: str  # Human-readable name
    level: RuleLevel = RuleLevel.GLOBAL
    category: RuleCategory = RuleCategory.CODE_QUALITY
    severity: RuleSeverity = RuleSeverity.WARNING
    applies_to_sections: list[str] = field(default_factory=list)  # e.g., ["security", "api"]
    validation_fn: str = ""  # Name of validation function to call
    validation_args: dict[str, Any] = field(default_factory=dict)  # Arguments to pass
    description: str = ""  # Human-readable description of the rule
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert rule to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level.value,
            "category": self.category.value,
            "severity": self.severity.value,
            "applies_to_sections": self.applies_to_sections,
            "validation_fn": self.validation_fn,
            "validation_args": self.validation_args,
            "description": self.description,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        """Create rule from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            level=RuleLevel(data.get("level", "global")),
            category=RuleCategory(data.get("category", "code_quality")),
            severity=RuleSeverity(data.get("severity", "warning")),
            applies_to_sections=data.get("applies_to_sections", []),
            validation_fn=data.get("validation_fn", ""),
            validation_args=data.get("validation_args", {}),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
        )


class MergeMode(Enum):
    """Mode for merging same-as references."""

    REPLACE = "replace"  # Completely replace the section
    EXTEND = "extend"  # Add to existing items (lists only)
    MERGE = "merge"  # Deep merge (dicts and lists)


@dataclass
class SameAsReference:
    """Reference to another block's section for reuse.

    Allows a block to inherit or copy sections from another block,
    reducing duplication in specifications.
    """

    target_section: str  # Section in this block to populate, e.g., "security"
    source_block: str  # Path to source block, e.g., "auth-service" or "../common"
    source_section: str | None = None  # Section in source (defaults to target_section)
    merge_mode: MergeMode = MergeMode.REPLACE

    def __post_init__(self) -> None:
        """Set defaults."""
        if self.source_section is None:
            self.source_section = self.target_section

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_section": self.target_section,
            "source_block": self.source_block,
            "source_section": self.source_section,
            "merge_mode": self.merge_mode.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SameAsReference:
        """Create from dictionary."""
        return cls(
            target_section=data.get("target_section", ""),
            source_block=data.get("source_block", ""),
            source_section=data.get("source_section"),
            merge_mode=MergeMode(data.get("merge_mode", "replace")),
        )


@dataclass
class RuleViolation:
    """A violation detected when validating a rule.

    Contains information about what rule was violated, where, and how.
    """

    rule: Rule
    block_path: str  # Path of the block where violation occurred
    section: str  # Section where violation occurred
    message: str  # Human-readable description of the violation
    line_number: int | None = None  # Optional line number in source
    suggestion: str = ""  # Optional suggestion for fixing

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule.id,
            "rule_name": self.rule.name,
            "severity": self.rule.severity.value,
            "block_path": self.block_path,
            "section": self.section,
            "message": self.message,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        """Human-readable representation."""
        severity = self.rule.severity.value.upper()
        location = f"{self.block_path}:{self.section}"
        if self.line_number:
            location += f":{self.line_number}"
        return f"[{severity}] {self.rule.id} at {location}: {self.message}"
