"""Security command for running security scans."""

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


@click.group()
def security() -> None:
    """Security scanning and vulnerability detection commands."""
    pass


@security.command("scan")
@click.argument("path", required=False, default=".")
@click.option(
    "--mode",
    type=click.Choice(["lightweight", "heavyweight"]),
    default="lightweight",
    help="Scan mode: lightweight (fast, pattern-based) or heavyweight (thorough, LLM-powered)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif", "markdown"]),
    default="text",
    help="Output format",
)
@click.option("--spec", "spec_path", help="Path to specification for compliance checking")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--output", "-o", help="Write output to file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--fail-on-high", is_flag=True, help="Exit with error on high severity findings")
def scan(
    path: str,
    mode: str,
    output_format: str,
    spec_path: Optional[str],
    specs_dir: str,
    output: Optional[str],
    verbose: bool,
    fail_on_high: bool,
) -> None:
    """Run a security scan on code files.

    PATH is the directory or file to scan (default: current directory).

    Examples:
        spec-dev security scan
        spec-dev security scan src/ --mode heavyweight
        spec-dev security scan . --format json -o report.json
        spec-dev security scan . --spec auth/login --mode heavyweight
    """
    scan_path = Path(path)

    if not scan_path.exists():
        console.print(f"[red]Error:[/red] Path not found: {path}")
        raise SystemExit(1)

    # Load spec if provided
    spec = None
    if spec_path:
        spec = _load_spec(spec_path, specs_dir)
        if spec:
            console.print(f"[dim]Using spec: {spec.name}[/dim]")

    # Import security agent
    try:
        from src.agents.security import SecurityScanAgent, ScanMode
        from src.agents.security.findings import SecurityReport
    except ImportError as e:
        console.print(f"[red]Error:[/red] Could not import SecurityScanAgent: {e}")
        raise SystemExit(1)

    # Get LLM client for heavyweight mode
    llm_client = None
    if mode == "heavyweight":
        llm_client = _get_llm_client(verbose)

    # Create agent
    scan_mode = ScanMode.LIGHTWEIGHT if mode == "lightweight" else ScanMode.HEAVYWEIGHT
    agent = SecurityScanAgent(
        mode=scan_mode,
        llm_client=llm_client,
    )

    console.print(f"\n[bold]Security Scan[/bold]")
    console.print(f"  Path: {scan_path.absolute()}")
    console.print(f"  Mode: {mode}")

    # Collect files
    if scan_path.is_file():
        files = {str(scan_path): scan_path.read_text()}
    else:
        files = agent._scan_directory(scan_path)

    console.print(f"  Files to scan: {len(files)}")

    if not files:
        console.print("[yellow]No files found to scan[/yellow]")
        return

    # Run scan
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Scanning {len(files)} files...", total=None)
        report = agent.scan_files(files, spec)
        progress.update(task, completed=True)

    # Output results
    if output_format == "json":
        result = json.dumps(report.to_dict(), indent=2)
    elif output_format == "sarif":
        result = _to_sarif(report)
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

    # Exit with error if blocking issues found
    if report.has_blocking_issues:
        console.print(f"\n[red]Security scan found blocking issues![/red]")
        raise SystemExit(1)

    if fail_on_high and report.high_count > 0:
        console.print(f"\n[red]Security scan found high severity issues (--fail-on-high)[/red]")
        raise SystemExit(1)


@security.command("check")
@click.argument("file_path")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def check(file_path: str, verbose: bool) -> None:
    """Quick security check on a single file.

    FILE_PATH is the path to the file to check.

    Example:
        spec-dev security check src/auth/handler.py
    """
    path = Path(file_path)

    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise SystemExit(1)

    if not path.is_file():
        console.print(f"[red]Error:[/red] Not a file: {file_path}")
        raise SystemExit(1)

    try:
        from src.agents.security import SecurityScanAgent, ScanMode
    except ImportError as e:
        console.print(f"[red]Error:[/red] Could not import SecurityScanAgent: {e}")
        raise SystemExit(1)

    # Read file
    content = path.read_text()
    files = {str(path): content}

    # Quick scan
    agent = SecurityScanAgent(mode=ScanMode.LIGHTWEIGHT)
    report = agent.scan_files(files)

    if report.findings:
        console.print(f"\n[yellow]Found {len(report.findings)} issue(s) in {file_path}[/yellow]\n")
        for finding in report.findings:
            severity_style = _get_severity_style(finding.severity.value)
            console.print(f"[{severity_style}]{finding.severity.value.upper()}[/{severity_style}]: {finding.title}")
            if finding.line_number:
                console.print(f"  Line {finding.line_number}: {finding.description}")
            else:
                console.print(f"  {finding.description}")
            if finding.recommendation:
                console.print(f"  [dim]Fix: {finding.recommendation}[/dim]")
            console.print()
    else:
        console.print(f"[green]No security issues found in {file_path}[/green]")


