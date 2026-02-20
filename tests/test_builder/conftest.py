"""Pytest fixtures for builder tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest import mock

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
)
from src.llm.client import LLMClient, LLMResponse


class MockLLMClient(LLMClient):
    """Mock LLM client for testing."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or []
        self.call_count = 0
        self.calls: list[dict] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })

        if self.call_count < len(self.responses):
            content = self.responses[self.call_count]
        else:
            content = '{"question": "Test question?", "options": []}'

        self.call_count += 1

        return LLMResponse(
            content=content,
            model="mock-model",
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )

    def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        response = self.generate(system_prompt, user_prompt, max_tokens, temperature)
        yield response.content


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """Create a mock LLM client."""
    return MockLLMClient()


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with .spec-dev."""
    spec_dev = tmp_path / ".spec-dev"
    spec_dev.mkdir()
    specs = tmp_path / "specs"
    specs.mkdir()
    return tmp_path


@pytest.fixture
def sample_session() -> BuilderSession:
    """Create a sample builder session."""
    return BuilderSession(
        id="bs-test123",
        name="Test System",
        phase=SessionPhase.DISCUSSION,
        research_depth=ResearchDepth.MEDIUM,
        initial_description="A test system for unit testing",
        project_root=".",
        specs_dir="specs",
    )


@pytest.fixture
def session_with_decisions() -> BuilderSession:
    """Create a session with some decisions made."""
    session = BuilderSession(
        id="bs-decisions",
        name="Test System",
        phase=SessionPhase.DISCUSSION,
        research_depth=ResearchDepth.MEDIUM,
        initial_description="A test system",
        current_topic_index=2,
    )

    # Add some decisions
    session.decisions = [
        Decision(
            id="dec-001",
            topic="Problem & Scope",
            question="What is the primary problem?",
            options=[
                Option("scope-specific", "Specific", "Focused scope"),
                Option("scope-broad", "Broad", "Wide scope"),
            ],
            selected_option_id="scope-specific",
        ),
        Decision(
            id="dec-002",
            topic="Architecture",
            question="What architecture?",
            options=[
                Option("arch-mono", "Monolith", "Single app"),
                Option("arch-micro", "Microservices", "Distributed"),
            ],
            selected_option_id="arch-mono",
        ),
    ]

    return session


@pytest.fixture
def sample_hierarchy() -> HierarchyDesign:
    """Create a sample hierarchy design."""
    return HierarchyDesign(
        root_name="test-system",
        blocks=[
            BlockDesign(
                path="test-system",
                name="Test System",
                block_type="root",
                description="Root block",
                tech_stack="Python",
            ),
            BlockDesign(
                path="test-system/api",
                name="API Gateway",
                block_type="component",
                description="API component",
                parent_path="test-system",
                tech_stack="Python, FastAPI",
                api_endpoints=[
                    {"method": "GET", "path": "/health"},
                ],
            ),
            BlockDesign(
                path="test-system/core",
                name="Core Service",
                block_type="component",
                description="Core business logic",
                parent_path="test-system",
                tech_stack="Python",
                dependencies=["test-system/api"],
            ),
        ],
    )


@pytest.fixture
def session_with_hierarchy(
    session_with_decisions: BuilderSession, sample_hierarchy: HierarchyDesign
) -> BuilderSession:
    """Create a session with hierarchy design."""
    session_with_decisions.hierarchy_design = sample_hierarchy
    session_with_decisions.phase = SessionPhase.REVIEW
    return session_with_decisions
