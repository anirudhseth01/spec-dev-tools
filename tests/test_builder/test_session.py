"""Tests for session data structures and serialization."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    ResearchDepth,
    Decision,
    Option,
    BlockDesign,
    HierarchyDesign,
    ExecutionProgress,
    DISCUSSION_TOPICS,
)


class TestOption:
    """Tests for Option dataclass."""

    def test_option_creation(self):
        """Test basic option creation."""
        option = Option(
            id="opt-1",
            label="Option 1",
            description="First option",
            pros=["Pro 1", "Pro 2"],
            cons=["Con 1"],
            recommendation_score=0.8,
        )

        assert option.id == "opt-1"
        assert option.label == "Option 1"
        assert len(option.pros) == 2
        assert len(option.cons) == 1
        assert option.recommendation_score == 0.8

    def test_option_serialization(self):
        """Test option to_dict and from_dict."""
        option = Option(
            id="opt-1",
            label="Option 1",
            description="First option",
            pros=["Pro 1"],
            cons=["Con 1"],
            recommendation_score=0.7,
        )

        data = option.to_dict()
        restored = Option.from_dict(data)

        assert restored.id == option.id
        assert restored.label == option.label
        assert restored.pros == option.pros
        assert restored.recommendation_score == option.recommendation_score

    def test_option_default_values(self):
        """Test option default values."""
        option = Option(id="opt-1", label="Label", description="Desc")

        assert option.pros == []
        assert option.cons == []
        assert option.recommendation_score == 0.5


class TestDecision:
    """Tests for Decision dataclass."""

    def test_decision_creation(self):
        """Test basic decision creation."""
        decision = Decision(
            id="dec-1",
            topic="Architecture",
            question="What architecture?",
        )

        assert decision.id == "dec-1"
        assert decision.topic == "Architecture"
        assert not decision.is_decided
        assert decision.selected_option is None

    def test_decision_with_selection(self):
        """Test decision with selected option."""
        options = [
            Option("opt-a", "Option A", "First"),
            Option("opt-b", "Option B", "Second"),
        ]
        decision = Decision(
            id="dec-1",
            topic="Architecture",
            question="What architecture?",
            options=options,
            selected_option_id="opt-a",
        )

        assert decision.is_decided
        assert decision.selected_option is not None
        assert decision.selected_option.label == "Option A"

    def test_decision_serialization(self):
        """Test decision serialization."""
        options = [Option("opt-a", "Option A", "First")]
        decision = Decision(
            id="dec-1",
            topic="Tech Stack",
            question="What tech?",
            options=options,
            selected_option_id="opt-a",
            user_notes="Custom note",
        )

        data = decision.to_dict()
        restored = Decision.from_dict(data)

        assert restored.id == decision.id
        assert restored.topic == decision.topic
        assert restored.selected_option_id == decision.selected_option_id
        assert restored.user_notes == decision.user_notes
        assert len(restored.options) == 1


class TestBlockDesign:
    """Tests for BlockDesign dataclass."""

    def test_block_design_creation(self):
        """Test basic block design creation."""
        block = BlockDesign(
            path="system/api",
            name="API Gateway",
            block_type="component",
            description="Handles API requests",
            parent_path="system",
        )

        assert block.path == "system/api"
        assert block.name == "API Gateway"
        assert block.block_type == "component"
        assert block.parent_path == "system"

    def test_block_design_serialization(self):
        """Test block design serialization."""
        block = BlockDesign(
            path="system/api",
            name="API",
            block_type="component",
            description="API component",
            parent_path="system",
            tech_stack="Python",
            dependencies=["system/core"],
            api_endpoints=[{"method": "GET", "path": "/health"}],
        )

        data = block.to_dict()
        restored = BlockDesign.from_dict(data)

        assert restored.path == block.path
        assert restored.tech_stack == block.tech_stack
        assert restored.dependencies == block.dependencies
        assert len(restored.api_endpoints) == 1


class TestHierarchyDesign:
    """Tests for HierarchyDesign dataclass."""

    def test_hierarchy_design_creation(self, sample_hierarchy):
        """Test hierarchy design creation."""
        assert sample_hierarchy.root_name == "test-system"
        assert len(sample_hierarchy.blocks) == 3

    def test_hierarchy_root_block(self, sample_hierarchy):
        """Test getting root block."""
        root = sample_hierarchy.root_block
        assert root is not None
        assert root.block_type == "root"
        assert root.path == "test-system"

    def test_hierarchy_get_block(self, sample_hierarchy):
        """Test getting block by path."""
        api = sample_hierarchy.get_block("test-system/api")
        assert api is not None
        assert api.name == "API Gateway"

        missing = sample_hierarchy.get_block("not-exists")
        assert missing is None

    def test_hierarchy_get_children(self, sample_hierarchy):
        """Test getting child blocks."""
        children = sample_hierarchy.get_children("test-system")
        assert len(children) == 2
        paths = [c.path for c in children]
        assert "test-system/api" in paths
        assert "test-system/core" in paths

    def test_hierarchy_get_leaves(self, sample_hierarchy):
        """Test getting leaf blocks."""
        # Add a leaf block
        sample_hierarchy.blocks.append(
            BlockDesign(
                path="test-system/core/util",
                name="Util",
                block_type="leaf",
                description="Utility",
                parent_path="test-system/core",
            )
        )

        leaves = sample_hierarchy.get_leaves()
        assert len(leaves) == 1
        assert leaves[0].path == "test-system/core/util"

    def test_hierarchy_serialization(self, sample_hierarchy):
        """Test hierarchy serialization."""
        data = sample_hierarchy.to_dict()
        restored = HierarchyDesign.from_dict(data)

        assert restored.root_name == sample_hierarchy.root_name
        assert len(restored.blocks) == len(sample_hierarchy.blocks)


class TestExecutionProgress:
    """Tests for ExecutionProgress dataclass."""

    def test_progress_creation(self):
        """Test basic progress creation."""
        progress = ExecutionProgress(
            total_blocks=5,
            completed_blocks=2,
            current_block="test/block",
            block_statuses={"test/block": "running"},
        )

        assert progress.total_blocks == 5
        assert progress.completed_blocks == 2
        assert progress.progress_percent == 40.0
        assert not progress.is_complete

    def test_progress_complete(self):
        """Test progress completion detection."""
        progress = ExecutionProgress(
            total_blocks=3,
            completed_blocks=3,
        )

        assert progress.is_complete
        assert progress.progress_percent == 100.0

    def test_progress_serialization(self):
        """Test progress serialization."""
        progress = ExecutionProgress(
            total_blocks=5,
            completed_blocks=2,
            block_statuses={"a": "completed", "b": "running"},
            errors=[{"block": "c", "errors": ["Error 1"]}],
        )

        data = progress.to_dict()
        restored = ExecutionProgress.from_dict(data)

        assert restored.total_blocks == progress.total_blocks
        assert restored.completed_blocks == progress.completed_blocks
        assert restored.block_statuses == progress.block_statuses


class TestBuilderSession:
    """Tests for BuilderSession dataclass."""

    def test_session_creation(self, sample_session):
        """Test basic session creation."""
        assert sample_session.id == "bs-test123"
        assert sample_session.name == "Test System"
        assert sample_session.phase == SessionPhase.DISCUSSION
        assert sample_session.research_depth == ResearchDepth.MEDIUM

    def test_session_id_generation(self):
        """Test automatic session ID generation."""
        session = BuilderSession(name="Test")
        assert session.id.startswith("bs-")
        assert len(session.id) == 11  # "bs-" + 8 chars

    def test_session_current_topic(self, sample_session):
        """Test current topic tracking."""
        topic = sample_session.current_topic
        assert topic is not None
        assert topic["id"] == "problem_scope"

        sample_session.current_topic_index = 2
        topic = sample_session.current_topic
        assert topic["id"] == "tech_stack"

    def test_session_is_discussion_complete(self, sample_session):
        """Test discussion completion detection."""
        assert not sample_session.is_discussion_complete

        sample_session.current_topic_index = len(DISCUSSION_TOPICS)
        assert sample_session.is_discussion_complete

    def test_session_add_decision(self, sample_session):
        """Test adding decisions."""
        decision = Decision(
            id="dec-1",
            topic="Test Topic",
            question="Test question?",
        )

        sample_session.add_decision(decision)

        assert len(sample_session.decisions) == 1
        assert sample_session.decisions[0].topic == "Test Topic"

    def test_session_get_decision(self, session_with_decisions):
        """Test getting decision by topic."""
        decision = session_with_decisions.get_decision("Architecture")
        assert decision is not None
        assert decision.selected_option_id == "arch-mono"

        missing = session_with_decisions.get_decision("Not Exists")
        assert missing is None

    def test_session_advance_topic(self, sample_session):
        """Test advancing to next topic."""
        assert sample_session.current_topic_index == 0

        sample_session.advance_topic()
        assert sample_session.current_topic_index == 1

    def test_session_transition(self, sample_session):
        """Test phase transitions."""
        assert sample_session.phase == SessionPhase.DISCUSSION

        sample_session.transition_to(SessionPhase.DESIGN)
        assert sample_session.phase == SessionPhase.DESIGN

        sample_session.transition_to(SessionPhase.REVIEW)
        assert sample_session.phase == SessionPhase.REVIEW

    def test_session_serialization(self, session_with_hierarchy):
        """Test full session serialization."""
        data = session_with_hierarchy.to_dict()
        restored = BuilderSession.from_dict(data)

        assert restored.id == session_with_hierarchy.id
        assert restored.name == session_with_hierarchy.name
        assert restored.phase == session_with_hierarchy.phase
        assert len(restored.decisions) == len(session_with_hierarchy.decisions)
        assert restored.hierarchy_design is not None
        assert len(restored.hierarchy_design.blocks) == len(
            session_with_hierarchy.hierarchy_design.blocks
        )

    def test_session_string_enum_conversion(self):
        """Test that string enum values are converted properly."""
        data = {
            "id": "bs-test",
            "name": "Test",
            "phase": "discussion",  # String value
            "research_depth": "medium",  # String value
            "decisions": [],
            "current_topic_index": 0,
            "execution_progress": {},
            "deployment_scope": "configs",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        session = BuilderSession.from_dict(data)

        assert session.phase == SessionPhase.DISCUSSION
        assert session.research_depth == ResearchDepth.MEDIUM
