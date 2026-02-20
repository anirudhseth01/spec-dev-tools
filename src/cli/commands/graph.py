"""Dependency graph CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command("graph")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["mermaid", "dot", "ascii", "json"]),
              default="mermaid", help="Output format")
@click.option("--output", "-o", "output_file", help="Output file (stdout if not specified)")
@click.option("--validate", is_flag=True, help="Also run cross-block validation")
def graph_command(specs_dir: str, output_format: str, output_file: str | None, validate: bool):
    """Generate dependency graph visualization.

    Examples:

        spec-dev graph

        spec-dev graph --format dot -o deps.dot

        spec-dev graph --format ascii

        spec-dev graph --validate
    """
    from src.visualization import GraphBuilder, GraphVisualizer, OutputFormat

    specs_path = Path(specs_dir)

    if not specs_path.exists():
        console.print(f"[red]Specs directory not found: {specs_dir}[/red]")
        return

    # Build graph
    builder = GraphBuilder(specs_path)
    graph = builder.build_graph()

    if not graph.nodes:
        console.print("[yellow]No blocks found in specs directory[/yellow]")
        return

    # Visualize
    visualizer = GraphVisualizer()
    format_enum = OutputFormat(output_format)
    output = visualizer.render(graph, format_enum)

    # Wrap mermaid in markdown code block for display
    if format_enum == OutputFormat.MERMAID and not output_file:
        console.print("```mermaid")
        console.print(output)
        console.print("```")
    elif output_file:
        Path(output_file).write_text(output)
        console.print(f"[green]Graph written to: {output_file}[/green]")
    else:
        console.print(output)

    # Summary
    console.print()
    console.print(f"[dim]Nodes: {len(graph.nodes)}, Edges: {len(graph.edges)}[/dim]")

    # Validate if requested
    if validate:
        console.print()
        _run_validation(specs_path)


def _run_validation(specs_path: Path):
    """Run cross-block validation."""
    from src.rules.cross_block import CrossBlockValidator, CrossBlockSeverity

    validator = CrossBlockValidator(specs_path)
    result = validator.validate()

    if not result.issues:
        console.print("[green]No cross-block issues found[/green]")
        return

    console.print("[bold]Cross-Block Validation:[/bold]")

    for issue in result.issues:
        severity_style = {
            CrossBlockSeverity.ERROR: "red",
            CrossBlockSeverity.WARNING: "yellow",
            CrossBlockSeverity.INFO: "blue",
        }.get(issue.severity, "white")

        target = f" -> {issue.target_block}" if issue.target_block else ""
        console.print(
            f"  [{severity_style}]{issue.severity.value}[/{severity_style}] "
            f"{issue.source_block}{target}: {issue.message}"
        )

    console.print()
    console.print(f"Errors: {result.error_count}, Warnings: {result.warning_count}")


@click.command("validate-cross")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def validate_cross_command(specs_dir: str, output_json: bool):
    """Validate cross-block interfaces and dependencies.

    Checks:
    - Missing dependencies
    - Circular dependencies
    - Output/input type mismatches
    - API endpoint conflicts
    - Orphaned blocks

    Examples:

        spec-dev validate-cross

        spec-dev validate-cross --json
    """
    from src.rules.cross_block import CrossBlockValidator, CrossBlockSeverity, visualize_dependency_graph
    import json

    specs_path = Path(specs_dir)

    if not specs_path.exists():
        console.print(f"[red]Specs directory not found: {specs_dir}[/red]")
        return

    validator = CrossBlockValidator(specs_path)
    result = validator.validate()

    if output_json:
        console.print(json.dumps(result.to_dict(), indent=2))
        return

    console.print(f"[bold]Cross-Block Validation Report[/bold]")
    console.print(f"Blocks analyzed: {len(result.blocks_analyzed)}")
    console.print()

    if not result.issues:
        console.print("[green]No issues found - all interfaces are compatible[/green]")
    else:
        from rich.table import Table

        table = Table(title="Issues")
        table.add_column("Severity", style="bold")
        table.add_column("Type")
        table.add_column("Source")
        table.add_column("Target")
        table.add_column("Message")

        for issue in result.issues:
            severity_style = {
                CrossBlockSeverity.ERROR: "red",
                CrossBlockSeverity.WARNING: "yellow",
                CrossBlockSeverity.INFO: "blue",
            }.get(issue.severity, "white")

            table.add_row(
                f"[{severity_style}]{issue.severity.value}[/{severity_style}]",
                issue.issue_type.value,
                issue.source_block,
                issue.target_block or "-",
                issue.message[:50] + "..." if len(issue.message) > 50 else issue.message,
            )

        console.print(table)

    # Show dependency graph
    console.print()
    console.print("[bold]Dependency Graph (Mermaid):[/bold]")
    console.print("```mermaid")
    console.print(visualize_dependency_graph(result))
    console.print("```")
