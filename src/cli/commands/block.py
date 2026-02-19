"""Block management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.tree import Tree

from src.spec.parser import BlockParser
from src.spec.block import BlockType
from src.rules.engine import RulesEngine
from src.orchestration.block_pipeline import BlockPipeline, ProcessingOrder

console = Console()


@click.group()
def block() -> None:
    """Block specification management commands."""
    pass


@block.command()
@click.argument("path")
@click.option(
    "--type",
    "block_type",
    type=click.Choice(["root", "component", "module", "leaf"]),
    default="leaf",
    help="Type of block",
)
@click.option("--specs-dir", default="specs", help="Directory for specifications")
def init(path: str, block_type: str, specs_dir: str) -> None:
    """Initialize a new block specification.

    PATH is the hierarchical path for the block (e.g., "payment-system/gateway").
    """
    specs_path = Path(specs_dir)
    block_dir = specs_path / path
    block_file = block_dir / "block.md"

    if block_file.exists():
        console.print(f"[red]Error:[/red] Block already exists at '{path}'")
        raise SystemExit(1)

    # Create directory
    block_dir.mkdir(parents=True, exist_ok=True)

    # Determine parent path
    parent_path = None
    if "/" in path:
        parent_path = "/".join(path.split("/")[:-1])

    # Generate block name from path
    name = path.split("/")[-1].replace("-", " ").title()

    # Create block.md from template
    template = _get_block_template(name, block_type, parent_path)
    block_file.write_text(template)

    console.print(f"[green]Created block:[/green] {block_file}")


@block.command()
@click.argument("root", required=False)
@click.option("--specs-dir", default="specs", help="Directory for specifications")
def tree(root: Optional[str], specs_dir: str) -> None:
    """Display block hierarchy as a tree.

    ROOT is the optional root path to start from.
    """
    specs_path = Path(specs_dir)
    parser = BlockParser(specs_path)

    # Parse all blocks
    if root:
        root_path = specs_path / root
        blocks = parser.parse_hierarchy(root_path)
    else:
        blocks = parser.parse_hierarchy()

    if not blocks:
        console.print("[yellow]No blocks found[/yellow]")
        return

    # Build tree
    root_blocks = [b for b in blocks if b.parent is None]

    for root_block in root_blocks:
        tree_widget = Tree(f"[bold]{root_block.name}[/bold] ({root_block.block_type.value})")
        _add_children_to_tree(root_block, tree_widget)
        console.print(tree_widget)


def _add_children_to_tree(block, tree_widget: Tree) -> None:
    """Recursively add children to tree widget."""
    for child in block.children:
        child_branch = tree_widget.add(
            f"{child.name} ({child.block_type.value})"
        )
        _add_children_to_tree(child, child_branch)


@block.command("validate")
@click.argument("path")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option("--recursive/--no-recursive", default=False, help="Validate children too")
def validate_block(path: str, specs_dir: str, project_dir: str, recursive: bool) -> None:
    """Validate a block specification.

    PATH is the block path to validate.
    """
    from src.cli.commands.validate import _validate_block

    specs_path = Path(specs_dir)
    project_path = Path(project_dir)
    block_file = specs_path / path / "block.md"

    if not block_file.exists():
        console.print(f"[red]Error:[/red] Block not found at '{path}'")
        raise SystemExit(1)

    if recursive:
        parser = BlockParser(specs_path)
        blocks = parser.parse_hierarchy(specs_path / path)

        errors = 0
        for block in blocks:
            try:
                _validate_block(block.directory / "block.md", project_path, run_rules=True)
            except SystemExit:
                errors += 1

        if errors > 0:
            console.print(f"\n[red]Validation failed for {errors} block(s)[/red]")
            raise SystemExit(1)
    else:
        _validate_block(block_file, project_path, run_rules=True)


@block.command()
@click.argument("path")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option("--recursive/--no-recursive", default=True, help="Process children too")
@click.option(
    "--order",
    type=click.Choice(["bottom-up", "top-down"]),
    default="bottom-up",
    help="Processing order",
)
@click.option("--dry-run", is_flag=True, help="Don't make actual changes")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def implement(
    path: str,
    specs_dir: str,
    project_dir: str,
    recursive: bool,
    order: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Implement a block specification.

    PATH is the block path to implement.
    """
    specs_path = Path(specs_dir)
    project_path = Path(project_dir)

    parser = BlockParser(specs_path)

    # Parse blocks
    if recursive:
        blocks = parser.parse_hierarchy(specs_path / path)
    else:
        block_file = specs_path / path / "block.md"
        if not block_file.exists():
            console.print(f"[red]Error:[/red] Block not found at '{path}'")
            raise SystemExit(1)
        blocks = [parser.parse_block(block_file)]

    if not blocks:
        console.print("[yellow]No blocks found to implement[/yellow]")
        return

    # Create pipeline
    processing_order = ProcessingOrder.BOTTOM_UP if order == "bottom-up" else ProcessingOrder.TOP_DOWN

    pipeline = BlockPipeline(
        blocks=blocks,
        project_root=project_path,
        agents=[],  # Add agents when available
        dry_run=dry_run,
        verbose=verbose,
    )

    # Run pipeline
    console.print(f"[bold]Implementing {len(blocks)} block(s) in {order} order...[/bold]")

    state = pipeline.run(order=processing_order)

    # Display results
    summary = state.get_summary()
    console.print(f"\n[bold]Results:[/bold]")
    console.print(f"  Total blocks: {summary['total_blocks']}")
    console.print(f"  Processed: {summary['processed_blocks']}")
    console.print(f"  Failed: {summary['failed_blocks']}")

    if state.failed_blocks > 0:
        console.print(f"\n[red]Implementation failed for {state.failed_blocks} block(s)[/red]")
        raise SystemExit(1)
    else:
        console.print(f"\n[green]Implementation complete![/green]")


def _get_block_template(name: str, block_type: str, parent_path: Optional[str]) -> str:
    """Generate block template content."""
    parent_line = f"- parent: {parent_path}" if parent_path else "- parent: none"

    return f"""# Block Specification: {name}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: {block_type}
{parent_line}

### 0.2: Sub-Blocks

<!-- List sub-blocks if this is a component or module -->

### 0.3: Scoped Rules

<!-- Define rules that apply to this block and its descendants -->
| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|

### 0.4: Same-As References

<!-- Reference sections from other blocks -->
| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|

## 1. Metadata

- spec_id: {name.lower().replace(' ', '-')}
- version: 1.0.0
- status: draft
- tech_stack:
- author:
- created:
- updated:

## 2. Overview

### Summary

[Brief description of the block]

### Goals

- [Goal 1]

### Non-Goals

- [Non-goal 1]

### Background

[Background context]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|

## 4. Outputs

### Return Values

### Side Effects

### Events

## 5. Dependencies

### Internal

### External

### Services

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|

### Error Codes

| Code | Description |
|------|-------------|

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Boundary Conditions

### Concurrency

### Failure Modes

## 9. Error Handling

### Error Types

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

## 12. Implementation

### Algorithms

### Patterns

### Constraints

## 13. Acceptance

### Criteria

- [ ] [Criterion 1]

### Definition of Done

- [ ] Code complete
- [ ] Tests passing
- [ ] Documentation updated
"""
