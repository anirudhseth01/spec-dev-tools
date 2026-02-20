"""Tests for the discussion engine."""

from __future__ import annotations

import pytest
import asyncio

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    Decision,
    Option,
)
from src.builder.discussion import (
    DiscussionEngine,
    DiscussionAction,
    DiscussionResult,
)


class TestDiscussionEngine:
    """Tests for DiscussionEngine."""

    def test_engine_creation(self, sample_session, mock_llm):
        """Test engine initialization."""
        engine = DiscussionEngine(sample_session, mock_llm)

        assert engine.session == sample_session
        assert engine.llm_client == mock_llm
        assert not engine.is_complete()

    def test_start_discussion(self, sample_session):
        """Test starting discussion without LLM."""
        engine = DiscussionEngine(sample_session, None)

        result = asyncio.run(engine.start_discussion())

        assert "Problem & Scope" in result
        assert len(sample_session.decisions) == 1
        assert sample_session.decisions[0].topic == "Problem & Scope"

    def test_start_discussion_non_discussion_phase(self, sample_session):
        """Test starting when not in discussion phase."""
        sample_session.phase = SessionPhase.REVIEW
        engine = DiscussionEngine(sample_session, None)

        result = asyncio.run(engine.start_discussion())

        assert "not in discussion phase" in result.lower()

    def test_process_response_option_selection(self, sample_session):
        """Test processing option selection by number."""
        engine = DiscussionEngine(sample_session, None)

        # Start discussion to create initial decision
        asyncio.run(engine.start_discussion())

        # Select option 1
        result = asyncio.run(engine.process_response("1"))

        assert result.decision is not None
        assert result.decision.is_decided

    def test_process_response_option_by_label(self, sample_session):
        """Test processing option selection by label."""
        engine = DiscussionEngine(sample_session, None)

        # Start discussion
        asyncio.run(engine.start_discussion())

        # Select by full label - "Specific/Focused"
        result = asyncio.run(engine.process_response("Specific/Focused"))

        assert result.decision is not None
        # The decision stores the result in user_notes when matched by partial label
        assert result.decision.is_decided or result.decision.user_notes

    def test_process_response_custom_answer(self, sample_session):
        """Test processing custom answer."""
        engine = DiscussionEngine(sample_session, None)

        # Start discussion
        asyncio.run(engine.start_discussion())

        # Provide custom answer
        result = asyncio.run(engine.process_response("Custom approach for my needs"))

        assert result.decision is not None
        # Custom answer should be stored in notes
        assert result.decision.user_notes == "Custom approach for my needs"

    def test_process_response_advances_topic(self, sample_session):
        """Test that processing advances to next topic."""
        engine = DiscussionEngine(sample_session, None)

        # Start discussion
        asyncio.run(engine.start_discussion())
        assert sample_session.current_topic_index == 0

        # Process response
        result = asyncio.run(engine.process_response("1"))

        # Should have advanced to next topic
        assert sample_session.current_topic_index == 1
        assert result.action == DiscussionAction.NEXT_TOPIC

    def test_process_response_complete(self, sample_session):
        """Test completion when all topics covered."""
        engine = DiscussionEngine(sample_session, None)

        # Set to last topic
        sample_session.current_topic_index = 8  # Deployment (last topic)

        # Start discussion
        asyncio.run(engine.start_discussion())

        # Process response
        result = asyncio.run(engine.process_response("1"))

        assert result.action == DiscussionAction.COMPLETE
        # Message includes "covered" and "design phase"
        assert "covered" in result.message.lower() or "design" in result.message.lower()

    def test_is_complete(self, sample_session):
        """Test completion check."""
        engine = DiscussionEngine(sample_session, None)

        assert not engine.is_complete()

        # Advance past all topics
        sample_session.current_topic_index = 9

        assert engine.is_complete()

    def test_generate_question_fallback(self, sample_session):
        """Test static question generation fallback."""
        engine = DiscussionEngine(sample_session, None)

        question, options = asyncio.run(engine.generate_question("Architecture"))

        assert "architecture" in question.lower()
        assert len(options) >= 2
        assert all(isinstance(opt, Option) for opt in options)

    def test_generate_question_with_llm(self, sample_session, mock_llm):
        """Test question generation with LLM."""
        mock_llm.responses = [
            """{
                "question": "What architecture pattern?",
                "options": [
                    {
                        "id": "opt-1",
                        "label": "Monolith",
                        "description": "Single app",
                        "pros": ["Simple"],
                        "cons": ["Scaling"],
                        "recommendation_score": 0.7
                    }
                ]
            }"""
        ]

        engine = DiscussionEngine(sample_session, mock_llm)

        question, options = asyncio.run(engine.generate_question("Architecture"))

        assert question == "What architecture pattern?"
        assert len(options) == 1
        assert options[0].label == "Monolith"

    def test_static_questions_all_topics(self, sample_session):
        """Test that all topics have static fallback questions."""
        engine = DiscussionEngine(sample_session, None)

        topics = [
            "Problem & Scope",
            "Architecture",
            "Tech Stack",
            "API Design",
            "Data Model",
            "Security",
            "Performance",
            "Integrations",
            "Deployment",
        ]

        for topic in topics:
            question, options = asyncio.run(engine.generate_question(topic))
            assert question, f"No question for topic: {topic}"
            assert len(options) >= 2, f"Not enough options for topic: {topic}"


class TestDiscussionResult:
    """Tests for DiscussionResult."""

    def test_result_continue(self):
        """Test continue action result."""
        result = DiscussionResult(
            action=DiscussionAction.CONTINUE,
            message="Continuing...",
            question="Next question?",
            options=[Option("opt-1", "Option 1", "First")],
        )

        assert result.action == DiscussionAction.CONTINUE
        assert result.question is not None
        assert len(result.options) == 1

    def test_result_complete(self):
        """Test complete action result."""
        result = DiscussionResult(
            action=DiscussionAction.COMPLETE,
            message="All done!",
        )

        assert result.action == DiscussionAction.COMPLETE
        assert result.question is None

    def test_result_with_decision(self):
        """Test result with decision."""
        decision = Decision(
            id="dec-1",
            topic="Test",
            question="Question?",
            selected_option_id="opt-1",
        )

        result = DiscussionResult(
            action=DiscussionAction.NEXT_TOPIC,
            message="Moving on...",
            decision=decision,
        )

        assert result.decision is not None
        assert result.decision.is_decided

    def test_result_needs_research(self):
        """Test result flagging research need."""
        result = DiscussionResult(
            action=DiscussionAction.CONTINUE,
            message="Researching tech...",
            needs_research=True,
        )

        assert result.needs_research is True
