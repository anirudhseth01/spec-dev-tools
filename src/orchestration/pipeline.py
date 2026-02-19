"""Pipeline orchestration for agent execution."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.agents.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from src.orchestration.state import AgentState, PipelineState, PipelineStatus

if TYPE_CHECKING:
    from src.spec.schemas import Spec


class Pipeline:
    """Orchestrates execution of agents in sequence.

    The pipeline manages the execution of multiple agents, passing
    context and results between them, and tracking overall state.
    """

    def __init__(
        self,
        spec: Spec,
        project_root: Path | str,
        agents: list[BaseAgent],
        branch_name: str = "",
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        """Initialize the pipeline.

        Args:
            spec: The specification to implement.
            project_root: Root directory of the project.
            agents: List of agents to execute in order.
            branch_name: Git branch name for the implementation.
            dry_run: If True, don't make actual changes.
            verbose: If True, output detailed progress.
        """
        self.spec = spec
        self.project_root = Path(project_root)
        self.agents = agents
        self.branch_name = branch_name or f"spec/{spec.name.lower().replace(' ', '-')}"
        self.dry_run = dry_run
        self.verbose = verbose

        # Initialize state
        self.state = PipelineState(
            spec_name=spec.name,
            project_root=self.project_root,
            branch_name=self.branch_name,
        )

        # Initialize agent states
        for agent in agents:
            self.state.set_agent_state(agent.name, AgentState(name=agent.name))

    def run(self) -> PipelineState:
        """Execute the pipeline.

        Runs all agents in sequence, stopping if any agent fails.

        Returns:
            Final pipeline state.
        """
        self.state.mark_started()

        # Build context
        context = AgentContext(
            spec=self.spec,
            project_root=self.project_root,
            branch_name=self.branch_name,
            dry_run=self.dry_run,
            verbose=self.verbose,
        )

        try:
            for agent in self.agents:
                result = self._run_agent(agent, context)

                # Store result in context for subsequent agents
                context.previous_results[agent.name] = result

                # Stop on failure
                if result.status == AgentStatus.FAILED:
                    self.state.mark_completed(success=False)
                    return self.state

            self.state.mark_completed(success=True)

        except Exception as e:
            self.state.mark_completed(success=False)
            # Record error in state
            if self.agents:
                current_agent = self.state.get_agent_state(self.agents[-1].name)
                if current_agent:
                    current_agent.error = str(e)

        return self.state

    def _run_agent(self, agent: BaseAgent, context: AgentContext) -> AgentResult:
        """Run a single agent.

        Args:
            agent: The agent to run.
            context: Execution context.

        Returns:
            Result of the agent execution.
        """
        agent_state = self.state.get_agent_state(agent.name)
        if agent_state is None:
            agent_state = AgentState(name=agent.name)
            self.state.set_agent_state(agent.name, agent_state)

        # Mark as running
        agent_state.status = AgentStatus.RUNNING
        agent_state.started_at = datetime.now()

        # Check if agent can run
        can_run, reason = agent.can_run(context)
        if not can_run:
            result = agent.skip(reason)
            agent_state.status = AgentStatus.SKIPPED
            agent_state.completed_at = datetime.now()
            agent_state.result = result
            return result

        # Execute agent
        try:
            result = agent.execute(context)
            agent_state.status = result.status
            agent_state.result = result
        except Exception as e:
            result = agent.failure(str(e), [str(e)])
            agent_state.status = AgentStatus.FAILED
            agent_state.error = str(e)
            agent_state.result = result

        agent_state.completed_at = datetime.now()
        return result

    def get_state(self) -> PipelineState:
        """Get current pipeline state."""
        return self.state

    def get_summary(self) -> dict:
        """Get pipeline execution summary."""
        return self.state.get_summary()
