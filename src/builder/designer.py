"""Block hierarchy designer for Spec Builder Mode.

The BlockDesigner takes decisions from the discussion phase and designs
a hierarchical block structure for the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.builder.session import (
    BuilderSession,
    Decision,
    BlockDesign,
    HierarchyDesign,
)
from src.llm.client import LLMClient


@dataclass
class ComponentInfo:
    """Information about a component extracted from decisions."""

    name: str
    description: str = ""
    category: str = ""  # api, service, data, integration, etc.
    dependencies: list[str] = field(default_factory=list)
    api_endpoints: list[dict[str, Any]] = field(default_factory=list)


# Prompts for hierarchy design
SYSTEM_PROMPT_DESIGN = """You are a software architect designing a system hierarchy.

Based on the design decisions provided, create a hierarchical block structure.

Rules:
1. There should be exactly one ROOT block
2. ROOT contains COMPONENT blocks (major features/services)
3. COMPONENT can contain MODULE blocks (sub-features)
4. MODULE can contain LEAF blocks (implementation units)
5. Each block has dependencies on other blocks

Respond in JSON format:
{{
    "root_name": "system-name",
    "blocks": [
        {{
            "path": "system-name",
            "name": "System Name",
            "block_type": "root",
            "description": "Root block description",
            "parent_path": null,
            "tech_stack": "Python, FastAPI",
            "dependencies": [],
            "api_endpoints": []
        }},
        {{
            "path": "system-name/api-gateway",
            "name": "API Gateway",
            "block_type": "component",
            "description": "Handles all API requests",
            "parent_path": "system-name",
            "tech_stack": "Python, FastAPI",
            "dependencies": [],
            "api_endpoints": [
                {{"method": "GET", "path": "/health", "description": "Health check"}}
            ]
        }}
    ],
    "cross_block_rules": [
        {{"rule": "All API calls must go through gateway", "blocks": ["api-gateway"]}}
    ]
}}
"""

SYSTEM_PROMPT_COMPONENTS = """You are analyzing design decisions to extract system components.

Given the decisions about architecture, tech stack, and features, identify the
main components that should be built.

For each component, specify:
- name: slug-case name
- description: what it does
- category: api, service, data, integration, worker, library
- dependencies: other components it depends on
- api_endpoints: if it exposes APIs

Respond in JSON format:
{{
    "components": [
        {{
            "name": "component-name",
            "description": "Description",
            "category": "api",
            "dependencies": [],
            "api_endpoints": [{{"method": "GET", "path": "/endpoint"}}]
        }}
    ]
}}
"""


class BlockDesigner:
    """Designs block hierarchies from discussion decisions.

    Takes the decisions made during the discussion phase and creates
    a hierarchical block structure that can be used to generate specs.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize the designer.

        Args:
            llm_client: LLM client for generating designs.
        """
        self.llm_client = llm_client

    async def design_hierarchy(self, session: BuilderSession) -> HierarchyDesign:
        """Design the complete block hierarchy from session decisions.

        Args:
            session: The builder session with decisions.

        Returns:
            HierarchyDesign with all blocks.
        """
        if not self.llm_client:
            # Fallback to rule-based design
            return self._design_from_rules(session)

        try:
            # Extract components from decisions
            components = await self._extract_components(session.decisions)

            # Assign block types
            block_types = self._assign_block_types(components)

            # Build dependency graph
            dependencies = self._build_dependency_graph(components)

            # Generate hierarchy using LLM
            decisions_text = self._format_decisions(session)

            user_prompt = f"""
Design a block hierarchy for: {session.name}

Description: {session.initial_description}

Design decisions:
{decisions_text}

Extracted components:
{self._format_components(components)}
"""

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_DESIGN,
                user_prompt=user_prompt,
                temperature=0.3,
            )

            import json

            data = json.loads(response.content)

            return HierarchyDesign(
                root_name=data["root_name"],
                blocks=[BlockDesign.from_dict(b) for b in data.get("blocks", [])],
                cross_block_rules=data.get("cross_block_rules", []),
            )

        except Exception as e:
            # Fallback to rule-based design
            print(f"LLM design failed: {e}, falling back to rule-based design")
            return self._design_from_rules(session)

    async def _extract_components(
        self, decisions: list[Decision]
    ) -> list[ComponentInfo]:
        """Extract components from architecture decisions.

        Args:
            decisions: List of decisions from discussion.

        Returns:
            List of extracted components.
        """
        if not self.llm_client:
            return self._extract_components_from_rules(decisions)

        try:
            decisions_text = "\n".join(
                f"- {d.topic}: {d.selected_option.label if d.selected_option else 'Custom: ' + d.user_notes}"
                for d in decisions
                if d.is_decided
            )

            user_prompt = f"""
