"""Research agent for validating technology choices and fetching documentation.

The ResearchAgent performs research on technology choices to help users
make informed decisions during the discussion phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.builder.session import ResearchDepth
from src.llm.client import LLMClient


class ResearchStatus(Enum):
    """Status of a research request."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ResearchResult:
    """Result of technology research."""

    technology: str
    summary: str = ""
    documentation_snippets: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    best_practices: list[str] = field(default_factory=list)
    related_technologies: list[str] = field(default_factory=list)
    recommendation: str = ""
    confidence: float = 0.0  # 0-1 confidence in recommendation
    status: ResearchStatus = ResearchStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "technology": self.technology,
            "summary": self.summary,
            "documentation_snippets": self.documentation_snippets,
            "known_issues": self.known_issues,
            "best_practices": self.best_practices,
            "related_technologies": self.related_technologies,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "status": self.status.value,
        }


@dataclass
class ValidationResult:
    """Result of compatibility validation."""

    is_compatible: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_compatible": self.is_compatible,
            "warnings": self.warnings,
            "errors": self.errors,
            "suggestions": self.suggestions,
        }


# Prompts for research
SYSTEM_PROMPT_RESEARCH = """You are a technology research assistant helping a developer
choose the right technologies for their project.

Given a technology choice and the project context, provide:
1. A brief summary of the technology
2. Relevant documentation points
3. Known issues or gotchas
4. Best practices for this use case
5. Related technologies to consider
6. Your recommendation

Respond in JSON format:
{{
    "summary": "Brief overview of the technology",
    "documentation_snippets": ["Key point 1", "Key point 2"],
    "known_issues": ["Issue 1", "Issue 2"],
    "best_practices": ["Practice 1", "Practice 2"],
    "related_technologies": ["Related tech 1"],
    "recommendation": "Your recommendation for this use case",
    "confidence": 0.8
}}
"""

SYSTEM_PROMPT_COMPATIBILITY = """You are validating technology compatibility.

Given a list of technology choices, determine if they work well together.
Consider version compatibility, ecosystem fit, and architectural patterns.

Respond in JSON format:
{{
    "is_compatible": true,
    "warnings": ["Potential issue 1"],
    "errors": ["Critical incompatibility 1"],
    "suggestions": ["Consider doing X instead"]
}}
"""


class ResearchAgent:
    """Agent for researching technology choices.

    Performs research based on the configured depth:
    - LIGHT: Quick validation only
    - MEDIUM: Fetch key documentation
    - DEEP: Comprehensive research
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        depth: ResearchDepth = ResearchDepth.MEDIUM,
    ):
        """Initialize the research agent.

        Args:
            llm_client: LLM client for generating research.
            depth: Depth of research to perform.
        """
        self.llm_client = llm_client
        self.depth = depth
        self._cache: dict[str, ResearchResult] = {}

    async def research_technology(
        self, tech: str, context: str = ""
    ) -> ResearchResult:
        """Research a technology choice.

        Args:
            tech: Technology name to research.
            context: Project context for relevant research.

        Returns:
            ResearchResult with findings.
        """
        # Check cache
        cache_key = f"{tech}:{context[:50]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.llm_client:
            # Return basic result without LLM
            result = ResearchResult(
                technology=tech,
                summary=f"Research for {tech} (LLM not available)",
                status=ResearchStatus.COMPLETED,
            )
            return result

        try:
            user_prompt = self._build_research_prompt(tech, context)

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_RESEARCH,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=self._get_max_tokens(),
            )

            import json

            data = json.loads(response.content)

            result = ResearchResult(
                technology=tech,
                summary=data.get("summary", ""),
                documentation_snippets=data.get("documentation_snippets", []),
                known_issues=data.get("known_issues", []),
                best_practices=data.get("best_practices", []),
                related_technologies=data.get("related_technologies", []),
                recommendation=data.get("recommendation", ""),
                confidence=data.get("confidence", 0.5),
                status=ResearchStatus.COMPLETED,
            )

            # Cache result
            self._cache[cache_key] = result
            return result

        except Exception as e:
            return ResearchResult(
                technology=tech,
                summary=f"Research failed: {str(e)}",
                status=ResearchStatus.FAILED,
            )

    async def validate_compatibility(
        self, choices: list[str], context: str = ""
    ) -> ValidationResult:
        """Validate that technology choices work together.

        Args:
            choices: List of technology names.
            context: Project context.

        Returns:
            ValidationResult with compatibility assessment.
        """
        if not self.llm_client:
            # Without LLM, assume compatible
            return ValidationResult(
                is_compatible=True,
                warnings=["Compatibility not validated (LLM not available)"],
            )

        try:
            user_prompt = f"""
Validate compatibility of these technology choices:
{', '.join(choices)}

Project context: {context}
"""

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT_COMPATIBILITY,
                user_prompt=user_prompt,
                temperature=0.2,
            )

            import json

            data = json.loads(response.content)

            return ValidationResult(
                is_compatible=data.get("is_compatible", True),
                warnings=data.get("warnings", []),
                errors=data.get("errors", []),
                suggestions=data.get("suggestions", []),
            )

        except Exception as e:
            return ValidationResult(
                is_compatible=True,
                warnings=[f"Compatibility check failed: {str(e)}"],
            )

    async def fetch_documentation(
        self, tech: str, topics: list[str]
    ) -> list[str]:
        """Fetch relevant documentation snippets.

        Args:
            tech: Technology name.
            topics: Specific topics to research.

        Returns:
            List of documentation snippets.
        """
        if self.depth == ResearchDepth.LIGHT:
            return []

        if not self.llm_client:
            return []

        try:
            user_prompt = f"""
Find documentation snippets for {tech} about:
{', '.join(topics)}

Return as JSON array of strings.
"""

            response = self.llm_client.generate(
                system_prompt="You are a documentation assistant. Return relevant documentation snippets as a JSON array of strings.",
                user_prompt=user_prompt,
                temperature=0.1,
            )

            import json

            return json.loads(response.content)

        except Exception:
            return []

    def _build_research_prompt(self, tech: str, context: str) -> str:
        """Build the research prompt based on depth."""
        base = f"Research the technology: {tech}"

        if context:
            base += f"\n\nProject context: {context}"

        depth_instructions = {
            ResearchDepth.LIGHT: "\n\nProvide a brief overview only.",
            ResearchDepth.MEDIUM: "\n\nProvide moderate detail with key documentation points.",
            ResearchDepth.DEEP: "\n\nProvide comprehensive analysis including edge cases and advanced patterns.",
        }

        return base + depth_instructions.get(self.depth, "")

    def _get_max_tokens(self) -> int:
        """Get max tokens based on research depth."""
        return {
            ResearchDepth.LIGHT: 512,
            ResearchDepth.MEDIUM: 1024,
            ResearchDepth.DEEP: 2048,
        }.get(self.depth, 1024)

    def clear_cache(self) -> None:
        """Clear the research cache."""
        self._cache.clear()
