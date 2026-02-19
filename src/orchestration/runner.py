"""Pipeline runner for executing orchestrated agent pipelines."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from src.agents.base import AgentResult, AgentStatus
from src.orchestration.flow_orchestrator import FlowOrchestrator, FlowState


class RunnerStatus(Enum):
    """Status of a pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # Some agents succeeded, some failed
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentProgress:
    """Progress information for a single agent."""

    agent_name: str
    status: AgentStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    message: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_name": self.agent_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class PipelineRunResult:
    """Result of a complete pipeline run."""

    status: RunnerStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_duration_ms: int = 0
    agent_results: dict[str, AgentResult] = field(default_factory=dict)
    agent_progress: list[AgentProgress] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    flow_state: Optional[FlowState] = None
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """Check if the run was fully successful."""
        return self.status == RunnerStatus.SUCCESS

    @property
    def is_partial(self) -> bool:
        """Check if the run was partially successful."""
        return self.status == RunnerStatus.PARTIAL

    @property
    def failed_agents(self) -> list[str]:
        """Get list of failed agent names."""
        return [
            name for name, result in self.agent_results.items()
            if result.status == AgentStatus.FAILED
        ]

    @property
    def successful_agents(self) -> list[str]:
        """Get list of successful agent names."""
        return [
            name for name, result in self.agent_results.items()
            if result.status == AgentStatus.SUCCESS
        ]

    def get_agent_result(self, agent_name: str) -> Optional[AgentResult]:
        """Get result for a specific agent."""
        return self.agent_results.get(agent_name)

    def get_artifact(self, key: str) -> Optional[Any]:
        """Get an artifact by key."""
        artifact = self.artifacts.get(key)
        if artifact and isinstance(artifact, dict) and "value" in artifact:
            return artifact["value"]
        return artifact

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
            "agent_results": {
                name: result.to_dict()
                for name, result in self.agent_results.items()
            },
            "agent_progress": [p.to_dict() for p in self.agent_progress],
            "artifacts": {
                key: (
                    val["value"] if isinstance(val, dict) and "value" in val
                    else val
                )
                for key, val in self.artifacts.items()
            },
            "failed_agents": self.failed_agents,
            "successful_agents": self.successful_agents,
            "error": self.error,
        }

    def to_summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"Pipeline Run: {self.status.value.upper()}",
            f"Duration: {self.total_duration_ms}ms",
            f"Agents: {len(self.successful_agents)} succeeded, {len(self.failed_agents)} failed",
        ]

        if self.failed_agents:
            lines.append(f"Failed: {', '.join(self.failed_agents)}")

        if self.error:
            lines.append(f"Error: {self.error}")

        return "\n".join(lines)


# Type aliases for callbacks
ProgressCallback = Callable[[str, AgentStatus, str], None]
AgentStartCallback = Callable[[str], None]
AgentCompleteCallback = Callable[[str, AgentResult], None]
ErrorCallback = Callable[[str, Exception], None]


