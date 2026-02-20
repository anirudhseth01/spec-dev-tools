"""Spec Builder Mode - Interactive, AI-guided spec hierarchy design and implementation.

This module provides an interactive system for designing and implementing
complete spec hierarchies through conversational Q&A, followed by autonomous execution.

Three Phases:
1. Interactive Discussion - Q&A with pros/cons, research, user decisions
2. Review & Approval - Present hierarchy, allow edits, get approval
3. Autonomous Execution - Parallel build/test/deploy with live dashboard
"""

from src.builder.session import (
    SessionPhase,
    ResearchDepth,
    Option,
    Decision,
    BlockDesign,
    HierarchyDesign,
    ExecutionProgress,
    BuilderSession,
)
from src.builder.persistence import SessionPersistence
from src.builder.discussion import DiscussionEngine, DiscussionResult
from src.builder.research import (
    ResearchAgent,
    ResearchResult,
    ValidationResult,
    RepoFile,
    ReusableComponent,
    RepoAnalysis,
    GitHubAnalyzer,
)
from src.builder.designer import BlockDesigner
from src.builder.generator import SpecGenerator, GeneratedSpec
from src.builder.executor import ExecutionOrchestrator, ExecutionResult, BlockResult
from src.builder.dashboard import LiveDashboard, ExecutionStatus

__all__ = [
    # Session
    "SessionPhase",
    "ResearchDepth",
    "Option",
    "Decision",
    "BlockDesign",
    "HierarchyDesign",
    "ExecutionProgress",
    "BuilderSession",
    # Persistence
    "SessionPersistence",
    # Discussion
    "DiscussionEngine",
    "DiscussionResult",
    # Research
    "ResearchAgent",
    "ResearchResult",
    "ValidationResult",
    "RepoFile",
    "ReusableComponent",
    "RepoAnalysis",
    "GitHubAnalyzer",
    # Designer
    "BlockDesigner",
    # Generator
    "SpecGenerator",
    "GeneratedSpec",
    # Executor
    "ExecutionOrchestrator",
    "ExecutionResult",
    "BlockResult",
    # Dashboard
    "LiveDashboard",
    "ExecutionStatus",
]
