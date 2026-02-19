"""Init command for creating new specifications."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("name")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--template", default=None, help="Template to use")
def init(name: str, specs_dir: str, template: Optional[str]) -> None:
    """Create a new feature specification.

    NAME is the name of the specification to create.
    """
    specs_path = Path(specs_dir)
    specs_path.mkdir(parents=True, exist_ok=True)

    # Create spec file
    spec_file = specs_path / f"{name}.md"

    if spec_file.exists():
        console.print(f"[red]Error:[/red] Specification '{name}' already exists")
        raise SystemExit(1)

    # Load template
    template_content = _get_template(template)
    template_content = template_content.replace("{{NAME}}", name)

    spec_file.write_text(template_content)
    console.print(f"[green]Created specification:[/green] {spec_file}")


def _get_template(template_name: Optional[str]) -> str:
    """Load template content."""
    if template_name:
        template_path = Path("specs/templates") / f"{template_name}.md"
        if template_path.exists():
            return template_path.read_text()

    # Default template
    return """# Feature Specification: {{NAME}}

## 1. Metadata

- spec_id: {{NAME}}
- version: 1.0.0
- status: draft
- tech_stack:
- author:
- created:
- updated:

## 2. Overview

### Summary

[Brief description of the feature]

### Goals

- [Goal 1]
- [Goal 2]

### Non-Goals

- [Non-goal 1]

### Background

[Background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
|      |      |          |         |             |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
|      |      |          |         |             |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
|      |      |          |         |             |

## 4. Outputs

### Return Values

- [Return value 1]

### Side Effects

- [Side effect 1]

### Events

- [Event 1]

## 5. Dependencies

### Internal

- [Internal dependency 1]

### External

- [External dependency 1]

### Services

- [Service dependency 1]

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
|        |      |         |          |             |

### Error Codes

| Code | Description |
|------|-------------|
|      |             |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
|    |             |       |          |       |          |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
|    |             |       |          |       |          |

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Boundary Conditions

- [Boundary condition 1]

### Concurrency

- [Concurrency concern 1]

### Failure Modes

- [Failure mode 1]

## 9. Error Handling

### Error Types

- [Error type 1]

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

- p50: 100
- p95: 500
- p99: 1000
- target_rps: 100
- memory_limit: 512

## 11. Security

- requires_auth: false
- auth_method:
- handles_pii: false
- encryption_at_rest: false
- encryption_in_transit: true

### Roles

- [Role 1]

## 12. Implementation

### Algorithms

- [Algorithm 1]

### Patterns

- [Pattern 1]

### Constraints

- [Constraint 1]

## 13. Acceptance

### Criteria

- [ ] [Criterion 1]

### Definition of Done

- [ ] Code complete
- [ ] Tests passing
- [ ] Documentation updated
"""
