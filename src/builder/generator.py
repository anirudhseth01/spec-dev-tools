"""Spec generator for creating spec markdown files from designs.

The SpecGenerator takes the hierarchy design and generates complete
specification markdown files for each block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.builder.session import BuilderSession, BlockDesign, HierarchyDesign
from src.llm.client import LLMClient


@dataclass
class GeneratedSpec:
    """A generated specification."""

    block_path: str
    content: str
    file_path: str
    template_used: str = ""
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "block_path": self.block_path,
            "content": self.content,
            "file_path": self.file_path,
            "template_used": self.template_used,
            "generated_at": self.generated_at.isoformat(),
        }


# Prompts for spec generation
SYSTEM_PROMPT_SPEC = """You are generating a specification markdown file.

Generate a complete specification following this structure:
1. Metadata (spec_id, version, status, tech_stack)
2. Overview (summary, goals, non-goals)
3. Inputs (user inputs, system inputs, env vars)
4. Outputs (return values, side effects, events)
5. Dependencies (internal, external, services)
6. API Contract (endpoints, error codes)
7. Test Cases (unit tests, integration tests)
8. Edge Cases (boundary conditions, concurrency, failure modes)
9. Error Handling (error types, retries, backoff)
10. Performance (latency, throughput, memory)
11. Security (auth, encryption, compliance)
12. Implementation (algorithms, patterns, constraints)
13. Acceptance Criteria (done definition)

Use proper markdown formatting with headers and tables.
"""


class SpecGenerator:
    """Generates specification markdown files from hierarchy designs.

    Takes a HierarchyDesign and generates complete spec files for
    each block, using appropriate templates based on block type.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize the generator.

        Args:
            llm_client: LLM client for generating content.
        """
        self.llm_client = llm_client

    async def generate_all_specs(
        self, hierarchy: HierarchyDesign, session: BuilderSession
    ) -> list[GeneratedSpec]:
        """Generate specs for all blocks in the hierarchy.

        Args:
            hierarchy: The hierarchy design.
            session: The builder session with decisions.

        Returns:
            List of generated specs.
        """
        specs = []

        for block in hierarchy.blocks:
            spec = await self.generate_block_spec(block, session)
            specs.append(spec)

        return specs

    async def generate_block_spec(
        self, block: BlockDesign, session: BuilderSession
    ) -> GeneratedSpec:
        """Generate spec for a single block.

        Args:
            block: The block design.
            session: The builder session.

        Returns:
            GeneratedSpec with content.
        """
        template_type = self._select_template(block)
        file_path = f"{session.specs_dir}/{block.path}/block.md"

        if not self.llm_client:
            # Generate from template
            content = self._generate_from_template(block, session, template_type)
        else:
            try:
                content = await self._generate_with_llm(block, session, template_type)
            except Exception:
                # Fallback to template
                content = self._generate_from_template(block, session, template_type)

        return GeneratedSpec(
            block_path=block.path,
            content=content,
            file_path=file_path,
            template_used=template_type,
        )

    def _select_template(self, block: BlockDesign) -> str:
        """Select the appropriate template for a block.

        Args:
            block: The block design.

        Returns:
            Template type name.
        """
        # Check API endpoints
        if block.api_endpoints:
            return "api-service"

        # Check name patterns
        name_lower = block.name.lower()
        if "cli" in name_lower or "command" in name_lower:
            return "cli-tool"
        if "worker" in name_lower or "job" in name_lower or "queue" in name_lower:
            return "worker-service"
        if "pipeline" in name_lower or "etl" in name_lower:
            return "data-pipeline"
        if "lib" in name_lower or "util" in name_lower or "helper" in name_lower:
            return "library"

        # Default based on block type
        if block.block_type == "root":
            return "api-service"  # Root often defines main API
        elif block.block_type == "component":
            return "api-service"
        elif block.block_type == "module":
            return "library"
        else:
            return "library"

    async def _generate_with_llm(
        self, block: BlockDesign, session: BuilderSession, template_type: str
    ) -> str:
        """Generate spec content using LLM.

        Args:
            block: The block design.
            session: The builder session.
            template_type: The template type.

        Returns:
            Generated markdown content.
        """
        decisions_context = self._build_decisions_context(session)

        user_prompt = f"""
Generate a complete specification for:
- Name: {block.name}
- Path: {block.path}
- Type: {block.block_type}
- Description: {block.description}
- Tech Stack: {block.tech_stack}
- Dependencies: {', '.join(block.dependencies) or 'none'}
- API Endpoints: {block.api_endpoints or 'none'}
- Parent: {block.parent_path or 'none (this is root)'}

