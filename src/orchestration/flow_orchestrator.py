"""Orchestrates operational flow between agents with dependency management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from src.agents.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from src.orchestration.section_router import SectionRouter, RoutedSpec
from src.spec.schemas import Spec


class FlowStrategy(Enum):
    """Strategy for executing agent flow."""

    SEQUENTIAL = "sequential"      # One after another
    PARALLEL_SIBLINGS = "parallel" # Same-level agents in parallel
    DAG = "dag"                    # Based on dependency graph


@dataclass
class AgentNode:
    """A node in the agent execution graph."""

    agent: BaseAgent
    depends_on: list[str] = field(default_factory=list)  # Agent names this depends on
    provides: list[str] = field(default_factory=list)    # What this agent produces
    priority: int = 0                                     # Higher = run earlier (within same level)


@dataclass
class FlowMessage:
    """Message passed between agents."""

    from_agent: str
    to_agent: str
    message_type: str  # "result", "artifact", "error", "request"
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FlowState:
    """Current state of the execution flow."""

    completed_agents: list[str] = field(default_factory=list)
    pending_agents: list[str] = field(default_factory=list)
    running_agents: list[str] = field(default_factory=list)
    failed_agents: list[str] = field(default_factory=list)
    messages: list[FlowMessage] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)  # Shared artifacts

    def can_run(self, agent_name: str, dependencies: list[str]) -> bool:
        """Check if an agent can run based on its dependencies."""
        return all(dep in self.completed_agents for dep in dependencies)

    def add_artifact(self, key: str, value: Any, from_agent: str) -> None:
        """Add a shared artifact from an agent."""
        self.artifacts[key] = {
            "value": value,
            "from_agent": from_agent,
            "timestamp": datetime.now(),
        }

    def get_artifact(self, key: str) -> Any | None:
        """Get a shared artifact."""
        artifact = self.artifacts.get(key)
        return artifact["value"] if artifact else None


class FlowOrchestrator:
    """Orchestrates the flow of execution between multiple agents.

    Handles:
    - Dependency resolution (which agents must run first)
    - Message passing between agents
    - Artifact sharing (code, test results, etc.)
    - Error propagation and recovery
    - Section routing (giving agents only what they need)
    """

    def __init__(
        self,
        spec: Spec,
        project_root: Path,
        strategy: FlowStrategy = FlowStrategy.SEQUENTIAL,
    ):
        """Initialize the orchestrator.

        Args:
            spec: The specification being implemented.
            project_root: Root directory of the project.
            strategy: Execution strategy to use.
        """
        self.spec = spec
        self.project_root = Path(project_root)
        self.strategy = strategy
        self.section_router = SectionRouter()
        self.nodes: dict[str, AgentNode] = {}
        self.state = FlowState()
        self.hooks: dict[str, list[Callable]] = {
            "pre_agent": [],
            "post_agent": [],
            "on_error": [],
            "on_complete": [],
        }

    def register_agent(
        self,
        agent: BaseAgent,
        depends_on: list[str] | None = None,
        provides: list[str] | None = None,
        priority: int = 0,
    ) -> None:
        """Register an agent in the execution graph.

        Args:
            agent: The agent to register.
            depends_on: Names of agents this one depends on.
            provides: Artifact keys this agent produces.
            priority: Execution priority (higher = earlier).
        """
        self.nodes[agent.name] = AgentNode(
            agent=agent,
            depends_on=depends_on or [],
            provides=provides or [],
            priority=priority,
        )
        self.state.pending_agents.append(agent.name)

    def add_hook(self, event: str, callback: Callable) -> None:
        """Add a hook to be called at specific events.

        Args:
            event: Event name (pre_agent, post_agent, on_error, on_complete).
            callback: Function to call.
        """
        if event in self.hooks:
            self.hooks[event].append(callback)

    def execute(self) -> FlowState:
        """Execute the full agent flow.

        Returns:
            Final flow state with results and artifacts.
        """
        if self.strategy == FlowStrategy.SEQUENTIAL:
            return self._execute_sequential()
        elif self.strategy == FlowStrategy.DAG:
            return self._execute_dag()
        else:
            return self._execute_sequential()  # Fallback

    def _execute_sequential(self) -> FlowState:
        """Execute agents in registration order, respecting dependencies."""
        # Sort by priority
        sorted_agents = sorted(
            self.nodes.values(),
            key=lambda n: n.priority,
            reverse=True,
        )

        for node in sorted_agents:
            if not self.state.can_run(node.agent.name, node.depends_on):
                self.state.failed_agents.append(node.agent.name)
                self._send_message(
                    from_agent="orchestrator",
                    to_agent=node.agent.name,
                    message_type="error",
                    payload={"reason": "Dependencies not satisfied"},
                )
                continue

            result = self._run_agent(node)

            if result.status == AgentStatus.FAILED:
                # Check if we should stop or continue
                if not self._handle_failure(node, result):
                    break

        self._trigger_hooks("on_complete", self.state)
        return self.state

    def _execute_dag(self) -> FlowState:
        """Execute agents based on dependency graph (enables parallelism)."""
        # Build execution levels
        levels = self._build_execution_levels()

        for level in levels:
            # In a real implementation, these could run in parallel
            for agent_name in level:
                node = self.nodes.get(agent_name)
                if node and self.state.can_run(agent_name, node.depends_on):
                    result = self._run_agent(node)
                    if result.status == AgentStatus.FAILED:
                        if not self._handle_failure(node, result):
                            return self.state

        self._trigger_hooks("on_complete", self.state)
        return self.state

    def _build_execution_levels(self) -> list[list[str]]:
        """Build levels for DAG execution (topological sort)."""
        levels: list[list[str]] = []
        remaining = set(self.nodes.keys())
        completed: set[str] = set()

        while remaining:
            # Find all agents whose dependencies are satisfied
            level = [
                name for name in remaining
                if all(dep in completed for dep in self.nodes[name].depends_on)
            ]

            if not level:
                # Circular dependency or missing dependency
                break

            levels.append(level)
            completed.update(level)
            remaining -= set(level)

        return levels

    def _run_agent(self, node: AgentNode) -> AgentResult:
        """Run a single agent with proper context."""
        agent = node.agent
        self.state.pending_agents.remove(agent.name)
        self.state.running_agents.append(agent.name)

        # Trigger pre-agent hooks
        self._trigger_hooks("pre_agent", agent.name)

        # Route only relevant spec sections to this agent
        routed_spec = self.section_router.route(self.spec, agent.name)

        # Build context with routed spec and shared artifacts
        context = AgentContext(
            spec=self.spec,  # Full spec for compatibility
            project_root=self.project_root,
            previous_results={
                name: self._get_agent_result(name)
                for name in self.state.completed_agents
            },
        )

        # Add routed spec info to context
        context.parent_context["routed_sections"] = list(routed_spec.sections.keys())
        context.parent_context["artifacts"] = dict(self.state.artifacts)

        # Execute
        try:
            result = agent.execute(context)
        except Exception as e:
            result = AgentResult(
                status=AgentStatus.FAILED,
                message=str(e),
                errors=[str(e)],
            )

        # Update state
        self.state.running_agents.remove(agent.name)

        if result.status == AgentStatus.SUCCESS:
            self.state.completed_agents.append(agent.name)

            # Collect artifacts from result
            for key in node.provides:
                if key in result.data:
                    self.state.add_artifact(key, result.data[key], agent.name)
        else:
            self.state.failed_agents.append(agent.name)

        # Send result message
        self._send_message(
            from_agent=agent.name,
            to_agent="orchestrator",
            message_type="result",
            payload={"status": result.status.value, "message": result.message},
        )

        # Trigger post-agent hooks
        self._trigger_hooks("post_agent", agent.name, result)

        return result

    def _get_agent_result(self, agent_name: str) -> AgentResult:
        """Get stored result for a completed agent."""
        # Find in messages
        for msg in reversed(self.state.messages):
            if msg.from_agent == agent_name and msg.message_type == "result":
                return AgentResult(
                    status=AgentStatus(msg.payload.get("status", "success")),
                    message=msg.payload.get("message", ""),
                )
        return AgentResult(status=AgentStatus.SUCCESS)

    def _handle_failure(self, node: AgentNode, result: AgentResult) -> bool:
        """Handle agent failure. Returns True to continue, False to stop."""
        self._trigger_hooks("on_error", node.agent.name, result)

        # For now, stop on any failure
        # Could be extended with retry logic, fallbacks, etc.
        return False

    def _send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a message between agents."""
        self.state.messages.append(FlowMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            payload=payload,
        ))

    def _trigger_hooks(self, event: str, *args: Any) -> None:
        """Trigger all hooks for an event."""
        for callback in self.hooks.get(event, []):
            try:
                callback(*args)
            except Exception:
                pass  # Don't let hooks break the flow


