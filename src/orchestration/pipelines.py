"""Pre-configured pipelines for common development workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent
from src.agents.coding import CodingAgent
from src.agents.security import SecurityScanAgent, ScanMode
from src.agents.testing import TestGeneratorAgent
from src.agents.review import CodeReviewAgent, ReviewMode
from src.orchestration.flow_orchestrator import (
    FlowOrchestrator,
    FlowStrategy,
    AGENT_DEPENDENCIES,
)
from src.spec.schemas import Spec


def create_full_pipeline(
    spec: Spec,
    project_root: Path,
    llm_client: Optional[Any] = None,
    dry_run: bool = False,
) -> FlowOrchestrator:
    """Create a full development pipeline with all agents.

    Pipeline order:
    1. CodingAgent - Generate implementation code
    2. SecurityScanAgent (lightweight) - Quick security scan
    3. TestGeneratorAgent - Generate tests
    4. CodeReviewAgent - Review code and tests

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        llm_client: Optional LLM client for agents that support it.
        dry_run: If True, agents won't write files.

    Returns:
        Configured FlowOrchestrator ready for execution.
    """
    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    # CodingAgent
    coding_agent = CodingAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=coding_agent,
        depends_on=[],
        provides=["code", "files_created"],
        priority=100,
    )

    # SecurityScanAgent (lightweight mode for CI)
    security_agent = SecurityScanAgent(
        mode=ScanMode.LIGHTWEIGHT,
        llm_client=llm_client,
    )
    orchestrator.register_agent(
        agent=security_agent,
        depends_on=["coding_agent"],
        provides=["security_report"],
        priority=80,
    )

    # TestGeneratorAgent
    test_agent = TestGeneratorAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=test_agent,
        depends_on=["coding_agent"],
        provides=["tests", "test_files"],
        priority=80,
    )

    # CodeReviewAgent
    review_agent = CodeReviewAgent(
        mode=ReviewMode.STANDARD,
        llm_client=llm_client,
        fail_on_errors=False,
    )
    orchestrator.register_agent(
        agent=review_agent,
        depends_on=[coding_agent.name, test_agent.name],
        provides=["review"],
        priority=50,
    )

    return orchestrator


def create_quick_pipeline(
    spec: Spec,
    project_root: Path,
    llm_client: Optional[Any] = None,
    dry_run: bool = False,
) -> FlowOrchestrator:
    """Create a lightweight pipeline for quick iterations.

    Pipeline order:
    1. CodingAgent - Generate implementation code
    2. SecurityScanAgent (lightweight) - Quick security scan

    This pipeline skips test generation and code review for faster
    feedback during initial development.

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        llm_client: Optional LLM client for agents that support it.
        dry_run: If True, agents won't write files.

    Returns:
        Configured FlowOrchestrator ready for execution.
    """
    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    # CodingAgent
    coding_agent = CodingAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=coding_agent,
        depends_on=[],
        provides=["code", "files_created"],
        priority=100,
    )

    # SecurityScanAgent (lightweight mode)
    security_agent = SecurityScanAgent(
        mode=ScanMode.LIGHTWEIGHT,
        llm_client=None,  # No LLM for quick mode
    )
    orchestrator.register_agent(
        agent=security_agent,
        depends_on=["coding_agent"],
        provides=["security_report"],
        priority=80,
    )

    return orchestrator


def create_test_pipeline(
    spec: Spec,
    project_root: Path,
    llm_client: Optional[Any] = None,
    dry_run: bool = False,
) -> FlowOrchestrator:
    """Create a test-focused pipeline.

    Pipeline order:
    1. CodingAgent - Generate implementation code
    2. TestGeneratorAgent - Generate comprehensive tests

    This pipeline focuses on generating code and tests without
    security scanning or code review.

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        llm_client: Optional LLM client for agents that support it.
        dry_run: If True, agents won't write files.

    Returns:
        Configured FlowOrchestrator ready for execution.
    """
    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    # CodingAgent
    coding_agent = CodingAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=coding_agent,
        depends_on=[],
        provides=["code", "files_created"],
        priority=100,
    )

    # TestGeneratorAgent
    test_agent = TestGeneratorAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=test_agent,
        depends_on=["coding_agent"],
        provides=["tests", "test_files"],
        priority=80,
    )

    return orchestrator


def create_review_pipeline(
    spec: Spec,
    project_root: Path,
    llm_client: Optional[Any] = None,
    dry_run: bool = False,
    strict_review: bool = True,
) -> FlowOrchestrator:
    """Create a pipeline with comprehensive review and heavyweight security.

    Pipeline order:
    1. CodingAgent - Generate implementation code
    2. SecurityScanAgent (heavyweight) - Deep security analysis with LLM
    3. TestGeneratorAgent - Generate comprehensive tests
    4. CodeReviewAgent (strict) - Strict code review

    This pipeline is designed for pre-merge validation with thorough
    security scanning and strict code review.

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        llm_client: Optional LLM client for agents (recommended for this pipeline).
        dry_run: If True, agents won't write files.
        strict_review: If True, CodeReviewAgent will fail on critical issues.

    Returns:
        Configured FlowOrchestrator ready for execution.
    """
    orchestrator = FlowOrchestrator(spec, project_root, FlowStrategy.DAG)

    # CodingAgent
    coding_agent = CodingAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=coding_agent,
        depends_on=[],
        provides=["code", "files_created"],
        priority=100,
    )

    # SecurityScanAgent (heavyweight mode with LLM)
    security_agent = SecurityScanAgent(
        mode=ScanMode.HEAVYWEIGHT,
        llm_client=llm_client,
    )
    orchestrator.register_agent(
        agent=security_agent,
        depends_on=["coding_agent"],
        provides=["security_report"],
        priority=80,
    )

    # TestGeneratorAgent
    test_agent = TestGeneratorAgent(
        llm_client=llm_client,
        dry_run=dry_run,
    )
    orchestrator.register_agent(
        agent=test_agent,
        depends_on=["coding_agent"],
        provides=["tests", "test_files"],
        priority=80,
    )

    # CodeReviewAgent (strict mode for thorough review)
    review_agent = CodeReviewAgent(
        mode=ReviewMode.DEEP if llm_client else ReviewMode.STANDARD,
        llm_client=llm_client,
        fail_on_errors=strict_review,
    )
    orchestrator.register_agent(
        agent=review_agent,
        depends_on=[coding_agent.name, test_agent.name],
        provides=["review"],
        priority=50,
    )

    return orchestrator


def create_custom_pipeline(
    spec: Spec,
    project_root: Path,
    agents: list[BaseAgent],
    strategy: FlowStrategy = FlowStrategy.DAG,
) -> FlowOrchestrator:
    """Create a custom pipeline with user-provided agents.

    Uses the default dependency configuration for known agent types.
    Unknown agents will have no dependencies.

    Args:
        spec: The specification to implement.
        project_root: Root directory of the project.
        agents: List of agent instances to include.
        strategy: Execution strategy (DAG recommended).

    Returns:
        Configured FlowOrchestrator ready for execution.
    """
    orchestrator = FlowOrchestrator(spec, project_root, strategy)

    for agent in agents:
        deps, provides = AGENT_DEPENDENCIES.get(agent.name, ([], []))
        orchestrator.register_agent(
            agent=agent,
            depends_on=deps,
            provides=provides,
        )

    return orchestrator
