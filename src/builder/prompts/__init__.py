"""Prompts for Spec Builder Mode.

This module contains LLM prompts for:
- Discovery: Discussion and research prompts
- Generation: Spec generation prompts
"""

from src.builder.prompts.discovery import (
    DISCOVERY_SYSTEM_PROMPT,
    QUESTION_GENERATION_PROMPT,
    RESPONSE_PARSING_PROMPT,
    RESEARCH_PROMPT,
    COMPATIBILITY_PROMPT,
)
from src.builder.prompts.generation import (
    SPEC_GENERATION_PROMPT,
    HIERARCHY_DESIGN_PROMPT,
    COMPONENT_EXTRACTION_PROMPT,
)

__all__ = [
    # Discovery
    "DISCOVERY_SYSTEM_PROMPT",
    "QUESTION_GENERATION_PROMPT",
    "RESPONSE_PARSING_PROMPT",
    "RESEARCH_PROMPT",
    "COMPATIBILITY_PROMPT",
    # Generation
    "SPEC_GENERATION_PROMPT",
    "HIERARCHY_DESIGN_PROMPT",
    "COMPONENT_EXTRACTION_PROMPT",
]