# Dependency configuration for all known agent types
AGENT_DEPENDENCIES: dict[str, tuple[list[str], list[str]]] = {
    # (depends_on, provides)
    "coding_agent": ([], ["code", "files_created"]),
    "linter_agent": (["coding_agent"], ["linted_code"]),
    # Support both naming conventions for test agent
    "test_generator_agent": (["coding_agent"], ["tests", "test_files"]),
    "testing_agent": (["coding_agent"], ["tests", "test_files"]),
    # CodeReviewAgent needs both code and tests - we check for either test agent name
    "code_review_agent": (["coding_agent", "testing_agent"], ["review"]),
    "security_agent": (["coding_agent"], ["security_report"]),
    "architecture_agent": (["coding_agent"], ["architecture_update"]),
}


# Convenience function for common flow patterns
def create_standard_flow(
    spec: Spec,
    project_root: Path,
    agents: list[BaseAgent],
) -> FlowOrchestrator:
    """Create a standard sequential flow with default dependencies.

    Standard flow:
    1. CodingAgent (produces: code, files_created)
    2. SecurityScanAgent (depends: coding_agent, produces: security_report)
    3. TestGeneratorAgent (depends: coding_agent, produces: tests, test_files)
    4. CodeReviewAgent (depends: coding_agent, test_generator_agent, produces: review)

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        agents: List of agent instances to include in the flow.

    Returns:
        Configured FlowOrchestrator ready for execution.
    """
    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    for agent in agents:
        deps, provides = AGENT_DEPENDENCIES.get(agent.name, ([], []))
        orchestrator.register_agent(
            agent=agent,
            depends_on=deps,
            provides=provides,
        )

    return orchestrator


