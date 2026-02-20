"""Tests for the spec generator."""

from __future__ import annotations

from pathlib import Path

import pytest
import asyncio

from src.builder.session import (
    BuilderSession,
    BlockDesign,
    HierarchyDesign,
    Decision,
    Option,
)
from src.builder.generator import SpecGenerator, GeneratedSpec


class TestSpecGenerator:
    """Tests for SpecGenerator."""

    def test_generator_creation(self, mock_llm):
        """Test generator initialization."""
        generator = SpecGenerator(mock_llm)
        assert generator.llm_client == mock_llm

    def test_generate_block_spec_without_llm(self, session_with_decisions):
        """Test template-based spec generation."""
        block = BlockDesign(
            path="test-system/api",
            name="API Gateway",
            block_type="component",
            description="Handles API requests",
            parent_path="test-system",
            tech_stack="Python, FastAPI",
            api_endpoints=[{"method": "GET", "path": "/health"}],
        )

        generator = SpecGenerator(None)

        spec = asyncio.run(generator.generate_block_spec(block, session_with_decisions))

        assert spec is not None
        assert spec.block_path == "test-system/api"
        assert "API Gateway" in spec.content
        assert "# Block Specification" in spec.content
        assert "## 1. Metadata" in spec.content
        assert "## 6. API Contract" in spec.content

    def test_generate_all_specs(self, session_with_hierarchy):
        """Test generating specs for all blocks."""
        generator = SpecGenerator(None)

        specs = asyncio.run(
            generator.generate_all_specs(
                session_with_hierarchy.hierarchy_design, session_with_hierarchy
            )
        )

        assert len(specs) == len(session_with_hierarchy.hierarchy_design.blocks)
        assert all(isinstance(s, GeneratedSpec) for s in specs)

    def test_select_template_api_service(self):
        """Test template selection for API service."""
        block = BlockDesign(
            path="test/api",
            name="API",
            block_type="component",
            description="API",
            api_endpoints=[{"method": "GET", "path": "/test"}],
        )

        generator = SpecGenerator(None)
        template = generator._select_template(block)

        assert template == "api-service"

    def test_select_template_cli_tool(self):
        """Test template selection for CLI tool."""
        block = BlockDesign(
            path="test/cli",
            name="CLI Tool",
            block_type="leaf",
            description="Command line tool",
        )

        generator = SpecGenerator(None)
        template = generator._select_template(block)

        assert template == "cli-tool"

    def test_select_template_worker(self):
        """Test template selection for worker service."""
        block = BlockDesign(
            path="test/worker",
            name="Background Worker",
            block_type="module",
            description="Process jobs",
        )

        generator = SpecGenerator(None)
        template = generator._select_template(block)

        assert template == "worker-service"

    def test_select_template_library(self):
        """Test template selection for library."""
        block = BlockDesign(
            path="test/lib",
            name="Utility Lib",
            block_type="leaf",
            description="Shared utilities",
        )

        generator = SpecGenerator(None)
        template = generator._select_template(block)

        assert template == "library"

    def test_generated_spec_content_sections(self, session_with_decisions):
        """Test that generated spec has all required sections."""
        block = BlockDesign(
            path="test-system",
            name="Test System",
            block_type="root",
            description="Root block",
        )

        generator = SpecGenerator(None)
        spec = asyncio.run(generator.generate_block_spec(block, session_with_decisions))

        required_sections = [
            "## 0. Block Configuration",
            "## 1. Metadata",
            "## 2. Overview",
            "## 3. Inputs",
            "## 4. Outputs",
            "## 5. Dependencies",
            "## 6. API Contract",
            "## 7. Test Cases",
            "## 8. Edge Cases",
            "## 9. Error Handling",
            "## 10. Performance",
            "## 11. Security",
            "## 12. Implementation",
            "## 13. Acceptance",
        ]

        for section in required_sections:
            assert section in spec.content, f"Missing section: {section}"

    def test_generated_spec_reflects_decisions(self, session_with_decisions):
        """Test that generated spec reflects session decisions."""
        # Add tech stack decision
        session_with_decisions.decisions.append(
            Decision(
                id="dec-tech",
                topic="Tech Stack",
                question="What tech?",
                options=[Option("stack-python", "Python", "Python with FastAPI")],
                selected_option_id="stack-python",
            )
        )

        block = BlockDesign(
            path="test-system",
            name="Test System",
            block_type="root",
            description="Root block",
            tech_stack="Python",
        )

        generator = SpecGenerator(None)
        spec = asyncio.run(generator.generate_block_spec(block, session_with_decisions))

        assert "Python" in spec.content

    def test_write_specs(self, session_with_hierarchy, temp_project_dir):
        """Test writing specs to disk."""
        generator = SpecGenerator(None)

        specs = asyncio.run(
            generator.generate_all_specs(
                session_with_hierarchy.hierarchy_design, session_with_hierarchy
            )
        )

        created_files = asyncio.run(generator.write_specs(specs, temp_project_dir))

        assert len(created_files) == len(specs)
        for f in created_files:
            assert Path(f).exists()
            assert Path(f).name == "block.md"

    def test_generated_spec_api_endpoints(self, session_with_decisions):
        """Test that API endpoints are included in spec."""
        block = BlockDesign(
            path="test/api",
            name="API",
            block_type="component",
            description="API",
            api_endpoints=[
                {"method": "GET", "path": "/health", "description": "Health check"},
                {"method": "POST", "path": "/users", "description": "Create user"},
            ],
        )

        generator = SpecGenerator(None)
        spec = asyncio.run(generator.generate_block_spec(block, session_with_decisions))

        assert "/health" in spec.content
        assert "/users" in spec.content
        assert "GET" in spec.content
        assert "POST" in spec.content


class TestGeneratedSpec:
    """Tests for GeneratedSpec dataclass."""

    def test_generated_spec_creation(self):
        """Test GeneratedSpec creation."""
        spec = GeneratedSpec(
            block_path="test/api",
            content="# Test Spec",
            file_path="specs/test/api/block.md",
            template_used="api-service",
        )

        assert spec.block_path == "test/api"
        assert spec.content == "# Test Spec"
        assert spec.template_used == "api-service"
        assert spec.generated_at is not None

    def test_generated_spec_to_dict(self):
        """Test GeneratedSpec serialization."""
        spec = GeneratedSpec(
            block_path="test/api",
            content="# Test",
            file_path="specs/test/api/block.md",
        )

        data = spec.to_dict()

        assert data["block_path"] == "test/api"
        assert data["content"] == "# Test"
        assert "generated_at" in data
