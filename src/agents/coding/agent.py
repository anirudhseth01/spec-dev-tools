"""CodingAgent with skeleton-first generation approach."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from src.agents.coding.plugins import PluginRegistry, LanguagePlugin
from src.agents.coding.context_builder import ContextBuilder, CodeContext
from src.agents.coding.ambiguity import AmbiguityResolver, Ambiguity, Resolution
from src.llm.client import LLMClient


@dataclass
class GenerationState:
    """Tracks state across generation phases."""

    skeleton_files: dict[str, str] = field(default_factory=dict)
    implementation_files: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    questions_pending: list[dict] = field(default_factory=list)
    questions_answered: dict[str, str] = field(default_factory=dict)


class CodingAgent(BaseAgent):
    """Generates code from specifications using skeleton-first approach.

    Flow:
    1. Build context (full relevant files)
    2. Generate skeletons (interfaces, types, signatures)
    3. Resolve ambiguities (ask critical, assume minor)
    4. Fill implementations
    5. Validate and return

    Design Decisions:
    - Skeleton-first: Generate interfaces → fill implementations
    - Full context: Give agent complete context of related code
    - Hybrid ambiguity: Ask critical questions, assume minor ones
    - Single agent + plugins: Language-agnostic with plugin support
    """

    name = "coding_agent"

    def __init__(
        self,
        llm_client: LLMClient,
        plugin_registry: Optional[PluginRegistry] = None,
        max_context_tokens: int = 70000,
        dry_run: bool = False,
    ):
        """Initialize CodingAgent.

        Args:
            llm_client: LLM client for generation.
            plugin_registry: Language plugin registry.
            max_context_tokens: Max tokens for code context.
            dry_run: If True, don't write files.
        """
        self.llm = llm_client
        self.plugins = plugin_registry or PluginRegistry()
        self.context_builder = ContextBuilder(max_tokens=max_context_tokens)
        self.ambiguity_resolver = AmbiguityResolver()
        self.dry_run = dry_run
        self.state = GenerationState()

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute code generation."""
        try:
            # Reset state
            self.state = GenerationState()

            # Detect or get language
            language = self._get_language(context)
            plugin = self.plugins.get(language)

            # Get routed spec sections (from parent context if available)
            spec_context = self._get_spec_context(context)

            # Phase 1: Generate skeletons
            skeletons = self._generate_skeletons(plugin, spec_context, context)
            self.state.skeleton_files = skeletons

            if not skeletons:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message="No skeleton files generated",
                    errors=["LLM did not generate any valid code files"],
                )

            # Phase 2: Check for ambiguities
            ambiguities = self.ambiguity_resolver.detect_ambiguities(spec_context)
            for ambiguity in ambiguities:
                resolution = self.ambiguity_resolver.resolve(ambiguity)
                if resolution.action == "ask":
                    self.state.questions_pending.append({
                        "question": resolution.question,
                        "options": resolution.options,
                        "category": ambiguity.category.value,
                    })
                else:
                    self.state.assumptions.append(resolution.documentation)

            # If we have critical questions, return early with questions
            if self.state.questions_pending:
                return AgentResult(
                    status=AgentStatus.PENDING,
                    message=f"Need answers to {len(self.state.questions_pending)} questions",
                    data={
                        "questions": self.state.questions_pending,
                        "skeleton_preview": skeletons,
                        "assumptions": self.state.assumptions,
                    },
                )

            # Phase 3: Build full context
            target_files = [
                context.project_root / f for f in skeletons.keys()
            ]
            code_context = self.context_builder.build_context(
                project_root=context.project_root,
                target_files=target_files,
                spec_context=spec_context,
            )

            # Phase 4: Generate implementations
            implementations = self._fill_implementations(
                plugin=plugin,
                skeletons=skeletons,
                spec_context=spec_context,
                code_context=code_context,
            )
            self.state.implementation_files = implementations

            # Phase 5: Validate syntax
            all_errors = []
            for filepath, code in implementations.items():
                syntax_errors = plugin.validate_syntax(code)
                for err in syntax_errors:
                    all_errors.append(f"{filepath}: {err}")

            if all_errors:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message=f"Syntax validation failed: {len(all_errors)} errors",
                    errors=all_errors,
                    data={
                        "implementations": implementations,
                        "assumptions": self.state.assumptions,
                    },
                )

            # Write files (unless dry run)
            files_created = []
            if not self.dry_run:
                for filepath, code in implementations.items():
                    full_path = context.project_root / filepath
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(code)
                    files_created.append(filepath)

            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=f"Generated {len(files_created)} files",
                data={
                    "code": implementations,
                    "files_created": files_created,
                    "skeletons": skeletons,
                    "assumptions": self.state.assumptions,
                    "language": language,
                },
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=str(e),
                errors=[str(e)],
            )

    def _get_language(self, context: AgentContext) -> str:
        """Determine target language."""
        # From spec metadata
        if context.spec and context.spec.metadata:
            tech_stack = context.spec.metadata.tech_stack
            if tech_stack:
                detected = self.plugins.detect_from_spec(tech_stack)
                if detected:
                    return detected

        # Auto-detect from project
        return self.plugins.detect_language(context.project_root)

    def _get_spec_context(self, context: AgentContext) -> str:
        """Get spec context for prompts."""
        # Check for routed spec in parent context
        if "routed_spec" in context.parent_context:
            routed = context.parent_context["routed_spec"]
            if hasattr(routed, "to_prompt_context"):
                return routed.to_prompt_context()

        # Fallback to full spec
        if context.spec:
            return self._spec_to_context(context.spec)

        return ""

    def _spec_to_context(self, spec: Any) -> str:
        """Convert spec to prompt context."""
        lines = []

        # Name is on Spec, not Metadata
        if hasattr(spec, "name") and spec.name:
            lines.append(f"# {spec.name}")

        if hasattr(spec, "overview") and spec.overview:
            lines.append("## Overview")
            if spec.overview.summary:
                lines.append(f"Summary: {spec.overview.summary}")
            if spec.overview.goals:
                lines.append("Goals:")
                for goal in spec.overview.goals:
                    lines.append(f"  - {goal}")
            if spec.overview.background:
                lines.append(f"Background: {spec.overview.background}")
            lines.append("")

        if hasattr(spec, "inputs") and spec.inputs:
            lines.append("## Inputs")
            for inp in spec.inputs.user_inputs:
                lines.append(f"- {inp.name}: {inp.type} - {inp.description}")
            for inp in spec.inputs.system_inputs:
                lines.append(f"- {inp.name}: {inp.type} - {inp.description}")
            lines.append("")

        if hasattr(spec, "outputs") and spec.outputs:
            lines.append("## Outputs")
            for out in spec.outputs.return_values:
                lines.append(f"- {out}")
            for effect in spec.outputs.side_effects:
                lines.append(f"- Side effect: {effect}")
            lines.append("")

        if hasattr(spec, "api_contract") and spec.api_contract:
            lines.append("## API Contract")
            for endpoint in spec.api_contract.endpoints:
                lines.append(f"- {endpoint.method} {endpoint.path}")
                if endpoint.description:
                    lines.append(f"  {endpoint.description}")
            lines.append("")

        return "\n".join(lines)

    def _generate_skeletons(
        self,
        plugin: LanguagePlugin,
        spec_context: str,
        context: AgentContext,
    ) -> dict[str, str]:
        """Generate code skeletons using LLM."""
        prompt = plugin.generate_skeleton_prompt(spec_context)
        system_prompt = plugin.get_skeleton_system_prompt()

        response = self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=prompt,
        )

        return plugin.parse_generated_code(response.content)

    def _fill_implementations(
        self,
        plugin: LanguagePlugin,
        skeletons: dict[str, str],
        spec_context: str,
        code_context: CodeContext,
    ) -> dict[str, str]:
        """Fill skeleton implementations using LLM."""
        implementations = {}

        # Combine all skeletons for context
        all_skeleton_content = "\n\n".join([
            f"# {filepath}\n{content}"
            for filepath, content in skeletons.items()
        ])

        # Add assumptions as context
        assumptions_text = ""
        if self.state.assumptions:
            assumptions_text = "\n## Assumptions Made\n" + "\n".join(self.state.assumptions)

        prompt = plugin.generate_implementation_prompt(
            skeleton=all_skeleton_content,
            spec_context=spec_context + assumptions_text,
            code_context=code_context.to_prompt(),
        )
        system_prompt = plugin.get_implementation_system_prompt()

        response = self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=prompt,
        )

        implementations = plugin.parse_generated_code(response.content)

        # Merge with skeletons (implementation may not regenerate all files)
        for filepath in skeletons:
            if filepath not in implementations:
                implementations[filepath] = skeletons[filepath]

        return implementations

    def continue_with_answers(
        self,
        context: AgentContext,
        answers: dict[str, str],
    ) -> AgentResult:
        """Continue generation after receiving answers to questions.

        Args:
            context: Agent context.
            answers: Dict mapping question text to chosen answer.

        Returns:
            AgentResult from continued generation.
        """
        self.state.questions_answered = answers
        self.state.questions_pending = []

        # Add answers as context
        for question, answer in answers.items():
            self.state.assumptions.append(
                f"# USER DECISION: {question}\n# Answer: {answer}"
            )

        # Continue with implementation phase
        return self.execute(context)
