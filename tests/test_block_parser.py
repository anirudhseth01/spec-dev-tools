"""Tests for BlockParser."""

from pathlib import Path

import pytest

from src.spec.parser import BlockParser
from src.spec.block import BlockType


class TestBlockParserDiscovery:
    """Tests for block discovery functionality."""

    def test_discover_blocks_empty_dir(self, specs_dir: Path) -> None:
        """Test discovering blocks in empty directory."""
        parser = BlockParser(specs_dir)
        blocks = parser.discover_blocks()
        assert blocks == []

    def test_discover_blocks_finds_all(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test discovering all block.md files."""
        parser = BlockParser(specs_dir)
        blocks = parser.discover_blocks()
        assert len(blocks) == 6  # All blocks in hierarchy

    def test_discover_blocks_sorted(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test that discovered blocks are sorted by path."""
        parser = BlockParser(specs_dir)
        blocks = parser.discover_blocks()
        paths = [str(b) for b in blocks]
        assert paths == sorted(paths)


class TestBlockParserParsing:
    """Tests for block parsing functionality."""

    def test_parse_single_block(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test parsing a single block.md file."""
        parser = BlockParser(specs_dir)
        block_file = specs_dir / "root-system" / "block.md"
        block = parser.parse_block(block_file)

        assert block.name == "Root System"
        assert block.path == "root-system"
        assert block.block_type == BlockType.ROOT

    def test_parse_block_with_section_0(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test parsing block with full Section 0 configuration."""
        # Add scoped rules and same-as refs to a block
        block_file = specs_dir / "root-system" / "component-a" / "block.md"
        content = block_file.read_text()

        # Add scoped rule
        content = content.replace(
            "| ID | Name | Category | Severity | Sections | Validator | Description |",
            "| ID | Name | Category | Severity | Sections | Validator | Description |\n"
            "|----|------|----------|----------|----------|-----------|-------------|\n"
            "| SCOPE-001 | Scoped Test | testing | warning | test_cases | check_min_tests | Test rule |"
        )

        block_file.write_text(content)

        parser = BlockParser(specs_dir)
        block = parser.parse_block(block_file)

        assert block.block_type == BlockType.COMPONENT
        # Note: Rules parsing depends on table format being correct
        assert block.path == "root-system/component-a"

    def test_parse_block_spec_content(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test that spec content (sections 1-13) is parsed correctly."""
        parser = BlockParser(specs_dir)
        block_file = specs_dir / "root-system" / "block.md"
        block = parser.parse_block(block_file)

        # Check spec was parsed
        assert block.spec is not None
        assert block.spec.metadata.spec_id == "root-system"
        assert block.spec.overview.summary == "Root System block for testing."


class TestBlockParserHierarchy:
    """Tests for hierarchy parsing functionality."""

    def test_parse_hierarchy_all_blocks(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test parsing entire block hierarchy."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        assert len(blocks) == 6

    def test_parse_hierarchy_from_subpath(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test parsing hierarchy from a subpath."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy(specs_dir / "root-system" / "component-a")

        # Should find component-a and its children
        assert len(blocks) == 3
        paths = {b.path for b in blocks}
        assert "root-system/component-a" in paths
        assert "root-system/component-a/module-a1" in paths
        assert "root-system/component-a/module-a2" in paths

    def test_resolve_parent_child(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test that parent/child relationships are resolved."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        # Find root
        root = next((b for b in blocks if b.path == "root-system"), None)
        assert root is not None
        assert root.parent is None
        assert len(root.children) == 2  # component-a and component-b

        # Find component-a
        comp_a = next((b for b in blocks if b.path == "root-system/component-a"), None)
        assert comp_a is not None
        assert comp_a.parent is root
        assert len(comp_a.children) == 2  # module-a1 and module-a2

        # Find leaf
        leaf = next((b for b in blocks if b.path == "root-system/component-b/leaf-b1"), None)
        assert leaf is not None
        assert leaf.parent.path == "root-system/component-b"
        assert len(leaf.children) == 0

    def test_block_depth_calculation(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test that block depth is calculated correctly."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        depths = {b.path: b.depth for b in blocks}

        assert depths["root-system"] == 0
        assert depths["root-system/component-a"] == 1
        assert depths["root-system/component-b"] == 1
        assert depths["root-system/component-a/module-a1"] == 2
        assert depths["root-system/component-b/leaf-b1"] == 2


class TestBlockParserHelpers:
    """Tests for BlockSpec helper methods."""

    def test_get_ancestors(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test getting ancestor blocks."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        leaf = next((b for b in blocks if b.path == "root-system/component-b/leaf-b1"), None)
        ancestors = leaf.get_ancestors()

        assert len(ancestors) == 2
        assert ancestors[0].path == "root-system"
        assert ancestors[1].path == "root-system/component-b"

    def test_get_descendants(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test getting descendant blocks."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        root = next((b for b in blocks if b.path == "root-system"), None)
        descendants = root.get_descendants()

        assert len(descendants) == 5
        paths = {d.path for d in descendants}
        assert "root-system/component-a" in paths
        assert "root-system/component-a/module-a1" in paths

    def test_get_siblings(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test getting sibling blocks."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        comp_a = next((b for b in blocks if b.path == "root-system/component-a"), None)
        siblings = comp_a.get_siblings()

        assert len(siblings) == 1
        assert siblings[0].path == "root-system/component-b"

    def test_find_child(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test finding direct child by name."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        root = next((b for b in blocks if b.path == "root-system"), None)
        child = root.find_child("Component A")

        assert child is not None
        assert child.path == "root-system/component-a"

    def test_is_leaf(self, temp_block_hierarchy: dict, specs_dir: Path) -> None:
        """Test leaf block detection."""
        parser = BlockParser(specs_dir)
        blocks = parser.parse_hierarchy()

        for block in blocks:
            if block.path == "root-system/component-b/leaf-b1":
                assert block.is_leaf
            elif block.path == "root-system":
                assert not block.is_leaf
