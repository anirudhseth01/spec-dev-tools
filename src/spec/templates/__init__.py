"""Spec templates for common patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TemplateVariable:
    """A variable in a template."""

    name: str
    description: str
    default: str | None = None
    required: bool = True


@dataclass
class SpecTemplate:
    """A spec template definition."""

    name: str
    description: str
    category: str
    variables: list[TemplateVariable] = field(default_factory=list)
    content: str = ""

    def render(self, variables: dict[str, str]) -> str:
        """Render the template with variables.

        Args:
            variables: Variable values.

        Returns:
            Rendered spec content.
        """
        result = self.content

        for var in self.variables:
            value = variables.get(var.name, var.default or "")
            result = result.replace(f"${{{var.name}}}", value)

        return result


class TemplateRegistry:
    """Registry of spec templates."""

    def __init__(self):
        """Initialize with default templates."""
        self.templates: dict[str, SpecTemplate] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default templates."""
        self.register(self._api_service_template())
        self.register(self._cli_tool_template())
        self.register(self._library_template())
        self.register(self._worker_service_template())
        self.register(self._data_pipeline_template())

    def register(self, template: SpecTemplate) -> None:
        """Register a template."""
        self.templates[template.name] = template

    def get(self, name: str) -> SpecTemplate | None:
        """Get a template by name."""
        return self.templates.get(name)

    def list(self) -> list[dict[str, Any]]:
        """List all templates."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "variables": [
                    {
                        "name": v.name,
                        "description": v.description,
                        "required": v.required,
                        "default": v.default,
                    }
                    for v in t.variables
                ],
            }
            for t in self.templates.values()
        ]

    def _api_service_template(self) -> SpecTemplate:
        """API service template."""
        return SpecTemplate(
            name="api-service",
            description="REST API service with CRUD endpoints",
            category="backend",
            variables=[
                TemplateVariable("name", "Service name", required=True),
                TemplateVariable("resource", "Primary resource name", default="item"),
                TemplateVariable("tech_stack", "Technology stack", default="Python, FastAPI, PostgreSQL"),
                TemplateVariable("auth_method", "Authentication method", default="JWT"),
            ],
            content=API_SERVICE_TEMPLATE,
        )

    def _cli_tool_template(self) -> SpecTemplate:
        """CLI tool template."""
        return SpecTemplate(
            name="cli-tool",
            description="Command-line interface tool",
            category="tooling",
            variables=[
                TemplateVariable("name", "Tool name", required=True),
                TemplateVariable("description", "Tool description", default="A CLI tool"),
                TemplateVariable("tech_stack", "Technology stack", default="Python, Click"),
            ],
            content=CLI_TOOL_TEMPLATE,
        )

    def _library_template(self) -> SpecTemplate:
        """Library template."""
        return SpecTemplate(
            name="library",
            description="Reusable library/package",
            category="library",
            variables=[
                TemplateVariable("name", "Library name", required=True),
                TemplateVariable("description", "Library description", default="A reusable library"),
                TemplateVariable("tech_stack", "Technology stack", default="Python"),
            ],
            content=LIBRARY_TEMPLATE,
        )

    def _worker_service_template(self) -> SpecTemplate:
        """Worker service template."""
        return SpecTemplate(
            name="worker-service",
            description="Background worker/job processor",
            category="backend",
            variables=[
                TemplateVariable("name", "Service name", required=True),
                TemplateVariable("job_type", "Type of jobs processed", default="task"),
                TemplateVariable("tech_stack", "Technology stack", default="Python, Celery, Redis"),
            ],
            content=WORKER_SERVICE_TEMPLATE,
        )

    def _data_pipeline_template(self) -> SpecTemplate:
        """Data pipeline template."""
        return SpecTemplate(
            name="data-pipeline",
            description="ETL/data processing pipeline",
            category="data",
            variables=[
                TemplateVariable("name", "Pipeline name", required=True),
                TemplateVariable("source", "Data source", default="database"),
                TemplateVariable("destination", "Data destination", default="data warehouse"),
                TemplateVariable("tech_stack", "Technology stack", default="Python, Apache Airflow"),
            ],
            content=DATA_PIPELINE_TEMPLATE,
        )


# Template content

API_SERVICE_TEMPLATE = """# Block Specification: ${name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: none

### 0.2: Sub-Blocks