def create_flow_with_all_agents(
    spec: Spec,
    project_root: Path,
    coding_agent: BaseAgent,
    security_agent: BaseAgent,
    test_generator_agent: BaseAgent,
    code_review_agent: BaseAgent,
) -> FlowOrchestrator:
    """Create a flow with all standard agents configured with proper dependencies.

    This is a convenience function that ensures all agents are properly connected:
    - CodingAgent: No dependencies, provides code and files_created
    - SecurityScanAgent: Depends on coding_agent, provides security_report
    - TestGeneratorAgent: Depends on coding_agent, provides tests and test_files
    - CodeReviewAgent: Depends on coding_agent and test agent, provides review

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        coding_agent: CodingAgent instance.
        security_agent: SecurityScanAgent instance.
        test_generator_agent: TestGeneratorAgent instance.
        code_review_agent: CodeReviewAgent instance.

    Returns:
        Configured FlowOrchestrator with all agents.
    """
    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    # Register CodingAgent (no dependencies, produces code)
    orchestrator.register_agent(
        agent=coding_agent,
        depends_on=[],
        provides=["code", "files_created"],
        priority=100,  # Highest priority, runs first
    )

    # Register SecurityScanAgent (depends on code)
    orchestrator.register_agent(
        agent=security_agent,
        depends_on=[coding_agent.name],
        provides=["security_report"],
        priority=80,
    )

    # Register TestGeneratorAgent (depends on code)
    orchestrator.register_agent(
        agent=test_generator_agent,
        depends_on=[coding_agent.name],
        provides=["tests", "test_files"],
        priority=80,
    )

    # Register CodeReviewAgent (depends on code and tests)
    orchestrator.register_agent(
        agent=code_review_agent,
        depends_on=[coding_agent.name, test_generator_agent.name],
        provides=["review"],
        priority=50,
    )

    return orchestrator
