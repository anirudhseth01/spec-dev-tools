"""Discussion engine for interactive Q&A during spec building.

The DiscussionEngine manages the conversational flow of gathering requirements
and making design decisions through the nine discussion topics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.builder.session import (
    BuilderSession,
    Decision,
    Option,
    SessionPhase,
    DISCUSSION_TOPICS,
)
from src.llm.client import LLMClient


class DiscussionAction(Enum):
    """Action to take after processing a response."""

    CONTINUE = "continue"  # Continue with more questions on same topic
    NEXT_TOPIC = "next_topic"  # Move to next topic
    COMPLETE = "complete"  # Discussion is complete
    CLARIFY = "clarify"  # Need clarification on answer
    ANALYZE_REPO = "analyze_repo"  # Analyzing a reference repository


@dataclass
class DiscussionResult:
    """Result of processing a user response."""

    action: DiscussionAction
    message: str  # Message to display to user
    question: str | None = None  # Next question if any
    options: list[Option] = field(default_factory=list)  # Options if any
    decision: Decision | None = None  # Recorded decision if any
    needs_research: bool = False  # Whether to trigger research
    repo_analysis: dict | None = None  # RepoAnalysis dict if analyzing a repo


# Prompts for discussion generation
SYSTEM_PROMPT_QUESTION = """You are a software architect helping design a new system.
You are conducting a requirements gathering session.

Your job is to ask clear, focused questions about the {topic} aspect of the system.
For each question, provide 2-4 concrete options with pros and cons.

Respond in JSON format:
{{
    "question": "The question to ask",
    "context": "Brief context explaining why this matters",
    "options": [
        {{
            "id": "option-1",
            "label": "Short label",
            "description": "Description of this option",
            "pros": ["Pro 1", "Pro 2"],
            "cons": ["Con 1", "Con 2"],
            "recommendation_score": 0.7
        }}
    ],
    "recommended_option": "option-1",
    "recommendation_reason": "Why this is recommended"
}}

Consider the following context about the system:
{context}

Previous decisions made:
{decisions}
"""

SYSTEM_PROMPT_PARSE = """You are parsing a user's response to a design question.

The question was: {question}

Available options were:
{options}

The user responded: {response}

Determine which option they selected, or if they provided a custom answer.
Also extract any additional notes or constraints they mentioned.

