"""Base agent class and related data structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.spec.schemas import Spec
    from src.spec.block import BlockSpec
    from src.rules.schemas import Rule


class AgentStatus(Enum):
    """Status of an agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentResult:
    """Result of an agent execution."""

    status: AgentStatus
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Check if the result indicates success."""
        return self.status == AgentStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """Check if the result indicates failure."""
        return self.status == AgentStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "status": self.status.value,
            "message": self.message,
            "data": self.data,
            "errors": self.errors,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
        }


@dataclass
class AgentContext:
    """Context passed to agents during execution.

    Contains all information needed for an agent to perform its task,
    including the specification, project configuration, and results
    from previous agents in the pipeline.
    """

    spec: Spec
    project_root: Path
    branch_name: str = ""
    dry_run: bool = False
    verbose: bool = False
    previous_results: dict[str, AgentResult] = field(default_factory=dict)
    # New fields for block support
    block: BlockSpec | None = None
    parent_context: dict[str, Any] = field(default_factory=dict)
    effective_rules: list[Rule] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure project_root is a Path."""
        if isinstance(self.project_root, str):
            self.project_root = Path(self.project_root)

    def get_result(self, agent_name: str) -> AgentResult | None:
        """Get the result from a previous agent.

        Args:
            agent_name: Name of the agent to get result for.

        Returns:
            AgentResult or None if not found.
        """
        return self.previous_results.get(agent_name)

    def has_block(self) -> bool:
        """Check if this context has an associated block."""
        return self.block is not None

    def get_block_path(self) -> str:
        """Get the block path or empty string."""
        return self.block.path if self.block else ""

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary (for serialization)."""
        return {
            "spec_name": self.spec.name if self.spec else "",
            "project_root": str(self.project_root),
            "branch_name": self.branch_name,
            "dry_run": self.dry_run,
            "verbose": self.verbose,
            "block_path": self.get_block_path(),
            "has_parent_context": bool(self.parent_context),
            "effective_rules_count": len(self.effective_rules),
        }


class BaseAgent(ABC):
    """Abstract base class for all agents.

    Agents are responsible for specific tasks in the spec-driven
    development pipeline, such as generating code, running tests,
    or creating documentation.
    """

    name: str = "base"
    description: str = "Base agent"
    requires: list[str] = []  # Names of prerequisite agents

    @abstractmethod
    def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's task.

        Args:
            context: Execution context with spec and project info.

        Returns:
            Result of the agent execution.
        """
        pass

    def can_run(self, context: AgentContext) -> tuple[bool, str]:
        """Check if this agent can run given the context.

        Verifies that all required predecessor agents have completed
        successfully.

        Args:
            context: Execution context.

        Returns:
            Tuple of (can_run, reason).
        """
        for required in self.requires:
            result = context.get_result(required)
            if result is None:
                return False, f"Required agent '{required}' has not run"
            if result.status != AgentStatus.SUCCESS:
                return False, f"Required agent '{required}' did not succeed"
        return True, ""

    def skip(self, reason: str) -> AgentResult:
        """Create a skipped result.

        Args:
            reason: Reason for skipping.

        Returns:
            AgentResult with SKIPPED status.
        """
        return AgentResult(
            status=AgentStatus.SKIPPED,
            message=reason,
        )

    def success(self, message: str = "", **data: Any) -> AgentResult:
        """Create a success result.

        Args:
            message: Success message.
            **data: Additional data to include.

        Returns:
            AgentResult with SUCCESS status.
        """
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=message,
            data=data,
        )

    def failure(self, message: str, errors: list[str] | None = None) -> AgentResult:
        """Create a failure result.

        Args:
            message: Failure message.
            errors: List of error messages.

        Returns:
            AgentResult with FAILED status.
        """
        return AgentResult(
            status=AgentStatus.FAILED,
            message=message,
            errors=errors or [],
        )
