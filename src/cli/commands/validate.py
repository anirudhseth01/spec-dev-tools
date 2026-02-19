"""Validate command for checking specifications."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from src.spec.parser import SpecParser, BlockParser
from src.rules.engine import RulesEngine

console = Console()


@click.command()
@click.argument("name")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--rules/--no-rules", default=False, help="Also run rule validation")
@click.option("--project-dir", default=".", help="Project root directory")
def validate(name: str, specs_dir: str, rules: bool, project_dir: str) -> None:
    """Validate a specification for completeness.

    NAME is the name of the specification to validate.
    """
    specs_path = Path(specs_dir)
    project_path = Path(project_dir)

    # Check if it's a block spec
    block_path = specs_path / name / "block.md"
    if block_path.exists():
        _validate_block(block_path, project_path, rules)
    else:
        _validate_spec(name, specs_path, project_path, rules)


def _validate_spec(name: str, specs_path: Path, project_path: Path, run_rules: bool) -> None:
    """Validate a feature specification."""
    parser = SpecParser(specs_path)

    try:
        spec = parser.parse_by_name(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Specification '{name}' not found")
        raise SystemExit(1)

    # Check basic validity
    issues = []

    if not spec.name:
        issues.append("Missing specification name")

    if not spec.metadata.spec_id:
        issues.append("Missing spec_id in metadata")

    if not spec.overview.summary:
        issues.append("Missing summary in overview")

    if not spec.overview.goals:
        issues.append("No goals defined")

    if not spec.test_cases.unit_tests:
        issues.append("No unit tests defined")

    # Display results
    if issues:
        console.print(f"[yellow]Validation issues for '{name}':[/yellow]")
        for issue in issues:
            console.print(f"  - {issue}")
    else:
        console.print(f"[green]Specification '{name}' is valid[/green]")


def _validate_block(block_path: Path, project_path: Path, run_rules: bool) -> None:
    """Validate a block specification."""
    parser = BlockParser(block_path.parent.parent)

    try:
        block = parser.parse_block(block_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to parse block: {e}")
        raise SystemExit(1)

    issues = []

    # Basic validation
    if not block.name:
        issues.append("Missing block name")

    if not block.spec.metadata.spec_id:
        issues.append("Missing spec_id in metadata")

    # Rule validation
    if run_rules:
        engine = RulesEngine(project_path)
        violations = engine.validate(block)

        if violations:
            console.print(f"\n[yellow]Rule violations for '{block.path}':[/yellow]")
            table = Table(show_header=True)
            table.add_column("Severity")
            table.add_column("Rule")
            table.add_column("Section")
            table.add_column("Message")

            for v in violations:
                severity_style = {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                }.get(v.rule.severity.value, "white")

                table.add_row(
                    f"[{severity_style}]{v.rule.severity.value.upper()}[/{severity_style}]",
                    v.rule.id,
                    v.section,
                    v.message,
                )

            console.print(table)

            # Check for errors
            errors = [v for v in violations if v.rule.severity.value == "error"]
            if errors:
                console.print(f"\n[red]Found {len(errors)} error(s). Block is not valid.[/red]")
                raise SystemExit(1)

    # Display results
    if issues:
        console.print(f"[yellow]Validation issues for '{block.path}':[/yellow]")
        for issue in issues:
            console.print(f"  - {issue}")
        raise SystemExit(1)
    else:
        console.print(f"[green]Block '{block.path}' is valid[/green]")