class PipelineRunner:
    """Executes pipelines with progress reporting and error handling.

    The PipelineRunner wraps a FlowOrchestrator and provides:
    - Progress reporting hooks for real-time updates
    - Result aggregation across all agents
    - Error handling with partial results
    - Artifact collection from all agents

    Example usage:
        runner = PipelineRunner(orchestrator)
        runner.on_progress(lambda name, status, msg: print(f"{name}: {status}"))
        result = runner.run()
        if result.is_success:
            code = result.get_artifact("code")
    """

    def __init__(self, orchestrator: FlowOrchestrator):
        """Initialize the runner.

        Args:
            orchestrator: Configured FlowOrchestrator to execute.
        """
        self.orchestrator = orchestrator
        self._progress_callbacks: list[ProgressCallback] = []
        self._agent_start_callbacks: list[AgentStartCallback] = []
        self._agent_complete_callbacks: list[AgentCompleteCallback] = []
        self._error_callbacks: list[ErrorCallback] = []
        self._cancelled = False
        self._current_run: Optional[PipelineRunResult] = None

    def on_progress(self, callback: ProgressCallback) -> "PipelineRunner":
        """Register a progress callback.

        The callback receives (agent_name, status, message) for each state change.

        Args:
            callback: Function to call on progress updates.

        Returns:
            Self for chaining.
        """
        self._progress_callbacks.append(callback)
        return self

    def on_agent_start(self, callback: AgentStartCallback) -> "PipelineRunner":
        """Register a callback for when an agent starts.

        Args:
            callback: Function to call when agent starts (receives agent name).

        Returns:
            Self for chaining.
        """
        self._agent_start_callbacks.append(callback)
        return self

    def on_agent_complete(self, callback: AgentCompleteCallback) -> "PipelineRunner":
        """Register a callback for when an agent completes.

        Args:
            callback: Function to call when agent completes (receives name, result).

        Returns:
            Self for chaining.
        """
        self._agent_complete_callbacks.append(callback)
        return self

    def on_error(self, callback: ErrorCallback) -> "PipelineRunner":
        """Register an error callback.

        Args:
            callback: Function to call on errors (receives agent name, exception).

        Returns:
            Self for chaining.
        """
        self._error_callbacks.append(callback)
        return self

    def cancel(self) -> None:
        """Cancel the current run.

        Note: This sets a flag that will be checked between agent executions.
        Currently running agents will complete.
        """
        self._cancelled = True

    def run(self) -> PipelineRunResult:
        """Execute the pipeline.

        Returns:
            PipelineRunResult with all agent results and artifacts.
        """
        self._cancelled = False
        start_time = datetime.now()
        start_ms = time.time() * 1000

        # Initialize result
        self._current_run = PipelineRunResult(
            status=RunnerStatus.RUNNING,
            started_at=start_time,
        )

        try:
            # Set up orchestrator hooks
            self._setup_hooks()

            # Execute the pipeline
            flow_state = self.orchestrator.execute()

            # Process results
            self._process_flow_state(flow_state)

            # Determine final status
            self._current_run.status = self._determine_status(flow_state)
            self._current_run.flow_state = flow_state

        except Exception as e:
            self._current_run.status = RunnerStatus.FAILED
            self._current_run.error = str(e)
            self._notify_progress("pipeline", AgentStatus.FAILED, str(e))

        finally:
            # Finalize timing
            end_time = datetime.now()
            self._current_run.completed_at = end_time
            self._current_run.total_duration_ms = int(time.time() * 1000 - start_ms)

        return self._current_run

    def _setup_hooks(self) -> None:
        """Set up orchestrator hooks for progress tracking."""
        # Pre-agent hook
        def on_pre_agent(agent_name: str) -> None:
            self._notify_agent_start(agent_name)
            progress = AgentProgress(
                agent_name=agent_name,
                status=AgentStatus.RUNNING,
                started_at=datetime.now(),
            )
            if self._current_run:
                self._current_run.agent_progress.append(progress)
            self._notify_progress(agent_name, AgentStatus.RUNNING, "Started")

        # Post-agent hook
        def on_post_agent(agent_name: str, result: AgentResult) -> None:
            if self._current_run:
                # Update progress
                for progress in self._current_run.agent_progress:
                    if progress.agent_name == agent_name:
                        progress.status = result.status
                        progress.completed_at = datetime.now()
                        progress.message = result.message
                        if progress.started_at:
                            delta = progress.completed_at - progress.started_at
                            progress.duration_ms = int(delta.total_seconds() * 1000)
                        if result.status == AgentStatus.FAILED:
                            progress.error = "; ".join(result.errors) if result.errors else result.message
                        break

                # Store result
                self._current_run.agent_results[agent_name] = result

            self._notify_agent_complete(agent_name, result)
            self._notify_progress(agent_name, result.status, result.message)

        # Error hook
        def on_error(agent_name: str, result: AgentResult) -> None:
            if result.errors:
                for callback in self._error_callbacks:
                    try:
                        callback(agent_name, Exception("; ".join(result.errors)))
                    except Exception:
                        pass

        self.orchestrator.add_hook("pre_agent", on_pre_agent)
        self.orchestrator.add_hook("post_agent", on_post_agent)
        self.orchestrator.add_hook("on_error", on_error)

    def _process_flow_state(self, flow_state: FlowState) -> None:
        """Process the final flow state."""
        if not self._current_run:
            return

        # Collect artifacts
        self._current_run.artifacts = dict(flow_state.artifacts)

        # Ensure all agents have results
        for agent_name in flow_state.completed_agents:
            if agent_name not in self._current_run.agent_results:
                self._current_run.agent_results[agent_name] = AgentResult(
                    status=AgentStatus.SUCCESS,
                    message="Completed",
                )

        for agent_name in flow_state.failed_agents:
            if agent_name not in self._current_run.agent_results:
                self._current_run.agent_results[agent_name] = AgentResult(
                    status=AgentStatus.FAILED,
                    message="Failed",
                )

    def _determine_status(self, flow_state: FlowState) -> RunnerStatus:
        """Determine the final run status."""
        if self._cancelled:
            return RunnerStatus.CANCELLED

        if not flow_state.failed_agents and flow_state.completed_agents:
            return RunnerStatus.SUCCESS

        if flow_state.failed_agents and flow_state.completed_agents:
            return RunnerStatus.PARTIAL

        if flow_state.failed_agents:
            return RunnerStatus.FAILED

        return RunnerStatus.SUCCESS

    def _notify_progress(self, agent_name: str, status: AgentStatus, message: str) -> None:
        """Notify all progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(agent_name, status, message)
            except Exception:
                pass  # Don't let callbacks break the pipeline

    def _notify_agent_start(self, agent_name: str) -> None:
        """Notify all agent start callbacks."""
        for callback in self._agent_start_callbacks:
            try:
                callback(agent_name)
            except Exception:
                pass

    def _notify_agent_complete(self, agent_name: str, result: AgentResult) -> None:
        """Notify all agent complete callbacks."""
        for callback in self._agent_complete_callbacks:
            try:
                callback(agent_name, result)
            except Exception:
                pass


def run_pipeline(orchestrator: FlowOrchestrator) -> PipelineRunResult:
    """Convenience function to run a pipeline without explicit runner.

    Args:
        orchestrator: Configured FlowOrchestrator to execute.

    Returns:
        PipelineRunResult with all results and artifacts.
    """
    runner = PipelineRunner(orchestrator)
    return runner.run()


def run_pipeline_with_progress(
    orchestrator: FlowOrchestrator,
    progress_callback: ProgressCallback,
) -> PipelineRunResult:
    """Run a pipeline with progress reporting.

    Args:
        orchestrator: Configured FlowOrchestrator to execute.
        progress_callback: Callback for progress updates.

    Returns:
        PipelineRunResult with all results and artifacts.
    """
    runner = PipelineRunner(orchestrator)
    runner.on_progress(progress_callback)
    return runner.run()
