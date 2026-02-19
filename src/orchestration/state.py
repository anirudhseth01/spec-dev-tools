"""State management for pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from src.agents.base import AgentResult, AgentStatus


class PipelineStatus(Enum):
    """Overall status of a pipeline execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentState:
    """State of a single agent in the pipeline."""

    name: str
    status: AgentStatus = AgentStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: AgentResult | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
        }


@dataclass
class PipelineState:
    """State of an entire pipeline execution."""

    spec_name: str
    project_root: Path
    branch_name: str = ""
    pr_url: str = ""
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    agents: dict[str, AgentState] = field(default_factory=dict)
    block_path: str = ""  # For block pipelines

    def __post_init__(self) -> None:
        """Ensure project_root is a Path."""
        if isinstance(self.project_root, str):
            self.project_root = Path(self.project_root)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate total duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_agent_state(self, name: str) -> AgentState | None:
        """Get state for a specific agent."""
        return self.agents.get(name)

    def set_agent_state(self, name: str, state: AgentState) -> None:
        """Set state for a specific agent."""
        self.agents[name] = state

    def mark_started(self) -> None:
        """Mark the pipeline as started."""
        self.status = PipelineStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, success: bool = True) -> None:
        """Mark the pipeline as completed."""
        self.status = PipelineStatus.SUCCESS if success else PipelineStatus.FAILED
        self.completed_at = datetime.now()

    def mark_cancelled(self) -> None:
        """Mark the pipeline as cancelled."""
        self.status = PipelineStatus.CANCELLED
        self.completed_at = datetime.now()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the pipeline state."""
        agent_summary = {
            "pending": 0,
            "running": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

        for agent in self.agents.values():
            agent_summary[agent.status.value] = agent_summary.get(agent.status.value, 0) + 1

        return {
            "spec_name": self.spec_name,
            "block_path": self.block_path,
            "status": self.status.value,
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "duration_seconds": self.duration_seconds,
            "agents": agent_summary,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spec_name": self.spec_name,
            "project_root": str(self.project_root),
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "status": self.status.value,
            "block_path": self.block_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "agents": {name: state.to_dict() for name, state in self.agents.items()},
        }
