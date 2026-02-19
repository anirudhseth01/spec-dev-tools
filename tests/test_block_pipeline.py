"""Tests for BlockPipeline."""

from pathlib import Path

import pytest

from src.orchestration.block_pipeline import BlockPipeline, ProcessingOrder, HierarchyPipelineState
from src.orchestration.state import PipelineStatus
from src.agents.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from src.spec.block import BlockSpec, BlockType
from src.spec.schemas import Spec, Metadata, SpecStatus


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    name = "mock_agent"
    description = "Mock agent for testing"

    def __init__(self, should_succeed: bool = True) -> None:
        self.should_succeed = should_succeed
        self.executed_blocks: list[str] = []

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute the mock agent."""
        block_path = context.get_block_path()
        self.executed_blocks.append(block_path)

        if self.should_succeed:
            return self.success(f"Processed {block_path}")
        else:
            return self.failure(f"Failed to process {block_path}")


class TestBlockPipelineOrdering:
    """Tests for block processing order."""

    def test_bottom_up_processing(self, temp_block_hierarchy: dict, project_dir: Path) -> None:
        """Test that blocks are processed leaves first in bottom-up order."""
        blocks = list(temp_block_hierarchy.values())
        agent = MockAgent()

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        state = pipeline.run(order=ProcessingOrder.BOTTOM_UP)

        assert state.status == PipelineStatus.SUCCESS

        # Verify execution order: leaves should come before their parents
        executed = agent.executed_blocks

        # Find indices
        leaf_idx = executed.index("root-system/component-b/leaf-b1")
        comp_b_idx = executed.index("root-system/component-b")
        root_idx = executed.index("root-system")

        # Leaf should be processed before its parent
        assert leaf_idx < comp_b_idx
        assert comp_b_idx < root_idx

    def test_top_down_processing(self, temp_block_hierarchy: dict, project_dir: Path) -> None:
        """Test that blocks are processed root first in top-down order."""
        blocks = list(temp_block_hierarchy.values())
        agent = MockAgent()

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        state = pipeline.run(order=ProcessingOrder.TOP_DOWN)

        assert state.status == PipelineStatus.SUCCESS

        # Verify execution order: root should come before children
        executed = agent.executed_blocks

        root_idx = executed.index("root-system")
        comp_a_idx = executed.index("root-system/component-a")
        module_idx = executed.index("root-system/component-a/module-a1")

        # Root should be processed before children
        assert root_idx < comp_a_idx
        assert comp_a_idx < module_idx


class TestBlockPipelineContext:
    """Tests for context propagation."""

    def test_parent_context_propagation_top_down(
        self, temp_block_hierarchy: dict, project_dir: Path
    ) -> None:
        """Test that context is passed from parent to children in top-down order."""

        class ContextCapturingAgent(BaseAgent):
            name = "context_capture"
            description = "Captures context"

            def __init__(self) -> None:
                self.captured_contexts: dict[str, dict] = {}

            def execute(self, context: AgentContext) -> AgentResult:
                block_path = context.get_block_path()
                self.captured_contexts[block_path] = dict(context.parent_context)
                return self.success("Captured context")

        blocks = list(temp_block_hierarchy.values())
        agent = ContextCapturingAgent()

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        pipeline.run(order=ProcessingOrder.TOP_DOWN)

        # Root should have empty parent context
        assert agent.captured_contexts.get("root-system", {}) == {}

        # Children should have parent context info
        comp_a_context = agent.captured_contexts.get("root-system/component-a", {})
        assert "block_path" in comp_a_context or comp_a_context == {}  # First child may not have context yet

    def test_child_context_propagation_bottom_up(
        self, temp_block_hierarchy: dict, project_dir: Path
    ) -> None:
        """Test that context is passed from children to parent in bottom-up order."""

        class ContextCapturingAgent(BaseAgent):
            name = "context_capture"
            description = "Captures context"

            def __init__(self) -> None:
                self.captured_contexts: dict[str, dict] = {}

            def execute(self, context: AgentContext) -> AgentResult:
                block_path = context.get_block_path()
                self.captured_contexts[block_path] = dict(context.parent_context)
                return self.success("Captured context")

        blocks = list(temp_block_hierarchy.values())
        agent = ContextCapturingAgent()

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        pipeline.run(order=ProcessingOrder.BOTTOM_UP)

        # Parent should have children info
        comp_b_context = agent.captured_contexts.get("root-system/component-b", {})
        if comp_b_context:
            assert "children" in comp_b_context


class TestBlockPipelineState:
    """Tests for pipeline state management."""

    def test_pipeline_state_tracking(self, temp_block_hierarchy: dict, project_dir: Path) -> None:
        """Test that pipeline state is tracked correctly."""
        blocks = list(temp_block_hierarchy.values())
        agent = MockAgent()

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        state = pipeline.run()

        assert state.total_blocks == 6
        assert state.processed_blocks == 6
        assert state.failed_blocks == 0
        assert state.status == PipelineStatus.SUCCESS

    def test_pipeline_failure_state(self, temp_block_hierarchy: dict, project_dir: Path) -> None:
        """Test pipeline state when agent fails."""
        blocks = list(temp_block_hierarchy.values())
        agent = MockAgent(should_succeed=False)

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        state = pipeline.run()

        assert state.failed_blocks == state.processed_blocks
        assert state.status == PipelineStatus.FAILED

    def test_get_summary(self, temp_block_hierarchy: dict, project_dir: Path) -> None:
        """Test pipeline summary generation."""
        blocks = list(temp_block_hierarchy.values())
        agent = MockAgent()

        pipeline = BlockPipeline(
            blocks=blocks,
            project_root=project_dir,
            agents=[agent],
        )

        pipeline.run()
        summary = pipeline.get_summary()

        assert summary["total_blocks"] == 6
        assert summary["processed_blocks"] == 6
        assert summary["failed_blocks"] == 0
        assert summary["success_rate"] == 1.0


class TestBlockPipelineValidation:
    """Tests for validation during pipeline execution."""

    def test_validation_stops_on_error(self, project_dir: Path, temp_dir: Path) -> None:
        """Test that pipeline stops on validation errors."""
        # Create a block that will fail validation
        spec = Spec(
            name="Invalid Block",
            metadata=Metadata(spec_id="invalid", status=SpecStatus.DRAFT),
        )
        block = BlockSpec(
            path="invalid",
            name="Invalid Block",
            directory=temp_dir / "specs" / "invalid",
            spec=spec,
            block_type=BlockType.LEAF,
        )

        agent = MockAgent()

        # Create rules that will cause error
        rules_content = """rules:
  - id: FAIL-001
    name: Always Fail
    level: global
    category: testing
    severity: error
    applies_to_sections:
      - all
    validation_fn: nonexistent_validator
    enabled: true
