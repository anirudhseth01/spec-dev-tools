"""Coding agent with skeleton-first generation approach."""

from src.agents.coding.agent import CodingAgent
from src.agents.coding.context_builder import ContextBuilder, CodeContext
from src.agents.coding.ambiguity import AmbiguityResolver, Ambiguity, Resolution

__all__ = [
    "Ambiguity",
    "CodeContext",
    "CodingAgent",
    "ContextBuilder",
    "Resolution",
    "AmbiguityResolver",
]
