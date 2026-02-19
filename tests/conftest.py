"""Pytest fixtures for spec-dev-tools tests."""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Optional

import pytest

from src.spec.schemas import (
    Metadata,
    Overview,
    Spec,
    SpecStatus,
    TestCase,
    TestCases,
    SecurityRequirements,
    PerformanceRequirements,
    ErrorHandling,
    APIContract,
    Endpoint,
)
from src.spec.block import BlockSpec, BlockType
from src.rules.schemas import Rule, RuleCategory, RuleLevel, RuleSeverity


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for tests."""
    return tmp_path


@pytest.fixture
def specs_dir(temp_dir: Path) -> Path:
    """Create a specs directory."""
    specs = temp_dir / "specs"
    specs.mkdir()
    return specs


@pytest.fixture
def project_dir(temp_dir: Path) -> Path:
    """Create a project directory with .spec-dev."""
    spec_dev = temp_dir / ".spec-dev"
    spec_dev.mkdir()
    return temp_dir


@pytest.fixture
def sample_spec() -> Spec:
    """Create a sample specification."""
    return Spec(
        name="Test Feature",
        metadata=Metadata(
            spec_id="test-feature",
            version="1.0.0",
            status=SpecStatus.DRAFT,
            tech_stack="Python",
            author="Test Author",
        ),
        overview=Overview(
            summary="A test feature for unit testing.",
            goals=["Goal 1", "Goal 2"],
            non_goals=["Non-goal 1"],
            background="Background context.",
        ),
        test_cases=TestCases(
            unit_tests=[
                TestCase(
                    test_id="UT-001",
                    description="Test happy path",
                    input="valid input",
                    expected_output="expected output",
                ),
                TestCase(
                    test_id="UT-002",
                    description="Test error case",
                    input="invalid input",
                    expected_output="error",
                ),
                TestCase(
                    test_id="UT-003",
                    description="Test edge case",
                    input="edge input",
                    expected_output="edge output",
                ),
            ],
            integration_tests=[
                TestCase(
                    test_id="IT-001",
                    description="Integration test",
                    input="integration input",
                    expected_output="integration output",
                ),
            ],
            min_line_coverage=80,
            min_branch_coverage=70,
        ),
        security=SecurityRequirements(
            requires_auth=True,
            auth_method="JWT",
            encryption_in_transit=True,
        ),
        performance=PerformanceRequirements(
            p50_ms=50,
            p95_ms=200,
            p99_ms=500,
            target_rps=100,
        ),
        error_handling=ErrorHandling(
            error_types=["ValidationError", "NotFoundError"],
            max_retries=3,
            backoff_strategy="exponential",
        ),
        api_contract=APIContract(
            endpoints=[
                Endpoint(
                    method="GET",
                    path="/api/v1/resource",
                    response_body='{"data": []}',
                    description="Get resources",
                ),
                Endpoint(
                    method="POST",
                    path="/api/v1/resource",
                    request_body='{"name": "string"}',
                    response_body='{"id": "string"}',
                    description="Create resource",
                ),
            ],
            error_codes={"400": "Bad Request", "404": "Not Found"},
        ),
    )


@pytest.fixture
def sample_block_spec(sample_spec: Spec, temp_dir: Path) -> BlockSpec:
    """Create a sample block specification."""
    block_dir = temp_dir / "specs" / "test-block"
    block_dir.mkdir(parents=True)

    return BlockSpec(
        path="test-block",
        name="Test Block",
        directory=block_dir,
        spec=sample_spec,
        block_type=BlockType.COMPONENT,
        depth=0,
    )


@pytest.fixture
def temp_block_hierarchy(specs_dir: Path, sample_spec: Spec) -> dict[str, BlockSpec]:
    """Create a temporary block hierarchy for testing.

    Structure:
    - root-system (root)
      - component-a (component)
        - module-a1 (module)
        - module-a2 (module)
      - component-b (component)
        - leaf-b1 (leaf)
    """
    blocks = {}

    # Create directories and block.md files
    structure = [
        ("root-system", BlockType.ROOT, None),
        ("root-system/component-a", BlockType.COMPONENT, "root-system"),
        ("root-system/component-a/module-a1", BlockType.MODULE, "root-system/component-a"),
        ("root-system/component-a/module-a2", BlockType.MODULE, "root-system/component-a"),
        ("root-system/component-b", BlockType.COMPONENT, "root-system"),
        ("root-system/component-b/leaf-b1", BlockType.LEAF, "root-system/component-b"),
    ]

    for path, block_type, parent_path in structure:
        block_dir = specs_dir / path
        block_dir.mkdir(parents=True, exist_ok=True)

        # Create block.md
        name = path.split("/")[-1].replace("-", " ").title()
        block_content = _create_block_content(name, block_type.value, parent_path)
        (block_dir / "block.md").write_text(block_content)

        # Create BlockSpec
        spec = Spec(
            name=name,
            metadata=Metadata(spec_id=path.replace("/", "-"), status=SpecStatus.DRAFT),
            overview=Overview(summary=f"Block for {name}"),
        )

        blocks[path] = BlockSpec(
            path=path,
            name=name,
            directory=block_dir,
            spec=spec,
            block_type=block_type,
            depth=path.count("/"),
        )

    # Link parent/child relationships
    for path, block in blocks.items():
        if "/" in path:
            parent_path = "/".join(path.split("/")[:-1])
            if parent_path in blocks:
                block.parent = blocks[parent_path]
                blocks[parent_path].children.append(block)

    return blocks


@pytest.fixture
def sample_global_rules(project_dir: Path) -> list[Rule]:
    """Create sample global rules and save to yaml."""
    rules = [
        Rule(
            id="TEST-001",
            name="Test Rule 1",
            level=RuleLevel.GLOBAL,
            category=RuleCategory.TESTING,
            severity=RuleSeverity.WARNING,
            applies_to_sections=["test_cases"],
            validation_fn="check_min_tests",
            validation_args={"min_unit_tests": 2},
            description="Require minimum unit tests",
            enabled=True,
        ),
        Rule(
            id="SEC-001",
            name="Auth Required",
            level=RuleLevel.GLOBAL,
            category=RuleCategory.SECURITY,
            severity=RuleSeverity.ERROR,
            applies_to_sections=["security", "api_contract"],
            validation_fn="check_auth_required",
            description="APIs must require auth",
            enabled=True,
        ),
    ]

    # Save to yaml
    rules_content = """rules:
  - id: TEST-001
    name: Test Rule 1
    level: global
    category: testing
    severity: warning
    applies_to_sections:
      - test_cases
    validation_fn: check_min_tests
    validation_args:
      min_unit_tests: 2
    description: Require minimum unit tests
    enabled: true
  - id: SEC-001
    name: Auth Required
    level: global
    category: security
    severity: error
    applies_to_sections:
      - security
      - api_contract
    validation_fn: check_auth_required
    description: APIs must require auth
    enabled: true
"""
    (project_dir / ".spec-dev" / "global-rules.yaml").write_text(rules_content)

    return rules


def _create_block_content(name: str, block_type: str, parent_path: Optional[str]) -> str:
    """Create block.md content for testing."""
    parent_line = f"- parent: {parent_path}" if parent_path else "- parent: none"

    return f"""# Block Specification: {name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: {block_type}
{parent_line}

### 0.2: Sub-Blocks

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|

## 1. Metadata

- spec_id: {name.lower().replace(' ', '-')}
- version: 1.0.0
- status: draft

## 2. Overview

### Summary

{name} block for testing.

### Goals

- Goal 1

### Non-Goals

- Non-goal 1

## 3. Inputs

## 4. Outputs

## 5. Dependencies

## 6. API Contract

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Test case 1 | input1 | output1 | | |

## 8. Edge Cases

## 9. Error Handling

### Error Types
- ValidationError

## 10. Performance

- p50: 100
- p95: 500
- p99: 1000

## 11. Security

- requires_auth: false

## 12. Implementation

## 13. Acceptance

### Criteria
- [ ] Done
"""