Respond in JSON format:
{{
    "selected_option_id": "option-1 or null if custom",
    "custom_answer": "Custom answer text if they didn't select an option",
    "notes": "Any additional notes or constraints mentioned",
    "needs_clarification": false,
    "clarification_reason": "Why clarification is needed if true"
}}
"""


class DiscussionEngine:
    """Manages the discussion flow for gathering requirements.

    The engine guides the user through nine discussion topics:
    1. Problem & Scope
    2. Architecture
    3. Tech Stack (with research)
    4. API Design
    5. Data Model
    6. Security
    7. Performance
    8. Integrations (with research)
    9. Deployment
    """

    def __init__(
        self,
        session: BuilderSession,
        llm_client: LLMClient | None = None,
        research_agent: Any | None = None,  # ResearchAgent, avoiding circular import
    ):
        """Initialize the discussion engine.

        Args:
            session: The builder session to work with.
            llm_client: LLM client for generating questions.
            research_agent: Optional research agent for tech validation.
        """
        self.session = session
        self.llm_client = llm_client
        self.research_agent = research_agent

    async def start_discussion(self) -> str:
        """Start or resume the discussion.

        Returns:
            The first/next question to present.
        """
        if self.session.phase != SessionPhase.DISCUSSION:
            return "Session is not in discussion phase."

        topic = self.session.current_topic
        if not topic:
            return "All discussion topics have been covered."

        # Generate the first question for the current topic
        question, options = await self.generate_question(topic["name"])

        # Create a pending decision for tracking
        decision_id = f"dec-{uuid.uuid4().hex[:8]}"
        decision = Decision(
            id=decision_id,
            topic=topic["name"],
            question=question,
            options=options,
        )
        self.session.add_decision(decision)

        return self._format_question_output(topic["name"], question, options)

    async def process_response(self, response: str) -> DiscussionResult:
        """Process a user's response to a question.

        Args:
            response: The user's response text.

        Returns:
            DiscussionResult with next action and content.
        """
        topic = self.session.current_topic
        if not topic:
            return DiscussionResult(
                action=DiscussionAction.COMPLETE,
                message="All topics have been covered. Ready for design phase.",
            )

        # Find the current pending decision
        current_decision = self._get_current_decision(topic["name"])
        if not current_decision:
            # No pending decision, generate new question
            question, options = await self.generate_question(topic["name"])
            return DiscussionResult(
                action=DiscussionAction.CONTINUE,
                message="Let's continue with this topic.",
                question=question,
                options=options,
            )

        # Parse the user's response
        selected_option, notes, needs_clarification = await self._parse_response(
            current_decision, response
        )

        if needs_clarification:
            return DiscussionResult(
                action=DiscussionAction.CLARIFY,
                message="I need some clarification on your answer.",
                question=current_decision.question,
                options=current_decision.options,
            )

        # Record the decision
        current_decision.selected_option_id = (
            selected_option.id if selected_option else None
        )
        current_decision.user_notes = notes
        current_decision.timestamp = datetime.now()

        # Check if we need research for this topic
        needs_research = topic.get("research_enabled", False) and selected_option

        if needs_research:
            return DiscussionResult(
                action=DiscussionAction.CONTINUE,
                message=f"Noted: {selected_option.label if selected_option else response}",
                decision=current_decision,
                needs_research=True,
            )

        # Move to next topic
        self.session.advance_topic()
        next_topic = self.session.current_topic

        if not next_topic:
            return DiscussionResult(
                action=DiscussionAction.COMPLETE,
                message="All discussion topics have been covered. Ready for design phase.",
                decision=current_decision,
            )

        # Generate next question
        question, options = await self.generate_question(next_topic["name"])

        # Create new decision for next topic
        new_decision = Decision(
            id=f"dec-{uuid.uuid4().hex[:8]}",
            topic=next_topic["name"],
            question=question,
            options=options,
        )
        self.session.add_decision(new_decision)

        return DiscussionResult(
            action=DiscussionAction.NEXT_TOPIC,
            message=f"Moving to {next_topic['name']}.",
            question=question,
            options=options,
            decision=current_decision,
        )

    async def generate_question(self, topic: str) -> tuple[str, list[Option]]:
        """Generate a question with options for a topic.

        Args:
            topic: The topic name.

        Returns:
            Tuple of (question text, list of options).
        """
        if not self.llm_client:
            # Fallback to static questions
            return self._get_static_question(topic)

        # Build context from previous decisions
        context = self._build_context()
        decisions_text = self._format_decisions()

        prompt = SYSTEM_PROMPT_QUESTION.format(
            topic=topic,
            context=context,
            decisions=decisions_text,
        )

        user_prompt = f"Generate a question about {topic} for this system: {self.session.initial_description}"

        try:
            response = self.llm_client.generate(
                system_prompt=prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )

            # Parse JSON response
            import json

            result = json.loads(response.content)

            options = [
                Option(
                    id=opt["id"],
                    label=opt["label"],
                    description=opt["description"],
                    pros=opt.get("pros", []),
                    cons=opt.get("cons", []),
                    recommendation_score=opt.get("recommendation_score", 0.5),
                )
                for opt in result.get("options", [])
            ]

            return result["question"], options

        except Exception:
            # Fallback to static questions on error
            return self._get_static_question(topic)

    async def _parse_response(
        self, decision: Decision, response: str
    ) -> tuple[Option | None, str, bool]:
        """Parse a user's response to find selected option.

        Args:
            decision: The decision being answered.
            response: User's response text.

        Returns:
            Tuple of (selected option, notes, needs clarification).
        """
        # First try simple matching
        response_lower = response.lower().strip()
        for option in decision.options:
            if (
                option.id.lower() == response_lower
                or option.label.lower() == response_lower
                or response_lower.startswith(option.label.lower()[:10])
            ):
                return option, "", False

        # Try number matching (1, 2, 3, etc.)
        try:
            num = int(response_lower)
            if 1 <= num <= len(decision.options):
                return decision.options[num - 1], "", False
        except ValueError:
            pass

        # Check for "option X" pattern
        for i, option in enumerate(decision.options, 1):
            if f"option {i}" in response_lower or f"#{i}" in response_lower:
                return option, response, False

        if not self.llm_client:
            # Without LLM, treat as custom response
            return None, response, False

        # Use LLM to parse complex responses
        try:
            options_text = "\n".join(
                f"- {opt.id}: {opt.label} - {opt.description}"
                for opt in decision.options
            )

            prompt = SYSTEM_PROMPT_PARSE.format(
                question=decision.question,
                options=options_text,
                response=response,
            )

            llm_response = self.llm_client.generate(
                system_prompt=prompt,
                user_prompt="Parse the user's response.",
                temperature=0.1,
            )

            import json

            result = json.loads(llm_response.content)

            if result.get("needs_clarification"):
                return None, "", True

            selected_id = result.get("selected_option_id")
            if selected_id:
                for option in decision.options:
                    if option.id == selected_id:
                        return option, result.get("notes", ""), False

            return None, result.get("custom_answer", response), False

        except Exception:
            # Default to treating as custom response
            return None, response, False

    def _get_current_decision(self, topic: str) -> Decision | None:
        """Get the current pending decision for a topic."""
        for decision in reversed(self.session.decisions):
            if decision.topic == topic and not decision.is_decided:
                return decision
        return None

    def _build_context(self) -> str:
        """Build context string from session."""
        parts = [f"System: {self.session.name}"]
        if self.session.initial_description:
            parts.append(f"Description: {self.session.initial_description}")
        return "\n".join(parts)

    def _format_decisions(self) -> str:
        """Format previous decisions as text."""
        if not self.session.decisions:
            return "No decisions yet."

        lines = []
        for d in self.session.decisions:
            if d.is_decided:
                opt = d.selected_option
                if opt:
                    lines.append(f"- {d.topic}: {opt.label}")
                    if d.user_notes:
                        lines.append(f"  Notes: {d.user_notes}")
        return "\n".join(lines) if lines else "No decisions yet."

    def _format_question_output(
        self, topic: str, question: str, options: list[Option]
    ) -> str:
        """Format question and options for display."""
        lines = [f"\n## {topic}\n", question, "\nOptions:"]
        for i, opt in enumerate(options, 1):
            lines.append(f"\n{i}. **{opt.label}**")
            lines.append(f"   {opt.description}")
            if opt.pros:
                lines.append(f"   + {', '.join(opt.pros)}")
            if opt.cons:
                lines.append(f"   - {', '.join(opt.cons)}")
        return "\n".join(lines)

    def _get_static_question(self, topic: str) -> tuple[str, list[Option]]:
        """Get static fallback questions for a topic."""
        static_questions = {
            "Problem & Scope": (
                "What is the primary problem this system will solve?",
                [
                    Option(
                        "scope-specific",
                        "Specific/Focused",
                        "A specific, well-defined problem",
                        ["Clear scope", "Faster delivery"],
                        ["Limited flexibility"],
                        0.7,
                    ),
                    Option(
                        "scope-broad",
                        "Broad/Platform",
                        "A broad platform solving multiple problems",
                        ["Flexible", "Scalable"],
                        ["Complex", "Slower to build"],
                        0.5,
                    ),
                ],
            ),
            "Architecture": (
                "What architecture pattern fits your needs?",
                [
                    Option(
                        "arch-monolith",
                        "Monolith",
                        "Single deployable unit",
                        ["Simple", "Easy to develop", "No network overhead"],
                        ["Scaling challenges", "Tech lock-in"],
                        0.6,
                    ),
                    Option(
                        "arch-microservices",
                        "Microservices",
                        "Distributed services",
                        ["Scalable", "Independent deployment"],
                        ["Complex", "Network overhead"],
                        0.4,
                    ),
                    Option(
                        "arch-modular",
                        "Modular Monolith",
                        "Monolith with clear boundaries",
                        ["Best of both", "Easy migration path"],
                        ["Discipline required"],
                        0.8,
                    ),
                ],
            ),
            "Tech Stack": (
                "What is your preferred technology stack?",
                [
                    Option(
                        "stack-python",
                        "Python",
                        "Python with FastAPI/Django",
                        ["Readable", "Great ecosystem", "ML/AI support"],
                        ["Performance", "Type safety"],
                        0.7,
                    ),
                    Option(
                        "stack-typescript",
                        "TypeScript",
                        "TypeScript with Node.js",
                        ["Full-stack", "Type safety", "Fast"],
                        ["Node.js quirks"],
                        0.7,
                    ),
                    Option(
                        "stack-go",
                        "Go",
                        "Go for backend services",
                        ["Fast", "Simple", "Concurrent"],
                        ["Verbose", "Smaller ecosystem"],
                        0.6,
                    ),
                ],
            ),
            "API Design": (
                "What API style will you use?",
                [
                    Option(
                        "api-rest",
                        "REST",
                        "RESTful HTTP API",
                        ["Simple", "Well understood", "Cacheable"],
                        ["Over/under fetching"],
                        0.8,
                    ),
                    Option(
                        "api-graphql",
                        "GraphQL",
                        "GraphQL API",
                        ["Flexible queries", "Strong typing"],
                        ["Complexity", "Caching hard"],
                        0.5,
                    ),
                    Option(
                        "api-grpc",
                        "gRPC",
                        "gRPC with Protocol Buffers",
                        ["Fast", "Type safe", "Streaming"],
                        ["Browser support", "Learning curve"],
                        0.4,
                    ),
                ],
            ),
            "Data Model": (
                "What is your primary data storage approach?",
                [
                    Option(
                        "data-sql",
                        "SQL Database",
                        "PostgreSQL/MySQL relational database",
                        ["ACID", "Mature", "Powerful queries"],
                        ["Scaling horizontal"],
                        0.8,
                    ),
                    Option(
                        "data-nosql",
                        "NoSQL",
                        "MongoDB/DynamoDB document store",
                        ["Flexible schema", "Scales well"],
                        ["Consistency", "Less powerful queries"],
                        0.5,
                    ),
                ],
            ),
            "Security": (
                "What are your security requirements?",
                [
                    Option(
                        "sec-standard",
                        "Standard",
                        "Standard web security practices",
                        ["Simpler implementation"],
                        ["May not meet compliance"],
                        0.5,
                    ),
                    Option(
                        "sec-compliance",
                        "Compliance-focused",
                        "SOC2/GDPR/HIPAA compliant",
                        ["Meets regulations", "Audit ready"],
                        ["More complex", "Slower development"],
                        0.7,
                    ),
                ],
            ),
            "Performance": (
                "What are your performance targets?",
                [
                    Option(
                        "perf-standard",
                        "Standard (p99 < 500ms)",
                        "Typical web application latency",
                        ["Easier to achieve"],
                        ["May not suit all use cases"],
                        0.7,
                    ),
                    Option(
                        "perf-high",
                        "High Performance (p99 < 100ms)",
                        "Low latency requirements",
                        ["Great UX"],
                        ["Requires optimization"],
                        0.5,
                    ),
                ],
            ),
            "Integrations": (
                "What external integrations do you need?",
                [
                    Option(
                        "int-minimal",
                        "Minimal",
                        "Few external dependencies",
                        ["Simpler", "More control"],
                        ["May need to build more"],
                        0.6,
                    ),
                    Option(
                        "int-many",
                        "Multiple Services",
                        "Integrating with multiple third-party services",
                        ["Faster development", "Best-of-breed"],
                        ["Vendor risk", "Complexity"],
                        0.5,
                    ),
                ],
            ),
            "Deployment": (
                "How will you deploy?",
                [
                    Option(
                        "deploy-container",
                        "Containers (K8s/ECS)",
                        "Containerized deployment",
                        ["Portable", "Scalable", "Mature"],
                        ["Complexity"],
                        0.8,
                    ),
                    Option(
                        "deploy-serverless",
                        "Serverless",
                        "AWS Lambda/Cloud Functions",
                        ["No ops", "Cost efficient"],
                        ["Cold starts", "Vendor lock-in"],
                        0.6,
                    ),
                    Option(
                        "deploy-vm",
                        "VMs/Bare Metal",
                        "Traditional VM deployment",
                        ["Simple", "Predictable"],
                        ["Manual scaling", "More ops"],
                        0.4,
                    ),
                ],
            ),
        }

        return static_questions.get(
            topic,
            (
                f"What approach will you take for {topic}?",
                [
                    Option("opt-a", "Option A", "First approach", [], [], 0.5),
                    Option("opt-b", "Option B", "Second approach", [], [], 0.5),
                ],
            ),
        )

    def is_complete(self) -> bool:
        """Check if all required topics have been covered."""
        return self.session.is_discussion_complete

    async def add_reference_repo(self, repo_url: str) -> DiscussionResult:
        """Add a reference repository to analyze for patterns.

        Args:
            repo_url: GitHub repository URL to analyze.

        Returns:
            DiscussionResult with analysis status.
        """
        if not self.research_agent:
            return DiscussionResult(
                action=DiscussionAction.CONTINUE,
                message="Research agent not available. Cannot analyze repository.",
            )

        try:
            # Build context from session
            context = self._build_context()

            # Analyze the repository
            analysis = await self.research_agent.analyze_github_repo(repo_url, context)

            # Store in session
            self.session.add_reference_repo(analysis.to_dict())

            # Format summary for display
            if analysis.status.value == "completed":
                summary_parts = [
                    f"Analyzed repository: **{analysis.repo_name}**",
                    f"Language: {analysis.primary_language}",
                ]

                if analysis.structure_summary:
                    summary_parts.append(f"\n{analysis.structure_summary}")

                if analysis.architecture_patterns:
                    summary_parts.append(
                        f"\nArchitecture patterns: {', '.join(analysis.architecture_patterns)}"
                    )

                if analysis.reusable_components:
                    summary_parts.append(
                        f"\nFound {len(analysis.reusable_components)} reusable components:"
                    )
                    for comp in analysis.reusable_components[:5]:  # Show top 5
                        summary_parts.append(
                            f"  - **{comp.name}** ({comp.component_type}): {comp.description}"
                        )
                        if comp.relevance_score > 0.7:
                            summary_parts.append(f"    Relevance: High ({comp.relevance_score:.0%})")

                if analysis.recommendations:
                    summary_parts.append("\nRecommendations:")
                    for rec in analysis.recommendations[:3]:
                        summary_parts.append(f"  - {rec}")

                return DiscussionResult(
                    action=DiscussionAction.ANALYZE_REPO,
                    message="\n".join(summary_parts),
                    repo_analysis=analysis.to_dict(),
                )
            else:
                return DiscussionResult(
                    action=DiscussionAction.CONTINUE,
                    message=f"Failed to analyze repository: {analysis.error_message}",
                    repo_analysis=analysis.to_dict(),
                )

        except Exception as e:
            return DiscussionResult(
                action=DiscussionAction.CONTINUE,
                message=f"Error analyzing repository: {str(e)}",
            )

    def get_reference_repos_summary(self) -> str:
        """Get a summary of all reference repositories.

        Returns:
            Formatted summary of reference repos.
        """
        if not self.session.reference_repos:
            return "No reference repositories added yet."

        lines = ["Reference repositories:"]
        for repo in self.session.reference_repos:
            repo_name = repo.get("repo_name", "Unknown")
            language = repo.get("primary_language", "Unknown")
            components = repo.get("reusable_components", [])
            lines.append(f"  - {repo_name} ({language}) - {len(components)} components")

        return "\n".join(lines)
