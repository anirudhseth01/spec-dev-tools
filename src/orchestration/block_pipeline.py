"""Block pipeline for hierarchical spec processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

from src.agents.base import AgentContext, AgentResult, AgentStatus, BaseAgent
from src.orchestration.pipeline import Pipeline
from src.orchestration.state import PipelineState, PipelineStatus
from src.rules.engine import RulesEngine

if TYPE_CHECKING:
    from src.spec.block import BlockSpec


class ProcessingOrder(Enum):
    """Order in which to process blocks in the hierarchy."""

    BOTTOM_UP = "bottom-up"  # Process leaves first, then up to root
    TOP_DOWN = "top-down"  # Process root first, then down to leaves


@dataclass
class BlockPipelineResult:
    """Result of processing a single block."""

    block_path: str
    pipeline_state: PipelineState
    success: bool
    context_for_children: dict[str, Any] = field(default_factory=dict)


@dataclass
class HierarchyPipelineState:
    """State of the entire hierarchy pipeline execution."""

    root_path: str
    order: ProcessingOrder
    status: PipelineStatus = PipelineStatus.PENDING
    block_results: dict[str, BlockPipelineResult] = field(default_factory=dict)
    total_blocks: int = 0
    processed_blocks: int = 0
    failed_blocks: int = 0

    def get_summary(self) -> dict[str, Any]:
        """Get summary of hierarchy pipeline state."""
        return {
            "root_path": self.root_path,
            "order": self.order.value,
            "status": self.status.value,
            "total_blocks": self.total_blocks,
            "processed_blocks": self.processed_blocks,
            "failed_blocks": self.failed_blocks,
            "success_rate": (
                (self.processed_blocks - self.failed_blocks) / self.total_blocks
                if self.total_blocks > 0
                else 0
            ),
        }


class BlockPipeline:
    """Pipeline for processing hierarchical block specifications.

    Processes blocks in either bottom-up (leaves first) or top-down
    (root first) order, passing context between parent and child blocks.
    """

    def __init__(
        self,
        blocks: list[BlockSpec],
        project_root: Path | str,
        agents: list[BaseAgent] | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        parallel_siblings: bool = False,
    ) -> None:
        """Initialize the block pipeline.

        Args:
            blocks: List of all blocks in the hierarchy.
            project_root: Root directory of the project.
            agents: List of agents to run for each block.
            dry_run: If True, don't make actual changes.
            verbose: If True, output detailed progress.
            parallel_siblings: If True, process siblings in parallel.
        """
        self.blocks = blocks
        self.project_root = Path(project_root)
        self.agents = agents or []
        self.dry_run = dry_run
        self.verbose = verbose
        self.parallel_siblings = parallel_siblings

        # Build block lookup
        self._blocks_by_path = {block.path: block for block in blocks}

        # Initialize rules engine
        self._rules_engine = RulesEngine(self.project_root)

        # State
        self.state = HierarchyPipelineState(
            root_path=blocks[0].path if blocks else "",
            order=ProcessingOrder.BOTTOM_UP,
            total_blocks=len(blocks),
        )

    def run(
        self,
        order: ProcessingOrder = ProcessingOrder.BOTTOM_UP,
    ) -> HierarchyPipelineState:
        """Execute the pipeline on all blocks.

        Args:
            order: Order in which to process blocks.

        Returns:
            Final hierarchy pipeline state.
        """
        self.state.order = order
        self.state.status = PipelineStatus.RUNNING

        # Get blocks in processing order
        ordered_levels = self._get_ordered_blocks(order)

        # Process each level
        for level_blocks in ordered_levels:
            for block in level_blocks:
                # Get parent context if available
                parent_context = self._get_parent_context(block, order)

                # Process the block
                result = self._process_block(block, parent_context)
                self.state.block_results[block.path] = result
                self.state.processed_blocks += 1

                if not result.success:
                    self.state.failed_blocks += 1

        # Determine final status
        if self.state.failed_blocks == 0:
            self.state.status = PipelineStatus.SUCCESS
        else:
            self.state.status = PipelineStatus.FAILED

        return self.state

    def _get_ordered_blocks(self, order: ProcessingOrder) -> list[list[BlockSpec]]:
        """Get blocks grouped by depth level in processing order.

        Args:
            order: Processing order.

        Returns:
            List of lists, where each inner list contains blocks at the same depth.
        """
        if not self.blocks:
            return []

        # Group blocks by depth
        by_depth: dict[int, list[BlockSpec]] = {}
        for block in self.blocks:
            depth = block.depth
            if depth not in by_depth:
                by_depth[depth] = []
            by_depth[depth].append(block)

        # Sort depths
        depths = sorted(by_depth.keys())

        if order == ProcessingOrder.BOTTOM_UP:
            # Deepest first
            depths = list(reversed(depths))

        # Return blocks grouped by level
        return [by_depth[d] for d in depths]

    def _get_parent_context(
        self, block: BlockSpec, order: ProcessingOrder
    ) -> dict[str, Any]:
        """Get context from parent block if it has been processed.

        Args:
            block: The block to get parent context for.
            order: Processing order.

        Returns:
            Parent context dictionary.
        """
        if order == ProcessingOrder.TOP_DOWN and block.parent:
            # In top-down, parent has already been processed
            parent_result = self.state.block_results.get(block.parent.path)
            if parent_result:
                return parent_result.context_for_children
        elif order == ProcessingOrder.BOTTOM_UP and block.children:
            # In bottom-up, children have already been processed
            # Aggregate context from children
            child_contexts = []
            for child in block.children:
                child_result = self.state.block_results.get(child.path)
                if child_result:
                    child_contexts.append({
                        "path": child.path,
                        "success": child_result.success,
                        "context": child_result.context_for_children,
                    })
            return {"children": child_contexts}

        return {}

    def _process_block(
        self, block: BlockSpec, parent_context: dict[str, Any]
    ) -> BlockPipelineResult:
        """Process a single block using the agent pipeline.

        Args:
            block: The block to process.
            parent_context: Context from parent/children blocks.

        Returns:
            Result of processing the block.
        """
        # Resolve same-as references
        resolved_block = self._rules_engine.resolve_same_as(block, self._blocks_by_path)

        # Get effective rules
        effective_rules = self._rules_engine.get_effective_rules(resolved_block)

        # Validate rules
        violations = self._rules_engine.validate(resolved_block)

        # Check for blocking violations
        has_errors = any(v.rule.severity.value == "error" for v in violations)
        if has_errors and not self.dry_run:
            return BlockPipelineResult(
                block_path=block.path,
                pipeline_state=PipelineState(
                    spec_name=block.name,
                    project_root=self.project_root,
                    block_path=block.path,
                    status=PipelineStatus.FAILED,
                ),
                success=False,
                context_for_children={
                    "errors": [str(v) for v in violations if v.rule.severity.value == "error"]
                },
            )

        # Build branch name
        branch_name = f"block/{block.path.replace('/', '-')}"

        # Create pipeline for this block
        pipeline = Pipeline(
            spec=resolved_block.spec,
            project_root=self.project_root,
            agents=self.agents,
            branch_name=branch_name,
            dry_run=self.dry_run,
            verbose=self.verbose,
        )

        # Update pipeline state with block info
        pipeline.state.block_path = block.path

        # Create context with block info
        context = AgentContext(
            spec=resolved_block.spec,
            project_root=self.project_root,
            branch_name=branch_name,
            dry_run=self.dry_run,
            verbose=self.verbose,
            block=resolved_block,
            parent_context=parent_context,
            effective_rules=effective_rules,
        )

        # Run agents manually to inject custom context
        pipeline.state.mark_started()
        try:
            for agent in self.agents:
                result = self._run_agent_with_context(agent, context, pipeline)
                context.previous_results[agent.name] = result
                if result.status == AgentStatus.FAILED:
                    pipeline.state.mark_completed(success=False)
                    break
            else:
                pipeline.state.mark_completed(success=True)
        except Exception as e:
            pipeline.state.mark_completed(success=False)

        # Build context for children/parent
        context_for_next = {
            "block_path": block.path,
            "branch_name": branch_name,
            "violations": [v.to_dict() for v in violations],
        }

        return BlockPipelineResult(
            block_path=block.path,
            pipeline_state=pipeline.state,
            success=pipeline.state.status == PipelineStatus.SUCCESS,
            context_for_children=context_for_next,
        )

    def _run_agent_with_context(
        self, agent: BaseAgent, context: AgentContext, pipeline: Pipeline
    ) -> AgentResult:
        """Run an agent with the provided context.

        Args:
            agent: The agent to run.
            context: Pre-built context with block info.
            pipeline: Pipeline for state tracking.

        Returns:
            Agent result.
        """
        from datetime import datetime
        from src.orchestration.state import AgentState

        agent_state = pipeline.state.get_agent_state(agent.name)
        if agent_state is None:
            agent_state = AgentState(name=agent.name)
            pipeline.state.set_agent_state(agent.name, agent_state)

        agent_state.status = AgentStatus.RUNNING
        agent_state.started_at = datetime.now()

        can_run, reason = agent.can_run(context)
        if not can_run:
            result = agent.skip(reason)
            agent_state.status = AgentStatus.SKIPPED
            agent_state.completed_at = datetime.now()
            agent_state.result = result
            return result

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

    def get_state(self) -> HierarchyPipelineState:
        """Get current hierarchy pipeline state."""
        return self.state

    def get_summary(self) -> dict[str, Any]:
        """Get summary of hierarchy pipeline execution."""
        return self.state.get_summary()