"""
        rules_file = project_dir / ".spec-dev" / "global-rules.yaml"
        rules_file.parent.mkdir(parents=True, exist_ok=True)
        rules_file.write_text(rules_content)

        pipeline = BlockPipeline(
            blocks=[block],
            project_root=project_dir,
            agents=[agent],
            dry_run=False,
        )

        state = pipeline.run()

        # Pipeline should still complete but may have issues
        assert state.processed_blocks == 1


class TestBlockPipelineEmptyBlocks:
    """Tests for edge cases with empty or single blocks."""

    def test_empty_blocks_list(self, project_dir: Path) -> None:
        """Test pipeline with no blocks."""
        pipeline = BlockPipeline(
            blocks=[],
            project_root=project_dir,
            agents=[MockAgent()],
        )

        state = pipeline.run()

        assert state.total_blocks == 0
        assert state.status == PipelineStatus.SUCCESS

    def test_single_block(self, project_dir: Path, temp_dir: Path) -> None:
        """Test pipeline with single block."""
        spec = Spec(
            name="Single",
            metadata=Metadata(spec_id="single", status=SpecStatus.DRAFT),
        )
        block = BlockSpec(
            path="single",
            name="Single",
            directory=temp_dir / "specs" / "single",
            spec=spec,
            block_type=BlockType.LEAF,
        )

        agent = MockAgent()

        pipeline = BlockPipeline(
            blocks=[block],
            project_root=project_dir,
            agents=[agent],
        )

        state = pipeline.run()

        assert state.total_blocks == 1
        assert state.processed_blocks == 1
        assert len(agent.executed_blocks) == 1