Extract system components from these design decisions:
{decisions_text}
"""

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_COMPONENTS,
                user_prompt=user_prompt,
                temperature=0.2,
            )

            import json

            data = json.loads(response.content)

            return [
                ComponentInfo(
                    name=c["name"],
                    description=c.get("description", ""),
                    category=c.get("category", ""),
                    dependencies=c.get("dependencies", []),
                    api_endpoints=c.get("api_endpoints", []),
                )
                for c in data.get("components", [])
            ]

        except Exception:
            return self._extract_components_from_rules(decisions)

    def _extract_components_from_rules(
        self, decisions: list[Decision]
    ) -> list[ComponentInfo]:
        """Extract components using rule-based logic."""
        components = []

        # Get architecture decision
        arch_decision = next(
            (d for d in decisions if d.topic == "Architecture" and d.is_decided), None
        )

        # Get API decision
        api_decision = next(
            (d for d in decisions if d.topic == "API Design" and d.is_decided), None
        )

        # Basic components based on decisions
        if api_decision:
            api_opt = api_decision.selected_option
            if api_opt:
                components.append(
                    ComponentInfo(
                        name="api-gateway",
                        description="API Gateway handling all external requests",
                        category="api",
                        api_endpoints=[
                            {"method": "GET", "path": "/health"},
                            {"method": "GET", "path": "/api/v1/status"},
                        ],
                    )
                )

        # Core service based on architecture
        if arch_decision:
            arch_opt = arch_decision.selected_option
            if arch_opt and "microservice" in arch_opt.id.lower():
                # Multiple services
                components.extend(
                    [
                        ComponentInfo(
                            name="core-service",
                            description="Core business logic service",
                            category="service",
                        ),
                        ComponentInfo(
                            name="data-service",
                            description="Data access service",
                            category="data",
                        ),
                    ]
                )
            else:
                # Monolith - single service
                components.append(
                    ComponentInfo(
                        name="core-service",
                        description="Main application service",
                        category="service",
                    )
                )

        # Data layer
        data_decision = next(
            (d for d in decisions if d.topic == "Data Model" and d.is_decided), None
        )
        if data_decision:
            components.append(
                ComponentInfo(
                    name="database",
                    description="Database layer",
                    category="data",
                )
            )

        # Ensure at least one component
        if not components:
            components.append(
                ComponentInfo(
                    name="main-service",
                    description="Main application",
                    category="service",
                )
            )

        return components

    def _assign_block_types(
        self, components: list[ComponentInfo]
    ) -> dict[str, str]:
        """Assign block types (root/component/module/leaf) to components.

        Args:
            components: List of components.

        Returns:
            Dict mapping component name to block type.
        """
        block_types = {}

        # Categories that are typically components vs modules
        component_categories = {"api", "service", "integration"}
        module_categories = {"worker", "data"}
        leaf_categories = {"library", "util"}

        for comp in components:
            if comp.category in component_categories:
                block_types[comp.name] = "component"
            elif comp.category in module_categories:
                block_types[comp.name] = "module"
            elif comp.category in leaf_categories:
                block_types[comp.name] = "leaf"
            else:
                # Default based on dependencies
                if comp.dependencies:
                    block_types[comp.name] = "module"
                else:
                    block_types[comp.name] = "component"

        return block_types

    def _build_dependency_graph(
        self, components: list[ComponentInfo]
    ) -> dict[str, list[str]]:
        """Build inter-block dependency graph.

        Args:
            components: List of components.

        Returns:
            Dict mapping component name to list of dependencies.
        """
        return {comp.name: comp.dependencies for comp in components}

    def _design_from_rules(self, session: BuilderSession) -> HierarchyDesign:
        """Design hierarchy using rule-based logic (fallback).

        Args:
            session: The builder session.

        Returns:
            HierarchyDesign created from rules.
        """
        root_name = session.name.lower().replace(" ", "-")

        # Get tech stack from decisions
        tech_stack = ""
        tech_decision = next(
            (
                d
                for d in session.decisions
                if d.topic == "Tech Stack" and d.is_decided
            ),
            None,
        )
        if tech_decision and tech_decision.selected_option:
            tech_stack = tech_decision.selected_option.label

        blocks = []

        # Create root block
        root = BlockDesign(
            path=root_name,
            name=session.name,
            block_type="root",
            description=session.initial_description,
            parent_path=None,
            tech_stack=tech_stack,
        )
        blocks.append(root)

        # Extract components and create blocks
        components = self._extract_components_from_rules(session.decisions)

        for comp in components:
            block = BlockDesign(
                path=f"{root_name}/{comp.name}",
                name=comp.name.replace("-", " ").title(),
                block_type="component",
                description=comp.description,
                parent_path=root_name,
                tech_stack=tech_stack,
                dependencies=comp.dependencies,
                api_endpoints=comp.api_endpoints,
            )
            blocks.append(block)

        return HierarchyDesign(
            root_name=root_name,
            blocks=blocks,
            cross_block_rules=[],
        )

    def _format_decisions(self, session: BuilderSession) -> str:
        """Format decisions for LLM prompt."""
        lines = []
        for d in session.decisions:
            if d.is_decided:
                opt = d.selected_option
                if opt:
                    lines.append(f"- {d.topic}: {opt.label} - {opt.description}")
                else:
                    lines.append(f"- {d.topic}: {d.user_notes}")
        return "\n".join(lines) if lines else "No decisions yet."

    def _format_components(self, components: list[ComponentInfo]) -> str:
        """Format components for LLM prompt."""
        lines = []
        for c in components:
            lines.append(
                f"- {c.name} ({c.category}): {c.description}"
                + (f" [depends on: {', '.join(c.dependencies)}]" if c.dependencies else "")
            )
        return "\n".join(lines) if lines else "No components identified."
