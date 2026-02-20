"""Spec linting CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.command("lint")
@click.argument("spec_path", required=False)
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--all", "lint_all", is_flag=True, help="Lint all specs")
@click.option("--fix", is_flag=True, help="Auto-fix issues where possible")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def lint_command(spec_path: str | None, specs_dir: str, lint_all: bool, fix: bool, output_json: bool, strict: bool):
    """Lint specifications for style and consistency.

    Examples:

        spec-dev lint my-feature

        spec-dev lint --all

        spec-dev lint my-feature --strict
    """
    from src.spec.linting import SpecLinter, LintSeverity
    import json

    linter = SpecLinter()
    specs_path = Path(specs_dir)
    results = []

    if lint_all:
        # Find all specs
        for spec_file in specs_path.rglob("block.md"):
            result = linter.lint_file(spec_file)
            results.append(result)

        for spec_file in specs_path.glob("*.md"):
            if spec_file.name != "block.md":
                result = linter.lint_file(spec_file)
                results.append(result)
    elif spec_path:
        # Lint specific spec
        path = Path(spec_path)
        if not path.exists():
            path = specs_path / spec_path / "block.md"
        if not path.exists():
            path = specs_path / f"{spec_path}.md"

        if not path.exists():
            console.print(f"[red]Spec not found: {spec_path}[/red]")
            return

        result = linter.lint_file(path)
        results.append(result)
    else:
        console.print("[red]Specify a spec or use --all[/red]")
        return

    if output_json:
        import json as json_module
        output = [r.to_dict() for r in results]
        console.print(json_module.dumps(output, indent=2))
        return

    # Display results
    total_errors = sum(r.error_count for r in results)
    total_warnings = sum(r.warning_count for r in results)
    total_info = sum(r.info_count for r in results)

    for result in results:
        if not result.issues:
            continue

        console.print(f"\n[bold]{result.spec_path}[/bold]")

        table = Table(show_header=True)
        table.add_column("Severity", style="bold")
        table.add_column("Rule")
        table.add_column("Message")
        table.add_column("Line")

        for issue in result.issues:
            severity_style = {
                LintSeverity.ERROR: "red",
                LintSeverity.WARNING: "yellow",
                LintSeverity.INFO: "blue",
            }.get(issue.severity, "white")

            table.add_row(
                f"[{severity_style}]{issue.severity.value}[/{severity_style}]",
                issue.rule_id,
                issue.message,
                str(issue.line or "-"),
            )

        console.print(table)

    # Summary
    console.print()
    if total_errors > 0:
        console.print(f"[red]Errors: {total_errors}[/red]", end=" ")
    if total_warnings > 0:
        console.print(f"[yellow]Warnings: {total_warnings}[/yellow]", end=" ")
    if total_info > 0:
        console.print(f"[blue]Info: {total_info}[/blue]", end=" ")

    console.print()

    # Exit code
    if strict and total_warnings > 0:
        raise SystemExit(1)
    if total_errors > 0:
        raise SystemExit(1)


@click.command("lint-rules")
def lint_rules_command():
    """List available lint rules."""
    from src.spec.linting import SpecLinter

    linter = SpecLinter()
    rules = linter.list_rules()

    table = Table(title="Lint Rules")
    table.add_column("Rule ID", style="cyan")
    table.add_column("Name")
    table.add_column("Severity")
    table.add_column("Category")
    table.add_column("Enabled")

    for rule in rules:
        severity_style = {
            "error": "red",
            "warning": "yellow",
            "info": "blue",
        }.get(rule["severity"], "white")

        table.add_row(
            rule["rule_id"],
            rule["name"],
            f"[{severity_style}]{rule['severity']}[/{severity_style}]",
            rule["category"],
            "yes" if rule["enabled"] else "no",
        )

    console.print(table)
