"""Execution orchestrator for parallel block implementation.

The ExecutionOrchestrator handles the autonomous execution phase,
running implementation for all blocks in parallel where possible.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.builder.session import (
    BuilderSession,
    BlockDesign,
    HierarchyDesign,
    ExecutionProgress,
    SessionPhase,
)
from src.llm.client import LLMClient


@dataclass
class BlockResult:
    """Result of executing a single block."""

    block_path: str
    success: bool = True
    message: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "block_path": self.block_path,
            "success": self.success,
            "message": self.message,
            "artifacts": self.artifacts,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ExecutionResult:
    """Result of the complete execution."""

    success: bool = True
    total_blocks: int = 0
    successful_blocks: int = 0
    failed_blocks: int = 0
    block_results: list[BlockResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "total_blocks": self.total_blocks,
            "successful_blocks": self.successful_blocks,
            "failed_blocks": self.failed_blocks,
            "block_results": [r.to_dict() for r in self.block_results],
            "total_duration_seconds": self.total_duration_seconds,
            "errors": self.errors,
        }


class ExecutionOrchestrator:
    """Orchestrates parallel execution of block implementations.

    Builds a DAG from the hierarchy and executes blocks in levels,
    respecting dependencies while maximizing parallelism.
    """

    def __init__(
        self,
        session: BuilderSession,
        project_root: Path,
        llm_client: LLMClient | None = None,
        max_workers: int = 4,
    ):
        """Initialize the orchestrator.

        Args:
            session: The builder session.
            project_root: Project root directory.
            llm_client: LLM client for code generation.
            max_workers: Maximum parallel workers.
        """
        self.session = session
        self.project_root = Path(project_root)
        self.llm_client = llm_client
        self.max_workers = max_workers

        # Callbacks
        self._on_block_start: Callable[[str], None] | None = None
        self._on_block_complete: Callable[[str, BlockResult], None] | None = None
        self._on_progress: Callable[[ExecutionProgress], None] | None = None

    def set_callbacks(
        self,
        on_block_start: Callable[[str], None] | None = None,
        on_block_complete: Callable[[str, BlockResult], None] | None = None,
        on_progress: Callable[[ExecutionProgress], None] | None = None,
    ) -> None:
        """Set execution callbacks.

        Args:
            on_block_start: Called when a block starts execution.
            on_block_complete: Called when a block completes.
            on_progress: Called when progress updates.
        """
        self._on_block_start = on_block_start
        self._on_block_complete = on_block_complete
        self._on_progress = on_progress

    async def execute(self, dry_run: bool = False) -> ExecutionResult:
        """Execute all blocks with parallelization.

        Args:
            dry_run: If True, don't actually write files.

        Returns:
            ExecutionResult with all block results.
        """
        if not self.session.hierarchy_design:
            return ExecutionResult(
                success=False,
                errors=["No hierarchy design in session"],
            )

        hierarchy = self.session.hierarchy_design
        start_time = datetime.now()

        # Transition session to execution phase
        self.session.transition_to(SessionPhase.EXECUTION)

        # Initialize progress
        self.session.execution_progress = ExecutionProgress(
            total_blocks=len(hierarchy.blocks),
            completed_blocks=0,
            block_statuses={b.path: "pending" for b in hierarchy.blocks},
        )

        # Build execution DAG
        levels = self._build_execution_levels(hierarchy)

        result = ExecutionResult(total_blocks=len(hierarchy.blocks))
        all_results: list[BlockResult] = []

        try:
            # Execute level by level
            for level_idx, level_blocks in enumerate(levels):
                level_results = await self._execute_level(
                    level_blocks, level_idx, dry_run
                )
                all_results.extend(level_results)

                # Check for failures
                failures = [r for r in level_results if not r.success]
                if failures:
                    # Stop execution on failures
                    result.success = False
                    for failure in failures:
                        result.errors.append(
                            f"Block {failure.block_path} failed: {failure.message}"
                        )
                    break

            result.block_results = all_results
            result.successful_blocks = sum(1 for r in all_results if r.success)
            result.failed_blocks = sum(1 for r in all_results if not r.success)

            if result.failed_blocks == 0:
                result.success = True
                self.session.transition_to(SessionPhase.COMPLETED)
            else:
                self.session.transition_to(SessionPhase.PAUSED)

        except Exception as e:
            result.success = False
            result.errors.append(f"Execution error: {str(e)}")
            self.session.transition_to(SessionPhase.PAUSED)

        result.total_duration_seconds = (datetime.now() - start_time).total_seconds()
        return result

    def _build_execution_levels(
        self, hierarchy: HierarchyDesign
    ) -> list[list[BlockDesign]]:
        """Build execution levels based on dependencies.

        Blocks with no dependencies (or only completed dependencies) go first.
        Returns a list of levels, each containing blocks that can run in parallel.

        Args:
            hierarchy: The hierarchy design.

        Returns:
            List of levels, each containing blocks to execute in parallel.
        """
        # Build dependency map
        dep_map: dict[str, list[str]] = {}
        block_map: dict[str, BlockDesign] = {}

        for block in hierarchy.blocks:
            block_map[block.path] = block
            dep_map[block.path] = list(block.dependencies)

            # Add parent as dependency (children depend on parent)
            if block.parent_path:
                dep_map[block.path].append(block.parent_path)

        # Topological sort into levels
        levels: list[list[BlockDesign]] = []
        completed: set[str] = set()
        remaining = set(block_map.keys())

        while remaining:
            # Find blocks with all dependencies satisfied
            level_paths = [
                path
                for path in remaining
                if all(dep in completed for dep in dep_map[path])
            ]

            if not level_paths:
                # Circular dependency or error - execute remaining anyway
                level_paths = list(remaining)

            levels.append([block_map[path] for path in level_paths])
            completed.update(level_paths)
            remaining -= set(level_paths)

        return levels

    async def _execute_level(
        self, blocks: list[BlockDesign], level_idx: int, dry_run: bool
    ) -> list[BlockResult]:
        """Execute a level of blocks in parallel.

        Args:
            blocks: Blocks to execute.
            level_idx: Index of the level.
            dry_run: If True, don't actually write files.

        Returns:
            List of block results.
        """
        results: list[BlockResult] = []

        # Update status to running
        for block in blocks:
            self.session.execution_progress.block_statuses[block.path] = "running"
            self.session.execution_progress.current_block = block.path
            if self._on_block_start:
                self._on_block_start(block.path)
            if self._on_progress:
                self._on_progress(self.session.execution_progress)

        # Execute blocks in parallel using thread pool
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor, self._execute_block_sync, block, dry_run
                )
                for block in blocks
            ]
            results = await asyncio.gather(*futures)

        # Update progress
        for block, result in zip(blocks, results):
            status = "completed" if result.success else "failed"
            self.session.execution_progress.block_statuses[block.path] = status

            if result.success:
                self.session.execution_progress.completed_blocks += 1
            else:
                self.session.execution_progress.errors.append(
                    {"block": block.path, "errors": result.errors}
                )

            if self._on_block_complete:
                self._on_block_complete(block.path, result)
            if self._on_progress:
                self._on_progress(self.session.execution_progress)

        return results

    def _execute_block_sync(
        self, block: BlockDesign, dry_run: bool
    ) -> BlockResult:
        """Execute a single block (synchronous version for thread pool).

        Args:
            block: The block to execute.
            dry_run: If True, don't actually write files.

        Returns:
            BlockResult with execution outcome.
        """
        start_time = datetime.now()

        try:
            # Try to use the existing FlowOrchestrator
            result = self._execute_with_flow_orchestrator(block, dry_run)
        except Exception as e:
            # Fallback to basic execution
            result = self._execute_basic(block, dry_run)
            if not result.success and not result.errors:
                result.errors.append(str(e))

        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result

    def _execute_with_flow_orchestrator(
        self, block: BlockDesign, dry_run: bool
    ) -> BlockResult:
        """Execute using the existing FlowOrchestrator.

        Args:
            block: The block to execute.
            dry_run: If True, don't actually write files.

        Returns:
            BlockResult with execution outcome.
        """
        try:
            from src.spec.parser import BlockParser
            from src.orchestration.flow_orchestrator import create_standard_flow

            specs_dir = self.project_root / self.session.specs_dir
            block_file = specs_dir / block.path / "block.md"

            if not block_file.exists():
                return BlockResult(
                    block_path=block.path,
                    success=False,
                    message=f"Block spec not found: {block_file}",
                    errors=[f"File not found: {block_file}"],
                )

            # Parse the block spec
            parser = BlockParser(specs_dir)
            block_spec = parser.parse_block(block_file)

            # Build agent pipeline
            agents = self._build_agent_pipeline(dry_run)

            if not agents:
                return BlockResult(
                    block_path=block.path,
                    success=True,
                    message="No agents available, skipping execution",
                )

            # Create and run orchestrator
            orchestrator = create_standard_flow(
                block_spec.spec, self.project_root, agents
            )
            state = orchestrator.execute()

            # Collect results
            files_created = []
            files_modified = []
            errors = []

            for agent_name in state.completed_agents:
                artifact = state.get_artifact(agent_name)
                if artifact:
                    files_created.extend(artifact.get("files_created", []))
                    files_modified.extend(artifact.get("files_modified", []))

            for agent_name in state.failed_agents:
                errors.append(f"Agent {agent_name} failed")

            return BlockResult(
                block_path=block.path,
                success=len(state.failed_agents) == 0,
                message="Execution completed"
                if not state.failed_agents
                else "Some agents failed",
                artifacts=state.artifacts,
                files_created=files_created,
                files_modified=files_modified,
                errors=errors,
            )

        except ImportError:
            # FlowOrchestrator not available, use basic execution
            return self._execute_basic(block, dry_run)
        except Exception as e:
            return BlockResult(
                block_path=block.path,
                success=False,
                message=f"Execution failed: {str(e)}",
                errors=[str(e)],
            )

    def _execute_basic(self, block: BlockDesign, dry_run: bool) -> BlockResult:
        """Basic execution without FlowOrchestrator.

        Args:
            block: The block to execute.
            dry_run: If True, don't actually write files.

        Returns:
            BlockResult with execution outcome.
        """
        # Check if block spec exists
        specs_dir = self.project_root / self.session.specs_dir
        block_file = specs_dir / block.path / "block.md"

        if not block_file.exists():
            return BlockResult(
                block_path=block.path,
                success=False,
                message=f"Block spec not found: {block_file}",
                errors=[f"File not found: {block_file}"],
            )

        if dry_run:
            return BlockResult(
                block_path=block.path,
                success=True,
                message="Dry run - would execute implementation",
            )

        # For now, just report success if spec exists
        # Full implementation would generate code here
        return BlockResult(
            block_path=block.path,
            success=True,
            message="Block spec exists, ready for implementation",
        )

    def _build_agent_pipeline(self, dry_run: bool) -> list:
        """Build the agent pipeline for execution.

        Args:
            dry_run: If True, configure agents for dry run.

        Returns:
            List of agent instances.
        """
        agents = []

        try:
            from src.agents.coding import CodingAgent

            agents.append(CodingAgent(llm_client=self.llm_client, dry_run=dry_run))
        except ImportError:
            pass

        try:
            from src.agents.testing import TestGeneratorAgent

            agents.append(TestGeneratorAgent(llm_client=self.llm_client, dry_run=dry_run))
        except ImportError:
            pass

        try:
            from src.agents.security import SecurityScanAgent, ScanMode

            agents.append(SecurityScanAgent(mode=ScanMode.LIGHTWEIGHT))
        except ImportError:
            pass

        try:
            from src.agents.review import CodeReviewAgent

            agents.append(CodeReviewAgent(llm_client=self.llm_client))
        except ImportError:
            pass

        return agents

    def get_execution_dag(self) -> dict[str, Any]:
        """Get the execution DAG for visualization.

        Returns:
            Dict with nodes and edges for DAG visualization.
        """
        if not self.session.hierarchy_design:
            return {"nodes": [], "edges": []}

        hierarchy = self.session.hierarchy_design
        nodes = []
        edges = []

        for block in hierarchy.blocks:
            status = self.session.execution_progress.block_statuses.get(
                block.path, "pending"
            )
            nodes.append(
                {
                    "id": block.path,
                    "name": block.name,
                    "type": block.block_type,
                    "status": status,
                }
            )

            # Add edges for dependencies
            for dep in block.dependencies:
                edges.append({"from": dep, "to": block.path})

            # Add edge from parent
            if block.parent_path:
                edges.append({"from": block.parent_path, "to": block.path})

        return {"nodes": nodes, "edges": edges}
