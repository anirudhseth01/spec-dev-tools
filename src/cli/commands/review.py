"""Review command for code review against specifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@click.command()
@click.argument("path")
@click.option("--spec", "spec_path", help="Path to specification for compliance checking")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    help="Output format",
)
@click.option("--output", "-o", help="Write output to file")
@click.option("--strict", is_flag=True, help="Strict mode - stricter compliance checking")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--include-tests", is_flag=True, help="Also review test files")
def review(
    path: str,
    spec_path: Optional[str],
    specs_dir: str,
    project_dir: str,
    output_format: str,
    output: Optional[str],
    strict: bool,
    verbose: bool,
    include_tests: bool,
) -> None:
    """Review code against a specification.

    PATH is the file or directory to review.

    This command performs:
    - Spec compliance checking (if spec provided)
    - Code quality analysis
    - Security issue detection
    - Test coverage evaluation

    Examples:
        spec-dev review src/
        spec-dev review src/auth/ --spec auth/login
        spec-dev review . --format markdown -o review.md
        spec-dev review src/api.py --strict
    """
    review_path = Path(path)
    project_path = Path(project_dir)

    if not review_path.exists():
        console.print(f"[red]Error:[/red] Path not found: {path}")
        raise SystemExit(1)

    # Load spec if provided
    spec = None
    if spec_path:
        spec = _load_spec(spec_path, Path(specs_dir))
        if spec:
            console.print(f"[dim]Reviewing against spec: {spec.name}[/dim]")
        else:
            console.print(f"[yellow]Warning:[/yellow] Could not load spec: {spec_path}")

    # Import code review agent
    try:
        from src.agents.review import CodeReviewAgent, ReviewReport
    except ImportError as e:
        console.print(f"[red]Error:[/red] Could not import CodeReviewAgent: {e}")
        raise SystemExit(1)

    # Get LLM client
    llm_client = _get_llm_client(verbose)

    # Create agent
    agent = CodeReviewAgent(
        llm_client=llm_client,
        strict_mode=strict,
    )

    console.print(f"\n[bold]Code Review[/bold]")
    console.print(f"  Path: {review_path.absolute()}")
    if strict:
        console.print(f"  Mode: Strict")

    # Collect files to review
    code_files = _collect_files(review_path, include_tests=False)
    test_files = _collect_files(review_path, include_tests=True, tests_only=True) if include_tests else {}

    console.print(f"  Code files: {len(code_files)}")
    if include_tests:
        console.print(f"  Test files: {len(test_files)}")

    if not code_files:
        console.print("[yellow]No code files found to review[/yellow]")
        return

    # Perform review
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Reviewing code...", total=None)
        report = agent.review_files(code_files, spec)
        progress.update(task, completed=True)

    # Output results
    if output_format == "json":
        result = report.to_json()
    elif output_format == "markdown":
        result = report.to_markdown()
    else:
        result = None  # Will use rich display

    # Write to file if specified
    if output:
        output_path = Path(output)
        if output_format == "text":
            output_content = report.to_markdown()
        else:
            output_content = result
        output_path.write_text(output_content)
        console.print(f"\n[dim]Report written to: {output}[/dim]")

    # Display results
    if output_format == "text":
        _display_text_report(report, verbose)
    elif result:
        console.print(result)

    # Exit with error if blockers found
    if report.has_blockers:
        console.print(f"\n[red]Review found blocking issues![/red]")
        raise SystemExit(1)


def _load_spec(spec_path: str, specs_path: Path):
    """Load specification for compliance checking."""
    try:
        # Check if it's a block spec
        block_path = specs_path / spec_path / "block.md"
        if block_path.exists():
            from src.spec.parser import BlockParser
            parser = BlockParser(specs_path)
            block = parser.parse_block(block_path)
            return block.spec
        else:
            from src.spec.parser import SpecParser
            parser = SpecParser(specs_path)
            return parser.parse_by_name(spec_path)
    except Exception as e:
        return None


def _get_llm_client(verbose: bool):
    """Get LLM client for intelligent review."""
    try:
        from src.llm.client import ClaudeClient
        if verbose:
            console.print("[dim]Using LLM for intelligent review...[/dim]")
        return ClaudeClient()
    except Exception as e:
        if verbose:
            console.print(f"[yellow]Warning:[/yellow] LLM not available: {e}")
            console.print("  Using rule-based review only")
        return None


def _collect_files(
    path: Path,
    include_tests: bool = False,
    tests_only: bool = False,
) -> dict[str, str]:
    """Collect files to review."""
    files = {}

    # Extensions to include
    code_extensions = [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".java", ".rb"]

    # Directories to skip
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", "dist", "build"}

    # Test patterns
    test_patterns = ["test_", "_test", ".test.", ".spec."]

    if path.is_file():
        try:
            files[str(path)] = path.read_text()
        except Exception:
            pass
    else:
        for ext in code_extensions:
            for file_path in path.rglob(f"*{ext}"):
                # Skip excluded directories
                if any(d in file_path.parts for d in skip_dirs):
                    continue

                # Check if it's a test file
                is_test = any(p in file_path.name for p in test_patterns) or "tests" in file_path.parts

                # Filter based on options
                if tests_only and not is_test:
                    continue
                if not include_tests and not tests_only and is_test:
                    continue

                try:
                    rel_path = str(file_path)
                    files[rel_path] = file_path.read_text()
                except Exception:
                    pass

    return files


def _get_severity_style(severity: str) -> str:
    """Get rich style for severity level."""
    styles = {
        "blocker": "bold red",
        "major": "red",
        "minor": "yellow",
        "suggestion": "blue",
        "praise": "green",
    }
    return styles.get(severity, "white")


def _display_text_report(report, verbose: bool) -> None:
    """Display report as rich text."""
    console.print("\n" + "=" * 60)
    console.print("[bold]Code Review Results[/bold]")
    console.print("=" * 60)

    # Summary
    if report.overall_rating == "approved":
        status = "[green]APPROVED[/green]"
    elif report.overall_rating == "changes_requested":
        status = "[yellow]CHANGES REQUESTED[/yellow]"
    else:
        status = "[red]NEEDS WORK[/red]"

    console.print(f"\nStatus: {status}")
    console.print(f"Files reviewed: {report.files_reviewed}")
    console.print(f"Spec compliance: {report.spec_compliance_score:.0%}")

    # Counts
    console.print(f"\nComments:")
    console.print(f"  [bold red]Blockers:[/bold red] {report.blocker_count}")
    console.print(f"  [red]Major:[/red] {report.major_count}")
    console.print(f"  [yellow]Minor:[/yellow] {report.minor_count}")

    # Show blockers
    blockers = [c for c in report.comments if c.severity.value == "blocker"]
    if blockers:
        console.print("\n[bold red]Blocking Issues:[/bold red]")
        for comment in blockers:
            _display_comment(comment)

    # Show major issues
    major = [c for c in report.comments if c.severity.value == "major"]
    if major:
        console.print("\n[bold]Major Issues:[/bold]")
        for comment in major:
            _display_comment(comment)

    # Show other issues if verbose
    if verbose:
        other = [c for c in report.comments if c.severity.value in ("minor", "suggestion")]
        if other:
            console.print("\n[bold]Minor Issues & Suggestions:[/bold]")
            table = Table(show_header=True)
            table.add_column("Severity")
            table.add_column("Location")
            table.add_column("Category")
            table.add_column("Issue")

            for comment in other:
                severity_style = _get_severity_style(comment.severity.value)
                location = comment.file_path
                if comment.line_number:
                    location += f":{comment.line_number}"

                table.add_row(
                    f"[{severity_style}]{comment.severity.value}[/{severity_style}]",
                    location[:40],
                    comment.category.value,
                    comment.title[:40],
                )

            console.print(table)

        # Show praise
        praise = [c for c in report.comments if c.severity.value == "praise"]
        if praise:
            console.print("\n[bold green]Positive Feedback:[/bold green]")
            for comment in praise:
                console.print(f"  [green]+[/green] {comment.file_path}: {comment.title}")


def _display_comment(comment) -> None:
    """Display a single review comment."""
    location = comment.file_path
    if comment.line_number:
        location += f":{comment.line_number}"

    severity_style = _get_severity_style(comment.severity.value)

    content = f"[bold]{comment.title}[/bold]\n\n"
    content += f"Location: {location}\n"
    content += f"Category: {comment.category.value}\n\n"
    content += comment.description

    if comment.code_snippet:
        content += f"\n\n```\n{comment.code_snippet}\n```"

    if comment.suggestion:
        content += f"\n\n[dim]Suggestion: {comment.suggestion}[/dim]"

    console.print(Panel(
        content,
        title=f"[{severity_style}]{comment.severity.value.upper()}[/{severity_style}] {comment.id}",
        border_style=severity_style,
    ))
