"""Routes spec sections to appropriate agents based on their needs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.spec.schemas import Spec


@dataclass
class AgentSections:
    """Defines which spec sections an agent needs."""

    agent_name: str
    required_sections: list[str] = field(default_factory=list)
    optional_sections: list[str] = field(default_factory=list)


# Default section requirements for each agent type
AGENT_SECTION_MAP: dict[str, AgentSections] = {
    "coding_agent": AgentSections(
        agent_name="coding_agent",
        required_sections=["overview", "inputs", "outputs", "api_contract", "dependencies"],
        optional_sections=["implementation", "error_handling"],
    ),
    "test_generator_agent": AgentSections(
        agent_name="test_generator_agent",
        required_sections=["test_cases", "edge_cases", "inputs", "outputs"],
        optional_sections=["api_contract", "error_handling"],
    ),
    "security_agent": AgentSections(
        agent_name="security_agent",
        required_sections=["security", "api_contract"],
        optional_sections=["inputs", "outputs", "dependencies"],
    ),
    "performance_agent": AgentSections(
        agent_name="performance_agent",
        required_sections=["performance", "api_contract"],
        optional_sections=["dependencies", "implementation"],
    ),
    "code_review_agent": AgentSections(
        agent_name="code_review_agent",
        required_sections=["overview", "api_contract", "security", "error_handling"],
        optional_sections=["performance", "implementation"],
    ),
    "linter_agent": AgentSections(
        agent_name="linter_agent",
        required_sections=["metadata"],
        optional_sections=[],
    ),
    "architecture_agent": AgentSections(
        agent_name="architecture_agent",
        required_sections=["overview", "dependencies", "api_contract"],
        optional_sections=["implementation"],
    ),
}


@dataclass
class RoutedSpec:
    """A spec filtered to only include relevant sections for an agent."""

    agent_name: str
    sections: dict[str, Any]
    token_estimate: int = 0

    def to_prompt_context(self) -> str:
        """Convert to a formatted string for LLM context."""
        lines = [f"# Relevant Spec Sections for {self.agent_name}\n"]

        for section_name, content in self.sections.items():
            lines.append(f"## {section_name.replace('_', ' ').title()}")
            lines.append(self._format_section(content))
            lines.append("")

        return "\n".join(lines)

    def _format_section(self, content: Any) -> str:
        """Format a section's content for display."""
        if content is None:
            return "(empty)"
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(f"- {item}" for item in content)
        if hasattr(content, "to_dict"):
            return str(content.to_dict())
        return str(content)


class SectionRouter:
    """Routes spec sections to agents based on their requirements.

    This reduces context size by only giving agents the sections they need,
    rather than the entire spec.
    """

    def __init__(self, custom_mappings: dict[str, AgentSections] | None = None):
        """Initialize router with optional custom mappings.

        Args:
            custom_mappings: Override default agent-to-section mappings.
        """
        self.mappings = {**AGENT_SECTION_MAP}
        if custom_mappings:
            self.mappings.update(custom_mappings)

    def route(
        self,
        spec: Spec,
        agent_name: str,
        include_optional: bool = True,
        max_tokens: int | None = None,
    ) -> RoutedSpec:
        """Extract relevant sections for a specific agent.

        Args:
            spec: The full specification.
            agent_name: Name of the agent to route to.
            include_optional: Whether to include optional sections.
            max_tokens: Maximum estimated tokens (truncates if exceeded).

        Returns:
            RoutedSpec with only relevant sections.
        """
        agent_sections = self.mappings.get(agent_name)

        if agent_sections is None:
            # Unknown agent gets everything
            return self._route_all(spec, agent_name)

        sections_to_include = list(agent_sections.required_sections)
        if include_optional:
            sections_to_include.extend(agent_sections.optional_sections)

        return self._extract_sections(spec, agent_name, sections_to_include, max_tokens)

    def _route_all(self, spec: Spec, agent_name: str) -> RoutedSpec:
        """Route all sections to an agent."""
        all_sections = [
            "metadata", "overview", "inputs", "outputs", "dependencies",
            "api_contract", "test_cases", "edge_cases", "error_handling",
            "performance", "security", "implementation", "acceptance",
        ]
        return self._extract_sections(spec, agent_name, all_sections, None)

    def _extract_sections(
        self,
        spec: Spec,
        agent_name: str,
        section_names: list[str],
        max_tokens: int | None,
    ) -> RoutedSpec:
        """Extract specific sections from a spec."""
        sections: dict[str, Any] = {}

        section_attr_map = {
            "metadata": spec.metadata,
            "overview": spec.overview,
            "inputs": spec.inputs,
            "outputs": spec.outputs,
            "dependencies": spec.dependencies,
            "api_contract": spec.api_contract,
            "test_cases": spec.test_cases,
            "edge_cases": spec.edge_cases,
            "error_handling": spec.error_handling,
            "performance": spec.performance,
            "security": spec.security,
            "implementation": spec.implementation,
            "acceptance": spec.acceptance,
        }

        total_tokens = 0

        for section_name in section_names:
            if section_name in section_attr_map:
                content = section_attr_map[section_name]
                section_tokens = self._estimate_tokens(content)

                # Check token limit
                if max_tokens and total_tokens + section_tokens > max_tokens:
                    # Try to include a summary instead
                    sections[section_name] = self._summarize_section(content)
                    total_tokens += 50  # Estimate for summary
                else:
                    sections[section_name] = content
                    total_tokens += section_tokens

        return RoutedSpec(
            agent_name=agent_name,
            sections=sections,
            token_estimate=total_tokens,
        )

    def _estimate_tokens(self, content: Any) -> int:
        """Rough token estimate (4 chars = 1 token)."""
        if content is None:
            return 0
        text = str(content)
        return len(text) // 4

    def _summarize_section(self, content: Any) -> str:
        """Create a brief summary when full content is too large."""
        if content is None:
            return "(empty)"

        text = str(content)
        if len(text) <= 200:
            return text

        return text[:200] + f"... (truncated, {len(text)} chars total)"

    def get_required_sections(self, agent_name: str) -> list[str]:
        """Get list of required sections for an agent."""
        agent_sections = self.mappings.get(agent_name)
        if agent_sections:
            return list(agent_sections.required_sections)
        return []

    def register_agent(self, agent_sections: AgentSections) -> None:
        """Register a new agent's section requirements."""
        self.mappings[agent_sections.agent_name] = agent_sections
