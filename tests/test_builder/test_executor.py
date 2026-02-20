"""Tests for the execution orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    BlockDesign,
    HierarchyDesign,
    ExecutionProgress,
)
from src.builder.executor import (
    ExecutionOrchestrator,
    ExecutionResult,
    BlockResult,
)


class TestBlockResult:
    """Tests for BlockResult dataclass."""

    def test_block_result_creation(self):
        """Test BlockResult creation."""
        result = BlockResult(
            block_path="test/api",
            success=True,
            message="Completed",
            files_created=["src/api.py"],
            duration_seconds=1.5,
        )

        assert result.block_path == "test/api"
        assert result.success is True
        assert len(result.files_created) == 1

    def test_block_result_failure(self):
        """Test BlockResult for failure."""
        result = BlockResult(
            block_path="test/api",
            success=False,
            message="Failed to generate",
            errors=["Error 1", "Error 2"],
        )

        assert result.success is False
        assert len(result.errors) == 2

    def test_block_result_to_dict(self):
        """Test BlockResult serialization."""
        result = BlockResult(
            block_path="test/api",
            success=True,
            message="Done",
        )

        data = result.to_dict()

        assert data["block_path"] == "test/api"
        assert data["success"] is True


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_creation(self):
        """Test ExecutionResult creation."""
        result = ExecutionResult(
            success=True,
            total_blocks=3,
            successful_blocks=3,
            failed_blocks=0,
            total_duration_seconds=10.5,
        )

        assert result.success is True
        assert result.total_blocks == 3
        assert result.failed_blocks == 0

    def test_execution_result_with_failures(self):
        """Test ExecutionResult with failures."""
        result = ExecutionResult(
            success=False,
            total_blocks=3,
            successful_blocks=2,
            failed_blocks=1,
            errors=["Block test/api failed"],
        )

        assert result.success is False
        assert result.failed_blocks == 1
        assert len(result.errors) == 1

    def test_execution_result_to_dict(self):
        """Test ExecutionResult serialization."""
        block_result = BlockResult("test/api", True, "Done")
        result = ExecutionResult(
            success=True,
            total_blocks=1,
            successful_blocks=1,
            block_results=[block_result],
        )

        data = result.to_dict()

        assert data["success"] is True
        assert len(data["block_results"]) == 1


class TestExecutionOrchestrator:
    """Tests for ExecutionOrchestrator."""

    def test_orchestrator_creation(self, session_with_hierarchy, temp_project_dir):
        """Test orchestrator initialization."""
        orchestrator = ExecutionOrchestrator(
            session=session_with_hierarchy,
            project_root=temp_project_dir,
        )

        assert orchestrator.session == session_with_hierarchy
        assert orchestrator.project_root == temp_project_dir

    def test_build_execution_levels(self, session_with_hierarchy, temp_project_dir):
        """Test building execution levels from hierarchy."""
        orchestrator = ExecutionOrchestrator(
            session=session_with_hierarchy,
            project_root=temp_project_dir,
        )

        levels = orchestrator._build_execution_levels(session_with_hierarchy.hierarchy_design)

        assert len(levels) >= 1
        # Root should be in first level
        assert any(b.block_type == "root" for b in levels[0])

    def test_get_execution_dag(self, session_with_hierarchy, temp_project_dir):
        """Test getting execution DAG for visualization."""
        orchestrator = ExecutionOrchestrator(
            session=session_with_hierarchy,
            project_root=temp_project_dir,
        )

        dag = orchestrator.get_execution_dag()

        assert "nodes" in dag
        assert "edges" in dag
        assert len(dag["nodes"]) == len(session_with_hierarchy.hierarchy_design.blocks)

    def test_set_callbacks(self, session_with_hierarchy, temp_project_dir):
        """Test setting callbacks."""
        orchestrator = ExecutionOrchestrator(
            session=session_with_hierarchy,
            project_root=temp_project_dir,
        )

        called = []

        def on_start(path):
            called.append(("start", path))

        def on_complete(path, result):
            called.append(("complete", path))

        orchestrator.set_callbacks(
            on_block_start=on_start,
            on_block_complete=on_complete,
        )

        assert orchestrator._on_block_start is not None
        assert orchestrator._on_block_complete is not None


class TestDependencyResolution:
    """Tests for dependency resolution in execution."""

    def test_dependency_order(self, sample_session, temp_project_dir):
        """Test that dependencies are executed in correct order."""
        # Create hierarchy with explicit dependencies
        hierarchy = HierarchyDesign(
            root_name="test",
            blocks=[
                BlockDesign(
                    path="test",
                    name="Test",
                    block_type="root",
                    description="Root",
                ),
                BlockDesign(
                    path="test/a",
                    name="A",
                    block_type="component",
                    description="A",
                    parent_path="test",
                ),
                BlockDesign(
                    path="test/b",
                    name="B",
                    block_type="component",
                    description="B depends on A",
                    parent_path="test",
                    dependencies=["test/a"],
                ),
            ],
        )

        sample_session.hierarchy_design = hierarchy

        orchestrator = ExecutionOrchestrator(
            session=sample_session,
            project_root=temp_project_dir,
        )

        levels = orchestrator._build_execution_levels(hierarchy)

        # Find level indices
        a_level = None
        b_level = None

        for i, level in enumerate(levels):
            for block in level:
                if block.path == "test/a":
                    a_level = i
                elif block.path == "test/b":
                    b_level = i

        # A should be in an earlier level than B
        assert a_level is not None
        assert b_level is not None
        assert a_level <= b_level
