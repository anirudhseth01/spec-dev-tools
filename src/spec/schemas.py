"""Core specification data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpecStatus(Enum):
    """Status of a specification."""

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    DEPRECATED = "deprecated"


@dataclass
class Metadata:
    """Section 1: Specification metadata."""

    spec_id: str = ""
    version: str = "1.0.0"
    status: SpecStatus = SpecStatus.DRAFT
    tech_stack: str = ""
    author: str = ""
    created: str = ""
    updated: str = ""


@dataclass
class Overview:
    """Section 2: Feature overview."""

    summary: str = ""
    goals: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    background: str = ""


@dataclass
class InputParam:
    """A single input parameter."""

    name: str = ""
    type: str = ""
    required: bool = True
    default: str = ""
    description: str = ""


@dataclass
class Inputs:
    """Section 3: Input specifications."""

    user_inputs: list[InputParam] = field(default_factory=list)
    system_inputs: list[InputParam] = field(default_factory=list)
    env_vars: list[InputParam] = field(default_factory=list)


@dataclass
class Outputs:
    """Section 4: Output specifications."""

    return_values: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


@dataclass
class Dependencies:
    """Section 5: Dependencies."""

    internal: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)


@dataclass
class Endpoint:
    """A single API endpoint."""

    method: str = ""
    path: str = ""
    request_body: str = ""
    response_body: str = ""
    description: str = ""


@dataclass
class APIContract:
    """Section 6: API contract specifications."""

    endpoints: list[Endpoint] = field(default_factory=list)
    error_codes: dict[str, str] = field(default_factory=dict)


@dataclass
class TestCase:
    """A single test case."""

    test_id: str = ""
    description: str = ""
    input: str = ""
    expected_output: str = ""
    setup: str = ""
    teardown: str = ""


@dataclass
class TestCases:
    """Section 7: Test cases."""

    unit_tests: list[TestCase] = field(default_factory=list)
    integration_tests: list[TestCase] = field(default_factory=list)
    min_line_coverage: int = 80
    min_branch_coverage: int = 70


@dataclass
class EdgeCases:
    """Section 8: Edge cases and boundary conditions."""

    boundary_conditions: list[str] = field(default_factory=list)
    concurrency: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)


@dataclass
class ErrorHandling:
    """Section 9: Error handling specifications."""

    error_types: list[str] = field(default_factory=list)
    max_retries: int = 3
    backoff_strategy: str = "exponential"


@dataclass
class PerformanceRequirements:
    """Section 10: Performance requirements."""

    p50_ms: int = 100
    p95_ms: int = 500
    p99_ms: int = 1000
    target_rps: int = 100
    memory_limit_mb: int = 512


@dataclass
class SecurityRequirements:
    """Section 11: Security requirements."""

    requires_auth: bool = False
    auth_method: str = ""
    roles: list[str] = field(default_factory=list)
    handles_pii: bool = False
    encryption_at_rest: bool = False
    encryption_in_transit: bool = True


@dataclass
class ImplementationNotes:
    """Section 12: Implementation notes."""

    algorithms: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


@dataclass
class AcceptanceCriteria:
    """Section 13: Acceptance criteria."""

    criteria: list[str] = field(default_factory=list)
    done_definition: list[str] = field(default_factory=list)


@dataclass
class Spec:
    """Complete feature specification."""

    name: str = ""
    metadata: Metadata = field(default_factory=Metadata)
    overview: Overview = field(default_factory=Overview)
    inputs: Inputs = field(default_factory=Inputs)
    outputs: Outputs = field(default_factory=Outputs)
    dependencies: Dependencies = field(default_factory=Dependencies)
    api_contract: APIContract = field(default_factory=APIContract)
    test_cases: TestCases = field(default_factory=TestCases)
    edge_cases: EdgeCases = field(default_factory=EdgeCases)
    error_handling: ErrorHandling = field(default_factory=ErrorHandling)
    performance: PerformanceRequirements = field(default_factory=PerformanceRequirements)
    security: SecurityRequirements = field(default_factory=SecurityRequirements)
    implementation: ImplementationNotes = field(default_factory=ImplementationNotes)
    acceptance: AcceptanceCriteria = field(default_factory=AcceptanceCriteria)

    def is_valid(self) -> bool:
        """Check if the specification has required fields."""
        return bool(self.name and self.metadata.spec_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert specification to dictionary."""
        return {
            "name": self.name,
            "metadata": {
                "spec_id": self.metadata.spec_id,
                "version": self.metadata.version,
                "status": self.metadata.status.value,
                "tech_stack": self.metadata.tech_stack,
                "author": self.metadata.author,
                "created": self.metadata.created,
                "updated": self.metadata.updated,
            },
            "overview": {
                "summary": self.overview.summary,
                "goals": self.overview.goals,
                "non_goals": self.overview.non_goals,
                "background": self.overview.background,
            },
            "inputs": {
                "user_inputs": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "default": p.default,
                        "description": p.description,
                    }
                    for p in self.inputs.user_inputs
                ],
                "system_inputs": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "default": p.default,
                        "description": p.description,
                    }
                    for p in self.inputs.system_inputs
                ],
                "env_vars": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "default": p.default,
                        "description": p.description,
                    }
                    for p in self.inputs.env_vars
                ],
            },
            "outputs": {
                "return_values": self.outputs.return_values,
                "side_effects": self.outputs.side_effects,
                "events": self.outputs.events,
            },
            "dependencies": {
                "internal": self.dependencies.internal,
                "external": self.dependencies.external,
                "services": self.dependencies.services,
            },
            "api_contract": {
                "endpoints": [
                    {
                        "method": e.method,
                        "path": e.path,
                        "request_body": e.request_body,
                        "response_body": e.response_body,
                        "description": e.description,
                    }
                    for e in self.api_contract.endpoints
                ],
                "error_codes": self.api_contract.error_codes,
            },
            "test_cases": {
                "unit_tests": [
                    {
                        "test_id": t.test_id,
                        "description": t.description,
                        "input": t.input,
                        "expected_output": t.expected_output,
                        "setup": t.setup,
                        "teardown": t.teardown,
                    }
                    for t in self.test_cases.unit_tests
                ],
                "integration_tests": [
                    {
                        "test_id": t.test_id,
                        "description": t.description,
                        "input": t.input,
                        "expected_output": t.expected_output,
                        "setup": t.setup,
                        "teardown": t.teardown,
                    }
                    for t in self.test_cases.integration_tests
                ],
                "min_line_coverage": self.test_cases.min_line_coverage,
                "min_branch_coverage": self.test_cases.min_branch_coverage,
            },
            "edge_cases": {
                "boundary_conditions": self.edge_cases.boundary_conditions,
                "concurrency": self.edge_cases.concurrency,
                "failure_modes": self.edge_cases.failure_modes,
            },
            "error_handling": {
                "error_types": self.error_handling.error_types,
                "max_retries": self.error_handling.max_retries,
                "backoff_strategy": self.error_handling.backoff_strategy,
            },
            "performance": {
                "p50_ms": self.performance.p50_ms,
                "p95_ms": self.performance.p95_ms,
                "p99_ms": self.performance.p99_ms,
                "target_rps": self.performance.target_rps,
                "memory_limit_mb": self.performance.memory_limit_mb,
            },
            "security": {
                "requires_auth": self.security.requires_auth,
                "auth_method": self.security.auth_method,
                "roles": self.security.roles,
                "handles_pii": self.security.handles_pii,
                "encryption_at_rest": self.security.encryption_at_rest,
                "encryption_in_transit": self.security.encryption_in_transit,
            },
            "implementation": {
                "algorithms": self.implementation.algorithms,
                "patterns": self.implementation.patterns,
                "constraints": self.implementation.constraints,
            },
            "acceptance": {
                "criteria": self.acceptance.criteria,
                "done_definition": self.acceptance.done_definition,
            },
        }