Template type: {template_type}

Design decisions from planning:
{decisions_context}

Generate the complete markdown specification.
"""

        response = self.llm_client.generate(
            system_prompt=SYSTEM_PROMPT_SPEC,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=4096,
        )

        return response.content

    def _generate_from_template(
        self, block: BlockDesign, session: BuilderSession, template_type: str
    ) -> str:
        """Generate spec from static template.

        Args:
            block: The block design.
            session: The builder session.
            template_type: The template type.

        Returns:
            Generated markdown content.
        """
        now = datetime.now().strftime("%Y-%m-%d")
        spec_id = block.path.replace("/", "-")

        # Build sections based on block type
        api_section = self._generate_api_section(block)
        test_section = self._generate_test_section(block)
        security_section = self._generate_security_section(session)
        performance_section = self._generate_performance_section(session)

        # Format parent line for hierarchy
        if block.parent_path:
            parent_line = f"- parent: {block.parent_path}"
        else:
            parent_line = "- parent: none"

        template = f"""# Block Specification: {block.name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: {block.block_type}
{parent_line}

### 0.2: Sub-Blocks

{self._generate_sub_blocks_section(block, session)}

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|

## 1. Metadata

- spec_id: {spec_id}
- version: 1.0.0
- status: draft
- tech_stack: {block.tech_stack or 'To be determined'}
- author: spec-builder
- created: {now}
- updated: {now}

## 2. Overview

### Summary

{block.description or f'{block.name} block for {session.name}.'}

### Goals

- Implement {block.name} functionality
- Integrate with other system components
{self._generate_goals(block, session)}

### Non-Goals

- Out of scope functionality
- Optimizations for future iterations

### Background

This block was designed as part of the {session.name} system.
{self._generate_background(block, session)}

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
{self._generate_inputs_table(block)}

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| config | object | yes | | System configuration |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| LOG_LEVEL | string | no | INFO | Logging level |

## 4. Outputs

### Return Values

- Success response with data
- Error response with details

### Side Effects

- Database modifications (if applicable)
- Event emissions

### Events

- operation.completed
- operation.failed

## 5. Dependencies

### Internal

{self._format_list(block.dependencies) or '- None'}

### External

- Logging framework
{self._generate_external_deps(block, session)}

### Services

- Configuration service

{api_section}

{test_section}

## 8. Edge Cases

### Boundary Conditions

- Empty input handling
- Maximum size inputs

### Concurrency

- Concurrent request handling

### Failure Modes

- Dependency unavailable
- Network timeout

## 9. Error Handling

### Error Types

- ValidationError: Invalid input data
- NotFoundError: Resource not found
- SystemError: Internal system error

### Retries

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

{performance_section}

## 11. Security

{security_section}

## 12. Implementation

### Algorithms

- Standard CRUD operations

### Patterns

- Repository pattern
- Service layer pattern

### Constraints

- Follow coding standards
- Maintain backward compatibility

## 13. Acceptance Criteria

### Criteria

- [ ] All tests passing
- [ ] Code review approved
- [ ] Documentation complete

### Done Definition

- Feature is deployable
- Meets performance requirements
- Security review passed
"""

        return template

    def _generate_api_section(self, block: BlockDesign) -> str:
        """Generate API Contract section."""
        if not block.api_endpoints:
            return """## 6. API Contract

### Endpoints

No API endpoints defined for this block.

### Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request |
| 404 | Not Found |
| 500 | Internal Server Error |
"""

        endpoints_table = "| Method | Path | Request | Response | Description |\n"
        endpoints_table += "|--------|------|---------|----------|-------------|\n"

        for ep in block.api_endpoints:
            method = ep.get("method", "GET")
            path = ep.get("path", "/")
            request = ep.get("request_body", "-")
            response = ep.get("response_body", "-")
            desc = ep.get("description", "-")
            endpoints_table += f"| {method} | {path} | {request} | {response} | {desc} |\n"

        return f"""## 6. API Contract

### Endpoints

{endpoints_table}

### Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 500 | Internal Server Error |
"""

    def _generate_test_section(self, block: BlockDesign) -> str:
        """Generate Test Cases section."""
        return """## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Happy path test | Valid input | Success response | | |
| UT-002 | Invalid input test | Invalid input | Error response | | |
| UT-003 | Edge case test | Edge input | Handled correctly | | |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | Full flow test | Complete request | Success | Start deps | Stop deps |

