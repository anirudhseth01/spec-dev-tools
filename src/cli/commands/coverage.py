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
@click.option("--code-dir", help="Implementation code directory")
@click.option("--test-dir", help="Test files directory")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all specs")
@click.option("--save", is_flag=True, help="Save coverage data")
def analyze_coverage(spec_name: str | None, specs_dir: str, code_dir: str | None, test_dir: str | None, analyze_all: bool, save: bool):
    """Analyze implementation coverage for a spec.

    Examples:

        spec-dev coverage analyze my-feature

        spec-dev coverage analyze my-feature --code-dir src/my_feature

        spec-dev coverage analyze --all --save
    """
    from src.coverage import CoverageTracker, ImplementationStatus

    project_dir = Path.cwd()
    specs_path = Path(specs_dir)
    code_path = Path(code_dir) if code_dir else None
    test_path = Path(test_dir) if test_dir else None

    tracker = CoverageTracker(project_dir, specs_path, code_path, test_path)

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

        # Code definition coverage (primary metric)
        if coverage.spec_definitions:
            console.print(f"[bold]Code Definitions from Spec:[/bold]")
            console.print(f"  Total definitions: {len(coverage.spec_definitions)}")
            console.print(f"  [green]Implemented: {len(coverage.implemented_definitions)}[/green]")
            console.print(f"  [red]Missing: {len(coverage.missing_definitions)}[/red]")
            console.print(f"  Coverage: {coverage.definition_coverage:.1f}%")
            console.print()

            # Show definition details table
            def_table = Table(title="Spec Definitions")
            def_table.add_column("Name", style="cyan")
            def_table.add_column("Type")
            def_table.add_column("Status")
            def_table.add_column("Section")

            for defn in coverage.spec_definitions:
                key = f"{defn.parent}.{defn.name}" if defn.parent else defn.name
                if key in coverage.implemented_definitions:
                    status = "[green]Implemented[/green]"
                else:
                    status = "[red]Missing[/red]"

                def_table.add_row(
                    key,
                    defn.definition_type.value,
                    status,
                    defn.source_section[:30] if defn.source_section else "",
                )

            console.print(def_table)

            # Show missing definitions
            if coverage.missing_definitions:
                console.print()
                console.print("[bold red]Missing Definitions:[/bold red]")
                for missing in coverage.missing_definitions[:20]:  # Limit output
                    console.print(f"  - {missing}")
                if len(coverage.missing_definitions) > 20:
                    console.print(f"  ... and {len(coverage.missing_definitions) - 20} more")

        # Section details (legacy, for backwards compatibility)
        table = Table(title="Section Coverage (Legacy)")
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

        console.print()
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