def _load_spec(spec_path: str, specs_dir: str):
    """Load specification for compliance checking."""
    specs_path = Path(specs_dir)

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
        console.print(f"[yellow]Warning:[/yellow] Could not load spec: {e}")
        return None


def _get_llm_client(verbose: bool):
    """Get LLM client for heavyweight mode."""
    try:
        from src.llm.client import ClaudeClient
        if verbose:
            console.print("[dim]Using LLM for deep analysis...[/dim]")
        return ClaudeClient()
    except Exception as e:
        if verbose:
            console.print(f"[yellow]Warning:[/yellow] LLM not available: {e}")
        return None


def _get_severity_style(severity: str) -> str:
    """Get rich style for severity level."""
    styles = {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "blue",
        "info": "dim",
    }
    return styles.get(severity, "white")


def _display_text_report(report, verbose: bool) -> None:
    """Display report as rich text."""
    console.print("\n" + "=" * 60)
    console.print("[bold]Security Scan Results[/bold]")
    console.print("=" * 60)

    # Summary
    status = "[green]PASSED[/green]" if not report.has_blocking_issues else "[red]FAILED[/red]"
    console.print(f"\nStatus: {status}")
    console.print(f"Files scanned: {report.files_scanned}")
    console.print(f"Scan duration: {report.scan_duration_ms}ms")

    # Counts
    console.print(f"\nFindings:")
    console.print(f"  [bold red]Critical:[/bold red] {report.critical_count}")
    console.print(f"  [red]High:[/red] {report.high_count}")
    console.print(f"  [yellow]Medium:[/yellow] {report.medium_count}")
    console.print(f"  [blue]Low:[/blue] {report.low_count}")

    # Show blocking findings
    if report.blocking_findings:
        console.print("\n[bold red]Blocking Issues:[/bold red]")
        for finding in report.blocking_findings:
            console.print(Panel(
                f"[bold]{finding.title}[/bold]\n\n"
                f"Location: {finding.location}\n"
                f"Category: {finding.category.value}\n\n"
                f"{finding.description}\n\n"
                f"[dim]Recommendation: {finding.recommendation}[/dim]",
                title=f"[{_get_severity_style(finding.severity.value)}]{finding.severity.value.upper()}[/{_get_severity_style(finding.severity.value)}] {finding.id}",
                border_style=_get_severity_style(finding.severity.value),
            ))

    # Show other findings if verbose
    if verbose:
        other_findings = [f for f in report.findings if not f.severity.blocks_pr]
        if other_findings:
            console.print("\n[bold]Other Findings:[/bold]")
            table = Table(show_header=True)
            table.add_column("Severity")
            table.add_column("Location")
            table.add_column("Issue")
            table.add_column("Category")

            for finding in other_findings:
                severity_style = _get_severity_style(finding.severity.value)
                table.add_row(
                    f"[{severity_style}]{finding.severity.value}[/{severity_style}]",
                    finding.location,
                    finding.title,
                    finding.category.value,
                )

            console.print(table)

    # Compliance results
    if report.compliance_results:
        console.print(f"\n[bold]Spec Compliance:[/bold] {report.compliance_score:.0%}")
        if verbose:
            for result in report.compliance_results:
                status_icon = {
                    "pass": "[green]PASS[/green]",
                    "fail": "[red]FAIL[/red]",
                    "partial": "[yellow]PARTIAL[/yellow]",
                    "not_found": "[dim]N/A[/dim]",
                }.get(result.status, "[dim]?[/dim]")
                console.print(f"  {status_icon} {result.requirement}")


def _to_sarif(report) -> str:
    """Convert report to SARIF format."""
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "spec-dev-tools",
                    "version": "0.1.0",
                    "informationUri": "https://github.com/spec-dev-tools",
                    "rules": [],
                }
            },
            "results": [],
        }]
    }

    rules = {}
    results = []

    for finding in report.findings:
        # Add rule if not already added
        if finding.id not in rules:
            rules[finding.id] = {
                "id": finding.id,
                "name": finding.title,
                "shortDescription": {"text": finding.title},
                "fullDescription": {"text": finding.description},
                "defaultConfiguration": {
                    "level": _severity_to_sarif_level(finding.severity.value)
                },
                "properties": {
                    "category": finding.category.value,
                }
            }

        # Add result
        result = {
            "ruleId": finding.id,
            "level": _severity_to_sarif_level(finding.severity.value),
            "message": {"text": finding.description},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": finding.file_path,
                    },
                }
            }],
        }

        if finding.line_number:
            result["locations"][0]["physicalLocation"]["region"] = {
                "startLine": finding.line_number,
            }

        results.append(result)

    sarif["runs"][0]["tool"]["driver"]["rules"] = list(rules.values())
    sarif["runs"][0]["results"] = results

    return json.dumps(sarif, indent=2)


def _severity_to_sarif_level(severity: str) -> str:
    """Convert severity to SARIF level."""
    mapping = {
        "critical": "error",
        "high": "error",
        "medium": "warning",
        "low": "note",
        "info": "note",
    }
    return mapping.get(severity, "warning")
