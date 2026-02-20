"""Integration tests for the complete builder flow."""

from __future__ import annotations

from pathlib import Path

import pytest
import asyncio

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    ResearchDepth,
    Decision,
    Option,
    BlockDesign,
    HierarchyDesign,
)
from src.builder.persistence import SessionPersistence
from src.builder.discussion import DiscussionEngine, DiscussionAction
from src.builder.designer import BlockDesigner
from src.builder.generator import SpecGenerator


class TestSessionPersistence:
    """Tests for session persistence."""

    def test_save_and_load_session(self, temp_project_dir):
        """Test saving and loading a session."""
        persistence = SessionPersistence(temp_project_dir)

        session = BuilderSession(
            name="Test Session",
            initial_description="Testing persistence",
            project_root=str(temp_project_dir),
        )

        # Save
        persistence.save(session)

        # Load
        loaded = persistence.load(session.id)

        assert loaded is not None
        assert loaded.name == "Test Session"
        assert loaded.initial_description == "Testing persistence"

    def test_list_sessions(self, temp_project_dir):
        """Test listing multiple sessions."""
        persistence = SessionPersistence(temp_project_dir)

        # Create sessions
        for i in range(3):
            session = BuilderSession(
                name=f"Session {i}",
                project_root=str(temp_project_dir),
            )
            persistence.save(session)

        # List
        sessions = persistence.list_sessions()
        assert len(sessions) == 3

    def test_delete_session(self, temp_project_dir):
        """Test deleting a session."""
        persistence = SessionPersistence(temp_project_dir)

        session = BuilderSession(
            name="To Delete",
            project_root=str(temp_project_dir),
        )
        persistence.save(session)

        # Verify exists
        assert persistence.exists(session.id)

        # Delete
        result = persistence.delete(session.id)
        assert result is True

        # Verify deleted
        assert not persistence.exists(session.id)

    def test_get_latest_session(self, temp_project_dir):
        """Test getting most recent session."""
        persistence = SessionPersistence(temp_project_dir)

        # Create multiple sessions
        for name in ["First", "Second", "Third"]:
            session = BuilderSession(
                name=name,
                project_root=str(temp_project_dir),
            )
            persistence.save(session)

        latest = persistence.get_latest_session()
        assert latest is not None

    def test_session_with_decisions(self, temp_project_dir):
        """Test persistence with decisions."""
        persistence = SessionPersistence(temp_project_dir)

        session = BuilderSession(
            name="With Decisions",
            project_root=str(temp_project_dir),
        )

        session.add_decision(
            Decision(
                id="dec-1",
                topic="Test",
                question="Question?",
                options=[Option("opt-1", "Option", "Description")],
                selected_option_id="opt-1",
            )
        )

        persistence.save(session)

        loaded = persistence.load(session.id)
        assert len(loaded.decisions) == 1
        assert loaded.decisions[0].is_decided


class TestDesignWorkflow:
    """Tests for the design workflow."""

    def test_designer_from_decisions(self, session_with_decisions):
        """Test designing hierarchy from decisions."""
        designer = BlockDesigner(None)

        hierarchy = asyncio.run(designer.design_hierarchy(session_with_decisions))

        assert hierarchy is not None
        assert hierarchy.root_name
        assert len(hierarchy.blocks) >= 1

    def test_generator_from_hierarchy(self, session_with_hierarchy):
        """Test generating specs from hierarchy."""
        generator = SpecGenerator(None)

        specs = asyncio.run(
            generator.generate_all_specs(
                session_with_hierarchy.hierarchy_design, session_with_hierarchy
            )
        )

        assert len(specs) == len(session_with_hierarchy.hierarchy_design.blocks)

    def test_write_specs_to_disk(self, session_with_hierarchy, temp_project_dir):
        """Test writing generated specs to disk."""
        generator = SpecGenerator(None)

        specs = asyncio.run(
            generator.generate_all_specs(
                session_with_hierarchy.hierarchy_design, session_with_hierarchy
            )
        )

        created_files = asyncio.run(generator.write_specs(specs, temp_project_dir))

        assert len(created_files) == len(specs)
        for f in created_files:
            assert Path(f).exists()


class TestDiscussionWorkflow:
    """Tests for the discussion workflow."""

    def test_discussion_flow(self, sample_session):
        """Test a simple discussion flow."""
        engine = DiscussionEngine(sample_session, None)

        # Start
        result = asyncio.run(engine.start_discussion())
        assert "Problem & Scope" in result

        # Answer first question
        result = asyncio.run(engine.process_response("1"))
        assert result.action in [DiscussionAction.NEXT_TOPIC, DiscussionAction.CONTINUE]

        # Session should have recorded decision
        assert len(sample_session.decisions) >= 1

    def test_discussion_records_decisions(self, sample_session):
        """Test that discussion records all decisions."""
        engine = DiscussionEngine(sample_session, None)

        asyncio.run(engine.start_discussion())

        # Answer 3 questions
        for _ in range(3):
            result = asyncio.run(engine.process_response("1"))
            if result.action == DiscussionAction.COMPLETE:
                break

        # Should have multiple decisions
        assert len(sample_session.decisions) >= 1


class TestEndToEnd:
    """End-to-end workflow tests."""

    def test_session_creation_to_design(self, temp_project_dir):
        """Test from session creation through design."""
        # Create session
        session = BuilderSession(
            name="E2E Test",
            initial_description="End to end test system",
            project_root=str(temp_project_dir),
        )

        # Simulate a few decisions
        for topic in ["Problem & Scope", "Architecture"]:
            session.add_decision(
                Decision(
                    id=f"dec-{topic}",
                    topic=topic,
                    question=f"Question about {topic}?",
                    options=[
                        Option("opt-1", "Option 1", "First option"),
                        Option("opt-2", "Option 2", "Second option"),
                    ],
                    selected_option_id="opt-1",
                )
            )

        # Design hierarchy
        designer = BlockDesigner(None)
        hierarchy = asyncio.run(designer.design_hierarchy(session))

        assert hierarchy is not None
        session.hierarchy_design = hierarchy
        session.transition_to(SessionPhase.REVIEW)

        # Generate specs
        generator = SpecGenerator(None)
        specs = asyncio.run(generator.generate_all_specs(hierarchy, session))

        assert len(specs) == len(hierarchy.blocks)

        # Write to disk
        created = asyncio.run(generator.write_specs(specs, temp_project_dir))

        for f in created:
            assert Path(f).exists()

    def test_spec_file_structure(self, session_with_hierarchy, temp_project_dir):
        """Test that generated specs have correct structure."""
        generator = SpecGenerator(None)

        specs = asyncio.run(
            generator.generate_all_specs(
                session_with_hierarchy.hierarchy_design, session_with_hierarchy
            )
        )

        asyncio.run(generator.write_specs(specs, temp_project_dir))

        for block in session_with_hierarchy.hierarchy_design.blocks:
            spec_file = temp_project_dir / "specs" / block.path / "block.md"
            assert spec_file.exists()

            content = spec_file.read_text()

            # Check required sections
            assert "# Block Specification" in content
            assert "## 0. Block Configuration" in content
            assert "## 1. Metadata" in content
            assert f"block_type: {block.block_type}" in content
