"""Coverage tracking CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("coverage")
def coverage_group():
    """Spec coverage tracking commands."""
    pass


@coverage_group.command("analyze")
@click.argument("spec_name", required=False)
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all specs")
@click.option("--save", is_flag=True, help="Save coverage data")
def analyze_coverage(spec_name: str | None, specs_dir: str, analyze_all: bool, save: bool):
    """Analyze implementation coverage for a spec.

    Examples:

        spec-dev coverage analyze my-feature

        spec-dev coverage analyze --all --save
    """
    from src.coverage import CoverageTracker, ImplementationStatus

    project_dir = Path.cwd()
    specs_path = Path(specs_dir)

    tracker = CoverageTracker(project_dir, specs_path)

    if analyze_all:
        all_coverage = tracker.get_all_coverage()

        if not all_coverage:
            console.print("[yellow]No specs found[/yellow]")
            return

        table = Table(title="Spec Coverage")
        table.add_column("Spec", style="cyan")
        table.add_column("Status")
        table.add_column("Coverage")
        table.add_column("Code Files")
        table.add_column("Test Files")

        for name, cov in sorted(all_coverage.items()):
            status_style = {
                ImplementationStatus.NOT_STARTED: "red",
                ImplementationStatus.PARTIAL: "yellow",
                ImplementationStatus.COMPLETE: "green",
                ImplementationStatus.VERIFIED: "bold green",
            }.get(cov.status, "white")

            table.add_row(
                name,
                f"[{status_style}]{cov.status.value}[/{status_style}]",
                f"{cov.overall_percentage:.1f}%",
                str(len(cov.code_files)),
                str(len(cov.test_files)),
            )

            if save:
                tracker.save_coverage(cov)

        console.print(table)

    elif spec_name:
        try:
            coverage = tracker.analyze_spec(spec_name)
        except FileNotFoundError:
            console.print(f"[red]Spec not found: {spec_name}[/red]")
            return

        console.print(f"[bold]Coverage: {spec_name}[/bold]")
        console.print(f"Status: {coverage.status.value}")
        console.print(f"Overall: {coverage.overall_percentage:.1f}%")
        console.print()

        # Section details
        table = Table(title="Section Coverage")
        table.add_column("Section")
        table.add_column("Status")
        table.add_column("Items")
        table.add_column("Coverage")

        for name, section in coverage.sections.items():
            status_style = {
                ImplementationStatus.NOT_STARTED: "red",
                ImplementationStatus.PARTIAL: "yellow",
                ImplementationStatus.COMPLETE: "green",
                ImplementationStatus.VERIFIED: "bold green",
            }.get(section.status, "white")

            table.add_row(
                name,
                f"[{status_style}]{section.status.value}[/{status_style}]",
                f"{len(section.implemented_items)}/{section.total_items}",
                f"{section.percentage:.1f}%",
            )

        console.print(table)

        # Files
        if coverage.code_files:
            console.print()
            console.print("[bold]Code Files:[/bold]")
            for f in coverage.code_files:
                console.print(f"  - {f}")

        if coverage.test_files:
            console.print()
            console.print("[bold]Test Files:[/bold]")
            for f in coverage.test_files:
                console.print(f"  - {f}")

        if save:
            tracker.save_coverage(coverage)
            console.print()
            console.print("[green]Coverage data saved[/green]")

    else:
        console.print("[red]Specify a spec name or use --all[/red]")


@coverage_group.command("report")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--output", "-o", "output_file", help="Output file")
def coverage_report(specs_dir: str, output_file: str | None):
    """Generate coverage report.

    Examples:

        spec-dev coverage report

        spec-dev coverage report -o coverage-report.md
    """
    from src.coverage import CoverageTracker

    project_dir = Path.cwd()
    specs_path = Path(specs_dir)

    tracker = CoverageTracker(project_dir, specs_path)
    report = tracker.generate_report()

    if output_file:
        Path(output_file).write_text(report)
        console.print(f"[green]Report written to: {output_file}[/green]")
    else:
        console.print(report)


@coverage_group.command("status")
@click.option("--specs-dir", default="specs", help="Specs directory")
def coverage_status(specs_dir: str):
    """Show quick coverage status summary.

    Examples:

        spec-dev coverage status
    """
    from src.coverage import CoverageTracker, ImplementationStatus

    project_dir = Path.cwd()
    specs_path = Path(specs_dir)

    tracker = CoverageTracker(project_dir, specs_path)
    all_coverage = tracker.get_all_coverage()

    if not all_coverage:
        console.print("[yellow]No specs found[/yellow]")
        return

    # Count by status
    status_counts = {
        ImplementationStatus.NOT_STARTED: 0,
        ImplementationStatus.PARTIAL: 0,
        ImplementationStatus.COMPLETE: 0,
        ImplementationStatus.VERIFIED: 0,
    }

    for cov in all_coverage.values():
        status_counts[cov.status] += 1

    total = len(all_coverage)
    avg_coverage = sum(c.overall_percentage for c in all_coverage.values()) / total

    console.print("[bold]Coverage Status[/bold]")
    console.print(f"Total specs: {total}")
    console.print(f"Average coverage: {avg_coverage:.1f}%")
    console.print()

    console.print(f"[red]Not Started: {status_counts[ImplementationStatus.NOT_STARTED]}[/red]")
    console.print(f"[yellow]Partial: {status_counts[ImplementationStatus.PARTIAL]}[/yellow]")
    console.print(f"[green]Complete: {status_counts[ImplementationStatus.COMPLETE]}[/green]")
    console.print(f"[bold green]Verified: {status_counts[ImplementationStatus.VERIFIED]}[/bold green]")
