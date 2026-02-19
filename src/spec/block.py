"""Block specification data structures for hierarchical specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.spec.schemas import Spec
    from src.rules.schemas import Rule, SameAsReference


class BlockType(Enum):
    """Type of block in the hierarchy."""

    ROOT = "root"
    COMPONENT = "component"
    MODULE = "module"
    LEAF = "leaf"


@dataclass
class SubBlockInfo:
    """Information about a sub-block."""

    name: str
    description: str = ""


@dataclass
class BlockMetadata:
    """Block configuration metadata from Section 0."""

    block_type: BlockType = BlockType.LEAF
    parent_path: str | None = None
    sub_blocks: list[SubBlockInfo] = field(default_factory=list)


@dataclass
class BlockSpec:
    """Complete block specification with hierarchy information.

    A BlockSpec represents a specification that is part of a hierarchical
    structure, with parent/child relationships and scoped rules.
    """

    path: str  # e.g., "payment-system/gateway"
    name: str
    directory: Path
    spec: Spec  # The actual spec content (sections 1-13)
    block_type: BlockType = BlockType.LEAF
    parent: BlockSpec | None = None
    children: list[BlockSpec] = field(default_factory=list)
    depth: int = 0
    scoped_rules: list[Rule] = field(default_factory=list)
    same_as_refs: list[SameAsReference] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize derived fields."""
        if isinstance(self.directory, str):
            self.directory = Path(self.directory)

    @property
    def is_root(self) -> bool:
        """Check if this is a root block."""
        return self.block_type == BlockType.ROOT

    @property
    def is_leaf(self) -> bool:
        """Check if this is a leaf block (no children)."""
        return self.block_type == BlockType.LEAF or len(self.children) == 0

    @property
    def has_children(self) -> bool:
        """Check if this block has child blocks."""
        return len(self.children) > 0

    def get_ancestors(self) -> list[BlockSpec]:
        """Get all ancestor blocks from root to parent."""
        ancestors = []
        current = self.parent
        while current is not None:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors

    def get_descendants(self) -> list[BlockSpec]:
        """Get all descendant blocks (depth-first)."""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants

    def get_siblings(self) -> list[BlockSpec]:
        """Get sibling blocks (same parent)."""
        if self.parent is None:
            return []
        return [child for child in self.parent.children if child.path != self.path]

    def find_child(self, name: str) -> BlockSpec | None:
        """Find a direct child by name."""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def find_descendant(self, path: str) -> BlockSpec | None:
        """Find a descendant by relative path."""
        parts = path.split("/")
        current: BlockSpec | None = self

        for part in parts:
            if current is None:
                return None
            current = current.find_child(part)

        return current

    def to_dict(self) -> dict:
        """Convert block to dictionary (without circular references)."""
        return {
            "path": self.path,
            "name": self.name,
            "directory": str(self.directory),
            "block_type": self.block_type.value,
            "depth": self.depth,
            "parent_path": self.parent.path if self.parent else None,
            "children": [child.path for child in self.children],
            "scoped_rules_count": len(self.scoped_rules),
            "same_as_refs_count": len(self.same_as_refs),
            "spec": self.spec.to_dict() if self.spec else None,
        }