### Coverage

- min_line_coverage: 80%
- min_branch_coverage: 70%
"""

    def _generate_security_section(self, session: BuilderSession) -> str:
        """Generate Security section based on decisions."""
        security_decision = next(
            (d for d in session.decisions if d.topic == "Security" and d.is_decided),
            None,
        )

        requires_auth = "true"
        auth_method = "JWT"
        handles_pii = "false"

        if security_decision and security_decision.selected_option:
            opt = security_decision.selected_option
            if "compliance" in opt.id.lower():
                handles_pii = "true"

        return f"""### Authentication

- requires_auth: {requires_auth}
- auth_method: {auth_method}

### Authorization

- roles: [user, admin]

### Data Protection

- handles_pii: {handles_pii}
- encryption_at_rest: {handles_pii}
- encryption_in_transit: true
"""

    def _generate_performance_section(self, session: BuilderSession) -> str:
        """Generate Performance section based on decisions."""
        perf_decision = next(
            (d for d in session.decisions if d.topic == "Performance" and d.is_decided),
            None,
        )

        p99 = "500"
        p95 = "200"
        p50 = "50"

        if perf_decision and perf_decision.selected_option:
            opt = perf_decision.selected_option
            if "high" in opt.id.lower():
                p99 = "100"
                p95 = "50"
                p50 = "20"

        return f"""### Latency

- p50: {p50}ms
- p95: {p95}ms
- p99: {p99}ms

### Throughput

- target_rps: 100

### Resources

- memory_limit: 512MB
"""

    def _generate_sub_blocks_section(
        self, block: BlockDesign, session: BuilderSession
    ) -> str:
        """Generate sub-blocks listing."""
        if block.block_type == "leaf":
            return "No sub-blocks (leaf node)."

        if not session.hierarchy_design:
            return "Sub-blocks to be determined."

        children = session.hierarchy_design.get_children(block.path)
        if not children:
            return "No sub-blocks defined."

        lines = []
        for child in children:
            lines.append(f"- {child.name}: {child.description}")

        return "\n".join(lines)

    def _generate_goals(self, block: BlockDesign, session: BuilderSession) -> str:
        """Generate additional goals based on block."""
        goals = []

        if block.api_endpoints:
            goals.append("- Provide reliable API endpoints")

        if block.dependencies:
            goals.append(f"- Integrate with {', '.join(block.dependencies)}")

        return "\n".join(goals)

    def _generate_background(
        self, block: BlockDesign, session: BuilderSession
    ) -> str:
        """Generate background context."""
        parts = []

        if block.block_type == "root":
            parts.append("This is the root block defining the overall system.")
        elif block.block_type == "component":
            parts.append(
                f"This component handles {block.description.lower() if block.description else 'its specific functionality'}."
            )

        return " ".join(parts)

    def _generate_inputs_table(self, block: BlockDesign) -> str:
        """Generate inputs table content."""
        if block.api_endpoints:
            # Generate from API endpoints
            lines = []
            for ep in block.api_endpoints:
                if ep.get("request_body"):
                    lines.append(
                        f"| request_data | object | yes | | Request payload for {ep.get('path')} |"
                    )
            if lines:
                return "\n".join(lines)

        return "| input_data | object | yes | | Primary input data |"

    def _generate_external_deps(
        self, block: BlockDesign, session: BuilderSession
    ) -> str:
        """Generate external dependencies."""
        deps = []

        tech_decision = next(
            (d for d in session.decisions if d.topic == "Tech Stack" and d.is_decided),
            None,
        )

        if tech_decision and tech_decision.selected_option:
            opt = tech_decision.selected_option
            if "python" in opt.id.lower():
                deps.extend(["- fastapi", "- pydantic"])
            elif "typescript" in opt.id.lower():
                deps.extend(["- express", "- zod"])

        return "\n".join(deps) if deps else "- Standard libraries"

    def _format_list(self, items: list[str]) -> str:
        """Format a list as markdown bullets."""
        if not items:
            return ""
        return "\n".join(f"- {item}" for item in items)

    async def write_specs(
        self, specs: list[GeneratedSpec], project_root: Path
    ) -> list[str]:
        """Write generated specs to disk.

        Args:
            specs: List of generated specs.
            project_root: Project root directory.

        Returns:
            List of created file paths.
        """
        created_files = []

        for spec in specs:
            file_path = project_root / spec.file_path
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w") as f:
                f.write(spec.content)

            created_files.append(str(file_path))

        return created_files