| Name | Type | Description |
|------|------|-------------|

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|

## 1. Metadata

- spec_id: ${name}
- version: 1.0.0
- status: draft
- tech_stack: ${tech_stack}
- author:
- created:
- updated:

## 2. Overview

### Summary

API service for managing ${resource} resources.

### Goals

- Provide CRUD operations for ${resource} resources
- Ensure secure access with ${auth_method} authentication
- Maintain high availability and performance

### Non-Goals

- Real-time streaming
- Batch operations (v1)

### Background

[Add background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| ${resource}_id | UUID | no | - | ID of ${resource} to operate on |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| user_id | UUID | yes | - | Authenticated user ID |
| tenant_id | UUID | yes | - | Tenant context |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| DATABASE_URL | string | yes | - | Database connection string |
| JWT_SECRET | string | yes | - | JWT signing secret |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| ${resource} | ${resource^} | Single ${resource} object |
| ${resource}s | list[${resource^}] | List of ${resource} objects |

### Side Effects

- Database records created/updated/deleted
- Audit events logged

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| ${resource}.created | ${resource^}CreatedEvent | New ${resource} created |
| ${resource}.updated | ${resource^}UpdatedEvent | ${resource^} modified |
| ${resource}.deleted | ${resource^}DeletedEvent | ${resource^} removed |

## 5. Dependencies

### Internal

| Module | Purpose |
|--------|---------|

### External

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | ^0.109 | Web framework |
| sqlalchemy | ^2.0 | ORM |
| pydantic | ^2.6 | Validation |

### Services

| Service | Purpose |
|---------|---------|
| PostgreSQL | Primary data store |

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| GET | /api/v1/${resource}s | - | list[${resource^}] | List all ${resource}s |
| POST | /api/v1/${resource}s | Create${resource^}Request | ${resource^} | Create ${resource} |
| GET | /api/v1/${resource}s/{id} | - | ${resource^} | Get ${resource} by ID |
| PUT | /api/v1/${resource}s/{id} | Update${resource^}Request | ${resource^} | Update ${resource} |
| DELETE | /api/v1/${resource}s/{id} | - | - | Delete ${resource} |

### Error Codes

| Code | Description |
|------|-------------|
| NOT_FOUND | ${resource^} not found |
| VALIDATION_ERROR | Invalid request data |
| UNAUTHORIZED | Authentication required |
| FORBIDDEN | Insufficient permissions |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Create ${resource} | Valid data | ${resource^} created | - | - |
| UT-002 | Get ${resource} | Valid ID | ${resource^} returned | Seed data | - |
| UT-003 | Update ${resource} | Valid data | ${resource^} updated | Seed data | - |
| UT-004 | Delete ${resource} | Valid ID | ${resource^} deleted | Seed data | - |
| UT-005 | Get non-existent | Invalid ID | 404 error | - | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | Full CRUD flow | - | All ops succeed | DB | Cleanup |

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Boundary Conditions

- Empty list response
- Maximum page size
- Concurrent updates

### Concurrency

- Optimistic locking for updates
- Race condition handling

### Failure Modes

- Database connection failure
- Validation errors

## 9. Error Handling

### Error Types

| Type | Retryable | Handler |
|------|-----------|---------|
| ValidationError | no | Return 400 |
| NotFoundError | no | Return 404 |
| DatabaseError | yes | Retry with backoff |

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

- p50: 50
- p95: 200
- p99: 500
- target_rps: 1000
- memory_limit: 512

## 11. Security

- requires_auth: true
- auth_method: ${auth_method}
- handles_pii: false
- encryption_at_rest: true
- encryption_in_transit: true

### Roles

| Role | Permissions |
|------|-------------|
| admin | Full access |
| user | Own resources only |

## 12. Implementation

### Algorithms

- Standard CRUD operations
- Pagination with cursor

### Patterns

- Repository pattern
- DTO pattern

### Constraints

- All endpoints require authentication
- Rate limiting applied

## 13. Acceptance

### Criteria

- [ ] All CRUD operations functional
- [ ] Authentication working
- [ ] Tests passing

### Definition of Done

- [ ] Code complete
- [ ] Tests passing
- [ ] Documentation updated
"""

CLI_TOOL_TEMPLATE = """# Block Specification: ${name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: none

## 1. Metadata

- spec_id: ${name}
- version: 1.0.0
- status: draft
- tech_stack: ${tech_stack}
- author:
- created:
- updated:

## 2. Overview

### Summary

${description}

### Goals

- Provide intuitive command-line interface
- Support common workflows
- Enable automation via scripting

### Non-Goals

- GUI interface
- Web interface

### Background

[Add background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| command | string | yes | - | Command to execute |
| args | list[string] | no | [] | Command arguments |
| flags | dict | no | {} | Command flags |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| CONFIG_PATH | string | no | ~/.${name}/config | Config file path |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| exit_code | int | 0 for success, non-zero for error |
| stdout | string | Standard output |
| stderr | string | Error output |

### Side Effects

- Files may be created/modified
- Config may be updated

### Events

## 5. Dependencies

### External

| Package | Version | Purpose |
|---------|---------|---------|
| click | ^8.1 | CLI framework |
| rich | ^13.0 | Terminal formatting |

## 6. API Contract

### Commands

| Command | Arguments | Flags | Description |
|---------|-----------|-------|-------------|
| init | [path] | --force | Initialize new project |
| run | <target> | --verbose | Run target |
| help | [command] | | Show help |

### Error Codes

| Code | Description |
|------|-------------|
| 1 | General error |
| 2 | Invalid arguments |
| 3 | File not found |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Init command | Valid path | Exit 0 | - | Cleanup |
| UT-002 | Help command | - | Help text | - | - |
| UT-003 | Invalid command | Unknown cmd | Exit 2 | - | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | Full workflow | - | Success | - | Cleanup |

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Boundary Conditions

- Empty arguments
- Very long arguments
- Special characters

### Failure Modes

- Invalid config
- Permission denied

## 9. Error Handling

- max_retries: 0
- User-friendly error messages

## 10. Performance

- Startup time < 100ms
- Command execution < 1s (typical)

## 11. Security

- requires_auth: false
- handles_pii: false

## 12. Implementation

### Patterns

- Command pattern
- Plugin architecture (optional)

## 13. Acceptance

### Criteria

- [ ] All commands functional
- [ ] Help text complete
- [ ] Error handling robust

### Definition of Done

- [ ] Code complete
- [ ] Tests passing
- [ ] README updated
"""

LIBRARY_TEMPLATE = """# Block Specification: ${name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: module
- parent: none

## 1. Metadata

- spec_id: ${name}
- version: 1.0.0
- status: draft
- tech_stack: ${tech_stack}
- author:
- created:
- updated:

## 2. Overview

### Summary

${description}

### Goals

- Provide clean, well-documented API
- Ensure high test coverage
- Support extensibility

### Non-Goals

- CLI interface
- Web interface

### Background

[Add background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|

### Side Effects

- None (pure library)

## 5. Dependencies

### External

| Package | Version | Purpose |
|---------|---------|---------|

## 6. API Contract

### Public API

| Function/Class | Signature | Description |
|----------------|-----------|-------------|

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|

- min_line_coverage: 90
- min_branch_coverage: 85

## 8. Edge Cases

### Boundary Conditions

### Failure Modes

## 9. Error Handling

- Custom exception classes
- Clear error messages

## 10. Performance

- Memory efficient
- No blocking operations

## 11. Security

- No network access
- No file system access (unless documented)

## 12. Implementation

### Patterns

- Clean architecture
- Dependency injection

## 13. Acceptance

### Criteria

- [ ] API documented
- [ ] Tests passing
- [ ] Examples provided

### Definition of Done

- [ ] Code complete
- [ ] Tests >90% coverage
- [ ] API documentation complete
"""

WORKER_SERVICE_TEMPLATE = """# Block Specification: ${name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: none

## 1. Metadata

- spec_id: ${name}
- version: 1.0.0
- status: draft
- tech_stack: ${tech_stack}
- author:
- created:
- updated:

## 2. Overview

### Summary

Background worker service for processing ${job_type} jobs.

### Goals

- Process jobs reliably with retry logic
- Scale horizontally
- Provide job status visibility

### Non-Goals

- Synchronous processing
- Real-time responses

### Background

[Add background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| job_payload | dict | yes | - | Job data |
| priority | int | no | 0 | Job priority |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| job_id | UUID | yes | - | Unique job identifier |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| REDIS_URL | string | yes | - | Redis connection |
| CONCURRENCY | int | no | 4 | Worker concurrency |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| result | dict | Job result |
| status | string | Job status |

### Side Effects

- Job results stored
- Notifications sent

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| job.started | JobStartedEvent | Job processing started |
| job.completed | JobCompletedEvent | Job finished successfully |
| job.failed | JobFailedEvent | Job failed after retries |

## 5. Dependencies

### External

| Package | Version | Purpose |
|---------|---------|---------|
| celery | ^5.3 | Task queue |
| redis | ^5.0 | Message broker |

### Services

| Service | Purpose |
|---------|---------|
| Redis | Job queue and results |

## 6. API Contract

### Job Types

| Job Type | Payload | Description |
|----------|---------|-------------|
| process_${job_type} | ${job_type}Payload | Process a ${job_type} |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Process valid job | Valid payload | Success | - | - |
| UT-002 | Handle invalid job | Bad payload | Error | - | - |
| UT-003 | Retry on failure | Transient error | Retry | - | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | End-to-end job | Full job | Complete | Redis | - |

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Concurrency

- Duplicate job prevention
- Race conditions

### Failure Modes

- Redis unavailable
- Job timeout

## 9. Error Handling

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

- Jobs/second: 100
- Memory per worker: 256MB

## 11. Security

- requires_auth: false (internal)
- Job payloads validated

## 12. Implementation

### Patterns

- Worker pattern
- Circuit breaker

## 13. Acceptance

### Criteria

- [ ] Jobs process reliably
- [ ] Retries work
- [ ] Monitoring in place

### Definition of Done

- [ ] Code complete
- [ ] Tests passing
- [ ] Deployed to staging
"""

DATA_PIPELINE_TEMPLATE = """# Block Specification: ${name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: none

## 1. Metadata

- spec_id: ${name}
- version: 1.0.0
- status: draft
- tech_stack: ${tech_stack}
- author:
- created:
- updated:

## 2. Overview

### Summary

Data pipeline for extracting data from ${source} and loading into ${destination}.

### Goals

- Reliable data transfer
- Incremental updates
- Data quality validation

### Non-Goals

- Real-time streaming
- Complex transformations (v1)

### Background

[Add background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| start_date | date | no | yesterday | Start of data range |
| end_date | date | no | today | End of data range |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| source_connection | Connection | yes | - | Source DB connection |
| dest_connection | Connection | yes | - | Destination connection |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| SOURCE_DB_URL | string | yes | - | Source database URL |
| DEST_DB_URL | string | yes | - | Destination database URL |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| rows_processed | int | Number of rows processed |
| status | string | Pipeline status |

### Side Effects

- Data written to ${destination}
- Audit logs created

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| pipeline.started | PipelineStartedEvent | Pipeline run started |
| pipeline.completed | PipelineCompletedEvent | Pipeline finished |

## 5. Dependencies

### External

| Package | Version | Purpose |
|---------|---------|---------|
| apache-airflow | ^2.8 | Orchestration |
| pandas | ^2.2 | Data processing |

### Services

| Service | Purpose |
|---------|---------|
| Airflow | Pipeline orchestration |

## 6. API Contract

### Pipeline Steps

| Step | Input | Output | Description |
|------|-------|--------|-------------|
| extract | Source config | Raw data | Extract from ${source} |
| transform | Raw data | Clean data | Clean and transform |
| load | Clean data | Row count | Load to ${destination} |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Extract step | Source data | DataFrame | Mock source | - |
| UT-002 | Transform step | Raw data | Clean data | - | - |
| UT-003 | Load step | Clean data | Success | Mock dest | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | Full pipeline | Date range | Data loaded | Test DBs | Cleanup |

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Boundary Conditions

- Empty source data
- Schema changes
- Large datasets

### Failure Modes

- Source unavailable
- Destination full
- Network timeout

## 9. Error Handling

- max_retries: 3
- Checkpoint and resume support

## 10. Performance

- Throughput: 10,000 rows/second
- Memory: 2GB max

## 11. Security

- Credentials in secrets manager
- Data encrypted in transit

## 12. Implementation

### Patterns

- ETL pattern
- Idempotent loads

## 13. Acceptance

### Criteria

- [ ] Data extracted correctly
- [ ] Transformations accurate
- [ ] Load successful

### Definition of Done

- [ ] Pipeline runs successfully
- [ ] Data quality checks pass
- [ ] Monitoring configured
"""