@coverage_group.command("test")
@click.option("--source", "-s", help="Source directory to measure coverage for")
@click.option("--tests", "-t", default="tests", help="Test directory")
@click.option("--min-line", default=80, help="Minimum line coverage percentage")
@click.option("--min-branch", default=70, help="Minimum branch coverage percentage")
@click.option("--html", is_flag=True, help="Generate HTML coverage report")
@click.option("--xml", is_flag=True, help="Generate XML coverage report (for CI)")
@click.option("--fail-under", type=int, help="Fail if coverage is below this percentage")
def test_coverage(
    source: str | None,
    tests: str,
    min_line: int,
    min_branch: int,
    html: bool,
    xml: bool,
    fail_under: int | None,
):
    """Run tests and measure line/branch coverage.

    Runs pytest with coverage and reports:
    - Line coverage percentage
    - Branch coverage percentage
    - Uncovered lines per file

    Examples:

        spec-dev coverage test

        spec-dev coverage test --source src/mypackage

        spec-dev coverage test --min-line 90 --min-branch 80

        spec-dev coverage test --html --fail-under 80
    """
    import json
    import shutil
    import subprocess
    import sys
    import tempfile

    project_dir = Path.cwd()

    # Find pytest executable
    pytest_path = shutil.which("pytest")
    if not pytest_path:
        # Try using python -m pytest
        pytest_cmd = [sys.executable, "-m", "pytest"]
    else:
        pytest_cmd = ["pytest"]

    # Build pytest command
    cmd = pytest_cmd + [tests, "-v"]

    # Add coverage options
    if source:
        cmd.extend([f"--cov={source}"])
    else:
        # Try to find source directory
        for candidate in ["src", "lib", project_dir.name]:
            if (project_dir / candidate).is_dir():
                cmd.extend([f"--cov={candidate}"])
                source = candidate
                break

    # Always include branch coverage
    cmd.append("--cov-branch")

    # Generate JSON report for parsing
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json_report = f.name

    cmd.extend([f"--cov-report=json:{json_report}"])

    # Optional HTML report
    if html:
        cmd.append("--cov-report=html")

    # Optional XML report
    if xml:
        cmd.append("--cov-report=xml")

    # Terminal report
    cmd.append("--cov-report=term-missing")

    # Fail under threshold
    if fail_under:
        cmd.extend([f"--cov-fail-under={fail_under}"])

    console.print(f"[bold]Running tests with coverage...[/bold]")
    console.print(f"Command: {' '.join(cmd)}")
    console.print()

    # Run pytest
    result = subprocess.run(cmd, capture_output=False)

    # Parse JSON report
    try:
        with open(json_report) as f:
            cov_data = json.load(f)

        totals = cov_data.get("totals", {})
        line_coverage = totals.get("percent_covered", 0)
        branch_coverage = totals.get("percent_covered_branches", 0) if "percent_covered_branches" in totals else None

        console.print()
        console.print("=" * 60)
        console.print("[bold]Coverage Summary[/bold]")
        console.print("=" * 60)

        # Line coverage
        line_style = "green" if line_coverage >= min_line else "red"
        console.print(f"Line Coverage:   [{line_style}]{line_coverage:.1f}%[/{line_style}] (target: {min_line}%)")

        # Branch coverage
        if branch_coverage is not None:
            branch_style = "green" if branch_coverage >= min_branch else "red"
            console.print(f"Branch Coverage: [{branch_style}]{branch_coverage:.1f}%[/{branch_style}] (target: {min_branch}%)")

        # File details
        files = cov_data.get("files", {})
        if files:
            console.print()
            console.print("[bold]Per-File Coverage:[/bold]")

            file_table = Table()
            file_table.add_column("File", style="cyan")
            file_table.add_column("Lines", justify="right")
            file_table.add_column("Miss", justify="right")
            file_table.add_column("Branch", justify="right")
            file_table.add_column("Cover", justify="right")
            file_table.add_column("Missing Lines")

            for filepath, data in sorted(files.items()):
                summary = data.get("summary", {})
                num_statements = summary.get("num_statements", 0)
                missing_lines = summary.get("missing_lines", 0)
                num_branches = summary.get("num_branches", 0)
                pct = summary.get("percent_covered", 0)

                # Get missing line numbers
                missing = data.get("missing_lines", [])
                missing_str = ", ".join(str(l) for l in missing[:5])
                if len(missing) > 5:
                    missing_str += f", +{len(missing) - 5} more"

                pct_style = "green" if pct >= min_line else ("yellow" if pct >= min_line * 0.8 else "red")

                file_table.add_row(
                    filepath,
                    str(num_statements),
                    str(missing_lines),
                    str(num_branches),
                    f"[{pct_style}]{pct:.0f}%[/{pct_style}]",
                    missing_str or "-",
                )

            console.print(file_table)

        # Summary
        console.print()
        if line_coverage >= min_line and (branch_coverage is None or branch_coverage >= min_branch):
            console.print("[bold green]Coverage targets met![/bold green]")
        else:
            console.print("[bold red]Coverage targets NOT met[/bold red]")
            if line_coverage < min_line:
                console.print(f"  Line coverage {line_coverage:.1f}% < {min_line}%")
            if branch_coverage is not None and branch_coverage < min_branch:
                console.print(f"  Branch coverage {branch_coverage:.1f}% < {min_branch}%")

        if html:
            console.print()
            console.print("[dim]HTML report: htmlcov/index.html[/dim]")

    except (FileNotFoundError, json.JSONDecodeError) as e:
        console.print(f"[yellow]Could not parse coverage report: {e}[/yellow]")

    finally:
        # Cleanup temp file
        try:
            Path(json_report).unlink()
        except Exception:
            pass

    # Exit with pytest's return code
    raise SystemExit(result.returncode)
