"""Tests for the block hierarchy designer."""

from __future__ import annotations

import pytest
import asyncio

from src.builder.session import (
    BuilderSession,
    Decision,
    Option,
    BlockDesign,
    HierarchyDesign,
)
from src.builder.designer import BlockDesigner, ComponentInfo


class TestBlockDesigner:
    """Tests for BlockDesigner."""

    def test_designer_creation(self, mock_llm):
        """Test designer initialization."""
        designer = BlockDesigner(mock_llm)
        assert designer.llm_client == mock_llm

    def test_design_hierarchy_without_llm(self, session_with_decisions):
        """Test rule-based hierarchy design."""
        designer = BlockDesigner(None)

        hierarchy = asyncio.run(designer.design_hierarchy(session_with_decisions))

        assert hierarchy is not None
        assert hierarchy.root_name
        assert len(hierarchy.blocks) >= 1

        # Should have a root block
        root = hierarchy.root_block
        assert root is not None
        assert root.block_type == "root"

    def test_design_hierarchy_with_llm(self, session_with_decisions, mock_llm):
        """Test LLM-based hierarchy design."""
        mock_llm.responses = [
            # Component extraction response
            """{
                "components": [
                    {"name": "api-gateway", "description": "API", "category": "api", "dependencies": []},
                    {"name": "core-service", "description": "Core", "category": "service", "dependencies": ["api-gateway"]}
                ]
            }""",
            # Hierarchy design response
            """{
                "root_name": "test-system",
                "blocks": [
                    {"path": "test-system", "name": "Test System", "block_type": "root", "description": "Root", "parent_path": null, "tech_stack": "Python", "dependencies": [], "api_endpoints": []},
                    {"path": "test-system/api-gateway", "name": "API Gateway", "block_type": "component", "description": "API", "parent_path": "test-system", "tech_stack": "Python", "dependencies": [], "api_endpoints": [{"method": "GET", "path": "/health"}]}
                ],
                "cross_block_rules": []
            }""",
        ]

        designer = BlockDesigner(mock_llm)

        hierarchy = asyncio.run(designer.design_hierarchy(session_with_decisions))

        assert hierarchy.root_name == "test-system"
        assert len(hierarchy.blocks) == 2

    def test_design_hierarchy_fallback_on_error(self, session_with_decisions, mock_llm):
        """Test fallback to rule-based on LLM error."""
        mock_llm.responses = ["invalid json"]

        designer = BlockDesigner(mock_llm)

        # Should not raise, should fallback
        hierarchy = asyncio.run(designer.design_hierarchy(session_with_decisions))

        assert hierarchy is not None
        assert len(hierarchy.blocks) >= 1

    def test_extract_components_from_rules(self, session_with_decisions):
        """Test rule-based component extraction."""
        designer = BlockDesigner(None)

        components = designer._extract_components_from_rules(
            session_with_decisions.decisions
        )

        assert len(components) >= 1
        assert all(isinstance(c, ComponentInfo) for c in components)

    def test_extract_components_with_api_decision(self, session_with_decisions):
        """Test component extraction with API decision."""
        # Add API decision
        api_decision = Decision(
            id="dec-api",
            topic="API Design",
            question="What API style?",
            options=[Option("api-rest", "REST", "RESTful API")],
            selected_option_id="api-rest",
        )
        session_with_decisions.decisions.append(api_decision)

        designer = BlockDesigner(None)
        components = designer._extract_components_from_rules(
            session_with_decisions.decisions
        )

        # Should include API gateway
        api_components = [c for c in components if "api" in c.name.lower()]
        assert len(api_components) >= 1

    def test_extract_components_microservices(self, session_with_decisions):
        """Test component extraction for microservices architecture."""
        # Update architecture decision to microservices
        for d in session_with_decisions.decisions:
            if d.topic == "Architecture":
                d.selected_option_id = "arch-microservices"
                d.options = [
                    Option("arch-microservices", "Microservices", "Distributed")
                ]

        designer = BlockDesigner(None)
        components = designer._extract_components_from_rules(
            session_with_decisions.decisions
        )

        # Should have multiple services
        assert len(components) >= 2

    def test_assign_block_types(self):
        """Test block type assignment."""
        components = [
            ComponentInfo(name="api", category="api"),
            ComponentInfo(name="service", category="service"),
            ComponentInfo(name="worker", category="worker"),
            ComponentInfo(name="lib", category="library"),
        ]

        designer = BlockDesigner(None)
        block_types = designer._assign_block_types(components)

        assert block_types["api"] == "component"
        assert block_types["service"] == "component"
        assert block_types["worker"] == "module"
        assert block_types["lib"] == "leaf"

    def test_build_dependency_graph(self):
        """Test dependency graph building."""
        components = [
            ComponentInfo(name="api", dependencies=[]),
            ComponentInfo(name="service", dependencies=["api"]),
            ComponentInfo(name="worker", dependencies=["service", "api"]),
        ]

        designer = BlockDesigner(None)
        deps = designer._build_dependency_graph(components)

        assert deps["api"] == []
        assert deps["service"] == ["api"]
        assert deps["worker"] == ["service", "api"]


class TestComponentInfo:
    """Tests for ComponentInfo dataclass."""

    def test_component_info_creation(self):
        """Test basic component info creation."""
        info = ComponentInfo(
            name="api-gateway",
            description="API Gateway",
            category="api",
            dependencies=["core"],
            api_endpoints=[{"method": "GET", "path": "/health"}],
        )

        assert info.name == "api-gateway"
        assert info.category == "api"
        assert len(info.dependencies) == 1
        assert len(info.api_endpoints) == 1

    def test_component_info_defaults(self):
        """Test component info default values."""
        info = ComponentInfo(name="test")

        assert info.description == ""
        assert info.category == ""
        assert info.dependencies == []
        assert info.api_endpoints == []
