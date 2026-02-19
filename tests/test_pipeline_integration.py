"""Integration tests for pipeline orchestration."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any

from src.agents.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from src.orchestration.flow_orchestrator import (
    FlowOrchestrator,
    FlowStrategy,
    FlowState,
    AGENT_DEPENDENCIES,
    create_standard_flow,
    create_flow_with_all_agents,
)
from src.orchestration.pipelines import (
    create_full_pipeline,
    create_quick_pipeline,
    create_test_pipeline,
    create_review_pipeline,
    create_custom_pipeline,
)
from src.orchestration.runner import (
    PipelineRunner,
    PipelineRunResult,
    RunnerStatus,
    AgentProgress,
    run_pipeline,
    run_pipeline_with_progress,
)
from src.spec.schemas import Spec, Metadata, Overview, TestCases, TestCase


# Mock agents for testing


class MockCodingAgent(BaseAgent):
    """Mock coding agent for testing."""

    name = "coding_agent"
    description = "Mock coding agent"

    def __init__(self, should_fail: bool = False, code_output: dict[str, str] | None = None):
        self.should_fail = should_fail
        self.code_output = code_output or {
            "src/main.py": "def main(): pass",
            "src/utils.py": "def helper(): pass",
        }
        self.execute_count = 0

    def execute(self, context: AgentContext) -> AgentResult:
        self.execute_count += 1
        if self.should_fail:
            return AgentResult(
                status=AgentStatus.FAILED,
                message="Mock coding failure",
                errors=["Intentional test failure"],
            )
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Generated 2 files",
            data={
                "code": self.code_output,
                "files_created": list(self.code_output.keys()),
            },
        )


class MockSecurityAgent(BaseAgent):
    """Mock security agent for testing."""

    name = "security_agent"
    description = "Mock security agent"
    requires = ["coding_agent"]

    def __init__(self, should_fail: bool = False, has_issues: bool = False):
        self.should_fail = should_fail
        self.has_issues = has_issues
        self.execute_count = 0

    def execute(self, context: AgentContext) -> AgentResult:
        self.execute_count += 1
        if self.should_fail:
            return AgentResult(
                status=AgentStatus.FAILED,
                message="Security scan failed",
                errors=["Critical vulnerability found"],
            )
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Security scan passed",
            data={
                "security_report": {
                    "vulnerabilities": 1 if self.has_issues else 0,
                    "passed": not self.has_issues,
                },
            },
        )


class MockTestingAgent(BaseAgent):
    """Mock testing agent for testing."""

    name = "testing_agent"
    description = "Mock testing agent"
    requires = ["coding_agent"]

    def __init__(self, should_fail: bool = False, test_output: dict[str, str] | None = None):
        self.should_fail = should_fail
        self.test_output = test_output or {
            "tests/test_main.py": "def test_main(): pass",
        }
        self.execute_count = 0

    def execute(self, context: AgentContext) -> AgentResult:
        self.execute_count += 1
        if self.should_fail:
            return AgentResult(
                status=AgentStatus.FAILED,
                message="Test generation failed",
                errors=["Could not generate tests"],
            )
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Generated 1 test file",
            data={
                "tests": self.test_output,
                "test_files": list(self.test_output.keys()),
            },
        )


class MockReviewAgent(BaseAgent):
    """Mock code review agent for testing."""

    name = "code_review_agent"
    description = "Mock review agent"
    requires = ["coding_agent", "testing_agent"]

    def __init__(self, should_fail: bool = False, score: int = 85):
        self.should_fail = should_fail
        self.score = score
        self.execute_count = 0

    def execute(self, context: AgentContext) -> AgentResult:
        self.execute_count += 1
        if self.should_fail:
            return AgentResult(
                status=AgentStatus.FAILED,
                message="Code review failed",
                errors=["Critical issues found"],
            )
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=f"Review complete: score {self.score}/100",
            data={
                "review": {
                    "score": self.score,
                    "issues": [],
                },
            },
        )


@pytest.fixture
def sample_spec() -> Spec:
    """Create a sample specification for testing."""
    return Spec(
        name="Test Feature",
        metadata=Metadata(
            spec_id="test-feature",
            version="1.0.0",
            tech_stack="Python",
        ),
        overview=Overview(
            summary="A test feature for integration testing.",
            goals=["Test pipeline execution"],
        ),
        test_cases=TestCases(
            unit_tests=[
                TestCase(
                    test_id="UT-001",
                    description="Test happy path",
                    input="valid input",
                    expected_output="success",
                ),
            ],
        ),
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


class TestFlowOrchestrator:
    """Tests for FlowOrchestrator."""

    def test_register_agent(self, sample_spec, project_dir):
        """Test registering agents."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        agent = MockCodingAgent()

        orchestrator.register_agent(
            agent=agent,
            depends_on=[],
            provides=["code"],
        )

        assert "coding_agent" in orchestrator.nodes
        assert agent.name in orchestrator.state.pending_agents

    def test_execute_single_agent(self, sample_spec, project_dir):
        """Test executing a single agent."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        agent = MockCodingAgent()

        orchestrator.register_agent(agent=agent, depends_on=[], provides=["code"])
        state = orchestrator.execute()

        assert "coding_agent" in state.completed_agents
        assert len(state.failed_agents) == 0
        assert "code" in state.artifacts

    def test_execute_with_dependencies(self, sample_spec, project_dir):
        """Test executing agents with dependencies."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        coding_agent = MockCodingAgent()
        security_agent = MockSecurityAgent()

        orchestrator.register_agent(
            agent=coding_agent,
            depends_on=[],
            provides=["code"],
            priority=100,
        )
        orchestrator.register_agent(
            agent=security_agent,
            depends_on=["coding_agent"],
            provides=["security_report"],
            priority=80,
        )

        state = orchestrator.execute()

        assert "coding_agent" in state.completed_agents
        assert "security_agent" in state.completed_agents
        assert coding_agent.execute_count == 1
        assert security_agent.execute_count == 1

    def test_dependency_failure_stops_downstream(self, sample_spec, project_dir):
        """Test that failure in a dependency stops downstream agents."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        coding_agent = MockCodingAgent(should_fail=True)
        security_agent = MockSecurityAgent()

        orchestrator.register_agent(
            agent=coding_agent,
            depends_on=[],
            provides=["code"],
        )
        orchestrator.register_agent(
            agent=security_agent,
            depends_on=["coding_agent"],
            provides=["security_report"],
        )

        state = orchestrator.execute()

        assert "coding_agent" in state.failed_agents
        # Security agent should not have run
        assert security_agent.execute_count == 0

    def test_artifacts_passed_between_agents(self, sample_spec, project_dir):
        """Test that artifacts are passed between agents."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        code_output = {"src/feature.py": "class Feature: pass"}
        coding_agent = MockCodingAgent(code_output=code_output)
        testing_agent = MockTestingAgent()

        orchestrator.register_agent(
            agent=coding_agent,
            depends_on=[],
            provides=["code", "files_created"],
        )
        orchestrator.register_agent(
            agent=testing_agent,
            depends_on=["coding_agent"],
            provides=["tests"],
        )

        state = orchestrator.execute()

        assert "code" in state.artifacts
        assert state.artifacts["code"]["value"] == code_output


