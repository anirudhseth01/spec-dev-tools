"""Implement command for running the full implementation pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

from src.spec.parser import SpecParser, BlockParser
from src.agents.base import AgentContext, AgentStatus
from src.orchestration.flow_orchestrator import FlowOrchestrator, FlowStrategy, create_standard_flow

console = Console()


@click.command()
@click.argument("spec_path")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing files")
@click.option("--skip-tests", is_flag=True, help="Skip test generation")
@click.option("--skip-security", is_flag=True, help="Skip security scan")
@click.option("--skip-review", is_flag=True, help="Skip code review")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option(
    "--llm-model",
    default="claude-sonnet-4-20250514",
    help="LLM model to use for code generation",
)
def implement(
    spec_path: str,
    specs_dir: str,
    project_dir: str,
    dry_run: bool,
    skip_tests: bool,
    skip_security: bool,
    skip_review: bool,
    verbose: bool,
    llm_model: str,
) -> None:
    """Run the full implementation pipeline for a specification.

    SPEC_PATH is the path to the specification (e.g., 'payment-gateway' or 'auth/login').

    This command orchestrates:
    1. CodingAgent - Generates code from spec
    2. SecurityScanAgent - Scans for vulnerabilities
    3. TestGeneratorAgent - Creates tests
    4. CodeReviewAgent - Reviews code against spec

    Example usage:
        spec-dev implement payment-gateway
        spec-dev implement auth/login --dry-run
        spec-dev implement api/users --skip-tests --skip-review
    """
    specs_path = Path(specs_dir)
    project_path = Path(project_dir)

    # Determine if this is a block spec or regular spec
    block_path = specs_path / spec_path / "block.md"
    is_block = block_path.exists()

    # Parse specification
    console.print(f"\n[bold]Loading specification:[/bold] {spec_path}")

    try:
        if is_block:
            parser = BlockParser(specs_path)
            block = parser.parse_block(block_path)
            spec = block.spec
            console.print(f"  Type: Block specification ({block.block_type.value})")
        else:
            parser = SpecParser(specs_path)
            spec = parser.parse_by_name(spec_path)
            console.print(f"  Type: Feature specification")
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Specification not found: {spec_path}")
        console.print(f"  Looked in: {specs_path / spec_path}")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error parsing specification:[/red] {e}")
        raise SystemExit(1)

    console.print(f"  Name: {spec.name}")
    if spec.metadata and spec.metadata.status:
        console.print(f"  Status: {spec.metadata.status.value}")

    if dry_run:
        console.print("\n[yellow]DRY RUN MODE - No files will be written[/yellow]")

    # Initialize LLM client
    llm_client = _get_llm_client(llm_model, verbose)

    # Build agent pipeline
    agents = _build_agent_pipeline(
        llm_client=llm_client,
        skip_tests=skip_tests,
        skip_security=skip_security,
        skip_review=skip_review,
        dry_run=dry_run,
        verbose=verbose,
    )

    if not agents:
        console.print("[red]Error:[/red] No agents available to run")
        raise SystemExit(1)

    # Show pipeline
    console.print(f"\n[bold]Pipeline:[/bold] {' -> '.join(a.name for a in agents)}")

    # Create orchestrator
    orchestrator = create_standard_flow(spec, project_path, agents)

    # Add progress hooks
    results = {}

    def on_pre_agent(agent_name: str) -> None:
        if verbose:
            console.print(f"\n[dim]Starting {agent_name}...[/dim]")

    def on_post_agent(agent_name: str, result) -> None:
        results[agent_name] = result
        status_style = "green" if result.status == AgentStatus.SUCCESS else "red"
        console.print(f"  [{status_style}]{agent_name}:[/{status_style}] {result.message}")

    orchestrator.add_hook("pre_agent", on_pre_agent)
    orchestrator.add_hook("post_agent", on_post_agent)

    # Execute pipeline
    console.print("\n[bold]Executing pipeline...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running agents...", total=None)
        state = orchestrator.execute()
        progress.update(task, completed=True)

    # Display results
    _display_results(state, results, verbose)

    # Exit with appropriate code
    if state.failed_agents:
        raise SystemExit(1)


def _get_llm_client(model: str, verbose: bool):
    """Get LLM client instance."""
    try:
        from src.llm.client import ClaudeClient
        if verbose:
            console.print(f"[dim]Using LLM model: {model}[/dim]")
        return ClaudeClient(model=model)
    except ImportError:
        console.print("[yellow]Warning:[/yellow] LLM client not available, using mock")
        try:
            from src.llm.mock_client import MockLLMClient
            return MockLLMClient()
        except ImportError:
            return None
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not initialize LLM: {e}")
        console.print("  Continuing without LLM support (template-based generation)")
        return None


def _build_agent_pipeline(
    llm_client,
    skip_tests: bool,
    skip_security: bool,
    skip_review: bool,
    dry_run: bool,
    verbose: bool,
) -> list:
    """Build the agent pipeline based on options."""
    agents = []

    # CodingAgent (always included)
    try:
        from src.agents.coding import CodingAgent
        agents.append(CodingAgent(
            llm_client=llm_client,
            dry_run=dry_run,
        ))
    except ImportError as e:
        console.print(f"[red]Error:[/red] Could not import CodingAgent: {e}")
        raise SystemExit(1)

    # SecurityScanAgent
    if not skip_security:
        try:
            from src.agents.security import SecurityScanAgent, ScanMode
            agents.append(SecurityScanAgent(
                mode=ScanMode.LIGHTWEIGHT,
                llm_client=llm_client,
            ))
        except ImportError:
            if verbose:
                console.print("[yellow]Warning:[/yellow] SecurityScanAgent not available")

    # TestGeneratorAgent
    if not skip_tests:
        try:
            from src.agents.testing import TestGeneratorAgent
            agents.append(TestGeneratorAgent(
                llm_client=llm_client,
                dry_run=dry_run,
            ))
        except ImportError:
            if verbose:
                console.print("[yellow]Warning:[/yellow] TestGeneratorAgent not available")

    # CodeReviewAgent
    if not skip_review:
        try:
            from src.agents.review import CodeReviewAgent
            agents.append(CodeReviewAgent(
                llm_client=llm_client,
            ))
        except ImportError:
            if verbose:
                console.print("[yellow]Warning:[/yellow] CodeReviewAgent not available")

    return agents


def _display_results(state, results: dict, verbose: bool) -> None:
    """Display pipeline execution results."""
    console.print("\n" + "=" * 60)
    console.print("[bold]Pipeline Results[/bold]")
    console.print("=" * 60)

    # Summary table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Message")

    for agent_name in state.completed_agents + state.failed_agents:
        result = results.get(agent_name)
        if result:
            if result.status == AgentStatus.SUCCESS:
                status = "[green]SUCCESS[/green]"
            elif result.status == AgentStatus.FAILED:
                status = "[red]FAILED[/red]"
            elif result.status == AgentStatus.SKIPPED:
                status = "[yellow]SKIPPED[/yellow]"
            else:
                status = result.status.value

            # Truncate message for table
            message = result.message[:60] + "..." if len(result.message) > 60 else result.message
            table.add_row(agent_name, status, message)

    console.print(table)

    # Show files created
    all_files_created = []
    for result in results.values():
        if result.files_created:
            all_files_created.extend(result.files_created)
        if result.data and "files_created" in result.data:
            all_files_created.extend(result.data["files_created"])

    if all_files_created:
        console.print(f"\n[bold]Files created:[/bold] {len(all_files_created)}")
        for f in all_files_created[:10]:
            console.print(f"  - {f}")
        if len(all_files_created) > 10:
            console.print(f"  ... and {len(all_files_created) - 10} more")

    # Show artifacts
    if verbose and state.artifacts:
        console.print(f"\n[bold]Artifacts:[/bold]")
        for key, artifact in state.artifacts.items():
            from_agent = artifact.get("from_agent", "unknown")
            console.print(f"  - {key} (from {from_agent})")

    # Show detailed errors if any
    if state.failed_agents:
        console.print(f"\n[red]Failed agents: {', '.join(state.failed_agents)}[/red]")
        for agent_name in state.failed_agents:
            result = results.get(agent_name)
            if result and result.errors:
                console.print(f"\n[red]{agent_name} errors:[/red]")
                for error in result.errors[:5]:
                    console.print(f"  - {error}")

    # Show security report if available
    security_result = results.get("security_agent")
    if security_result and security_result.data:
        report_data = security_result.data.get("report", {})
        if report_data.get("has_blocking_issues"):
            console.print(Panel(
                f"[red]Security scan found blocking issues![/red]\n"
                f"Critical: {report_data.get('counts', {}).get('critical', 0)}, "
                f"High: {report_data.get('counts', {}).get('high', 0)}",
                title="Security Alert",
                border_style="red",
            ))

    # Show review summary if available
    review_result = results.get("code_review_agent")
    if review_result and review_result.data:
        review_data = review_result.data.get("review", {})
        if review_data.get("has_blockers"):
            console.print(Panel(
                f"[yellow]Code review found issues that need attention[/yellow]\n"
                f"Blockers: {review_data.get('counts', {}).get('blocker', 0)}, "
                f"Major: {review_data.get('counts', {}).get('major', 0)}",
                title="Review Summary",
                border_style="yellow",
            ))

    # Final status
    if state.failed_agents:
        console.print(f"\n[red]Pipeline completed with failures[/red]")
    else:
        console.print(f"\n[green]Pipeline completed successfully![/green]")
