"""Ambiguity detection and resolution for code generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AmbiguityCategory(Enum):
    """Categories of ambiguities."""

    # Critical - ALWAYS ASK
    SECURITY = "security"
    DATA_PERSISTENCE = "data_persistence"
    EXTERNAL_API = "external_api"
    BREAKING_CHANGE = "breaking_change"
    PAYMENT = "payment"
    COMPLIANCE = "compliance"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"

    # Minor - CAN ASSUME
    VARIABLE_NAMING = "variable_naming"
    ERROR_MESSAGE_TEXT = "error_message_text"
    LOG_LEVELS = "log_levels"
    DOCSTRING_STYLE = "docstring_style"
    IMPORT_ORDERING = "import_ordering"
    CODE_FORMATTING = "code_formatting"
    TEST_NAMING = "test_naming"


@dataclass
class Ambiguity:
    """An ambiguous requirement in the spec."""

    category: AmbiguityCategory
    description: str
    possible_choices: list[str]
    context: str = ""
    spec_section: str = ""
    severity: str = "medium"  # "critical", "high", "medium", "low"


@dataclass
class Resolution:
    """Resolution for an ambiguity."""

    action: str  # "ask" or "assume"
    question: str | None = None
    options: list[str] | None = None
    chosen: str | None = None
    documentation: str | None = None


class AmbiguityResolver:
    """Handles ambiguous requirements with hybrid approach.

    Critical ambiguities -> ASK user
    Minor ambiguities -> ASSUME with documentation
    """

    # Categories that require user input
    CRITICAL_CATEGORIES = {
        AmbiguityCategory.SECURITY,
        AmbiguityCategory.DATA_PERSISTENCE,
        AmbiguityCategory.EXTERNAL_API,
        AmbiguityCategory.BREAKING_CHANGE,
        AmbiguityCategory.PAYMENT,
        AmbiguityCategory.COMPLIANCE,
        AmbiguityCategory.AUTHENTICATION,
        AmbiguityCategory.AUTHORIZATION,
    }

    # Categories where we can make assumptions
    MINOR_CATEGORIES = {
        AmbiguityCategory.VARIABLE_NAMING,
        AmbiguityCategory.ERROR_MESSAGE_TEXT,
        AmbiguityCategory.LOG_LEVELS,
        AmbiguityCategory.DOCSTRING_STYLE,
        AmbiguityCategory.IMPORT_ORDERING,
        AmbiguityCategory.CODE_FORMATTING,
        AmbiguityCategory.TEST_NAMING,
    }

    # Default assumptions for minor ambiguities
    DEFAULT_ASSUMPTIONS = {
        AmbiguityCategory.VARIABLE_NAMING: "Use project naming conventions",
        AmbiguityCategory.ERROR_MESSAGE_TEXT: "Use clear, actionable error messages",
        AmbiguityCategory.LOG_LEVELS: "INFO for normal operations, WARNING for recoverable issues, ERROR for failures",
        AmbiguityCategory.DOCSTRING_STYLE: "Google style docstrings",
        AmbiguityCategory.IMPORT_ORDERING: "Standard library, third-party, local imports",
        AmbiguityCategory.CODE_FORMATTING: "Follow project formatter (black/prettier)",
        AmbiguityCategory.TEST_NAMING: "test_<unit>_<scenario> pattern",
    }

    def resolve(self, ambiguity: Ambiguity) -> Resolution:
        """Resolve an ambiguity by asking or assuming."""
        if self._is_critical(ambiguity):
            return self._create_question(ambiguity)
        else:
            return self._make_assumption(ambiguity)

    def _is_critical(self, ambiguity: Ambiguity) -> bool:
        """Check if ambiguity requires user input."""
        return ambiguity.category in self.CRITICAL_CATEGORIES

    def _create_question(self, ambiguity: Ambiguity) -> Resolution:
        """Create a question to ask the user."""
        question = self._format_question(ambiguity)
        options = ambiguity.possible_choices.copy()

        # Add "Other" option if not present
        if not any(opt.lower().startswith("other") for opt in options):
            options.append("Other (please specify)")

        return Resolution(
            action="ask",
            question=question,
            options=options,
        )

    def _format_question(self, ambiguity: Ambiguity) -> str:
        """Format a user-friendly question."""
        templates = {
            AmbiguityCategory.SECURITY: (
                "Security consideration needed: {description}\n"
                "Which approach should I use?"
            ),
            AmbiguityCategory.DATA_PERSISTENCE: (
                "Data storage decision needed: {description}\n"
                "Which storage mechanism should I use?"
            ),
            AmbiguityCategory.EXTERNAL_API: (
                "External integration decision: {description}\n"
                "How should I handle this integration?"
            ),
            AmbiguityCategory.AUTHENTICATION: (
                "Authentication decision needed: {description}\n"
                "Which authentication method should I use?"
            ),
            AmbiguityCategory.AUTHORIZATION: (
                "Authorization decision needed: {description}\n"
                "How should permissions be handled?"
            ),
        }

        template = templates.get(
            ambiguity.category,
            "Decision needed: {description}\nWhich option should I use?"
        )

        return template.format(description=ambiguity.description)

    def _make_assumption(self, ambiguity: Ambiguity) -> Resolution:
        """Make an assumption for a minor ambiguity."""
        # Get default assumption or use first choice
        default = self.DEFAULT_ASSUMPTIONS.get(ambiguity.category)
        chosen = default if default else ambiguity.possible_choices[0]

        # Create documentation comment
        documentation = self._format_assumption_comment(ambiguity, chosen)

        return Resolution(
            action="assume",
            chosen=chosen,
            documentation=documentation,
        )

    def _format_assumption_comment(
        self, ambiguity: Ambiguity, chosen: str
    ) -> str:
        """Format an assumption as a code comment."""
        lines = [
            f"# ASSUMPTION: {ambiguity.description}",
            f"# Chose: {chosen}",
            f"# Category: {ambiguity.category.value}",
        ]

        if ambiguity.possible_choices:
            alternatives = [c for c in ambiguity.possible_choices if c != chosen]
            if alternatives:
                lines.append(f"# Alternatives considered: {', '.join(alternatives[:3])}")

        return "\n".join(lines)

    def detect_ambiguities(
        self,
        spec_context: str,
        existing_code: str | None = None,
    ) -> list[Ambiguity]:
        """Detect potential ambiguities in the spec.

        This is a heuristic-based detection. A more sophisticated
        implementation could use LLM to identify ambiguities.
        """
        ambiguities = []

        # Check for storage-related ambiguities
        storage_keywords = ["store", "persist", "save", "database", "cache"]
        if any(kw in spec_context.lower() for kw in storage_keywords):
            if not any(
                specific in spec_context.lower()
                for specific in ["postgres", "mysql", "redis", "sqlite", "mongodb"]
            ):
                ambiguities.append(Ambiguity(
                    category=AmbiguityCategory.DATA_PERSISTENCE,
                    description="Storage mechanism not specified",
                    possible_choices=[
                        "PostgreSQL (relational)",
                        "Redis (cache/fast access)",
                        "SQLite (simple/embedded)",
                        "MongoDB (document store)",
                    ],
                    context="Spec mentions data storage but doesn't specify the mechanism",
                ))

        # Check for auth-related ambiguities
        auth_keywords = ["authenticate", "login", "user", "session", "token"]
        if any(kw in spec_context.lower() for kw in auth_keywords):
            if not any(
                specific in spec_context.lower()
                for specific in ["jwt", "oauth", "session", "api key", "basic auth"]
            ):
                ambiguities.append(Ambiguity(
                    category=AmbiguityCategory.AUTHENTICATION,
                    description="Authentication method not specified",
                    possible_choices=[
                        "JWT tokens",
                        "OAuth 2.0",
                        "Session-based",
                        "API keys",
                    ],
                    context="Spec mentions authentication but doesn't specify the method",
                ))

        # Check for external API ambiguities
        api_keywords = ["external", "third-party", "integrate", "api", "webhook"]
        if any(kw in spec_context.lower() for kw in api_keywords):
            if "retry" not in spec_context.lower() and "timeout" not in spec_context.lower():
                ambiguities.append(Ambiguity(
                    category=AmbiguityCategory.EXTERNAL_API,
                    description="External API error handling not specified",
                    possible_choices=[
                        "Retry with exponential backoff",
                        "Fail fast with clear error",
                        "Circuit breaker pattern",
                        "Fallback to cached data",
                    ],
                    context="Spec mentions external APIs but doesn't specify error handling",
                ))

        return ambiguities

    def collect_assumptions(
        self, resolutions: list[Resolution]
    ) -> list[str]:
        """Collect all assumptions made for documentation."""
        return [
            r.documentation
            for r in resolutions
            if r.action == "assume" and r.documentation
        ]

    def collect_questions(
        self, resolutions: list[Resolution]
    ) -> list[dict[str, Any]]:
        """Collect all questions that need user answers."""
        return [
            {"question": r.question, "options": r.options}
            for r in resolutions
            if r.action == "ask"
        ]