class TestDependencyResolution:
    """Tests for dependency resolution."""

    def test_dag_execution_levels(self, sample_spec, project_dir):
        """Test DAG builds correct execution levels."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        # Register agents with complex dependencies
        coding_agent = MockCodingAgent()
        security_agent = MockSecurityAgent()
        testing_agent = MockTestingAgent()
        review_agent = MockReviewAgent()

        orchestrator.register_agent(coding_agent, [], ["code"])
        orchestrator.register_agent(security_agent, ["coding_agent"], ["security_report"])
        orchestrator.register_agent(testing_agent, ["coding_agent"], ["tests"])
        orchestrator.register_agent(review_agent, ["coding_agent", "testing_agent"], ["review"])

        levels = orchestrator._build_execution_levels()

        # Level 0: coding_agent (no deps)
        assert "coding_agent" in levels[0]

        # Level 1: security_agent and testing_agent (both depend only on coding)
        assert "security_agent" in levels[1]
        assert "testing_agent" in levels[1]

        # Level 2: review_agent (depends on coding and testing)
        assert "code_review_agent" in levels[2]

    def test_agent_dependencies_config(self):
        """Test AGENT_DEPENDENCIES configuration."""
        # Coding agent has no dependencies
        deps, provides = AGENT_DEPENDENCIES["coding_agent"]
        assert deps == []
        assert "code" in provides

        # Security agent depends on coding
        deps, provides = AGENT_DEPENDENCIES["security_agent"]
        assert "coding_agent" in deps
        assert "security_report" in provides

        # Testing agent depends on coding
        deps, provides = AGENT_DEPENDENCIES["testing_agent"]
        assert "coding_agent" in deps
        assert "tests" in provides


class TestPipelines:
    """Tests for pre-configured pipelines."""

    def test_create_full_pipeline(self, sample_spec, project_dir):
        """Test creating full pipeline."""
        orchestrator = create_full_pipeline(
            spec=sample_spec,
            project_root=project_dir,
            llm_client=None,
            dry_run=True,
        )

        # Should have 4 agents
        assert len(orchestrator.nodes) == 4
        assert "coding_agent" in orchestrator.nodes
        assert "security_agent" in orchestrator.nodes
        # The test agent name may be "testing_agent" or similar
        test_agent_registered = any(
            "test" in name.lower()
            for name in orchestrator.nodes.keys()
        )
        assert test_agent_registered
        assert "code_review_agent" in orchestrator.nodes

    def test_create_quick_pipeline(self, sample_spec, project_dir):
        """Test creating quick pipeline."""
        orchestrator = create_quick_pipeline(
            spec=sample_spec,
            project_root=project_dir,
            dry_run=True,
        )

        # Should have only 2 agents
        assert len(orchestrator.nodes) == 2
        assert "coding_agent" in orchestrator.nodes
        assert "security_agent" in orchestrator.nodes

    def test_create_test_pipeline(self, sample_spec, project_dir):
        """Test creating test-focused pipeline."""
        orchestrator = create_test_pipeline(
            spec=sample_spec,
            project_root=project_dir,
            dry_run=True,
        )

        # Should have 2 agents
        assert len(orchestrator.nodes) == 2
        assert "coding_agent" in orchestrator.nodes

    def test_create_custom_pipeline(self, sample_spec, project_dir):
        """Test creating custom pipeline."""
        agents = [
            MockCodingAgent(),
            MockSecurityAgent(),
        ]

        orchestrator = create_custom_pipeline(
            spec=sample_spec,
            project_root=project_dir,
            agents=agents,
        )

        assert len(orchestrator.nodes) == 2


class TestPipelineRunner:
    """Tests for PipelineRunner."""

    def test_run_simple_pipeline(self, sample_spec, project_dir):
        """Test running a simple pipeline."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        assert result.status == RunnerStatus.SUCCESS
        assert "coding_agent" in result.successful_agents
        assert result.total_duration_ms >= 0  # May be 0 for very fast executions

    def test_run_with_progress_callback(self, sample_spec, project_dir):
        """Test running with progress callback."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        progress_events = []

        def on_progress(agent_name, status, message):
            progress_events.append((agent_name, status, message))

        runner = PipelineRunner(orchestrator)
        runner.on_progress(on_progress)
        result = runner.run()

        assert len(progress_events) > 0
        # Should have at least RUNNING and SUCCESS events
        statuses = [e[1] for e in progress_events]
        assert AgentStatus.RUNNING in statuses

    def test_run_with_agent_callbacks(self, sample_spec, project_dir):
        """Test running with agent start/complete callbacks."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        started_agents = []
        completed_agents = []

        runner = PipelineRunner(orchestrator)
        runner.on_agent_start(lambda name: started_agents.append(name))
        runner.on_agent_complete(lambda name, result: completed_agents.append((name, result)))
        result = runner.run()

        assert "coding_agent" in started_agents
        assert any(name == "coding_agent" for name, _ in completed_agents)

    def test_run_with_failure(self, sample_spec, project_dir):
        """Test running with agent failure."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(should_fail=True), [], ["code"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        assert result.status == RunnerStatus.FAILED
        assert "coding_agent" in result.failed_agents

    def test_run_partial_success(self, sample_spec, project_dir):
        """Test partial success when later agent fails."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        coding_agent = MockCodingAgent()
        security_agent = MockSecurityAgent(should_fail=True)

        orchestrator.register_agent(coding_agent, [], ["code"])
        orchestrator.register_agent(security_agent, ["coding_agent"], ["security_report"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        # Coding succeeded, security failed
        assert "coding_agent" in result.successful_agents
        assert "security_agent" in result.failed_agents

    def test_result_artifacts(self, sample_spec, project_dir):
        """Test that artifacts are collected in result."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        code_output = {"src/app.py": "def app(): pass"}
        orchestrator.register_agent(
            MockCodingAgent(code_output=code_output),
            [],
            ["code"],
        )

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        assert "code" in result.artifacts
        code = result.get_artifact("code")
        assert code == code_output

    def test_result_summary(self, sample_spec, project_dir):
        """Test result summary generation."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        summary = result.to_summary()
        assert "SUCCESS" in summary
        assert "1 succeeded" in summary

    def test_result_to_dict(self, sample_spec, project_dir):
        """Test result serialization."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        result_dict = result.to_dict()
        assert result_dict["status"] == "success"
        assert "started_at" in result_dict
        assert "completed_at" in result_dict
        assert "coding_agent" in result_dict["successful_agents"]


class TestErrorPropagation:
    """Tests for error propagation in pipelines."""

    def test_error_callback(self, sample_spec, project_dir):
        """Test error callback is invoked on failure."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(should_fail=True), [], ["code"])

        errors = []

        def on_error(agent_name, exception):
            errors.append((agent_name, str(exception)))

        runner = PipelineRunner(orchestrator)
        runner.on_error(on_error)
        result = runner.run()

        assert len(errors) > 0
        assert errors[0][0] == "coding_agent"

    def test_downstream_not_run_on_upstream_failure(self, sample_spec, project_dir):
        """Test downstream agents don't run when upstream fails."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        coding_agent = MockCodingAgent(should_fail=True)
        testing_agent = MockTestingAgent()
        review_agent = MockReviewAgent()

        orchestrator.register_agent(coding_agent, [], ["code"])
        orchestrator.register_agent(testing_agent, ["coding_agent"], ["tests"])
        orchestrator.register_agent(review_agent, ["coding_agent", "testing_agent"], ["review"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        # Only coding agent should have run
        assert coding_agent.execute_count == 1
        assert testing_agent.execute_count == 0
        assert review_agent.execute_count == 0


class TestArtifactPassing:
    """Tests for artifact passing between agents."""

    def test_artifacts_in_context(self, sample_spec, project_dir):
        """Test that artifacts are available in agent context."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        code_output = {"src/service.py": "class Service: pass"}
        coding_agent = MockCodingAgent(code_output=code_output)

        # Custom agent to capture context
        received_artifacts = {}

        class CapturingAgent(BaseAgent):
            name = "capturing_agent"

            def execute(self, context: AgentContext) -> AgentResult:
                nonlocal received_artifacts
                received_artifacts = context.parent_context.get("artifacts", {})
                return AgentResult(status=AgentStatus.SUCCESS)

        capturing_agent = CapturingAgent()

        orchestrator.register_agent(coding_agent, [], ["code"])
        orchestrator.register_agent(capturing_agent, ["coding_agent"], [])

        orchestrator.execute()

        assert "code" in received_artifacts
        assert received_artifacts["code"]["value"] == code_output

    def test_previous_results_in_context(self, sample_spec, project_dir):
        """Test that previous results are available in context."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        coding_agent = MockCodingAgent()

        # Custom agent to capture context
        received_results = {}

        class ResultCapturingAgent(BaseAgent):
            name = "result_capturing_agent"

            def execute(self, context: AgentContext) -> AgentResult:
                nonlocal received_results
                received_results = dict(context.previous_results)
                return AgentResult(status=AgentStatus.SUCCESS)

        capturing_agent = ResultCapturingAgent()

        orchestrator.register_agent(coding_agent, [], ["code"])
        orchestrator.register_agent(capturing_agent, ["coding_agent"], [])

        orchestrator.execute()

        assert "coding_agent" in received_results
        assert received_results["coding_agent"].status == AgentStatus.SUCCESS


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_run_pipeline(self, sample_spec, project_dir):
        """Test run_pipeline convenience function."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        result = run_pipeline(orchestrator)

        assert result.status == RunnerStatus.SUCCESS

    def test_run_pipeline_with_progress(self, sample_spec, project_dir):
        """Test run_pipeline_with_progress convenience function."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)
        orchestrator.register_agent(MockCodingAgent(), [], ["code"])

        events = []

        result = run_pipeline_with_progress(
            orchestrator,
            lambda name, status, msg: events.append((name, status)),
        )

        assert result.status == RunnerStatus.SUCCESS
        assert len(events) > 0

    def test_create_standard_flow(self, sample_spec, project_dir):
        """Test create_standard_flow with agents."""
        agents = [
            MockCodingAgent(),
            MockSecurityAgent(),
            MockTestingAgent(),
        ]

        orchestrator = create_standard_flow(
            spec=sample_spec,
            project_root=project_dir,
            agents=agents,
        )

        assert len(orchestrator.nodes) == 3
        # Verify dependencies were set from AGENT_DEPENDENCIES
        security_node = orchestrator.nodes["security_agent"]
        assert "coding_agent" in security_node.depends_on


class TestFullPipelineExecution:
    """End-to-end tests for full pipeline execution."""

    def test_full_pipeline_all_succeed(self, sample_spec, project_dir):
        """Test full pipeline execution with all agents succeeding."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        coding_agent = MockCodingAgent()
        security_agent = MockSecurityAgent()
        testing_agent = MockTestingAgent()
        review_agent = MockReviewAgent()

        orchestrator.register_agent(coding_agent, [], ["code", "files_created"], priority=100)
        orchestrator.register_agent(security_agent, ["coding_agent"], ["security_report"], priority=80)
        orchestrator.register_agent(testing_agent, ["coding_agent"], ["tests", "test_files"], priority=80)
        orchestrator.register_agent(review_agent, ["coding_agent", "testing_agent"], ["review"], priority=50)

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        assert result.status == RunnerStatus.SUCCESS
        assert len(result.successful_agents) == 4
        assert len(result.failed_agents) == 0

        # Verify all agents ran
        assert coding_agent.execute_count == 1
        assert security_agent.execute_count == 1
        assert testing_agent.execute_count == 1
        assert review_agent.execute_count == 1

        # Verify artifacts
        assert result.get_artifact("code") is not None
        assert result.get_artifact("security_report") is not None
        assert result.get_artifact("tests") is not None
        assert result.get_artifact("review") is not None

    def test_full_pipeline_with_agent_progress(self, sample_spec, project_dir):
        """Test full pipeline with progress tracking."""
        orchestrator = FlowOrchestrator(sample_spec, project_dir, FlowStrategy.DAG)

        orchestrator.register_agent(MockCodingAgent(), [], ["code"])
        orchestrator.register_agent(MockSecurityAgent(), ["coding_agent"], ["security_report"])

        runner = PipelineRunner(orchestrator)
        result = runner.run()

        # Check agent progress
        assert len(result.agent_progress) == 2

        for progress in result.agent_progress:
            assert progress.status == AgentStatus.SUCCESS
            assert progress.started_at is not None
            assert progress.completed_at is not None
            assert progress.duration_ms >= 0
